"""Yuque (语雀) knowledge base connector.

Fetches documents from a Yuque repo via the v2 REST API:
  https://www.yuque.com/developer/api

Authentication: personal token passed as X-Auth-Token header.
Config keys:
  - token      (str)  — Yuque personal access token
  - namespace  (str)  — repo namespace, e.g. "myuser/myrepo" or "myteam/myrepo"
  - base_url   (str)  — optional, defaults to "https://www.yuque.com/api/v2"
  - timeout    (int)  — optional, request timeout in seconds, defaults to 30
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import SyncConnectionResult, SyncResource


class YuqueConnector(BaseSyncConnector):
    """Synchronise documents from a Yuque (语雀) knowledge base repo."""

    connector_type: str = "yuque"

    DEFAULT_BASE_URL = "https://www.yuque.com/api/v2"
    DEFAULT_TIMEOUT = 30
    PAGE_SIZE = 100  # Yuque caps at 100 per page

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.logger = logging.getLogger("sync.connector.yuque")
        self._session = self._build_session()

    # ── helpers ──────────────────────────────────────────────────────────

    @property
    def _token(self) -> str:
        return self.config.get("token", "")

    @property
    def _namespace(self) -> str:
        return self.config.get("namespace", "")

    @property
    def _base_url(self) -> str:
        return self.config.get("base_url", self.DEFAULT_BASE_URL).rstrip("/")

    @property
    def _timeout(self) -> int:
        return int(self.config.get("timeout", self.DEFAULT_TIMEOUT))

    def _headers(self) -> dict[str, str]:
        return {
            "X-Auth-Token": self._token,
            "User-Agent": "CognitiveOS-Sync/1.0",
            "Accept": "application/json",
        }

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=2,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _get(self, path: str, params: dict | None = None) -> dict:
        """Perform a GET request to the Yuque API and return parsed JSON."""
        url = f"{self._base_url}{path}"
        self.logger.debug("GET %s params=%s", url, params)
        try:
            resp = self._session.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            self.logger.error("Timeout requesting %s", url)
            raise
        except requests.exceptions.ConnectionError:
            self.logger.error("Connection error requesting %s", url)
            raise
        except requests.exceptions.HTTPError as exc:
            self.logger.error(
                "HTTP %s requesting %s: %s",
                exc.response.status_code if exc.response is not None else "?",
                url,
                exc,
            )
            raise
        except Exception:
            self.logger.exception("Unexpected error requesting %s", url)
            raise

    def _paginate(self, path: str, params: dict | None = None) -> list[dict]:
        """Fetch all pages for a paginated list endpoint.

        Yuque returns: {"data": [...], "total": N, "offset": 0, "limit": 100}
        """
        base_params = (params or {}).copy()
        base_params.setdefault("limit", self.PAGE_SIZE)
        base_params.setdefault("offset", 0)

        all_items: list[dict] = []
        total: int | None = None

        while True:
            body = self._get(path, params=base_params)
            page_data = body.get("data", [])
            if isinstance(page_data, list):
                all_items.extend(page_data)
                total = body.get("total", len(page_data))
            else:
                # Some endpoints return a single object under "data"
                return [page_data] if page_data else []

            # Break when we have fetched everything
            if base_params["offset"] + base_params["limit"] >= (total or 0):
                break
            base_params["offset"] += base_params["limit"]

        return all_items

    def _parse_dt(self, value: str | None) -> datetime | None:
        """Parse a Yuque ISO-8601 timestamp into a timezone-aware datetime."""
        if not value:
            return None
        try:
            # Python 3.7+ can handle the trailing Z
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            self.logger.warning("Could not parse datetime: %s", value)
            return None

    def _document_to_resource(self, doc: dict) -> SyncResource:
        """Map a single Yuque doc dict to a SyncResource."""
        return SyncResource(
            resource_id=str(doc.get("id", "")),
            name=doc.get("title", "Untitled"),
            resource_type="document",
            updated_at=self._parse_dt(doc.get("content_updated_at") or doc.get("updated_at")),
            size_bytes=doc.get("word_count", 0) or 0,
            metadata={
                "slug": doc.get("slug", ""),
                "description": doc.get("description", ""),
                "format": doc.get("format", "markdown"),
                "user_id": doc.get("user_id"),
                "created_at": doc.get("created_at"),
                "yuque_url": f"https://www.yuque.com/{self._namespace}/{doc.get('slug', '')}",
            },
        )

    # ── SyncConnector interface ──────────────────────────────────────────

    def test_connection(self) -> SyncConnectionResult:
        """Validate the token and namespace by listing the user + repo.

        Tries:
          1. GET /user  (verifies the token)
          2. GET /repos/{namespace}  (verifies the repo exists)
        Returns SyncConnectionResult with resource count on success.
        """
        if not self._token:
            return SyncConnectionResult(
                success=False,
                message="Missing required config key: token",
                resources_count=0,
            )
        if not self._namespace:
            return SyncConnectionResult(
                success=False,
                message="Missing required config key: namespace (e.g. 'myuser/myrepo')",
                resources_count=0,
            )

        try:
            # Verify token by fetching the authenticated user
            user_body = self._get("/user")
            user_data = user_body.get("data", {})
            user_name = user_data.get("name") or user_data.get("login", "unknown")
            self.logger.info("Authenticated as Yuque user: %s", user_name)
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status in (401, 403):
                return SyncConnectionResult(
                    success=False,
                    message="Authentication failed — token is invalid or expired",
                    resources_count=0,
                )
            return SyncConnectionResult(
                success=False,
                message=f"Yuque API error ({status}): {exc}",
                resources_count=0,
            )
        except requests.exceptions.Timeout:
            return SyncConnectionResult(
                success=False,
                message="Connection timed out while reaching Yuque API",
                resources_count=0,
            )
        except requests.exceptions.ConnectionError:
            return SyncConnectionResult(
                success=False,
                message="Could not connect to Yuque API — check network / DNS",
                resources_count=0,
            )
        except Exception as exc:
            self.logger.exception("test_connection failed")
            return SyncConnectionResult(
                success=False,
                message=f"Unexpected error: {exc}",
                resources_count=0,
            )

        # Verify the repo / namespace exists
        try:
            repo_body = self._get(f"/repos/{self._namespace}")
            repo_data = repo_body.get("data", {})
            repo_name = repo_data.get("name", self._namespace)
            docs_count = repo_data.get("docs_count", 0) or 0
            self.logger.info("Found Yuque repo '%s' with %s docs", repo_name, docs_count)
            return SyncConnectionResult(
                success=True,
                message=f"Connected to Yuque repo '{repo_name}' — {docs_count} documents available",
                resources_count=docs_count,
            )
        except Exception as exc:
            return SyncConnectionResult(
                success=False,
                message=f"Token is valid but could not access repo '{self._namespace}': {exc}",
                resources_count=0,
            )

    def list_resources(self) -> list[SyncResource]:
        """List all documents in the configured Yuque repo.

        Uses the paginated /repos/{namespace}/docs endpoint.
        Returns an empty list on error (errors are logged).
        """
        if not self._namespace:
            self.logger.error("Cannot list resources: no namespace configured")
            return []

        try:
            raw_docs = self._paginate(f"/repos/{self._namespace}/docs")
        except Exception:
            self.logger.exception("Failed to list documents for repo '%s'", self._namespace)
            return []

        resources = [self._document_to_resource(d) for d in raw_docs]
        self.logger.info(
            "Listed %d resources from Yuque repo '%s'", len(resources), self._namespace
        )
        return resources

    def fetch_changes(self, since: datetime | None) -> list:
        """Return documents changed since the given timestamp.

        Calls list_resources() and filters locally on updated_at because
        Yuque's /repos/{namespace}/docs endpoint does not have a since
        query parameter. An optional ``since_ts`` is set in each item's
        metadata so the pipeline can correlate timestamps.

        When *since* is None all resources are returned.
        """
        resources = self.list_resources()

        if since is None:
            self.logger.debug("fetch_changes: no since filter — returning all %d docs", len(resources))
            return [self._resource_to_change_dict(r) for r in resources]

        # Ensure comparison is timezone-aware
        since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)

        changed = []
        for r in resources:
            if r.updated_at is None:
                # Never been updated — include it (treat as new)
                changed.append(self._resource_to_change_dict(r))
                continue
            r_utc = r.updated_at if r.updated_at.tzinfo else r.updated_at.replace(tzinfo=timezone.utc)
            if r_utc >= since_utc:
                changed.append(self._resource_to_change_dict(r))

        self.logger.info(
            "fetch_changes: %d of %d docs changed since %s",
            len(changed), len(resources), since_utc.isoformat(),
        )
        return changed

    def fetch_content(self, resource_id: str) -> dict:
        """Fetch the full body of a single Yuque document.

        GET /repos/{namespace}/docs/{id}  — returns {"data": {..., "body": "..."}}

        Returns:
            {"content": str, "content_type": str, "metadata": dict}
            On failure returns the same shape with empty content and an error in metadata.
        """
        try:
            body = self._get(f"/repos/{self._namespace}/docs/{resource_id}")
        except Exception:
            self.logger.exception("Failed to fetch document %s", resource_id)
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"resource_id": resource_id, "error": "fetch_failed"},
            }

        doc = body.get("data", {})
        if not doc:
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"resource_id": resource_id, "error": "no_data"},
            }

        # Yuque returns different body fields depending on format:
        #   "lake" format → body_lake (JSON structured), body_html (HTML)
        #   "markdown" format → body (markdown string)
        doc_format = doc.get("format", "markdown")
        if doc_format == "lake":
            content = doc.get("body_lake", "") or doc.get("body_html", "") or doc.get("body", "")
            content_type = "html"
        elif doc_format == "html":
            content = doc.get("body_html", "") or doc.get("body", "")
            content_type = "html"
        else:
            content = doc.get("body", "") or doc.get("body_html", "")
            content_type = "markdown"

        content = content if isinstance(content, str) else str(content)

        return {
            "content": content,
            "content_type": content_type,
            "metadata": {
                "resource_id": resource_id,
                "title": doc.get("title", ""),
                "slug": doc.get("slug", ""),
                "format": doc_format,
                "updated_at": doc.get("content_updated_at") or doc.get("updated_at"),
                "created_at": doc.get("created_at"),
                "description": doc.get("description", ""),
                "yuque_url": f"https://www.yuque.com/{self._namespace}/{doc.get('slug', '')}",
                "hash": self.compute_hash(content),
            },
        }

    def _resource_to_change_dict(self, r: SyncResource) -> dict:
        """Convert a SyncResource into a lightweight change descriptor dict."""
        return {
            "resource_id": r.resource_id,
            "name": r.name,
            "resource_type": r.resource_type,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "size_bytes": r.size_bytes,
            "metadata": r.metadata,
        }


# ── Auto-registration ────────────────────────────────────────────────────

from src.sync import _register  # noqa: E402

_register("yuque", YuqueConnector)
