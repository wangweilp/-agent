"""Logseq connector — syncs local Logseq graph (markdown + EDN files).

Reads .md files from pages/ and journals/ directories of a Logseq graph.
Detects changes via filesystem mtime + content hash.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import SyncConnectionResult, SyncResource


class LogseqConnector(BaseSyncConnector):
    """Sync connector for local Logseq graphs.

    Discovers markdown files in pages/ and journals/ directories,
    reads their content, and tracks changes via mtime + content hash.
    """

    connector_type: str = "logseq"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.logger = logging.getLogger("sync.connector.logseq")

    # ── helpers ──

    @property
    def graph_root(self) -> Path:
        """Resolved absolute path to the Logseq graph root directory."""
        raw = self.config.get("graph_path", "")
        if not raw:
            return Path(".")
        return Path(raw).expanduser().resolve()

    def _resource_id_for(self, file_path: Path) -> str:
        """Relative path from graph root, forward slashes, as resource_id."""
        try:
            rel = file_path.resolve().relative_to(self.graph_root)
        except ValueError:
            rel = file_path
        return rel.as_posix()

    def _md_files(self) -> list[Path]:
        """Return all .md files under pages/ and journals/."""
        root = self.graph_root
        if not root.is_dir():
            return []
        files: list[Path] = []
        for sub in ("pages", "journals"):
            subdir = root / sub
            if subdir.is_dir():
                files.extend(sorted(subdir.rglob("*.md")))
        return files

    def _file_to_resource(self, file_path: Path) -> SyncResource:
        """Convert a file Path to a SyncResource."""
        stat = file_path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        rid = self._resource_id_for(file_path)
        return SyncResource(
            resource_id=rid,
            name=file_path.stem,
            resource_type="note",
            updated_at=mtime,
            size_bytes=stat.st_size,
            metadata={
                "path": str(file_path),
                "relative_path": rid,
                "extension": file_path.suffix,
            },
        )

    # ── connector interface ──

    def test_connection(self) -> SyncConnectionResult:
        """Validate that graph_path points to a readable Logseq graph.

        Checks that:
        - graph_path is configured
        - the directory exists and is readable
        - at least one of pages/ or journals/ exists
        """
        graph_path = self.config.get("graph_path", "")
        if not graph_path:
            return SyncConnectionResult(
                success=False,
                message="No graph_path configured. Provide the path to your Logseq graph root.",
                resources_count=0,
            )

        root = self.graph_root
        if not root.exists():
            return SyncConnectionResult(
                success=False,
                message=f"Graph path does not exist: {root}",
                resources_count=0,
            )
        if not root.is_dir():
            return SyncConnectionResult(
                success=False,
                message=f"Graph path is not a directory: {root}",
                resources_count=0,
            )

        pages_dir = root / "pages"
        journals_dir = root / "journals"
        has_pages = pages_dir.is_dir()
        has_journals = journals_dir.is_dir()

        if not has_pages and not has_journals:
            return SyncConnectionResult(
                success=False,
                message=f"No pages/ or journals/ directory found in graph: {root}",
                resources_count=0,
            )

        try:
            md_files = self._md_files()
        except PermissionError as e:
            return SyncConnectionResult(
                success=False,
                message=f"Permission denied reading graph: {e}",
                resources_count=0,
            )
        except OSError as e:
            return SyncConnectionResult(
                success=False,
                message=f"IO error reading graph: {e}",
                resources_count=0,
            )

        dirs_found = []
        if has_pages:
            dirs_found.append("pages/")
        if has_journals:
            dirs_found.append("journals/")

        return SyncConnectionResult(
            success=True,
            message=f"Connected. Found {', '.join(dirs_found)} with {len(md_files)} markdown files.",
            resources_count=len(md_files),
        )

    def list_resources(self) -> list[SyncResource]:
        """List all .md files in pages/ and journals/ as SyncResource objects."""
        try:
            return [self._file_to_resource(f) for f in self._md_files()]
        except (OSError, PermissionError) as e:
            self.logger.error("Failed to list resources: %s", e)
            return []

    def fetch_changes(self, since: datetime | None = None) -> list[dict]:
        """Return resources changed since the given timestamp (or all if None).

        Each change descriptor is a dict with:
            resource_id, updated_at, content_hash, size_bytes, change_type

        change_type is "new" when there is no previous timestamp (first sync),
        otherwise determined by comparing mtime.
        """
        if since is not None and since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)

        try:
            all_files = self._md_files()
        except (OSError, PermissionError) as e:
            self.logger.error("Failed to scan for changes: %s", e)
            return []

        changes: list[dict] = []
        for file_path in all_files:
            try:
                stat = file_path.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

                # Skip unchanged files when a since timestamp is provided
                if since is not None and mtime <= since:
                    continue

                content = file_path.read_text(encoding="utf-8", errors="replace")
                content_hash = self.compute_hash(content)

                change_type = "updated"
                if since is None:
                    change_type = "new"

                changes.append({
                    "resource_id": self._resource_id_for(file_path),
                    "name": file_path.stem,
                    "updated_at": mtime,
                    "content_hash": content_hash,
                    "size_bytes": stat.st_size,
                    "change_type": change_type,
                    "metadata": {
                        "path": str(file_path),
                        "relative_path": self._resource_id_for(file_path),
                        "extension": file_path.suffix,
                    },
                })
            except (OSError, PermissionError) as e:
                self.logger.warning(
                    "Skipping %s due to read error: %s", file_path, e
                )
                continue

        # Detect deletions: look at files that were tracked but no longer exist
        # This requires the caller to pass in previously-known resource_ids as
        # metadata on the since check; we provide a lightweight mechanism here.
        # For now, return what we found — the ChangeDetector handles deletions.

        return changes

    def fetch_content(self, resource_id: str) -> dict:
        """Read the full markdown content for a resource by its relative path.

        Args:
            resource_id: Relative path from graph root, e.g. "pages/My Note.md"

        Returns:
            {"content": str, "content_type": str, "metadata": dict}
            On error, returns empty content with an "error" metadata key.
        """
        file_path = self.graph_root / resource_id
        try:
            file_path = file_path.resolve()
            # Safety: ensure the resolved path is inside the graph root
            try:
                file_path.relative_to(self.graph_root.resolve())
            except ValueError:
                return {
                    "content": "",
                    "content_type": "text/markdown",
                    "metadata": {
                        "resource_id": resource_id,
                        "error": f"Path traversal detected: {resource_id} is outside the graph root",
                    },
                }

            if not file_path.is_file():
                return {
                    "content": "",
                    "content_type": "text/markdown",
                    "metadata": {
                        "resource_id": resource_id,
                        "error": f"File not found: {file_path}",
                    },
                }

            content = file_path.read_text(encoding="utf-8", errors="replace")
            stat = file_path.stat()
            content_hash = self.compute_hash(content)
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

            return {
                "content": content,
                "content_type": "text/markdown",
                "metadata": {
                    "resource_id": resource_id,
                    "path": str(file_path),
                    "name": file_path.stem,
                    "size_bytes": stat.st_size,
                    "updated_at": mtime.isoformat(),
                    "content_hash": content_hash,
                    "extension": file_path.suffix,
                },
            }
        except PermissionError as e:
            self.logger.error("Permission denied reading %s: %s", resource_id, e)
            return {
                "content": "",
                "content_type": "text/markdown",
                "metadata": {
                    "resource_id": resource_id,
                    "error": f"Permission denied: {e}",
                },
            }
        except OSError as e:
            self.logger.error("IO error reading %s: %s", resource_id, e)
            return {
                "content": "",
                "content_type": "text/markdown",
                "metadata": {
                    "resource_id": resource_id,
                    "error": f"IO error: {e}",
                },
            }
        except Exception as e:
            self.logger.error(
                "Unexpected error reading %s: %s", resource_id, e
            )
            return {
                "content": "",
                "content_type": "text/markdown",
                "metadata": {
                    "resource_id": resource_id,
                    "error": f"Unexpected error: {e}",
                },
            }


from src.sync import _register  # noqa: E402

_register("logseq", LogseqConnector)
