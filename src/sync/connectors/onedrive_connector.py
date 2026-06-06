"""OneDrive sync connector — Microsoft OneDrive cloud storage via Microsoft Graph API.

Uses OAuth 2.0 with refresh token, delta queries for incremental sync,
and eTag-based change detection.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import SyncConnectionResult, SyncResource


# ── Microsoft Graph API constants ──

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
SCOPE_DEFAULT = "https://graph.microsoft.com/.default"
REQUEST_TIMEOUT = 30  # seconds


class OnedriveConnector(BaseSyncConnector):
    """Sync connector for Microsoft OneDrive via Microsoft Graph API.

    Credentials expected in self.config:
        - client_id: str       — Azure AD application client ID
        - client_secret: str   — Azure AD application client secret
        - refresh_token: str   — OAuth 2.0 refresh token
        - folder: str          — (optional) subfolder path relative to root,
                                  e.g. "/Documents/Notes"
    """

    connector_type: str = "onedrive"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.logger = logging.getLogger("sync.connector.onedrive")

        # OAuth credentials
        self.client_id: str = self.config.get("client_id", "")
        self.client_secret: str = self.config.get("client_secret", "")
        self.refresh_token: str = self.config.get("refresh_token", "")
        self.folder: str = self.config.get("folder", "").rstrip("/")

        # Cached access token and expiry
        self._access_token: str = ""
        self._token_expires_at: float = 0.0

        # Delta token for incremental sync (persisted per-connector in practice)
        self._delta_token: str = ""

    # ── Public API ──

    def test_connection(self) -> SyncConnectionResult:
        """Validate credentials by obtaining an access token and listing root folder."""
        if not self.client_id or not self.client_secret or not self.refresh_token:
            return SyncConnectionResult(
                success=False,
                message="Missing credentials: client_id, client_secret, and refresh_token are required",
                resources_count=0,
            )

        try:
            token = self._acquire_token()
            if not token:
                return SyncConnectionResult(
                    success=False,
                    message="Failed to acquire access token — check credentials",
                    resources_count=0,
                )

            # Try listing root (one page to confirm connectivity)
            url = self._build_list_url()
            resp = self._request("GET", url)
            if resp is None:
                return SyncConnectionResult(
                    success=False,
                    message="No response from Microsoft Graph API — network or permission issue",
                    resources_count=0,
                )

            if resp.status_code != 200:
                return SyncConnectionResult(
                    success=False,
                    message=f"Microsoft Graph API returned HTTP {resp.status_code}: {self._extract_error(resp)}",
                    resources_count=0,
                )

            data = resp.json()
            resources = data.get("value", [])
            count = len(resources)

            return SyncConnectionResult(
                success=True,
                message=f"Connected successfully. Found {count} item(s) in folder.",
                resources_count=count,
            )

        except requests.exceptions.Timeout:
            return SyncConnectionResult(
                success=False,
                message="Connection timed out while contacting Microsoft Graph API",
                resources_count=0,
            )
        except requests.exceptions.ConnectionError:
            return SyncConnectionResult(
                success=False,
                message="Network connection error — cannot reach Microsoft Graph API",
                resources_count=0,
            )
        except Exception as exc:
            self.logger.exception("test_connection failed")
            return SyncConnectionResult(
                success=False,
                message=f"Unexpected error: {exc}",
                resources_count=0,
            )

    def list_resources(self) -> list[SyncResource]:
        """List all files and folders in the configured OneDrive folder.

        Handles pagination through @odata.nextLink.
        """
        resources: list[SyncResource] = []

        try:
            items = self._paginate_list(self._build_list_url())
            for item in items:
                resource = self._item_to_resource(item)
                if resource is not None:
                    resources.append(resource)

        except Exception as exc:
            self.logger.exception("list_resources failed: %s", exc)

        return resources

    def fetch_changes(self, since: datetime | None) -> list[dict]:
        """Fetch changes using Microsoft Graph Delta Query.

        If *since* is None, returns all items (initial full sync).
        Otherwise uses delta token or filters by lastModifiedDateTime.

        Returns a list of raw change dicts with keys:
            resource_id, name, change_type, updated_at, e_tag, metadata
        """
        changes: list[dict] = []

        try:
            token = self._acquire_token()
            if not token:
                self.logger.error("Cannot fetch changes — no access token")
                return changes

            # Build delta URL — use delta token if available for true incremental
            delta_url = f"{self._build_drive_root()}/delta"
            if self._delta_token:
                delta_url += f"?token={self._delta_token}"

            items, new_delta_token = self._paginate_delta(delta_url)
            if new_delta_token:
                self._delta_token = new_delta_token

            for item in items:
                change = self._delta_item_to_change(item, since)
                if change is not None:
                    changes.append(change)

        except Exception as exc:
            self.logger.exception("fetch_changes failed: %s", exc)

        return changes

    def fetch_content(self, resource_id: str) -> dict:
        """Download the content of a OneDrive file by resource ID.

        Returns dict with keys: "content", "content_type", "metadata"
        """
        empty: dict = {"content": "", "content_type": "text/plain", "metadata": {}}

        try:
            token = self._acquire_token()
            if not token:
                return empty

            # First get item metadata for mime type and file info
            meta_url = f"{GRAPH_BASE}/me/drive/items/{resource_id}"
            meta_resp = self._request("GET", meta_url)
            if meta_resp is None or meta_resp.status_code != 200:
                self.logger.warning(
                    "Cannot fetch metadata for %s: HTTP %s",
                    resource_id,
                    meta_resp.status_code if meta_resp is not None else "None",
                )
                return empty

            meta = meta_resp.json()
            file_info = meta.get("file", {})
            mime_type = file_info.get("mimeType", "application/octet-stream")
            item_name = meta.get("name", resource_id)
            item_size = meta.get("size", 0)
            item_updated = meta.get("lastModifiedDateTime", "")

            # Determine content_type from mime for downstream processing
            content_type = self._mime_to_content_type(mime_type)

            # For folders, return a listing representation
            if meta.get("folder") is not None:
                children = self._paginate_list(
                    f"{GRAPH_BASE}/me/drive/items/{resource_id}/children"
                )
                content = self._format_folder_content(item_name, children)
                return {
                    "content": content,
                    "content_type": "text/plain",
                    "metadata": {
                        "name": item_name,
                        "resource_id": resource_id,
                        "is_folder": True,
                        "child_count": len(children),
                        "updated_at": item_updated,
                        "size_bytes": item_size,
                    },
                }

            # Download file content
            content_url = f"{GRAPH_BASE}/me/drive/items/{resource_id}/content"
            content_resp = self._request("GET", content_url)
            if content_resp is None or content_resp.status_code != 200:
                self.logger.warning(
                    "Cannot download content for %s: HTTP %s",
                    resource_id,
                    content_resp.status_code if content_resp is not None else "None",
                )
                return empty

            # Graph returns raw bytes; decode safely
            raw = content_resp.content
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                # Binary files — return placeholder with hex digest
                digest = self.compute_hash(raw.decode("latin-1", errors="replace"))
                content = f"[Binary file: {item_name}] sha256:{digest}"

            return {
                "content": content,
                "content_type": content_type,
                "metadata": {
                    "name": item_name,
                    "resource_id": resource_id,
                    "mime_type": mime_type,
                    "updated_at": item_updated,
                    "size_bytes": item_size,
                    "e_tag": meta.get("eTag", ""),
                    "web_url": meta.get("webUrl", ""),
                    "download_url": meta.get("@microsoft.graph.downloadUrl", ""),
                },
            }

        except requests.exceptions.Timeout:
            self.logger.error("Timeout fetching content for %s", resource_id)
            return empty
        except Exception as exc:
            self.logger.exception("fetch_content failed for %s: %s", resource_id, exc)
            return empty

    # ── Authentication ──

    def _acquire_token(self) -> str:
        """Obtain or refresh an OAuth 2.0 access token using the refresh token.

        Returns the access token string, or empty string on failure.
        """
        import time as _time

        # Return cached token if still valid (with 60s buffer)
        if self._access_token and _time.time() < self._token_expires_at - 60:
            return self._access_token

        payload: dict[str, str] = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
            "scope": SCOPE_DEFAULT,
        }

        try:
            resp = requests.post(AUTH_URL, data=payload, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                self.logger.error(
                    "Token acquisition failed: HTTP %s — %s",
                    resp.status_code,
                    resp.text[:300],
                )
                self._access_token = ""
                return ""

            data = resp.json()
            self._access_token = data.get("access_token", "")
            expires_in = int(data.get("expires_in", 3600))
            self._token_expires_at = _time.time() + expires_in

            # Update refresh token if a new one was returned
            new_refresh = data.get("refresh_token", "")
            if new_refresh and new_refresh != self.refresh_token:
                self.refresh_token = new_refresh
                self.config["refresh_token"] = new_refresh

            return self._access_token

        except requests.exceptions.Timeout:
            self.logger.error("Token acquisition timed out")
            self._access_token = ""
            return ""
        except Exception as exc:
            self.logger.exception("Token acquisition error: %s", exc)
            self._access_token = ""
            return ""

    # ── HTTP helpers ──

    def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response | None:
        """Send an authenticated HTTP request to Microsoft Graph.

        Returns the Response object on success, or None on non-retryable failure.
        Automatically retries once on 401 with a fresh token.
        """
        token = self._acquire_token()
        if not token:
            return None

        headers = kwargs.pop("headers", {})
        headers.setdefault("Authorization", f"Bearer {token}")
        headers.setdefault("Accept", "application/json")
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)

        resp = requests.request(method, url, headers=headers, **kwargs)

        # Retry once on 401 with fresh token
        if resp.status_code == 401:
            self.logger.debug("401 received — refreshing token and retrying")
            self._access_token = ""  # force refresh
            token = self._acquire_token()
            if not token:
                return resp  # return original 401 for caller to handle
            headers["Authorization"] = f"Bearer {token}"
            resp = requests.request(method, url, headers=headers, **kwargs)

        return resp

    # ── URL builders ──

    def _build_drive_root(self) -> str:
        """Build the root drive URL, respecting the configured folder."""
        if self.folder:
            return f"{GRAPH_BASE}/me/drive/root:{self.folder}"
        return f"{GRAPH_BASE}/me/drive/root"

    def _build_list_url(self) -> str:
        """Build the URL for listing children of the configured folder."""
        return f"{self._build_drive_root()}:/children"

    # ── Pagination ──

    def _paginate_list(self, start_url: str) -> list[dict]:
        """Iterate @odata.nextLink pages and return all items."""
        results: list[dict] = []
        url: str | None = start_url

        while url:
            resp = self._request("GET", url)
            if resp is None or resp.status_code != 200:
                self.logger.warning(
                    "Pagination stopped at %s: HTTP %s",
                    url,
                    resp.status_code if resp is not None else "None",
                )
                break

            data = resp.json()
            results.extend(data.get("value", []))
            url = data.get("@odata.nextLink")

        return results

    def _paginate_delta(self, start_url: str) -> tuple[list[dict], str]:
        """Iterate delta query pages. Returns (items, delta_token)."""
        results: list[dict] = []
        url: str | None = start_url
        delta_token: str = ""

        while url:
            resp = self._request("GET", url)
            if resp is None or resp.status_code != 200:
                self.logger.warning(
                    "Delta pagination stopped at %s: HTTP %s",
                    url,
                    resp.status_code if resp is not None else "None",
                )
                break

            data = resp.json()
            results.extend(data.get("value", []))

            # Check for delta token — presence of @odata.deltaLink means we are done
            dlink = data.get("@odata.deltaLink", "")
            if dlink:
                # Extract token from the deltaLink query string
                from urllib.parse import parse_qs, urlparse

                parsed = urlparse(dlink)
                qs = parse_qs(parsed.query)
                delta_token = qs.get("token", [""])[0]
                break

            url = data.get("@odata.nextLink")

        return results, delta_token

    # ── Mapping helpers ──

    def _item_to_resource(self, item: dict) -> SyncResource | None:
        """Convert a Microsoft Graph driveItem dict to a SyncResource."""
        rid = item.get("id", "")
        if not rid:
            return None

        name = item.get("name", rid)
        is_folder = item.get("folder") is not None
        resource_type = "folder" if is_folder else "document"

        # Map common extensions to more specific types
        if not is_folder:
            ext = (name.rsplit(".", 1)[-1].lower() if "." in name else "")
            resource_type = self._ext_to_resource_type(ext)

        updated_raw = item.get("lastModifiedDateTime", "")
        updated_at = None
        if updated_raw:
            try:
                # Graph returns ISO 8601 with possible 'Z' suffix
                updated_at = datetime.fromisoformat(
                    updated_raw.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        size = item.get("size", 0) or 0

        # Capture metadata useful for change detection and content fetching
        metadata: dict[str, Any] = {
            "e_tag": item.get("eTag", ""),
            "c_tag": item.get("cTag", ""),
            "web_url": item.get("webUrl", ""),
            "created_by": (
                item.get("createdBy", {}).get("user", {}).get("displayName", "")
            ),
            "last_modified_by": (
                item.get("lastModifiedBy", {}).get("user", {}).get("displayName", "")
            ),
            "mime_type": (item.get("file", {}) or {}).get("mimeType", ""),
        }

        return SyncResource(
            resource_id=rid,
            name=name,
            resource_type=resource_type,
            updated_at=updated_at,
            size_bytes=size,
            metadata=metadata,
        )

    def _delta_item_to_change(
        self, item: dict, since: datetime | None
    ) -> dict | None:
        """Convert a delta item to a change descriptor dict.

        Filters by *since* timestamp when no delta token was used (initial sync
        fallback). Delta queries with tokens handle this server-side.
        """
        rid = item.get("id", "")
        name = item.get("name", "")
        e_tag = item.get("eTag", "")

        updated_raw = item.get("lastModifiedDateTime", "")
        updated_at = None
        if updated_raw:
            try:
                updated_at = datetime.fromisoformat(
                    updated_raw.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        # Determine change type from delta flags
        deleted_info = item.get("deleted")
        if deleted_info is not None:
            change_type = "deleted"
        elif item.get("@microsoft.graph.downloadUrl") and not item.get(
            "lastModifiedDateTime"
        ):
            # Items that appear only via delta with no prior record
            change_type = "new"
        else:
            change_type = "updated"

        # Apply client-side time filter if no delta token (initial sync)
        if since is not None and updated_at is not None and updated_at < since:
            return None

        return {
            "resource_id": rid,
            "name": name,
            "change_type": change_type,
            "updated_at": updated_at,
            "e_tag": e_tag,
            "metadata": {
                "web_url": item.get("webUrl", ""),
                "size": item.get("size", 0),
                "deleted": deleted_info is not None,
            },
        }

    # ── Content helpers ──

    @staticmethod
    def _format_folder_content(folder_name: str, children: list[dict]) -> str:
        """Format a folder listing as readable text."""
        lines: list[str] = [f"Folder: {folder_name}", "=" * 40, ""]
        for child in children:
            name = child.get("name", "(unnamed)")
            is_folder = child.get("folder") is not None
            prefix = "[DIR]  " if is_folder else "[FILE] "
            size = child.get("size", 0)
            size_str = _human_size(size) if size else ""
            lines.append(f"{prefix}{name}  {size_str}")
        return "\n".join(lines)

    @staticmethod
    def _mime_to_content_type(mime: str) -> str:
        """Map MIME types to our simplified content_type labels."""
        if not mime:
            return "text/plain"
        mime_lower = mime.lower()
        if "text/plain" in mime_lower:
            return "text/plain"
        if "text/markdown" in mime_lower or "text/x-markdown" in mime_lower:
            return "text/markdown"
        if "text/html" in mime_lower:
            return "text/html"
        if "application/json" in mime_lower:
            return "application/json"
        if "text/csv" in mime_lower:
            return "text/csv"
        if any(
            t in mime_lower
            for t in (
                "application/pdf",
                "image/",
                "audio/",
                "video/",
                "application/zip",
                "application/octet-stream",
                "application/vnd.openxmlformats",
                "application/msword",
            )
        ):
            return "binary"
        return "text/plain"

    @staticmethod
    def _ext_to_resource_type(ext: str) -> str:
        """Map file extension to resource_type label."""
        ext_map = {
            "md": "document",
            "txt": "document",
            "pdf": "document",
            "doc": "document",
            "docx": "document",
            "xls": "spreadsheet",
            "xlsx": "spreadsheet",
            "csv": "spreadsheet",
            "ppt": "presentation",
            "pptx": "presentation",
            "jpg": "image",
            "jpeg": "image",
            "png": "image",
            "gif": "image",
            "svg": "image",
            "mp3": "audio",
            "wav": "audio",
            "mp4": "video",
            "mov": "video",
            "avi": "video",
            "zip": "archive",
            "rar": "archive",
            "7z": "archive",
            "json": "data",
            "xml": "data",
            "yaml": "data",
            "yml": "data",
            "html": "webpage",
            "htm": "webpage",
            "py": "code",
            "js": "code",
            "ts": "code",
            "java": "code",
            "cpp": "code",
            "c": "code",
            "go": "code",
            "rs": "code",
        }
        return ext_map.get(ext, "document")

    @staticmethod
    def _extract_error(resp: requests.Response) -> str:
        """Extract a human-readable error message from a Graph API error response."""
        try:
            body = resp.json()
            err = body.get("error", {})
            return err.get("message", resp.text[:200])
        except Exception:
            return resp.text[:200]


# ── Helpers ──


def _human_size(size_bytes: int) -> str:
    """Format byte count as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    for unit in ("KB", "MB", "GB", "TB"):
        size_bytes /= 1024.0
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
    return f"{size_bytes:.1f}PB"


# ── Register ──

from src.sync import _register  # noqa: E402

_register("onedrive", OnedriveConnector)
