"""Obsidian vault connector — sync local markdown files from an Obsidian vault.

Reads .md files from a local filesystem vault. Tracks changes via mtime
and content hash, exactly like a folder watcher but scoped to Obsidian
conventions (ignores hidden folders, respects .obsidian/ internals).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import SyncConnectionResult, SyncResource


class ObsidianConnector(BaseSyncConnector):
    """Sync connector for a local Obsidian vault (markdown files on disk)."""

    connector_type: str = "obsidian"

    # Directories that are never user notes
    _IGNORED_DIRS: set[str] = {".obsidian", ".trash", ".git", ".svn", "__pycache__"}

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.logger = logging.getLogger("sync.connector.obsidian")
        self._vault_path: Path | None = None

    # ── helpers ──

    @property
    def vault_path(self) -> Path:
        """Resolve vault_path from config on first access (lazy + cached)."""
        if self._vault_path is None:
            raw = self.config.get("credentials", {}).get(
                "vault_path",
                self.config.get("vault_path", ""),
            )
            if not raw:
                raise ValueError("Obsidian connector requires 'vault_path' in credentials")
            self._vault_path = Path(raw).expanduser().resolve()
        return self._vault_path

    def _should_index(self, path: Path) -> bool:
        """True if the file is a user-created markdown note we should sync."""
        if not path.is_file():
            return False
        if path.suffix.lower() != ".md":
            return False
        # Skip files whose any parent is an ignored directory
        parts = set(path.relative_to(self.vault_path).parts[:-1])
        if parts & self._IGNORED_DIRS:
            return False
        return True

    def _stat_to_updated_at(self, path: Path) -> datetime:
        """Return mtime as a timezone-aware UTC datetime."""
        mtime = path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc)

    def _make_resource(self, path: Path) -> SyncResource:
        """Build a SyncResource from a vault .md file path."""
        relative = path.relative_to(self.vault_path)
        resource_id = str(relative.as_posix())
        name = relative.stem
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        return SyncResource(
            resource_id=resource_id,
            name=name,
            resource_type="note",
            updated_at=mtime,
            size_bytes=stat.st_size,
            metadata={
                "absolute_path": str(path),
                "relative_path": str(relative.as_posix()),
                "extension": path.suffix.lower(),
                "inode": stat.st_ino,
            },
        )

    # ── BaseSyncConnector interface ──

    def test_connection(self) -> SyncConnectionResult:
        """Validate the vault path exists, is a directory, and contains .md files."""
        try:
            vp = self.vault_path
        except ValueError as exc:
            self.logger.warning("test_connection: missing vault_path — %s", exc)
            return SyncConnectionResult(
                success=False,
                message="Missing vault_path in credentials",
                resources_count=0,
            )

        if not vp.exists():
            self.logger.warning("test_connection: vault path does not exist — %s", vp)
            return SyncConnectionResult(
                success=False,
                message=f"Vault path does not exist: {vp}",
                resources_count=0,
            )
        if not vp.is_dir():
            self.logger.warning("test_connection: vault path is not a directory — %s", vp)
            return SyncConnectionResult(
                success=False,
                message=f"Vault path is not a directory: {vp}",
                resources_count=0,
            )

        try:
            md_files = list(vp.rglob("*.md"))
            # Filter out ignored dirs
            visible = [f for f in md_files if self._should_index(f)]
            count = len(visible)
            self.logger.info(
                "test_connection: vault=%s, total_md=%d, visible=%d",
                vp, len(md_files), count,
            )
            return SyncConnectionResult(
                success=True,
                message=f"Connected to vault at {vp} ({count} notes found)",
                resources_count=count,
            )
        except PermissionError:
            self.logger.exception("test_connection: permission denied reading vault")
            return SyncConnectionResult(
                success=False,
                message=f"Permission denied reading vault: {vp}",
                resources_count=0,
            )
        except OSError as exc:
            self.logger.exception("test_connection: OS error reading vault")
            return SyncConnectionResult(
                success=False,
                message=f"Error reading vault: {exc}",
                resources_count=0,
            )

    def list_resources(self) -> list[SyncResource]:
        """Walk the vault and return a SyncResource for every visible .md file."""
        resources: list[SyncResource] = []
        try:
            vp = self.vault_path
        except ValueError:
            self.logger.error("list_resources: vault_path not configured")
            return resources

        try:
            for md_file in vp.rglob("*.md"):
                if not self._should_index(md_file):
                    continue
                try:
                    resources.append(self._make_resource(md_file))
                except OSError as exc:
                    self.logger.warning("list_resources: skipping unreadable file %s — %s", md_file, exc)
                    continue
        except PermissionError:
            self.logger.exception("list_resources: permission denied walking vault")
        except OSError as exc:
            self.logger.exception("list_resources: OS error walking vault — %s", exc)

        self.logger.info("list_resources: %d visible notes found in %s", len(resources), self.vault_path)
        return resources

    def fetch_changes(self, since: datetime | None) -> list[dict[str, Any]]:
        """Return change descriptors for every .md file modified since `since`.

        Each descriptor is a lightweight dict:
            {"resource_id": str, "change_type": "new"|"updated",
             "content_hash": str, "updated_at": datetime,
             "size_bytes": int, "metadata": dict}

        When `since` is None, all files are reported as "new".
        """
        changes: list[dict[str, Any]] = []
        try:
            vp = self.vault_path
        except ValueError:
            self.logger.error("fetch_changes: vault_path not configured")
            return changes

        # Normalise `since` to a UTC timestamp for comparison
        since_ts: float | None = None
        if since is not None:
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            since_ts = since.timestamp()

        try:
            for md_file in vp.rglob("*.md"):
                if not self._should_index(md_file):
                    continue
                try:
                    stat = md_file.stat()
                    mtime_ts = stat.st_mtime
                    if since_ts is not None and mtime_ts <= since_ts:
                        continue

                    content = md_file.read_text(encoding="utf-8", errors="replace")
                    content_hash = self.compute_hash(content)
                    mtime = datetime.fromtimestamp(mtime_ts, tz=timezone.utc)
                    relative = md_file.relative_to(vp)

                    change_type = "updated" if since_ts is not None else "new"

                    changes.append({
                        "resource_id": str(relative.as_posix()),
                        "name": relative.stem,
                        "change_type": change_type,
                        "content_hash": content_hash,
                        "updated_at": mtime,
                        "size_bytes": stat.st_size,
                        "metadata": {
                            "absolute_path": str(md_file),
                            "relative_path": str(relative.as_posix()),
                            "extension": md_file.suffix.lower(),
                            "inode": stat.st_ino,
                        },
                    })
                except OSError as exc:
                    self.logger.warning("fetch_changes: skipping %s — %s", md_file, exc)
                    continue
        except PermissionError:
            self.logger.exception("fetch_changes: permission denied walking vault")
        except OSError as exc:
            self.logger.exception("fetch_changes: OS error walking vault — %s", exc)

        self.logger.info(
            "fetch_changes: since=%s, changes=%d",
            since.isoformat() if since else "epoch", len(changes),
        )
        return changes

    def fetch_content(self, resource_id: str) -> dict[str, Any]:
        """Read the full content of a single markdown note.

        Returns:
            {"content": str, "content_type": str, "metadata": dict}

        Returns an error dict with empty content on failure.
        """
        try:
            vp = self.vault_path
        except ValueError:
            self.logger.error("fetch_content: vault_path not configured")
            return {"content": "", "content_type": "markdown", "metadata": {"error": "vault_path not configured"}}

        file_path = (vp / resource_id).resolve()

        # Security: ensure the resolved path stays inside the vault
        try:
            file_path.relative_to(vp)
        except ValueError:
            self.logger.warning("fetch_content: path traversal attempt — %s", resource_id)
            return {"content": "", "content_type": "markdown", "metadata": {"error": "resource_id escapes vault"}}

        if not file_path.exists():
            self.logger.warning("fetch_content: file not found — %s", file_path)
            return {"content": "", "content_type": "markdown", "metadata": {"error": "file not found"}}

        if not file_path.is_file():
            self.logger.warning("fetch_content: not a file — %s", file_path)
            return {"content": "", "content_type": "markdown", "metadata": {"error": "not a file"}}

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.logger.exception("fetch_content: read error — %s", file_path)
            return {"content": "", "content_type": "markdown", "metadata": {"error": str(exc)}}

        stat = file_path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        content_hash = self.compute_hash(content)

        self.logger.info("fetch_content: %s (%d bytes)", resource_id, len(content))
        return {
            "content": content,
            "content_type": "markdown",
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

_register("obsidian", ObsidianConnector)
