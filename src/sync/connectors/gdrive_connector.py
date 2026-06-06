"""Google Drive sync connector.

Authenticates via OAuth 2.0 refresh token and exposes files in a
configured folder as SyncResource objects. Supports listing, change
detection via the Drive API changes endpoint + md5Checksum, and content
download (binary) / export (Google Docs).

API reference: https://developers.google.com/drive/api/reference/rest/v3
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import SyncConnectionResult, SyncResource

# ---------------------------------------------------------------------------
# Google API endpoints
# ---------------------------------------------------------------------------

_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"

# Fields requested by default when listing files
_LIST_FIELDS = (
    "nextPageToken,"
    "files(id,name,mimeType,modifiedTime,size,md5Checksum,"
    "trashed,parents,webViewLink)"
)

# MIME types we export as text instead of downloading binary
_GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
_GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
_GOOGLE_SLIDES_MIME = "application/vnd.google-apps.presentation"

_EXPORT_FORMATS: dict[str, str] = {
    _GOOGLE_DOC_MIME: "text/markdown",
    _GOOGLE_SHEET_MIME: "text/csv",
    _GOOGLE_SLIDES_MIME: "text/plain",
}

_REQUEST_TIMEOUT = 30  # seconds


class GdriveConnector(BaseSyncConnector):
    """Sync connector for Google Drive cloud storage.

    Credentials expected in *self.config*::

        {
            "client_id": "...",
            "client_secret": "...",
            "refresh_token": "...",
            "folder_id": "..."   # optional — root if omitted
        }
    """

    connector_type = "gdrive"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.logger = logging.getLogger("sync.connector.gdrive")
        self._access_token: str | None = None

    # ── helpers ────────────────────────────────────────────────────────

    def _get_access_token(self) -> str:
        """Exchange the refresh token for a short-lived access token.

        Caches the token in memory so repeated calls within the same
        connector lifetime only hit the OAuth endpoint once.
        """
        if self._access_token:
            return self._access_token

        payload = {
            "client_id": self.config.get("client_id", ""),
            "client_secret": self.config.get("client_secret", ""),
            "refresh_token": self.config.get("refresh_token", ""),
            "grant_type": "refresh_token",
        }

        try:
            resp = requests.post(
                _OAUTH_TOKEN_URL,
                data=payload,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data.get("access_token", "")
            if not self._access_token:
                raise ValueError("OAuth response missing access_token")
            return self._access_token
        except requests.RequestException as exc:
            self.logger.error("Failed to obtain access token: %s", exc)
            raise

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Accept": "application/json",
        }

    def _api_request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> requests.Response:
        """Wrapper around requests that injects auth headers and timeout."""
        url = f"{_DRIVE_API_BASE}/{path.lstrip('/')}"
        kwargs.setdefault("timeout", _REQUEST_TIMEOUT)
        kwargs.setdefault("headers", {}).update(self._auth_headers())
        return requests.request(method, url, **kwargs)

    def _resource_type_from_mime(self, mime_type: str) -> str:
        """Map a Drive MIME type to a SyncResource resource_type."""
        if mime_type == "application/vnd.google-apps.folder":
            return "folder"
        if mime_type.startswith("application/vnd.google-apps."):
            return "document"
        if mime_type.startswith("image/"):
            return "image"
        if mime_type.startswith("video/"):
            return "video"
        if mime_type.startswith("audio/"):
            return "audio"
        if mime_type in (
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ):
            return "document"
        if mime_type and "spreadsheet" in mime_type:
            return "spreadsheet"
        if mime_type and "presentation" in mime_type:
            return "presentation"
        return "file"

    def _file_to_resource(self, file: dict) -> SyncResource:
        """Convert a Drive API file dict into a SyncResource."""
        updated_raw = file.get("modifiedTime")
        updated_at: datetime | None = None
        if updated_raw:
            try:
                # Drive returns ISO-8601 with 'Z' suffix
                updated_at = datetime.fromisoformat(
                    updated_raw.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                updated_at = None

        size_raw = file.get("size")
        try:
            size_bytes = int(size_raw) if size_raw is not None else 0
        except (TypeError, ValueError):
            size_bytes = 0

        return SyncResource(
            resource_id=file.get("id", ""),
            name=file.get("name", "Untitled"),
            resource_type=self._resource_type_from_mime(
                file.get("mimeType", "")
            ),
            updated_at=updated_at,
            size_bytes=size_bytes,
            metadata={
                "mimeType": file.get("mimeType", ""),
                "md5Checksum": file.get("md5Checksum", ""),
                "webViewLink": file.get("webViewLink", ""),
                "trashed": file.get("trashed", False),
            },
        )

    # ── SyncConnector interface ────────────────────────────────────────

    def test_connection(self) -> SyncConnectionResult:
        """Validate credentials by obtaining a token and listing the folder.

        Returns
        -------
        SyncConnectionResult
            *success* is True when the API responds with 200 and we can
            enumerate at least the root of the configured folder.
        """
        try:
            # Step 1 — can we authenticate?
            self._get_access_token()

            # Step 2 — can we access the configured folder?
            folder_id = self.config.get("folder_id", "root")
            query = "trashed=false"
            if folder_id and folder_id != "root":
                query = f"'{folder_id}' in parents and trashed=false"

            resp = self._api_request(
                "GET",
                "files",
                params={
                    "q": query,
                    "pageSize": 1,
                    "fields": "files(id,name)",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            files = data.get("files", [])

            return SyncConnectionResult(
                success=True,
                message=(
                    f"Connected to Google Drive. "
                    f"Folder contains {len(files)} visible item(s) "
                    f"in the first page."
                ),
                resources_count=len(files),
            )
        except Exception as exc:
            self.logger.exception("Connection test failed")
            return SyncConnectionResult(
                success=False,
                message=str(exc),
                resources_count=0,
            )

    def list_resources(self) -> list[SyncResource]:
        """List all non-trashed files in the configured folder.

        Handles pagination so every file is returned.
        """
        folder_id = self.config.get("folder_id", "root")
        query = "trashed=false"
        if folder_id and folder_id != "root":
            query = f"'{folder_id}' in parents and trashed=false"

        resources: list[SyncResource] = []
        page_token: str | None = None

        try:
            while True:
                params: dict = {
                    "q": query,
                    "pageSize": 100,
                    "fields": _LIST_FIELDS,
                }
                if page_token:
                    params["pageToken"] = page_token

                resp = self._api_request("GET", "files", params=params)
                resp.raise_for_status()
                data = resp.json()

                for file in data.get("files", []):
                    resources.append(self._file_to_resource(file))

                page_token = data.get("nextPageToken")
                if not page_token:
                    break

            self.logger.info(
                "Listed %d resources from folder '%s'",
                len(resources),
                folder_id,
            )
            return resources
        except Exception as exc:
            self.logger.exception("list_resources failed: %s", exc)
            return []

    def fetch_changes(self, since: datetime | None) -> list:
        """Return resources changed since *since* (or all when *since* is None).

        Prefers the Drive Changes API for robust incremental sync; falls
        back to a full file listing filtered by ``modifiedTime`` for
        accounts where the Changes resource is not available (e.g. some
        service accounts without a full Drive license).
        """
        try:
            return self._fetch_changes_via_api(since)
        except Exception:
            self.logger.warning(
                "Changes API unavailable — falling back to file listing",
                exc_info=True,
            )
            try:
                return self._fetch_changes_via_files(since)
            except Exception:
                self.logger.exception("fetch_changes fallback also failed")
                return []

    # -- Changes API path -------------------------------------------------

    def _fetch_changes_via_api(self, since: datetime | None) -> list:
        """Use ``changes.list`` for true incremental sync."""
        results: list[SyncResource] = []
        page_token: str | None = None

        # The Changes API requires an initial page token.  If we don't have
        # one yet, start from the earliest change.
        if since is None:
            # Get the most recent starting page token
            resp = self._api_request(
                "GET",
                "changes/startPageToken",
                params={"fields": "startPageToken"},
            )
            resp.raise_for_status()
            page_token = resp.json().get("startPageToken", "")
        else:
            page_token = self.config.get("changes_page_token", "")

        if not page_token and since is not None:
            # No prior token — fall through to file listing
            raise RuntimeError("No saved page token for incremental sync")

        seen = 0
        while True:
            params: dict = {
                "pageToken": page_token,
                "pageSize": 100,
                "fields": (
                    "nextPageToken,newStartPageToken,"
                    "changes(fileId,file(name,mimeType,modifiedTime,"
                    "size,md5Checksum,trashed,parents,webViewLink))"
                ),
                "includeItemsFromAllDrives": "true",
                "supportsAllDrives": "true",
            }
            if since is not None:
                params["pageToken"] = page_token  # type: ignore[assignment]

            resp = self._api_request("GET", "changes", params=params)
            resp.raise_for_status()
            data = resp.json()

            for change in data.get("changes", []):
                file_data = change.get("file")
                if file_data:
                    # Skip trashed items unless the caller explicitly wants them
                    if file_data.get("trashed"):
                        continue

                    folder_id = self.config.get("folder_id", "root")
                    if folder_id and folder_id != "root":
                        parents = file_data.get("parents", [])
                        if folder_id not in parents:
                            continue

                    # Apply since-filter client-side because the Changes
                    # API does not natively filter by modifiedTime.
                    updated_raw = file_data.get("modifiedTime", "")
                    if since and updated_raw:
                        try:
                            dt = datetime.fromisoformat(
                                updated_raw.replace("Z", "+00:00")
                            )
                            if dt < since:
                                continue
                        except (ValueError, TypeError):
                            pass

                    results.append(self._file_to_resource(file_data))

            # Save the new start page token for the next call
            new_token = data.get("newStartPageToken")
            if new_token:
                self.config["changes_page_token"] = new_token

            page_token = data.get("nextPageToken")
            if not page_token:
                break
            seen += len(data.get("changes", []))
            if seen > 10000:  # safety valve
                self.logger.warning("Changes pagination cutoff at 10k items")
                break

        self.logger.info("fetch_changes (API) returned %d items", len(results))
        return results

    # -- File listing fallback --------------------------------------------

    def _fetch_changes_via_files(self, since: datetime | None) -> list:
        """List all files and filter client-side by modifiedTime."""
        all_resources = self.list_resources()
        if since is None:
            return all_resources

        # Ensure *since* is timezone-aware for safe comparison
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)

        filtered: list[SyncResource] = []
        for r in all_resources:
            if r.updated_at is None:
                filtered.append(r)  # include items with unknown date
                continue
            if r.updated_at.tzinfo is None:
                r_aware = r.updated_at.replace(tzinfo=timezone.utc)
            else:
                r_aware = r.updated_at
            if r_aware >= since:
                filtered.append(r)

        self.logger.info(
            "fetch_changes (files fallback) returned %d items", len(filtered)
        )
        return filtered

    # ── fetch_content ───────────────────────────────────────────────────

    def fetch_content(self, resource_id: str) -> dict:
        """Download or export the content of a single Drive file.

        Returns
        -------
        dict
            ``{"content": str, "content_type": str, "metadata": dict}``
        """
        try:
            # First, get metadata to determine MIME type
            meta = self._api_request(
                "GET",
                f"files/{resource_id}",
                params={
                    "fields": "id,name,mimeType,md5Checksum,size,modifiedTime,webViewLink"
                },
            )
            meta.raise_for_status()
            file_info = meta.json()
            mime_type = file_info.get("mimeType", "application/octet-stream")

            # Google Docs / Sheets / Slides must be *exported*, not downloaded
            if mime_type in _EXPORT_FORMATS:
                export_mime = _EXPORT_FORMATS[mime_type]
                content_resp = self._api_request(
                    "GET",
                    f"files/{resource_id}/export",
                    params={"mimeType": export_mime},
                    headers={  # override Accept for binary download
                        **self._auth_headers(),
                        "Accept": export_mime,
                    },
                )
                content_resp.raise_for_status()
                content = content_resp.text
            else:
                # Binary / non-Google files: download media
                content_resp = self._api_request(
                    "GET",
                    f"files/{resource_id}",
                    params={"alt": "media"},
                    headers={
                        **self._auth_headers(),
                        "Accept": "*/*",
                    },
                )
                content_resp.raise_for_status()

                # Try to decode as UTF-8 text; fall back to a placeholder
                # for truly binary files.
                try:
                    content = content_resp.text
                except UnicodeDecodeError:
                    content = (
                        f"[Binary file: {file_info.get('name', resource_id)} "
                        f"({file_info.get('size', '?')} bytes)]"
                    )

            # Determine a user-friendly content_type label
            if mime_type in _EXPORT_FORMATS:
                content_type = "text/markdown" if mime_type == _GOOGLE_DOC_MIME else "text/plain"
            elif mime_type.startswith("text/"):
                content_type = mime_type
            elif mime_type == "application/json":
                content_type = "application/json"
            else:
                content_type = mime_type

            return {
                "content": content,
                "content_type": content_type,
                "metadata": {
                    "resource_id": file_info.get("id", resource_id),
                    "name": file_info.get("name", ""),
                    "mimeType": mime_type,
                    "md5Checksum": file_info.get("md5Checksum", ""),
                    "size": file_info.get("size", "0"),
                    "modifiedTime": file_info.get("modifiedTime", ""),
                    "webViewLink": file_info.get("webViewLink", ""),
                    "content_hash": self.compute_hash(content),
                },
            }
        except Exception as exc:
            self.logger.exception(
                "fetch_content failed for resource '%s': %s", resource_id, exc
            )
            return {
                "content": f"[Error fetching content: {exc}]",
                "content_type": "text/plain",
                "metadata": {
                    "resource_id": resource_id,
                    "error": str(exc),
                },
            }


# ── Auto-registration ───────────────────────────────────────────────────

from src.sync import _register  # noqa: E402

_register("gdrive", GdriveConnector)
