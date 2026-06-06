"""Feishu/Lark sync connector — sync documents from Feishu Wiki Space via Open API.

Uses Feishu Open API:
  - Tenant access token for authentication
  - Wiki Space API to list documents (nodes)
  - Docx API to fetch document content and raw text
  - Drive API as fallback when space_id is not configured

Credentials (from self.config):
  - app_id: Feishu app ID
  - app_secret: Feishu app secret
  - space_id: (optional) Wiki space ID to list documents from
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import SyncConnectionResult, SyncResource


class FeishuConnector(BaseSyncConnector):
    """Sync documents from Feishu/Lark Wiki Space via Open API.

    Authenticates using tenant access token obtained from app_id + app_secret.
    Lists documents from a Wiki space (or drive root) and fetches content
    as markdown text.
    """

    connector_type = "feishu"

    BASE_URL = "https://open.feishu.cn/open-apis"
    AUTH_URL = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    WIKI_NODES_URL = "https://open.feishu.cn/open-apis/wiki/v2/spaces/{space_id}/nodes"
    DRIVE_FILES_URL = f"{BASE_URL}/drive/v1/files"
    DOCX_RAW_URL = f"{BASE_URL}/docx/v1/documents/{{document_id}}/raw_content"
    DOCX_BLOCKS_URL = f"{BASE_URL}/docx/v1/documents/{{document_id}}/blocks"
    DOCX_META_URL = f"{BASE_URL}/docx/v1/documents/{{document_id}}"
    PAGE_SIZE = 100

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._access_token: str | None = None
        self._token_expiry: float = 0.0

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _get_access_token(self) -> str | None:
        """Obtain a tenant access token, caching until expiry."""
        now = time.time()
        if self._access_token and now < self._token_expiry - 60:
            return self._access_token

        app_id = self.config.get("app_id", "")
        app_secret = self.config.get("app_secret", "")

        if not app_id or not app_secret:
            self.logger.error("Feishu connector requires app_id and app_secret in config")
            return None

        try:
            resp = requests.post(
                self.AUTH_URL,
                json={"app_id": app_id, "app_secret": app_secret},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            self.logger.error("Failed to obtain Feishu access token: %s", exc)
            return None

        code = data.get("code", -1)
        if code != 0:
            self.logger.error(
                "Feishu auth returned error code=%s msg=%s",
                code,
                data.get("msg", "unknown"),
            )
            return None

        self._access_token = data.get("tenant_access_token", "")
        # Tokens are valid for ~2 hours; cache for 1h50m
        expires_in = data.get("expire", 7200)
        self._token_expiry = now + expires_in

        if not self._access_token:
            self.logger.error("Feishu auth response missing tenant_access_token")
        return self._access_token or None

    def _headers(self) -> dict[str, str]:
        """Build Authorization header dict. Returns empty auth if no token."""
        token = self._get_access_token()
        if token:
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            }
        return {"Content-Type": "application/json; charset=utf-8"}

    # ------------------------------------------------------------------
    # test_connection
    # ------------------------------------------------------------------

    def test_connection(self) -> SyncConnectionResult:
        """Validate credentials and connectivity to Feishu.

        Attempts to obtain an access token, then lists at most one page of
        resources to confirm the space/drive is accessible.
        """
        token = self._get_access_token()
        if not token:
            return SyncConnectionResult(
                success=False,
                message="Authentication failed — check app_id and app_secret",
                resources_count=0,
            )

        # Try listing resources to confirm access
        resources = self.list_resources()
        count = len(resources)

        return SyncConnectionResult(
            success=True,
            message=f"Connected to Feishu. Found {count} resource(s).",
            resources_count=count,
        )

    # ------------------------------------------------------------------
    # list_resources
    # ------------------------------------------------------------------

    def list_resources(self) -> list[SyncResource]:
        """List all documents in the configured Feishu Wiki space.

        Uses the Wiki Space nodes API when space_id is configured,
        otherwise falls back to the Drive file listing API.
        """
        space_id = self.config.get("space_id", "")
        if space_id:
            return self._list_wiki_nodes(space_id)
        return self._list_drive_files()

    def _list_wiki_nodes(self, space_id: str) -> list[SyncResource]:
        """Paginate through all nodes in a Feishu Wiki space."""
        resources: list[SyncResource] = []
        headers = self._headers()
        page_token: str | None = None

        while True:
            params: dict = {"page_size": self.PAGE_SIZE}
            if page_token:
                params["page_token"] = page_token

            url = self.WIKI_NODES_URL.format(space_id=space_id)
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as exc:
                self.logger.error("Failed to list Feishu wiki nodes: %s", exc)
                break

            code = data.get("code", -1)
            if code != 0:
                self.logger.error(
                    "Feishu wiki nodes API error code=%s msg=%s",
                    code,
                    data.get("msg", ""),
                )
                break

            items = data.get("data", {}).get("items", [])
            for item in items:
                node_type = item.get("node_type", "doc")
                obj_type = item.get("obj_type", "doc")
                # Determine resource type string
                if node_type == "folder":
                    res_type = "folder"
                elif obj_type == "doc":
                    res_type = "document"
                elif obj_type == "sheet":
                    res_type = "spreadsheet"
                elif obj_type == "bitable":
                    res_type = "database"
                elif obj_type == "mindnote":
                    res_type = "mindmap"
                else:
                    res_type = obj_type or "unknown"

                updated_at = _parse_unix_millis(item.get("update_time"))
                resources.append(
                    SyncResource(
                        resource_id=item.get("node_token", "") or item.get("obj_token", ""),
                        name=item.get("title", "Untitled"),
                        resource_type=res_type,
                        updated_at=updated_at,
                        size_bytes=0,
                        metadata={
                            "node_type": node_type,
                            "obj_type": obj_type,
                            "obj_token": item.get("obj_token", ""),
                            "space_id": space_id,
                            "parent_node_token": item.get("parent_node_token", ""),
                        },
                    )
                )

            if not data.get("data", {}).get("has_more", False):
                break
            page_token = data.get("data", {}).get("page_token", "")

        return resources

    def _list_drive_files(self) -> list[SyncResource]:
        """Fallback: list files from the Feishu Drive root folder."""
        resources: list[SyncResource] = []
        headers = self._headers()
        page_token: str | None = None

        while True:
            params: dict = {"page_size": self.PAGE_SIZE}
            if page_token:
                params["page_token"] = page_token

            try:
                resp = requests.get(
                    self.DRIVE_FILES_URL,
                    headers=headers,
                    params=params,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as exc:
                self.logger.error("Failed to list Feishu drive files: %s", exc)
                break

            code = data.get("code", -1)
            if code != 0:
                self.logger.error(
                    "Feishu drive files API error code=%s msg=%s",
                    code,
                    data.get("msg", ""),
                )
                break

            items = data.get("data", {}).get("files", [])
            for item in items:
                mime_type = item.get("type", "unknown")
                if mime_type == "docx" or mime_type == "doc":
                    res_type = "document"
                elif mime_type == "sheet":
                    res_type = "spreadsheet"
                elif mime_type == "bitable":
                    res_type = "database"
                elif mime_type == "folder":
                    res_type = "folder"
                elif mime_type == "mindnote":
                    res_type = "mindmap"
                else:
                    res_type = mime_type

                updated_at = _parse_unix_millis(item.get("modified_time"))
                resources.append(
                    SyncResource(
                        resource_id=item.get("token", ""),
                        name=item.get("name", "Untitled"),
                        resource_type=res_type,
                        updated_at=updated_at,
                        size_bytes=int(item.get("size", 0)),
                        metadata={
                            "mime_type": mime_type,
                            "revision": item.get("revision", 0),
                            "url": item.get("url", ""),
                        },
                    )
                )

            if not data.get("data", {}).get("has_more", False):
                break
            page_token = data.get("data", {}).get("page_token", "")

        return resources

    # ------------------------------------------------------------------
    # fetch_changes
    # ------------------------------------------------------------------

    def fetch_changes(self, since: datetime | None = None) -> list[dict]:
        """Return resources changed since the given timestamp (or all if None).

        Returns:
            List of dicts with keys: resource_id, name, resource_type,
            updated_at, change_type ("new" or "updated").
        """
        all_resources = self.list_resources()

        if since is None:
            return [
                {
                    "resource_id": r.resource_id,
                    "name": r.name,
                    "resource_type": r.resource_type,
                    "updated_at": r.updated_at,
                    "change_type": "new",
                }
                for r in all_resources
            ]

        # Ensure since is timezone-aware for comparison
        since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)

        changes: list[dict] = []
        for r in all_resources:
            if r.updated_at and r.updated_at > since_utc:
                changes.append({
                    "resource_id": r.resource_id,
                    "name": r.name,
                    "resource_type": r.resource_type,
                    "updated_at": r.updated_at,
                    "change_type": "updated",
                })
            elif r.updated_at is None:
                # Resources without timestamps are treated as new
                changes.append({
                    "resource_id": r.resource_id,
                    "name": r.name,
                    "resource_type": r.resource_type,
                    "updated_at": r.updated_at,
                    "change_type": "new",
                })

        return changes

    # ------------------------------------------------------------------
    # fetch_content
    # ------------------------------------------------------------------

    def fetch_content(self, resource_id: str) -> dict:
        """Fetch the full content of a Feishu document as markdown text.

        Args:
            resource_id: The document token (node_token or obj_token).

        Returns:
            {"content": str, "content_type": str, "metadata": dict}
        """
        headers = self._headers()

        # First, get document metadata (title, type)
        doc_meta = self._fetch_doc_meta(resource_id, headers)
        title = doc_meta.get("title", resource_id)
        revision = doc_meta.get("revision", 0)

        # Fetch raw content (preferred — yields markdown-like plain text)
        raw_content = self._fetch_raw_content(resource_id, headers)

        if raw_content is not None:
            content = raw_content
            content_type = "text"
        else:
            # Fall back to block-based content extraction
            content = self._fetch_blocks_content(resource_id, headers, title)
            content_type = "markdown"

        metadata = {
            "resource_id": resource_id,
            "title": title,
            "revision": revision,
            "fetched_at": self.now_utc().isoformat(),
        }

        return {
            "content": content,
            "content_type": content_type,
            "metadata": metadata,
        }

    def _fetch_doc_meta(self, document_id: str, headers: dict) -> dict:
        """Get document metadata (title, revision, type)."""
        try:
            resp = requests.get(
                self.DOCX_META_URL.format(document_id=document_id),
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            self.logger.warning("Failed to fetch Feishu doc meta: %s", exc)
            return {}

        if data.get("code", -1) != 0:
            self.logger.warning(
                "Feishu doc meta error code=%s msg=%s",
                data.get("code"),
                data.get("msg", ""),
            )
            return {}

        doc = data.get("data", {}).get("document", {})
        return {
            "title": doc.get("title", ""),
            "revision": int(doc.get("revision", 0)),
            "document_id": doc.get("document_id", document_id),
        }

    def _fetch_raw_content(self, document_id: str, headers: dict) -> str | None:
        """Fetch raw (plain text) content of a document. Returns None on failure."""
        try:
            resp = requests.get(
                self.DOCX_RAW_URL.format(document_id=document_id),
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            self.logger.warning("Failed to fetch Feishu raw content: %s", exc)
            return None

        if data.get("code", -1) != 0:
            self.logger.warning(
                "Feishu raw content error code=%s msg=%s",
                data.get("code"),
                data.get("msg", ""),
            )
            return None

        return data.get("data", {}).get("content", "")

    def _fetch_blocks_content(
        self, document_id: str, headers: dict, title: str
    ) -> str:
        """Fetch document content by iterating through blocks and converting to markdown."""
        lines: list[str] = []
        if title:
            lines.append(f"# {title}")

        page_token: str | None = None
        while True:
            params: dict = {"page_size": self.PAGE_SIZE}
            if page_token:
                params["page_token"] = page_token

            try:
                resp = requests.get(
                    self.DOCX_BLOCKS_URL.format(document_id=document_id),
                    headers=headers,
                    params=params,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as exc:
                self.logger.error("Failed to fetch Feishu doc blocks: %s", exc)
                break

            if data.get("code", -1) != 0:
                self.logger.error(
                    "Feishu blocks API error code=%s msg=%s",
                    data.get("code"),
                    data.get("msg", ""),
                )
                break

            items = data.get("data", {}).get("items", [])
            for block in items:
                rendered = _render_block_to_markdown(block)
                if rendered:
                    lines.append(rendered)

            if not data.get("data", {}).get("has_more", False):
                break
            page_token = data.get("data", {}).get("page_token", "")

        return "\n\n".join(lines)


# ------------------------------------------------------------------
# Block rendering helpers
# ------------------------------------------------------------------


def _render_block_to_markdown(block: dict) -> str:
    """Convert a single Feishu docx block to markdown text."""
    block_type = block.get("block_type", 0)
    text = _extract_block_text(block)

    # Heading blocks
    heading_map = {
        3: lambda t: f"# {t}",
        4: lambda t: f"## {t}",
        5: lambda t: f"### {t}",
        6: lambda t: f"#### {t}",
        7: lambda t: f"##### {t}",
        8: lambda t: f"###### {t}",
    }

    if block_type in heading_map:
        return heading_map[block_type](text) if text else ""

    if block_type == 9:  # bullet list
        return f"- {text}" if text else ""
    if block_type == 10:  # ordered list
        return f"1. {text}" if text else ""
    if block_type == 11:  # code block
        lang = block.get("code", {}).get("language", "")
        return f"```{lang}\n{text}\n```"
    if block_type == 12:  # quote
        return "\n".join(f"> {line}" for line in text.split("\n"))
    if block_type == 13:  # callout / alert
        return f"> **Note:** {text}" if text else ""
    if block_type == 14:  # divider
        return "---"
    if block_type == 15:  # image
        return _extract_image_markdown(block)
    if block_type == 17:  # table — render as text grid
        return _render_table(block)
    if block_type == 18:  # task / todo
        done = block.get("task", {}).get("done", False)
        checkbox = "[x]" if done else "[ ]"
        return f"- {checkbox} {text}" if text else f"- {checkbox}"
    if block_type == 21:  # grid / column layout placeholder
        return f"<!-- grid: {text} -->" if text else ""

    # Default: plain text paragraph
    return text


def _extract_block_text(block: dict) -> str:
    """Extract plain text content from any block type's text elements.

    Feishu stores text in block -> block_specific_field -> elements -> text_run.
    """
    # Known fields that contain text elements for different block types
    text_container_keys = [
        "text",       # paragraph, quote
        "heading1", "heading2", "heading3", "heading4", "heading5",
        "heading6", "heading7", "heading8", "heading9",
        "bullet",
        "ordered",
        "code",
        "callout",
        "task",
        "table_cell",
    ]

    for key in text_container_keys:
        container = block.get(key, None)
        if isinstance(container, dict):
            elements = container.get("elements", [])
            if elements:
                parts: list[str] = []
                for elem in elements:
                    run = elem.get("text_run", {})
                    content = run.get("content", "")
                    if content:
                        parts.append(content)
                    # Also check inline elements like mention, equation, etc.
                    mention = elem.get("mention_user", {})
                    if mention:
                        parts.append(f"@{mention.get('name', mention.get('user_id', 'unknown'))}")
                    equation = elem.get("equation", {})
                    if equation:
                        parts.append(equation.get("content", ""))
                if parts:
                    return "".join(parts)

    # Fallback: check raw text content field (used in raw_content API)
    raw = block.get("text_content", "")
    return raw


def _extract_image_markdown(block: dict) -> str:
    """Render an image block as markdown."""
    image_data = block.get("image", {})
    alt = image_data.get("caption", "")
    url = image_data.get("image_url", "")
    if url:
        return f"![{alt}]({url})"
    return f"[Image: {alt}]" if alt else "[Image]"


def _render_table(block: dict) -> str:
    """Render a Feishu table block as a simple text representation."""
    table_data = block.get("table", {})
    rows = table_data.get("cells", [])
    if not rows:
        return ""

    lines: list[str] = []
    for row in rows:
        if isinstance(row, list):
            cells = [_extract_cell_text(cell) for cell in row]
        else:
            cells = [_extract_cell_text(row)]
        lines.append(" | ".join(cells))

    return "\n".join(lines)


def _extract_cell_text(cell: dict) -> str:
    """Extract text from a table cell."""
    if isinstance(cell, str):
        return cell
    if isinstance(cell, dict):
        return _extract_block_text(cell)
    return str(cell)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _parse_unix_millis(ms: int | float | str | None) -> datetime | None:
    """Convert a Feishu Unix timestamp (milliseconds) to a timezone-aware UTC datetime."""
    if ms is None:
        return None
    try:
        value = float(ms)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    # Feishu API always returns timestamps in milliseconds
    return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)


# ------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------

from src.sync import _register  # noqa: E402

_register("feishu", FeishuConnector)
