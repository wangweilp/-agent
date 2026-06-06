"""Dropbox sync connector — cloud storage via Dropbox API v2.

Uses the Dropbox HTTP API (https://api.dropboxapi.com/2/) with OAuth 2.0
bearer-token authentication. Supports folder listing, incremental change
detection via cursor-based polling, and file content download.

Credentials (self.config):
    access_token  — OAuth 2.0 access token (required)
    folder_path   — Dropbox path to sync, e.g. "/my-folder" or "" for root
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import SyncConnectionResult, SyncResource

# ── Dropbox API constants ──
_DROPBOX_API_BASE = "https://api.dropboxapi.com/2"
_DROPBOX_CONTENT_BASE = "https://content.dropboxapi.com/2"
_REQUEST_TIMEOUT = 30.0

# File extension -> content_type mapping used by fetch_content()
_EXT_TO_CONTENT_TYPE: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xml": "application/xml",
    ".html": "text/html",
    ".htm": "text/html",
    ".py": "text/x-python",
    ".js": "text/javascript",
    ".ts": "text/typescript",
    ".css": "text/css",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".toml": "text/toml",
    ".ini": "text/plain",
    ".cfg": "text/plain",
    ".log": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".zip": "application/zip",
}


def _ext_to_readable_type(ext: str) -> str:
    """Map a lowercase file extension to a readable content_type label."""
    return _EXT_TO_CONTENT_TYPE.get(ext, "application/octet-stream")


class DropboxConnector(BaseSyncConnector):
    """Sync connector for Dropbox cloud storage.

    Uses the Dropbox API v2 to list files, detect changes, and download
    content. Requires a valid OAuth 2.0 access token in self.config.
    """

    connector_type = "dropbox"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.logger = logging.getLogger("sync.connector.dropbox")

    # ── helpers ──

    def _headers(self) -> dict[str, str]:
        """Build the Authorization + Content-Type header dict."""
        token = self.config.get("access_token", "")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _folder_path(self) -> str:
        """Return the configured Dropbox folder path, defaulting to root."""
        path = self.config.get("folder_path", "").strip()
        if path and not path.startswith("/"):
            path = "/" + path
        return path or ""

    def _api_post(self, endpoint: str, payload: dict) -> dict | None:
        """Call a Dropbox API RPC endpoint (api.dropboxapi.com).

        Returns the parsed JSON body on success, or None on failure.
        """
        url = f"{_DROPBOX_API_BASE}{endpoint}"
        try:
            resp = requests.post(
                url,
                headers=self._headers(),
                json=payload,
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code >= 400:
                self.logger.error(
                    "Dropbox API error %d on %s: %s",
                    resp.status_code,
                    endpoint,
                    resp.text[:500],
                )
                return None
            return resp.json()
        except requests.RequestException as exc:
            self.logger.error("Dropbox API request failed for %s: %s", endpoint, exc)
            return None

    def _content_api_get(self, path: str) -> bytes | None:
        """Download a file via the Dropbox content API (content.dropboxapi.com).

        Returns raw bytes on success, None on failure.
        """
        url = f"{_DROPBOX_CONTENT_BASE}/files/download"
        headers = {
            "Authorization": f"Bearer {self.config.get('access_token', '')}",
            "Content-Type": "",  # required: send empty Content-Type
            "Dropbox-API-Arg": '{"path":"' + path + '"}',
        }
        try:
            resp = requests.get(
                url,
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code >= 400:
                self.logger.error(
                    "Dropbox download error %d for %s: %s",
                    resp.status_code,
                    path,
                    resp.text[:500],
                )
                return None
            return resp.content
        except requests.RequestException as exc:
            self.logger.error("Dropbox download failed for %s: %s", path, exc)
            return None

    def _entry_to_resource(self, entry: dict) -> SyncResource:
        """Convert a Dropbox file-list entry dict to a SyncResource."""
        name = entry.get("name", "")
        resource_id = entry.get("id", "") or entry.get("path_lower", "")
        tag = entry.get(".tag", "file")
        resource_type = "folder" if tag == "folder" else "file"

        updated_at: datetime | None = None
        server_modified = entry.get("server_modified", "")
        if server_modified:
            try:
                # Dropbox returns ISO-8601, e.g. "2015-05-12T15:50:38Z"
                updated_at = datetime.fromisoformat(
                    server_modified.replace("Z", "+00:00")
                )
            except ValueError:
                self.logger.debug("Could not parse server_modified: %s", server_modified)

        size_bytes = entry.get("size", 0) or 0

        metadata: dict = {
            "path_lower": entry.get("path_lower", ""),
            "path_display": entry.get("path_display", ""),
            "tag": tag,
            "client_modified": entry.get("client_modified", ""),
            "server_modified": server_modified,
            "rev": entry.get("rev", ""),
            "content_hash": entry.get("content_hash", ""),
        }

        return SyncResource(
            resource_id=resource_id,
            name=name,
            resource_type=resource_type,
            updated_at=updated_at,
            size_bytes=size_bytes,
            metadata=metadata,
        )

    def _list_folder_all(self) -> list[dict]:
        """List all entries in the configured folder, following pagination."""
        folder = self._folder_path()
        payload: dict = {
            "path": folder,
            "recursive": True,
            "include_deleted": False,
            "include_has_explicit_shared_members": False,
        }

        all_entries: list[dict] = []
        result = self._api_post("/files/list_folder", payload)
        if result is None:
            return all_entries

        entries: list[dict] = result.get("entries", [])
        all_entries.extend(entries)

        has_more = result.get("has_more", False)
        cursor = result.get("cursor", "")

        while has_more and cursor:
            cont = self._api_post(
                "/files/list_folder/continue", {"cursor": cursor}
            )
            if cont is None:
                break
            all_entries.extend(cont.get("entries", []))
            has_more = cont.get("has_more", False)
            cursor = cont.get("cursor", "")

        return all_entries

    # ── required interface ──

    def test_connection(self) -> SyncConnectionResult:
        """Validate the access token by calling users/get_current_account.

        Returns a SyncConnectionResult with success=True and a user-display
        message when the token is valid.
        """
        token = self.config.get("access_token", "")
        if not token:
            return SyncConnectionResult(
                success=False,
                message="Missing access_token in config",
            )

        data = self._api_post("/users/get_current_account", {"account_id": None})
        if data is None:
            return SyncConnectionResult(
                success=False,
                message="Failed to connect to Dropbox — check access_token and network",
            )

        account_id = data.get("account_id", "")
        email = data.get("email", "")
        name = data.get("name", {}).get("display_name", account_id)

        self.logger.info("Dropbox connection OK for account %s (%s)", name, email)

        # Count resources for the connection result
        entries = self._list_folder_all()
        file_count = sum(1 for e in entries if e.get(".tag") == "file")

        return SyncConnectionResult(
            success=True,
            message=f"Connected as {name} ({email})",
            resources_count=file_count,
        )

    def list_resources(self) -> list[SyncResource]:
        """List all files and folders recursively under the configured path.

        Folders are included so downstream logic can distinguish hierarchies.
        """
        try:
            entries = self._list_folder_all()
        except Exception as exc:
            self.logger.exception("list_resources failed: %s", exc)
            return []

        resources: list[SyncResource] = []
        for entry in entries:
            try:
                resources.append(self._entry_to_resource(entry))
            except Exception as exc:
                self.logger.warning("Skipping malformed entry: %s", exc)
                continue

        self.logger.info("list_resources returned %d items", len(resources))
        return resources

    def fetch_changes(self, since: datetime | None) -> list[dict]:
        """Return entries changed since *since*.

        The Dropbox API does not provide a native "modified since" endpoint,
        so we list all files and filter by server_modified client-side.
        The returned dictionaries are lightweight change descriptors with
        keys: resource_id, name, resource_type, updated_at, size_bytes,
        metadata, change_type ("new" / "updated" / "deleted").
        """
        try:
            entries = self._list_folder_all()
        except Exception as exc:
            self.logger.exception("fetch_changes failed: %s", exc)
            return []

        changes: list[dict] = []
        for entry in entries:
            try:
                resource = self._entry_to_resource(entry)
            except Exception:
                continue

            # Filter by timestamp
            if since is not None and resource.updated_at is not None:
                if resource.updated_at <= since:
                    continue

            change_type = "new"
            # Simple heuristic: if we have server_modified, treat as updated
            if resource.updated_at is not None and since is not None:
                change_type = "updated"

            changes.append({
                "resource_id": resource.resource_id,
                "name": resource.name,
                "resource_type": resource.resource_type,
                "updated_at": resource.updated_at.isoformat() if resource.updated_at else None,
                "size_bytes": resource.size_bytes,
                "metadata": resource.metadata,
                "change_type": change_type,
            })

        self.logger.info(
            "fetch_changes returned %d items (since=%s)",
            len(changes),
            since.isoformat() if since else "None",
        )
        return changes

    def fetch_content(self, resource_id: str) -> dict:
        """Download the file content for *resource_id*.

        The resource_id can be a Dropbox path (e.g. "/docs/readme.md") or a
        file ID (e.g. "id:abc123"). We prefer the path form.

        Returns:
            {"content": str, "content_type": str, "metadata": dict}

        On failure, returns an error dict.
        """
        # Determine whether resource_id is an id: prefix or a path
        path = resource_id
        if resource_id.startswith("id:"):
            # Dropbox API supports "id:xxx" for download — pass through
            pass
        elif not resource_id.startswith("/"):
            path = "/" + resource_id
        else:
            path = resource_id

        raw = self._content_api_get(path)
        if raw is None:
            return {
                "content": "",
                "content_type": "text/plain",
                "metadata": {"error": "download_failed", "path": path},
            }

        # Detect text vs binary — try UTF-8 first, fall back to latin-1
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = raw.decode("latin-1")
            except UnicodeDecodeError:
                content = raw.decode("utf-8", errors="replace")

        # Map file extension to content_type
        import os
        _, ext = os.path.splitext(path)
        ext = ext.lower()
        content_type = _ext_to_readable_type(ext)

        # Compute a content hash via the base-class helper
        content_hash = self.compute_hash(content)

        metadata: dict = {
            "path": path,
            "size_bytes": len(raw),
            "content_hash": content_hash,
            "encoding": "utf-8" if content == raw.decode("utf-8", errors="replace") else "latin-1",
        }

        self.logger.info("fetch_content downloaded %s (%d bytes)", path, len(raw))

        return {
            "content": content,
            "content_type": content_type,
            "metadata": metadata,
        }


# ── Self-registration ──
from src.sync import _register  # noqa: E402

_register("dropbox", DropboxConnector)
