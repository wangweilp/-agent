"""Notion connector — sync Notion pages and databases via the Notion API.

Endpoints used:
  - GET  /v1/users/me              → test_connection
  - POST /v1/search                → list_resources / fetch_changes
  - GET  /v1/pages/{id}            → fetch_content (properties)
  - GET  /v1/blocks/{id}/children  → fetch_content (body)
  - POST /v1/databases/{id}/query  → list_resources (database rows)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import SyncConnectionResult, SyncResource

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
DEFAULT_TIMEOUT = 30  # seconds


def _parse_iso(s: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string to a timezone-aware datetime."""
    if not s:
        return None
    try:
        # Notion returns timestamps like "2024-01-15T10:30:00.000Z"
        s_clean = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


class NotionConnector(BaseSyncConnector):
    """Sync connector for Notion pages and databases."""

    connector_type: str = "notion"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.logger = logging.getLogger("sync.connector.notion")
        self._session = requests.Session()

    # ── helpers ──────────────────────────────────────────────────────────

    @property
    def _api_key(self) -> str:
        return self.config.get("api_key", "") or self.config.get("credentials", {}).get("api_key", "")

    @property
    def _database_id(self) -> str:
        return self.config.get("database_id", "") or self.config.get("credentials", {}).get("database_id", "")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> requests.Response:
        url = f"{NOTION_API_BASE}{path}"
        return self._session.get(url, headers=self._headers(), params=params, timeout=DEFAULT_TIMEOUT)

    def _post(self, path: str, body: dict | None = None) -> requests.Response:
        url = f"{NOTION_API_BASE}{path}"
        return self._session.post(url, headers=self._headers(), json=body or {}, timeout=DEFAULT_TIMEOUT)

    @staticmethod
    def _extract_title(properties: dict) -> str:
        """Pull a human-readable title from a Notion page properties dict."""
        for prop in properties.values():
            if not isinstance(prop, dict):
                continue
            prop_type = prop.get("type", "")
            if prop_type == "title":
                title_parts = prop.get("title", [])
                return "".join(t.get("plain_text", "") for t in title_parts)
        # fallback: try any rich_text field
        for prop in properties.values():
            if isinstance(prop, dict) and prop.get("type") == "rich_text":
                parts = prop.get("rich_text", [])
                return "".join(t.get("plain_text", "") for t in parts)
        return "Untitled"

    @staticmethod
    def _page_to_resource(page: dict) -> SyncResource:
        resource_id = page.get("id", "")
        props = page.get("properties", {})
        name = NotionConnector._extract_title(props)
        updated_at = _parse_iso(page.get("last_edited_time"))
        url = page.get("url", "")
        return SyncResource(
            resource_id=resource_id,
            name=name,
            resource_type="page",
            updated_at=updated_at,
            size_bytes=0,
            metadata={
                "url": url,
                "created_time": page.get("created_time", ""),
                "archived": page.get("archived", False),
                "object": page.get("object", ""),
            },
        )

    @staticmethod
    def _database_row_to_resource(row: dict, database_id: str) -> SyncResource:
        resource_id = row.get("id", "")
        props = row.get("properties", {})
        name = NotionConnector._extract_title(props)
        updated_at = _parse_iso(row.get("last_edited_time"))
        url = row.get("url", "")
        return SyncResource(
            resource_id=resource_id,
            name=name,
            resource_type="database_row",
            updated_at=updated_at,
            size_bytes=0,
            metadata={
                "url": url,
                "database_id": database_id,
                "created_time": row.get("created_time", ""),
                "archived": row.get("archived", False),
            },
        )

    def _blocks_to_markdown(self, blocks: list[dict]) -> str:
        """Convert a list of Notion block objects to a Markdown string."""
        lines: list[str] = []
        for block in blocks:
            line = self._block_to_text(block)
            if line:
                lines.append(line)
        return "\n\n".join(lines)

    def _block_to_text(self, block: dict) -> str:
        """Convert a single Notion block to a text line."""
        block_type = block.get("type", "")
        block_content = block.get(block_type, {})

        if block_type == "paragraph":
            text = self._rich_text_to_str(block_content.get("rich_text", []))
            return text if text else ""

        elif block_type in ("heading_1", "heading_2", "heading_3"):
            level = int(block_type[-1])
            prefix = "#" * level + " "
            text = self._rich_text_to_str(block_content.get("rich_text", []))
            return f"{prefix}{text}" if text else ""

        elif block_type == "bulleted_list_item":
            text = self._rich_text_to_str(block_content.get("rich_text", []))
            return f"- {text}" if text else ""

        elif block_type == "numbered_list_item":
            text = self._rich_text_to_str(block_content.get("rich_text", []))
            return f"1. {text}" if text else ""

        elif block_type == "to_do":
            checked = block_content.get("checked", False)
            marker = "[x]" if checked else "[ ]"
            text = self._rich_text_to_str(block_content.get("rich_text", []))
            return f"- {marker} {text}" if text else ""

        elif block_type == "toggle":
            text = self._rich_text_to_str(block_content.get("rich_text", []))
            return f"> {text}" if text else ""

        elif block_type == "quote":
            text = self._rich_text_to_str(block_content.get("rich_text", []))
            return f"> {text}" if text else ""

        elif block_type == "callout":
            icon = block_content.get("icon", {}).get("emoji", "")
            text = self._rich_text_to_str(block_content.get("rich_text", []))
            prefix = f"{icon} " if icon else ""
            return f"> {prefix}{text}" if text else ""

        elif block_type == "code":
            language = block_content.get("language", "")
            text = self._rich_text_to_str(block_content.get("rich_text", []))
            return f"```{language}\n{text}\n```" if text else ""

        elif block_type == "divider":
            return "---"

        elif block_type == "image":
            caption = self._rich_text_to_str(block_content.get("caption", []))
            url = ""
            file_info = block_content.get("file") or block_content.get("external", {})
            url = file_info.get("url", "")
            if url:
                return f"![{caption}]({url})" if caption else f"![]({url})"
            return ""

        elif block_type in ("bookmark", "link_preview"):
            url = block_content.get("url", "")
            return url if url else ""

        elif block_type == "child_page":
            title = block_content.get("title", "Untitled")
            return f"[Page: {title}]"

        elif block_type == "child_database":
            title = block_content.get("title", "Untitled Database")
            return f"[Database: {title}]"

        else:
            # unsupported block types — return empty
            return ""

    @staticmethod
    def _rich_text_to_str(rich_text: list[dict]) -> str:
        """Concatenate a Notion rich_text array into a plain string."""
        return "".join(t.get("plain_text", "") for t in rich_text)

    def _fetch_all_blocks(self, block_id: str) -> list[dict]:
        """Recursively fetch all block children for a block/page."""
        all_blocks: list[dict] = []
        cursor: str | None = None

        while True:
            body: dict[str, Any] = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            try:
                resp = self._get(f"/blocks/{block_id}/children")
                # The Notion API doesn't support query params on GET for blocks,
                # so we use paginated GET. Actually, let me re-check...
                # The official API uses GET with query params for pagination.
                # We'll handle it via params.
                resp = self._session.get(
                    f"{NOTION_API_BASE}/blocks/{block_id}/children",
                    headers=self._headers(),
                    params={"page_size": 100, **({"start_cursor": cursor} if cursor else {})},
                    timeout=DEFAULT_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as e:
                self.logger.error("Failed to fetch blocks for %s: %s", block_id, e)
                break

            all_blocks.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        return all_blocks

    # ── connector interface ──────────────────────────────────────────────

    def test_connection(self) -> SyncConnectionResult:
        """Verify the API key by calling /v1/users/me."""
        if not self._api_key:
            return SyncConnectionResult(
                success=False,
                message="Missing Notion API key. Set api_key in config or credentials.",
                resources_count=0,
            )

        try:
            resp = self._get("/users/me")
            if resp.status_code == 401:
                return SyncConnectionResult(
                    success=False,
                    message="Invalid Notion API key (HTTP 401).",
                    resources_count=0,
                )
            resp.raise_for_status()
            user = resp.json()
            user_name = user.get("name") or user.get("bot", {}).get("owner", {}).get("user", {}).get("name", "Unknown")
            return SyncConnectionResult(
                success=True,
                message=f"Connected to Notion as '{user_name}'.",
                resources_count=0,
            )
        except requests.ConnectionError:
            return SyncConnectionResult(
                success=False,
                message="Cannot reach Notion API — network error.",
                resources_count=0,
            )
        except requests.Timeout:
            return SyncConnectionResult(
                success=False,
                message="Notion API request timed out.",
                resources_count=0,
            )
        except requests.RequestException as e:
            self.logger.exception("test_connection failed")
            return SyncConnectionResult(
                success=False,
                message=f"Notion API error: {e}",
                resources_count=0,
            )

    def list_resources(self) -> list[SyncResource]:
        """List all searchable Notion pages and optionally database rows."""
        resources: list[SyncResource] = []

        if not self._api_key:
            self.logger.warning("No Notion API key configured; returning empty list.")
            return resources

        # 1. Search for all pages the integration can access
        try:
            cursor: str | None = None
            while True:
                body: dict[str, Any] = {
                    "filter": {"property": "object", "value": "page"},
                    "page_size": 100,
                }
                if cursor:
                    body["start_cursor"] = cursor
                resp = self._post("/search", body)
                resp.raise_for_status()
                data = resp.json()
                for page in data.get("results", []):
                    resources.append(self._page_to_resource(page))
                if not data.get("has_more"):
                    break
                cursor = data.get("next_cursor")
        except requests.RequestException as e:
            self.logger.error("Failed to list Notion pages: %s", e)

        # 2. If a database_id is configured, also list its rows
        db_id = self._database_id
        if db_id:
            try:
                cursor: str | None = None
                while True:
                    body: dict[str, Any] = {"page_size": 100}
                    if cursor:
                        body["start_cursor"] = cursor
                    resp = self._post(f"/databases/{db_id}/query", body)
                    resp.raise_for_status()
                    data = resp.json()
                    for row in data.get("results", []):
                        resources.append(self._database_row_to_resource(row, db_id))
                    if not data.get("has_more"):
                        break
                    cursor = data.get("next_cursor")
            except requests.RequestException as e:
                self.logger.error("Failed to query Notion database %s: %s", db_id, e)

        return resources

    def fetch_changes(self, since: datetime | None) -> list:
        """Return resources changed since the given timestamp.

        Uses the Notion search API filtered by last_edited_time.
        When `since` is None, returns all pages (same as list_resources).
        """
        changes: list[dict] = []

        if not self._api_key:
            self.logger.warning("No Notion API key configured; returning empty change list.")
            return changes

        try:
            cursor: str | None = None
            while True:
                body: dict[str, Any] = {
                    "filter": {"property": "object", "value": "page"},
                    "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                    "page_size": 100,
                }
                if cursor:
                    body["start_cursor"] = cursor
                resp = self._post("/search", body)
                resp.raise_for_status()
                data = resp.json()

                for page in data.get("results", []):
                    last_edited = _parse_iso(page.get("last_edited_time", ""))
                    if since is not None and last_edited and last_edited <= since:
                        # results are sorted desc, so we can stop early
                        return changes
                    resource = self._page_to_resource(page)
                    changes.append({
                        "resource_id": resource.resource_id,
                        "name": resource.name,
                        "resource_type": resource.resource_type,
                        "updated_at": resource.updated_at.isoformat() if resource.updated_at else None,
                        "metadata": resource.metadata,
                        "raw": page,
                    })

                if not data.get("has_more"):
                    break
                cursor = data.get("next_cursor")
        except requests.RequestException as e:
            self.logger.error("Failed to fetch Notion changes: %s", e)

        return changes

    def fetch_content(self, resource_id: str) -> dict:
        """Fetch full content for a single Notion page.

        Returns:
            {"content": str, "content_type": str, "metadata": dict}

        Fetches page properties (title, etc.) and all child blocks,
        then converts the blocks to a Markdown string.
        """
        if not self._api_key:
            return {"content": "", "content_type": "text", "metadata": {}}

        metadata: dict[str, Any] = {}
        content_parts: list[str] = []

        try:
            # 1. Fetch page properties
            page_resp = self._get(f"/pages/{resource_id}")
            page_resp.raise_for_status()
            page = page_resp.json()

            title = self._extract_title(page.get("properties", {}))
            if title:
                content_parts.append(f"# {title}\n")

            metadata = {
                "title": title,
                "url": page.get("url", ""),
                "created_time": page.get("created_time", ""),
                "last_edited_time": page.get("last_edited_time", ""),
                "archived": page.get("archived", False),
                "properties": {},
            }

            # Extract structured properties
            for prop_name, prop_value in page.get("properties", {}).items():
                if not isinstance(prop_value, dict):
                    continue
                prop_type = prop_value.get("type", "")
                extracted = self._extract_property_value(prop_value, prop_type)
                if extracted is not None:
                    metadata["properties"][prop_name] = extracted
                    if prop_type not in ("title",):
                        content_parts.append(f"**{prop_name}**: {extracted}\n")

            # 2. Fetch child blocks
            blocks = self._fetch_all_blocks(resource_id)
            if blocks:
                md = self._blocks_to_markdown(blocks)
                if md:
                    content_parts.append(md)

            content = "\n".join(content_parts).strip()
            content_type = "markdown"

            return {
                "content": content,
                "content_type": content_type,
                "metadata": metadata,
            }
        except requests.RequestException as e:
            self.logger.error("Failed to fetch content for %s: %s", resource_id, e)
            return {"content": "", "content_type": "text", "metadata": {"error": str(e)}}

    def _extract_property_value(self, prop: dict, prop_type: str) -> str | None:
        """Extract a human-readable value from a Notion property object."""
        if prop_type == "title":
            return self._rich_text_to_str(prop.get("title", []))
        elif prop_type == "rich_text":
            return self._rich_text_to_str(prop.get("rich_text", []))
        elif prop_type == "number":
            num = prop.get("number")
            return str(num) if num is not None else None
        elif prop_type == "select":
            sel = prop.get("select")
            return sel.get("name", "") if sel else None
        elif prop_type == "multi_select":
            items = prop.get("multi_select", [])
            return ", ".join(item.get("name", "") for item in items) if items else None
        elif prop_type == "date":
            d = prop.get("date")
            return d.get("start", "") if d else None
        elif prop_type == "checkbox":
            return "Yes" if prop.get("checkbox") else "No"
        elif prop_type == "url":
            return prop.get("url", "") or None
        elif prop_type == "email":
            return prop.get("email", "") or None
        elif prop_type == "phone_number":
            return prop.get("phone_number", "") or None
        elif prop_type == "formula":
            formula = prop.get("formula", {})
            ftype = formula.get("type", "")
            return str(formula.get(ftype, "")) if ftype else None
        elif prop_type == "relation":
            rels = prop.get("relation", [])
            return ", ".join(r.get("id", "") for r in rels) if rels else None
        elif prop_type == "rollup":
            return str(prop.get("rollup", {}))
        elif prop_type == "status":
            s = prop.get("status")
            return s.get("name", "") if s else None
        elif prop_type in ("people", "created_by", "last_edited_by"):
            people = prop.get(prop_type, [])
            if isinstance(people, dict):
                people = [people]
            if isinstance(people, list):
                return ", ".join(p.get("name", p.get("id", "")) for p in people)
            return None
        elif prop_type in ("files",):
            files = prop.get("files", [])
            return ", ".join(f.get("name", f.get("file", {}).get("url", "")) for f in files) if files else None
        else:
            return None


# ── Auto-register ────────────────────────────────────────────────────────────

from src.sync import _register  # noqa: E402

_register("notion", NotionConnector)
