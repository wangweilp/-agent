"""Local folder connector — watches a local filesystem folder for file changes.

Recursively walks a directory, tracks files via mtime and content hash,
and returns SyncResource objects for every visible file (skipping hidden
files and common VCS/editor artifacts).

Security: folder_path MUST be within one of the server-configured allowed roots
(Settings.sync_local_folder_allowed_roots). The connector refuses to operate
on paths outside the allowlist.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import SyncConnectionResult, SyncResource

# Global reference set by bootstrap (main.py) — avoids circular import of Settings
_ALLOWED_ROOTS: list[Path] = []
_MAX_FILE_BYTES: int = 10 * 1024 * 1024


def configure_local_folder_allowlist(allowed_roots: list[str], max_file_bytes: int | None = None) -> None:
    """Set the allowlist from server config. Called once at bootstrap."""
    global _ALLOWED_ROOTS, _MAX_FILE_BYTES
    _ALLOWED_ROOTS = [Path(r).expanduser().resolve() for r in allowed_roots if r.strip()]
    if max_file_bytes is not None:
        _MAX_FILE_BYTES = max_file_bytes


def _validate_path_within_allowlist(folder_path: Path) -> None:
    """Raise ValueError if folder_path is not within any allowed root."""
    if not _ALLOWED_ROOTS:
        raise ValueError(
            "local_folder sync is disabled: no allowed roots configured. "
            "Contact your administrator to add paths to SYNC_LOCAL_FOLDER_ALLOWED_ROOTS."
        )
    resolved = folder_path.expanduser().resolve()
    for root in _ALLOWED_ROOTS:
        try:
            resolved.relative_to(root)
            return  # OK — within an allowed root
        except ValueError:
            continue
    raise ValueError(
        f"Access denied: '{folder_path}' is not within any allowed sync root. "
        f"Allowed roots: {[str(r) for r in _ALLOWED_ROOTS]}"
    )


# ── Content-type mapping by file extension ──

_CONTENT_TYPE_MAP: dict[str, str] = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".html": "html",
    ".htm": "html",
    ".json": "json",
    ".csv": "csv",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "text",
    ".cfg": "text",
    ".py": "text",
    ".js": "text",
    ".ts": "text",
    ".jsx": "text",
    ".tsx": "text",
    ".go": "text",
    ".rs": "text",
    ".java": "text",
    ".c": "text",
    ".cpp": "text",
    ".h": "text",
    ".hpp": "text",
    ".css": "text",
    ".scss": "text",
    ".less": "text",
    ".sql": "text",
    ".sh": "text",
    ".bash": "text",
    ".zsh": "text",
    ".ps1": "text",
    ".bat": "text",
    ".rst": "text",
    ".tex": "text",
    ".log": "text",
    ".svg": "text",
}


# Directories and file patterns to skip
_SKIP_DIRS: set[str] = {
    ".git", ".svn", ".hg",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules", ".venv", "venv", ".env", ".tox",
    ".obsidian", ".trash", ".DS_Store",
    ".idea", ".vscode", ".vs",
}

_SKIP_PREFIXES: tuple[str, ...] = (".", "~")

# Max file size to read (10 MB)
_MAX_FILE_BYTES: int = 10 * 1024 * 1024


def _guess_content_type(extension: str) -> str:
    """Map a lowercase file extension (with leading dot) to a content_type string."""
    return _CONTENT_TYPE_MAP.get(extension, "text")


def _is_hidden_or_ignored(path: Path) -> bool:
    """True if the path or any of its components should be skipped."""
    for part in path.parts:
        if part in _SKIP_DIRS:
            return True
        if part.startswith(_SKIP_PREFIXES):
            return True
    return False


class LocalFolderConnector(BaseSyncConnector):
    """Sync connector that watches a local folder for file changes.

    Uses os.stat metadata (mtime, size, inode) and content hashing
    to detect new, updated, and deleted files.
    """

    connector_type: str = "local_folder"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.logger = logging.getLogger("sync.connector.local_folder")
        self._folder_path: Path | None = None

    # ── helpers ──

    @property
    def folder_path(self) -> Path:
        """Resolve folder_path from config on first access (lazy + cached).

        Raises ValueError if path is not within a server-configured allowed root.
        """
        if self._folder_path is None:
            raw = (
                self.config.get("folder_path", "")
                or self.config.get("credentials", {}).get("folder_path", "")
            )
            if not raw:
                raise ValueError("local_folder connector requires 'folder_path' in config or credentials")
            path = Path(raw)
            _validate_path_within_allowlist(path)
            self._folder_path = path.expanduser().resolve()
        return self._folder_path

    @staticmethod
    def _stat_to_utc_datetime(path: Path) -> datetime:
        """Return mtime as a timezone-aware UTC datetime."""
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

    def _make_resource(self, file_path: Path, stat: os.stat_result | None = None) -> SyncResource:
        """Build a SyncResource from a file path.

        Args:
            file_path: Absolute path to the file.
            stat: Pre-fetched stat result (avoids a second syscall).

        Returns:
            SyncResource with resource_id = relative posix path from folder root.
        """
        relative = file_path.relative_to(self.folder_path)
        if stat is None:
            stat = file_path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        extension = file_path.suffix.lower()

        return SyncResource(
            resource_id=relative.as_posix(),
            name=file_path.name,
            resource_type=_guess_content_type(extension),
            updated_at=mtime,
            size_bytes=stat.st_size,
            metadata={
                "absolute_path": str(file_path),
                "relative_path": relative.as_posix(),
                "extension": extension,
                "inode": stat.st_ino,
            },
        )

    def _should_include(self, file_path: Path) -> bool:
        """True if this file should be synced (not hidden, not in skip dirs)."""
        if not file_path.is_file():
            return False
        # Skip hidden files and ignored directory trees
        try:
            rel = file_path.relative_to(self.folder_path)
        except ValueError:
            return False
        if _is_hidden_or_ignored(rel):
            return False
        return True

    # ── BaseSyncConnector interface ──

    def test_connection(self) -> SyncConnectionResult:
        """Validate the folder path exists and is a readable directory."""
        try:
            fp = self.folder_path
        except ValueError as exc:
            self.logger.warning("test_connection: missing folder_path — %s", exc)
            return SyncConnectionResult(
                success=False,
                message="Missing folder_path in config or credentials",
                resources_count=0,
            )

        if not fp.exists():
            self.logger.warning("test_connection: folder does not exist — %s", fp)
            return SyncConnectionResult(
                success=False,
                message=f"Folder does not exist: {fp}",
                resources_count=0,
            )
        if not fp.is_dir():
            self.logger.warning("test_connection: path is not a directory — %s", fp)
            return SyncConnectionResult(
                success=False,
                message=f"Path is not a directory: {fp}",
                resources_count=0,
            )

        # Walk once to count visible files
        try:
            count = 0
            for entry in fp.rglob("*"):
                if self._should_include(entry):
                    count += 1
        except PermissionError:
            self.logger.exception("test_connection: permission denied reading folder")
            return SyncConnectionResult(
                success=False,
                message=f"Permission denied reading folder: {fp}",
                resources_count=0,
            )
        except OSError as exc:
            self.logger.exception("test_connection: OS error reading folder")
            return SyncConnectionResult(
                success=False,
                message=f"Error reading folder: {exc}",
                resources_count=0,
            )

        self.logger.info("test_connection: folder=%s, visible_files=%d", fp, count)
        return SyncConnectionResult(
            success=True,
            message=f"Connected to folder at {fp} ({count} files found)",
            resources_count=count,
        )

    def list_resources(self) -> list[SyncResource]:
        """Walk the folder recursively and return a SyncResource for every visible file."""
        resources: list[SyncResource] = []
        try:
            fp = self.folder_path
        except ValueError:
            self.logger.error("list_resources: folder_path not configured")
            return resources

        try:
            for entry in fp.rglob("*"):
                if not self._should_include(entry):
                    continue
                try:
                    resources.append(self._make_resource(entry))
                except OSError as exc:
                    self.logger.warning(
                        "list_resources: skipping unreadable file %s — %s", entry, exc,
                    )
                    continue
        except PermissionError:
            self.logger.exception("list_resources: permission denied walking folder")
        except OSError as exc:
            self.logger.exception("list_resources: OS error walking folder — %s", exc)

        self.logger.info(
            "list_resources: %d visible files found in %s", len(resources), self.folder_path,
        )
        return resources

    def fetch_changes(self, since: datetime | None) -> list[dict[str, Any]]:
        """Return change descriptors for every file modified since `since`.

        Each descriptor:
            {"resource_id": str, "name": str, "change_type": "new"|"updated",
             "content_hash": str, "updated_at": datetime,
             "size_bytes": int, "metadata": dict}

        When `since` is None, all files are reported as "new".
        """
        changes: list[dict[str, Any]] = []
        try:
            fp = self.folder_path
        except ValueError:
            self.logger.error("fetch_changes: folder_path not configured")
            return changes

        since_ts: float | None = None
        if since is not None:
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            since_ts = since.timestamp()

        try:
            for entry in fp.rglob("*"):
                if not self._should_include(entry):
                    continue
                try:
                    stat = entry.stat()
                    mtime_ts = stat.st_mtime
                    if since_ts is not None and mtime_ts <= since_ts:
                        continue

                    content = entry.read_text(encoding="utf-8", errors="replace")
                    content_hash = self.compute_hash(content)
                    mtime = datetime.fromtimestamp(mtime_ts, tz=timezone.utc)
                    relative = entry.relative_to(fp)

                    change_type = "updated" if since_ts is not None else "new"

                    changes.append({
                        "resource_id": relative.as_posix(),
                        "name": entry.name,
                        "change_type": change_type,
                        "content_hash": content_hash,
                        "updated_at": mtime,
                        "size_bytes": stat.st_size,
                        "metadata": {
                            "absolute_path": str(entry),
                            "relative_path": relative.as_posix(),
                            "extension": entry.suffix.lower(),
                            "inode": stat.st_ino,
                        },
                    })
                except OSError as exc:
                    self.logger.warning("fetch_changes: skipping %s — %s", entry, exc)
                    continue
        except PermissionError:
            self.logger.exception("fetch_changes: permission denied walking folder")
        except OSError as exc:
            self.logger.exception("fetch_changes: OS error walking folder — %s", exc)

        self.logger.info(
            "fetch_changes: since=%s, changes=%d",
            since.isoformat() if since else "epoch",
            len(changes),
        )
        return changes

    def fetch_content(self, resource_id: str) -> dict[str, Any]:
        """Read the full content of a single file by its resource_id.

        Returns:
            {"content": str, "content_type": str, "metadata": dict}

        Returns an error dict with empty content on failure.
        """
        try:
            fp = self.folder_path
        except ValueError:
            self.logger.error("fetch_content: folder_path not configured")
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"error": "folder_path not configured"},
            }

        file_path = (fp / resource_id).resolve()

        # Security: prevent path-traversal — resolved path must stay inside folder
        try:
            file_path.relative_to(fp)
        except ValueError:
            self.logger.warning("fetch_content: path traversal attempt — %s", resource_id)
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"error": "resource_id escapes folder root"},
            }

        if not file_path.exists():
            self.logger.warning("fetch_content: file not found — %s", file_path)
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"error": "file not found"},
            }

        if not file_path.is_file():
            self.logger.warning("fetch_content: not a file — %s", file_path)
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"error": "not a file"},
            }

        try:
            stat = file_path.stat()
        except OSError as exc:
            self.logger.exception("fetch_content: stat error — %s", file_path)
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"error": f"stat failed: {exc}"},
            }

        max_bytes = _MAX_FILE_BYTES
        if stat.st_size > max_bytes:
            self.logger.warning(
                "fetch_content: file too large (%d bytes), skipping — %s",
                stat.st_size, resource_id,
            )
            return {
                "content": "[file exceeds 10 MB size limit]",
                "content_type": "text",
                "metadata": {
                    "error": "file too large",
                    "size_bytes": stat.st_size,
                    "resource_id": resource_id,
                },
            }

        content_type = _guess_content_type(file_path.suffix.lower())

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.logger.exception("fetch_content: read error — %s", file_path)
            return {
                "content": "",
                "content_type": content_type,
                "metadata": {"error": str(exc)},
            }

        content_hash = self.compute_hash(content)
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        self.logger.debug("fetch_content: %s (%d bytes)", resource_id, len(content))
        return {
            "content": content,
            "content_type": content_type,
            "metadata": {
                "resource_id": resource_id,
                "absolute_path": str(file_path),
                "filename": file_path.name,
                "stem": file_path.stem,
                "extension": file_path.suffix.lower(),
                "size_bytes": stat.st_size,
                "updated_at": mtime.isoformat(),
                "content_hash": content_hash,
            },
        }


# ── Auto-registration ──
from src.sync import _register  # noqa: E402

_register("local_folder", LocalFolderConnector)
