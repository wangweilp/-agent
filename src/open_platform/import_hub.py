"""Import Hub — metadata-only import center. No file execution. No runtime.

Step 27: Import readiness for Notion/Markdown/Obsidian/PDF.
No real import. No file read. No execution. import_active=False.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


class ImportSourceType(StrEnum):
    NOTION = "notion"
    MARKDOWN = "markdown"
    OBSIDIAN = "obsidian"
    PDF = "pdf"
    CSV = "csv"
    JSON = "json"


class ImportStatus(StrEnum):
    NOT_STARTED = "not_started"
    CONFIGURED = "configured"
    METADATA_VALIDATED = "metadata_validated"
    IMPORT_READY = "import_ready"
    IMPORT_ACTIVE = "import_active"
    FAIL_CLOSED = "fail_closed"


@dataclass
class ImportSource:
    source_id: str = field(default_factory=lambda: f"impsrc_{uuid4().hex[:16]}")
    source_type: str = ""
    source_name: str = ""
    description: str = ""
    file_count: int = 0
    estimated_size_bytes: int = 0
    import_allowed: bool = False
    file_write_allowed: bool = False
    execution_allowed: bool = False
    metadata_only: bool = True
    supported_formats: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def is_import_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "source_id": self.source_id, "source_type": self.source_type,
            "source_name": self.source_name, "description": self.description,
            "file_count": self.file_count, "estimated_size_bytes": self.estimated_size_bytes,
            "import_allowed": self.import_allowed,
            "file_write_allowed": self.file_write_allowed,
            "execution_allowed": self.execution_allowed,
            "metadata_only": self.metadata_only,
            "supported_formats": self.supported_formats,
            "warnings": self.warnings,
        }


@dataclass
class ImportHubReport:
    report_id: str = field(default_factory=lambda: f"imprep_{uuid4().hex[:16]}")
    status: str = ImportStatus.NOT_STARTED
    import_active: bool = False
    import_allowed: bool = False
    sources_configured: int = 0
    total_files_pending: int = 0
    sources: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    execution_allowed: bool = False
    runtime_enabled: bool = False
    metadata_only: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "report_id": self.report_id, "status": self.status,
            "import_active": self.import_active, "import_allowed": self.import_allowed,
            "sources_configured": self.sources_configured,
            "total_files_pending": self.total_files_pending,
            "sources": self.sources,
            "warnings": self.warnings,
            "execution_allowed": self.execution_allowed,
            "runtime_enabled": self.runtime_enabled,
            "metadata_only": self.metadata_only,
            "created_at": self.created_at.isoformat(),
        }


SUPPORTED_IMPORT_SOURCES = {
    ImportSourceType.NOTION: ImportSource(
        source_type=ImportSourceType.NOTION, source_name="Notion Import",
        description="Import from Notion workspace (API-based, future)",
        supported_formats=[".md", ".csv"], import_allowed=False,
        warnings=["Notion API not connected", "Import disabled by default"]),
    ImportSourceType.MARKDOWN: ImportSource(
        source_type=ImportSourceType.MARKDOWN, source_name="Markdown Import",
        description="Import markdown files (local/remote, future)",
        supported_formats=[".md"], import_allowed=False,
        warnings=["No file read access", "Import disabled by default"]),
    ImportSourceType.OBSIDIAN: ImportSource(
        source_type=ImportSourceType.OBSIDIAN, source_name="Obsidian Vault Import",
        description="Import from Obsidian vault directory (future)",
        supported_formats=[".md"], import_allowed=False,
        warnings=["No file system access", "Import disabled by default"]),
    ImportSourceType.PDF: ImportSource(
        source_type=ImportSourceType.PDF, source_name="PDF Import",
        description="Import PDF documents with metadata extraction (future)",
        supported_formats=[".pdf"], import_allowed=False,
        warnings=["PDF parsing not implemented", "Import disabled by default"]),
    ImportSourceType.CSV: ImportSource(
        source_type=ImportSourceType.CSV, source_name="CSV Import",
        description="Import CSV data files (future)",
        supported_formats=[".csv"], import_allowed=False,
        warnings=["CSV parsing not implemented", "Import disabled by default"]),
    ImportSourceType.JSON: ImportSource(
        source_type=ImportSourceType.JSON, source_name="JSON Import",
        description="Import JSON data files (future)",
        supported_formats=[".json"], import_allowed=False,
        warnings=["JSON parsing not implemented", "Import disabled by default"]),
}


class ImportHub:
    """Import Hub — metadata-only. No real import. No file read."""

    def __init__(self):
        self._import_active = False

    def assess_readiness(self) -> ImportHubReport:
        sources = [s.to_dict() for s in SUPPORTED_IMPORT_SOURCES.values()]
        return ImportHubReport(
            status=ImportStatus.CONFIGURED,
            import_active=False, import_allowed=False,
            sources_configured=len(SUPPORTED_IMPORT_SOURCES),
            sources=sources,
            warnings=["Import Hub is metadata-configured only",
                       "No import operations are active",
                       "All import_allowed=False"],
            execution_allowed=False, runtime_enabled=False, metadata_only=True,
        )

    def get_supported_sources(self) -> dict[str, dict]:
        return {k.value: v.to_dict() for k, v in SUPPORTED_IMPORT_SOURCES.items()}
