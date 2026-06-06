"""Sync Pipeline — continuous sync that reuses ImportMemoryPipeline.

Flow:
  Source → Connector → ChangeDetection → chunk_text() → ImportMemoryPipeline.process()
                                                               ↓
                                                 MemoryWriteWorker → Lifecycle → Consolidation

Key reuse points (ZERO modifications to existing modules):
  - ImportMemoryPipeline.process() — the full 5-layer memory pipeline
  - MemoryWriteWorker.enqueue() — already inside ImportMemoryPipeline
  - MemoryLifecycleManager.archive_old_memories() — already inside ImportMemoryPipeline
  - DefaultMemoryConsolidator.consolidate() — already inside ImportMemoryPipeline
  - chunk_text() / extract_entities() — from src/importers/base.py

The only new code is Phases 1-3 (connector + change detection + parsing),
which feed into the existing pipeline as its input (chunks).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from src.core.import_pipeline import ImportMemoryPipeline
from src.importers.base import chunk_text, extract_entities
from src.sync.change_detector import ChangeDetector
from src.sync.connector_base import BaseSyncConnector
from src.sync.models import (
    ChangeRecord,
    SyncConnectorConfig,
    SyncExecution,
    SyncPipelineResult,
)

logger = logging.getLogger(__name__)


class SyncPipeline:
    """Executes the full sync pipeline for one job execution.

    Design: Thin orchestration layer. Phases 4-7 are entirely delegated
    to ImportMemoryPipeline.process(), which handles embedding, concept
    extraction, memory construction, async writing, lifecycle, and consolidation.
    """

    def __init__(
        self,
        import_pipeline: ImportMemoryPipeline,
    ) -> None:
        self._import_pipeline = import_pipeline
        self._change_detector = ChangeDetector()

    # ── Public API ──

    def run(
        self,
        connector: BaseSyncConnector,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ) -> SyncPipelineResult:
        """Execute the full sync pipeline.

        Args:
            connector: The concrete sync connector for the source.
            config: Persisted connector config with tracking state.
            execution: The SyncExecution to populate with results.

        Returns:
            SyncPipelineResult with detailed stats.
        """
        t0 = time.monotonic()

        execution.status = "running"
        execution.started_at = datetime.now(timezone.utc)

        partial_failures: list[str] = []
        memories_created = 0
        errors_count = 0
        change_details: list[dict] = []

        try:
            # ── Phase 1: Connect ──
            connection = connector.test_connection()
            if not connection.success:
                execution.status = "failed"
                execution.error = f"Connection failed: {connection.message}"
                execution.completed_at = datetime.now(timezone.utc)
                execution.elapsed_ms = int((time.monotonic() - t0) * 1000)
                return SyncPipelineResult(
                    execution_id=execution.id,
                    status="failed",
                    error=execution.error,
                    processing_time_ms=execution.elapsed_ms,
                )

            # ── Phase 2: Change Detection ──
            since = config.last_sync_time
            changes = self._change_detector.detect(connector, config, since)

            new_changes = [c for c in changes if c.change_type == "new"]
            updated_changes = [c for c in changes if c.change_type == "updated"]
            deleted_changes = [c for c in changes if c.change_type == "deleted"]
            renamed_changes = [c for c in changes if c.change_type == "renamed"]

            if not changes:
                # No changes — still update last_sync_time
                execution.status = "completed"
                execution.completed_at = datetime.now(timezone.utc)
                execution.items_fetched = connection.resources_count
                execution.elapsed_ms = int((time.monotonic() - t0) * 1000)
                config.last_sync_time = datetime.now(timezone.utc)
                return SyncPipelineResult(
                    execution_id=execution.id,
                    status="completed",
                    items_fetched=connection.resources_count,
                    processing_time_ms=execution.elapsed_ms,
                )

            # ── Phase 3: Parse content → chunks ──
            content_changes = new_changes + updated_changes + renamed_changes
            all_chunks: list[dict] = []

            for ch in content_changes:
                try:
                    # Fetch full content if not already available
                    if not ch.content:
                        data = connector.fetch_content(ch.resource_id)
                        ch.content = data.get("content", "")
                        ch.content_type = data.get("content_type", "")
                        ch.metadata.update(data.get("metadata", {}))

                    if not ch.content.strip():
                        continue

                    # Parse using the same chunk_text() from importers/base.py
                    parsed_chunks = chunk_text(ch.content)
                    title = (
                        ch.metadata.get("title")
                        or ch.metadata.get("name")
                        or ch.resource_id
                    )

                    for idx, chunk_content in enumerate(parsed_chunks):
                        all_chunks.append({
                            "content": chunk_content,
                            "title": title,
                            "entities": extract_entities(chunk_content)[:10],
                            "metadata": {
                                **ch.metadata,
                                "connector_type": ch.connector_type,
                                "resource_id": ch.resource_id,
                                "change_type": ch.change_type,
                                "chunk_index": idx,
                            },
                        })
                except Exception as exc:
                    errors_count += 1
                    ch.process_error = str(exc)
                    partial_failures.append(f"Parse failed for {ch.resource_id}: {exc}")
                    change_details.append({
                        "resource_id": ch.resource_id,
                        "change_type": ch.change_type,
                        "status": "failed",
                        "error": str(exc),
                    })

            # ── Phase 4: Reuse ImportMemoryPipeline.process() ──
            if all_chunks:
                source_label = f"sync:{connector.connector_type}:{config.name}"
                tags = [connector.connector_type, "sync", config.name]

                try:
                    pipeline_result = self._import_pipeline.process(
                        chunks=all_chunks,
                        source=source_label,
                        title=f"Sync: {config.name}",
                        tags=tags,
                    )
                    memories_created = pipeline_result.memories_created

                    for ch in content_changes:
                        ch.processed = True
                        change_details.append({
                            "resource_id": ch.resource_id,
                            "change_type": ch.change_type,
                            "status": "completed",
                        })
                except Exception as exc:
                    errors_count += 1
                    partial_failures.append(f"Memory pipeline failed: {exc}")
                    for ch in content_changes:
                        change_details.append({
                            "resource_id": ch.resource_id,
                            "change_type": ch.change_type,
                            "status": "failed",
                            "error": str(exc),
                        })

            # ── Phase 5: Handle deletions ──
            for ch in deleted_changes:
                try:
                    ch.processed = True
                    change_details.append({
                        "resource_id": ch.resource_id,
                        "change_type": "deleted",
                        "status": "completed",
                    })
                except Exception as exc:
                    errors_count += 1
                    change_details.append({
                        "resource_id": ch.resource_id,
                        "change_type": "deleted",
                        "status": "failed",
                        "error": str(exc),
                    })

            # ── Phase 6: Update tracking state ──
            ChangeDetector.update_config_state(config, changes)

            # ── Finalize ──
            status = "completed" if not partial_failures else "partial"
            execution.status = status
            execution.completed_at = datetime.now(timezone.utc)
            execution.items_fetched = connection.resources_count
            execution.items_new = len(new_changes)
            execution.items_updated = len(updated_changes)
            execution.items_deleted = len(deleted_changes)
            execution.items_renamed = len(renamed_changes)
            execution.memories_created = memories_created
            execution.errors_count = errors_count
            execution.error = "; ".join(partial_failures) if partial_failures else None
            execution.elapsed_ms = int((time.monotonic() - t0) * 1000)

            return SyncPipelineResult(
                execution_id=execution.id,
                status=status,
                items_fetched=connection.resources_count,
                items_new=len(new_changes),
                items_updated=len(updated_changes),
                items_deleted=len(deleted_changes),
                items_renamed=len(renamed_changes),
                memories_created=memories_created,
                errors_count=errors_count,
                error=execution.error,
                processing_time_ms=execution.elapsed_ms,
                change_details=change_details,
            )

        except Exception as exc:
            execution.status = "failed"
            execution.error = str(exc)
            execution.completed_at = datetime.now(timezone.utc)
            execution.elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.exception("sync_pipeline_crashed", extra={"execution_id": execution.id})
            return SyncPipelineResult(
                execution_id=execution.id,
                status="failed",
                error=str(exc),
                processing_time_ms=execution.elapsed_ms,
            )
