"""Weixin Reader (微信读书) sync connector.

Syncs books, highlights, and notes from Weixin Reader (weread.qq.com).
Uses the internal weread API with cookie-based session authentication.

API endpoints (no official public API; these are the internal endpoints
used by the weread web app):

    GET /shelf                          — books in the user's shelf
    GET /user/notebooks                 — books with annotations metadata
    GET /book/info?bookId={bookId}      — book detail (title, author, intro, ...)
    GET /book/bookmarklist?bookId={id}  — highlights and notes for a book

Highlight item shape returned by /book/bookmarklist:
    { bookmarkId, bookId, chapterUid, chapterName, markText, content,
      createTime, style, type (1=highlight 2=note), range, ... }
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import requests

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import SyncConnectionResult, SyncResource


class WeixinReaderConnector(BaseSyncConnector):
    """Sync connector for Weixin Reader (微信读书).

    Authenticates via a browser session cookie stored in ``self.config["cookie"]``.

    Resources
    ---------
    Each book in the user's shelf becomes one ``SyncResource`` with type ``"book"``.
    Its ``resource_id`` is ``"weread_book:{bookId}"``.

    Content
    -------
    ``fetch_content(resource_id)`` returns book metadata plus all highlights
    and notes rendered as Markdown text.
    """

    connector_type = "weixin_reader"

    BASE_URL = "https://i.weread.qq.com"
    REQUEST_TIMEOUT = 15.0  # seconds

    # ── Construction ────────────────────────────────────────────────────

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.logger = logging.getLogger("sync.connector.weixin_reader")

    # ── Internal helpers ────────────────────────────────────────────────

    def _get_headers(self) -> dict[str, str]:
        """Build HTTP headers with cookie-based auth."""
        headers: dict[str, str] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://weread.qq.com/",
            "Accept": "application/json, text/plain, */*",
        }
        cookie = self.config.get("cookie", "")
        if cookie:
            headers["Cookie"] = cookie
        return headers

    def _api_get(
        self, path: str, params: dict | None = None
    ) -> dict | list | None:
        """Call a weread API endpoint and return the parsed JSON body.

        Returns ``None`` on any failure (timeout, connection error, non-200,
        or JSON decode error).  The caller always receives a safe value.
        """
        url = f"{self.BASE_URL}{path}"
        try:
            resp = requests.get(
                url,
                headers=self._get_headers(),
                params=params,
                timeout=self.REQUEST_TIMEOUT,
            )
        except requests.exceptions.Timeout:
            self.logger.warning("Timeout requesting %s", path)
            return None
        except requests.exceptions.ConnectionError:
            self.logger.warning("Connection refused for %s", path)
            return None
        except requests.exceptions.RequestException as exc:
            self.logger.warning("Request failed for %s: %s", path, exc)
            return None

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                self.logger.warning("Invalid JSON from %s", path)
                return None

        self.logger.warning("API %s returned HTTP %s", path, resp.status_code)
        return None

    @staticmethod
    def _extract_book_id(raw: str) -> str:
        """Normalise a raw book-id value.

        Handles:
          - bare ids like ``"abc123"`` or ``"MP_WXS_abc123"``
          - full weread URLs like
            ``https://weread.qq.com/web/bookDetail/abc123``
        """
        if not raw:
            return ""

        # Full URL
        for pattern in (r"/bookDetail/([a-zA-Z0-9]+)", r"/reader/([a-zA-Z0-9]+)"):
            m = re.search(pattern, raw)
            if m:
                return m.group(1)

        # Prefixed id — strip known prefixes
        for prefix in ("MP_WXS_", "MP_", "WXS_"):
            if raw.startswith(prefix):
                return raw[len(prefix) :]

        return raw

    # ── Public interface ────────────────────────────────────────────────

    def test_connection(self) -> SyncConnectionResult:
        """Validate credentials by hitting the bookshelf endpoint.

        A missing or expired cookie causes the API to return an error code
        (or an empty / wrong-shaped body) instead of the expected ``books`` key.
        """
        cookie = self.config.get("cookie", "")
        if not cookie:
            return SyncConnectionResult(
                success=False,
                message=(
                    "No cookie configured. Provide a valid Weixin Reader "
                    "session cookie in the connector config."
                ),
                resources_count=0,
            )

        data = self._api_get("/shelf")
        if data is None:
            return SyncConnectionResult(
                success=False,
                message=(
                    "Failed to reach the Weixin Reader API. "
                    "Check network connectivity and cookie validity."
                ),
                resources_count=0,
            )

        # The real /shelf endpoint includes a "books" list on success.
        # On auth failure it returns something like {"errCode": -2012, ...}
        if not isinstance(data, dict):
            return SyncConnectionResult(
                success=False,
                message="Unexpected API response format — expected a JSON object.",
                resources_count=0,
            )

        if "errCode" in data:
            return SyncConnectionResult(
                success=False,
                message=f"Authentication failed: {data.get('errMsg', 'invalid cookie')}",
                resources_count=0,
            )

        books = data.get("books") or []
        return SyncConnectionResult(
            success=True,
            message=f"Connected successfully. {len(books)} book(s) on shelf.",
            resources_count=len(books),
        )

    def list_resources(self) -> list[SyncResource]:
        """Return one SyncResource per book on the user's shelf.

        Enriches each book with highlight/note counts from the notebooks API
        when available.
        """
        resources: list[SyncResource] = []

        shelf = self._api_get("/shelf")
        if not shelf or not isinstance(shelf, dict):
            return resources

        books = shelf.get("books")
        if not books:
            return resources

        # Enrich with notebook metadata (highlight counts, last-note time)
        notebooks_data = self._api_get("/user/notebooks")
        notebook_map: dict[str, dict] = {}
        if notebooks_data and isinstance(notebooks_data, dict):
            for entry in notebooks_data.get("books", []) or []:
                book_obj = entry.get("book", {})
                bid = str(book_obj.get("bookId", ""))
                if bid:
                    notebook_map[bid] = entry

        for book in books:
            if not isinstance(book, dict):
                continue

            book_id = str(book.get("bookId", ""))
            if not book_id:
                continue

            title = book.get("title") or "Untitled"
            author = book.get("author") or ""
            cover = book.get("cover") or ""

            # Timestamp
            updated_ts = book.get("updated", 0)
            updated_at: datetime | None = None
            if updated_ts:
                try:
                    updated_at = datetime.fromtimestamp(int(updated_ts), tz=timezone.utc)
                except (TypeError, ValueError, OSError):
                    updated_at = None

            # Highlight / note counts from the notebook entry
            nb = notebook_map.get(book_id, {})
            highlight_count: int = 0
            try:
                highlight_count = int(nb.get("highlightCount", 0) or 0)
            except (TypeError, ValueError):
                pass
            note_count: int = 0
            try:
                note_count = int(nb.get("noteCount", 0) or 0)
            except (TypeError, ValueError):
                pass
            sort_idx: int = 0
            try:
                sort_idx = int(nb.get("sort", 0) or 0)
            except (TypeError, ValueError):
                pass

            resources.append(
                SyncResource(
                    resource_id=f"weread_book:{book_id}",
                    name=title,
                    resource_type="book",
                    updated_at=updated_at,
                    size_bytes=0,
                    metadata={
                        "book_id": book_id,
                        "author": author,
                        "cover": cover,
                        "highlight_count": highlight_count,
                        "note_count": note_count,
                        "sort_index": sort_idx,
                        "url": f"https://weread.qq.com/web/bookDetail/{book_id}",
                    },
                )
            )

        return resources

    def fetch_changes(self, since: datetime | None) -> list[dict]:
        """Return change descriptors for highlights/notes modified since *since*.

        Each returned dict represents one highlight and carries enough
        metadata for the ChangeDetector to build a ChangeRecord:

            {
                "resource_id": str,
                "change_type": str,          # "new" | "updated"
                "content_hash": str,
                "metadata": {
                    "book_id", "title", "author",
                    "highlight_id", "chapter_uid", "chapter_name",
                    "mark_text", "mark_type", "created_at", ...
                },
            }

        When *since* is ``None`` every highlight is included.
        """
        changes: list[dict] = []

        notebooks = self._api_get("/user/notebooks")
        if not notebooks or not isinstance(notebooks, dict):
            return changes

        for entry in notebooks.get("books", []) or []:
            if not isinstance(entry, dict):
                continue

            book_obj = entry.get("book", {})
            if not isinstance(book_obj, dict):
                continue

            book_id = str(book_obj.get("bookId", ""))
            if not book_id:
                continue

            title = book_obj.get("title", "Untitled")
            author = book_obj.get("author", "")

            highlights = self._api_get(
                "/book/bookmarklist",
                params={"bookId": book_id},
            )
            if not highlights or not isinstance(highlights, dict):
                continue

            for item in highlights.get("updated", []) or []:
                if not isinstance(item, dict):
                    continue

                mark_text = (item.get("markText") or "").strip()
                if not mark_text:
                    continue

                create_time = item.get("createTime", 0)
                item_dt: datetime | None = None
                if create_time:
                    try:
                        item_dt = datetime.fromtimestamp(
                            int(create_time), tz=timezone.utc
                        )
                    except (TypeError, ValueError, OSError):
                        item_dt = None

                # Skip if unchanged since the cutoff
                if since is not None and item_dt is not None and item_dt <= since:
                    continue

                content_hash = self.compute_hash(mark_text)
                resource_id = f"weread_book:{book_id}"

                changes.append(
                    {
                        "resource_id": resource_id,
                        "change_type": "new" if since is None else "updated",
                        "content_hash": content_hash,
                        "metadata": {
                            "book_id": book_id,
                            "title": title,
                            "author": author,
                            "highlight_id": item.get("bookmarkId", ""),
                            "chapter_uid": item.get("chapterUid", 0),
                            "chapter_name": item.get("chapterName", ""),
                            "mark_text": mark_text[:200],
                            "mark_type": item.get("type", 1),
                            "created_at": item_dt.isoformat() if item_dt else None,
                        },
                    }
                )

        return changes

    def fetch_content(self, resource_id: str) -> dict:
        """Fetch full content for a book resource.

        ``resource_id``  —  ``"weread_book:{bookId}"`` or a bare book-id.

        Returns:
            {
                "content": str,       -- Markdown: title, metadata, all highlights & notes
                "content_type": str,  -- "text"
                "metadata": dict,     -- book metadata + content_hash
            }
        """
        # Normalise the book id
        if resource_id.startswith("weread_book:"):
            book_id = resource_id.split(":", 1)[1]
        else:
            book_id = self._extract_book_id(resource_id)

        empty_result: dict = {
            "content": "",
            "content_type": "text",
            "metadata": {"book_id": book_id, "resource_id": resource_id},
        }

        if not book_id:
            return empty_result

        # 1. Book metadata --------------------------------------------------
        book_info = self._api_get("/book/info", params={"bookId": book_id})
        if not book_info or not isinstance(book_info, dict):
            self.logger.warning("No book info for %s", book_id)
            # Continue with empty metadata — highlights may still exist
            book_info = {}

        title = book_info.get("title") or "Untitled"
        author = book_info.get("author") or ""
        cover = book_info.get("cover") or ""
        intro = book_info.get("intro") or ""
        translator = book_info.get("translator") or ""
        category = book_info.get("category") or ""
        publisher = book_info.get("publisher") or ""
        isbn = book_info.get("isbn") or ""

        # 2. Highlights & notes ---------------------------------------------
        highlights_data = self._api_get(
            "/book/bookmarklist", params={"bookId": book_id}
        )
        updated_items: list[dict] = []
        if highlights_data and isinstance(highlights_data, dict):
            updated_items = highlights_data.get("updated") or []

        # 3. Assemble Markdown content --------------------------------------
        lines: list[str] = []

        # --- header ---
        lines.append(f"# {title}")
        if author:
            lines.append(f"**作者**: {author}")
        if translator:
            lines.append(f"**译者**: {translator}")
        if publisher:
            lines.append(f"**出版社**: {publisher}")
        if isbn:
            lines.append(f"**ISBN**: {isbn}")
        if category:
            lines.append(f"**分类**: {category}")
        if cover:
            lines.append(f"\n![封面]({cover})")
        if intro:
            lines.append(f"\n## 简介\n\n{intro}")

        # --- highlights & notes ---
        if updated_items:
            lines.append(f"\n## 摘录与笔记 ({len(updated_items)} 条)\n")

            for i, item in enumerate(updated_items, 1):
                if not isinstance(item, dict):
                    continue

                mark_text = (item.get("markText") or "").strip()
                note_text = (item.get("content") or "").strip()
                chapter_name = item.get("chapterName") or ""
                mark_type = item.get("type", 1)  # 1=highlight, 2=note/review

                if not mark_text and not note_text:
                    continue

                chapter_label = f" — *{chapter_name}*" if chapter_name else ""

                if mark_type == 2 or note_text:
                    heading = f"### {i}. 笔记{chapter_label}"
                else:
                    heading = f"### {i}. 摘录{chapter_label}"

                lines.append(heading)
                lines.append("")
                if mark_text:
                    lines.append(f"> {mark_text}")
                    lines.append("")
                if note_text:
                    lines.append(f"**笔记**: {note_text}")
                    lines.append("")

        content = "\n".join(lines)

        if not content.strip():
            return empty_result

        content_hash = self.compute_hash(content)

        metadata: dict = {
            "book_id": book_id,
            "title": title,
            "author": author,
            "cover": cover,
            "publisher": publisher,
            "isbn": isbn,
            "category": category,
            "translator": translator,
            "url": f"https://weread.qq.com/web/bookDetail/{book_id}",
            "highlight_count": len(updated_items),
            "content_hash": content_hash,
            "resource_id": resource_id,
        }

        return {
            "content": content,
            "content_type": "text",
            "metadata": metadata,
        }


# ── Auto-register ────────────────────────────────────────────────────────
from src.sync import _register  # noqa: E402

_register("weixin_reader", WeixinReaderConnector)
