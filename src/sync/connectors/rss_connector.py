"""RSS/Atom Feed Connector — sync articles from RSS and Atom feeds.

Parses both RSS 2.0 and Atom 1.0 formats using stdlib xml.etree.ElementTree.
No external feed-parsing dependency required.

Entry metadata:
  - ``pubDate`` / ``updated`` timestamps for change detection
  - ``guid`` / ``id`` as stable resource identifiers
  - description / content for article body (full text when the feed provides it)

Credentials (via self.config):
  - ``feed_url`` (str): URL of the RSS or Atom feed

Optional config:
  - ``user_agent`` (str): custom User-Agent header
  - ``request_timeout`` (int): HTTP request timeout in seconds (default 30)
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import SyncConnectionResult, SyncResource

# Atom namespace
ATOM_NS = "http://www.w3.org/2005/Atom"

# HTML tag stripping regex (used to produce plain-text content when needed)
_HTML_TAG_RE = re.compile(r"<[^>]*>")


# ── Internal helpers ──────────────────────────────────────────────────────


def _parse_date(date_str: str) -> datetime | None:
    """Parse a feed date string into a timezone-aware datetime.

    Tries RFC 2822 (RSS) first, then ISO 8601 (Atom).
    Returns None when parsing fails.
    """
    if not date_str or not isinstance(date_str, str):
        return None
    date_str = date_str.strip()
    if not date_str:
        return None

    # RFC 2822 (RSS pubDate)
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        pass

    # ISO 8601 (Atom published / updated)
    try:
        cleaned = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        pass

    return None


def _text_of(element: ElementTree.Element, tag: str) -> str:
    """Return the stripped text of the first child with *tag* (no namespace)."""
    child = element.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return ""


def _atom_text_of(element: ElementTree.Element, tag: str) -> str:
    """Return the stripped text of the first Atom-namespaced child with *tag*."""
    child = element.find(f"{{{ATOM_NS}}}{tag}")
    if child is not None and child.text:
        return child.text.strip()
    return ""


def _atom_attr_of(element: ElementTree.Element, tag: str, attr: str) -> str:
    """Return *attr* from the first Atom-namespaced child with *tag*."""
    child = element.find(f"{{{ATOM_NS}}}{tag}")
    if child is not None:
        return child.get(attr, "").strip()
    return ""


def _strip_html(html: str) -> str:
    """Remove HTML tags, returning plain text."""
    if not html:
        return ""
    return _HTML_TAG_RE.sub("", html).strip()


# ── Connector ─────────────────────────────────────────────────────────────


class RssConnector(BaseSyncConnector):
    """Sync connector for RSS 2.0 and Atom 1.0 feeds.

    Fetches a feed URL, parses entries, and exposes them as SyncResource
    objects. Supports incremental change detection via pubDate / updated
    timestamps and content hashing.
    """

    connector_type = "rss"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.logger = logging.getLogger(f"sync.connector.{self.connector_type}")

        # In-memory cache of entries keyed by resource_id, populated by
        # _fetch_feed() and consumed by fetch_content().
        self._entries_cache: dict[str, dict] = {}
        self._feed_meta: dict[str, str] = {}

    # ── Config helpers ─────────────────────────────────────────────────

    @property
    def _feed_url(self) -> str:
        """Resolve the feed URL from config (top-level or nested credentials)."""
        url = self.config.get("feed_url", "")
        if not url:
            url = self.config.get("credentials", {}).get("feed_url", "")
        return url

    @property
    def _user_agent(self) -> str:
        return self.config.get(
            "user_agent",
            "Mozilla/5.0 (compatible; CognitiveOS-Sync/1.0; +https://cognitiveos.ai)",
        )

    @property
    def _timeout(self) -> int:
        return int(self.config.get("request_timeout", 30))

    # ── Feed fetching & parsing ────────────────────────────────────────

    def _fetch_feed(self) -> tuple[dict, list[dict]]:
        """Fetch and parse the feed. Returns (feed_meta, entries).

        Every entry dict has keys:
          resource_id, title, link, content, content_type, pub_date, author, guid.

        Raises ValueError when the feed URL is missing.
        Raises requests.RequestException on HTTP failures.
        Raises ElementTree.ParseError on XML failures.
        """
        url = self._feed_url
        if not url:
            raise ValueError("Missing feed_url in connector config")

        resp = requests.get(
            url,
            headers={"User-Agent": self._user_agent, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"},
            timeout=self._timeout,
        )
        resp.raise_for_status()

        # Strip leading whitespace to avoid "xml declaration not at start" errors
        xml_text = resp.text.lstrip()
        root = ElementTree.fromstring(xml_text)

        # Detect feed type by root element
        tag = _strip_ns(root.tag)
        if tag == "rss":
            return self._parse_rss(root)
        if tag == "feed":
            return self._parse_atom(root)

        raise ValueError(f"Unrecognized feed root element: {root.tag}")

    def _parse_rss(self, root: ElementTree.Element) -> tuple[dict, list[dict]]:
        """Parse RSS 2.0 feed."""
        channel = root.find("channel")
        if channel is None:
            raise ValueError("RSS feed missing <channel> element")

        feed_meta = {
            "title": _text_of(channel, "title"),
            "link": _text_of(channel, "link"),
            "description": _text_of(channel, "description"),
            "feed_type": "rss",
        }

        entries: list[dict] = []
        for item in channel.findall("item"):
            title = _text_of(item, "title")
            link = _text_of(item, "link")
            description = _text_of(item, "description")
            pub_date_str = _text_of(item, "pubDate")
            author = _text_of(item, "author")
            guid = _text_of(item, "guid")

            # content:encoded (commonly used for full-text in RSS)
            content_encoded = ""
            for child in item:
                if child.tag.endswith("}encoded") or child.tag == "encoded":
                    content_encoded = (child.text or "").strip()
                    break

            # Prefer content:encoded, fall back to description
            raw_content = content_encoded or description
            content_type = "html" if raw_content else "text"

            resource_id = guid or link or hashlib.sha256(
                (title + raw_content).encode("utf-8", errors="replace")
            ).hexdigest()

            pub_date = _parse_date(pub_date_str)

            entries.append({
                "resource_id": resource_id,
                "title": title or "Untitled",
                "link": link,
                "content": raw_content,
                "content_type": content_type,
                "pub_date": pub_date,
                "author": author,
                "guid": guid,
                "description": description,
            })

        return feed_meta, entries

    def _parse_atom(self, root: ElementTree.Element) -> tuple[dict, list[dict]]:
        """Parse Atom 1.0 feed."""
        feed_meta = {
            "title": _atom_text_of(root, "title"),
            "link": _atom_attr_of(root, "link", "href"),
            "description": _atom_text_of(root, "subtitle"),
            "feed_type": "atom",
        }

        entries: list[dict] = []
        for entry in root.findall(f"{{{ATOM_NS}}}entry"):
            title = _atom_text_of(entry, "title")
            link = (
                _atom_attr_of(entry, "link", "href")
                or _atom_text_of(entry, "link")
            )
            summary = _atom_text_of(entry, "summary")
            content = _atom_text_of(entry, "content")
            published_str = _atom_text_of(entry, "published")
            updated_str = _atom_text_of(entry, "updated")
            author_name = _atom_text_of(entry.find(f"{{{ATOM_NS}}}author") or ElementTree.Element("author"), "name")
            entry_id = _atom_text_of(entry, "id")

            # Atom <content> may have a type attribute
            content_type_attr = ""
            content_el = entry.find(f"{{{ATOM_NS}}}content")
            if content_el is not None:
                content_type_attr = content_el.get("type", "").lower()

            raw_content = content or summary or ""
            if "html" in content_type_attr:
                content_type = "html"
            elif raw_content:
                content_type = "html" if ("<" in raw_content and ">" in raw_content) else "text"
            else:
                content_type = "text"

            resource_id = entry_id or link or hashlib.sha256(
                (title + raw_content).encode("utf-8", errors="replace")
            ).hexdigest()

            # Use updated as primary date, published as fallback
            pub_date = _parse_date(updated_str) or _parse_date(published_str)

            entries.append({
                "resource_id": resource_id,
                "title": title or "Untitled",
                "link": link,
                "content": raw_content,
                "content_type": content_type,
                "pub_date": pub_date,
                "author": author_name,
                "guid": entry_id,
                "description": summary or raw_content,
            })

        return feed_meta, entries

    # ── SyncConnector interface ────────────────────────────────────────

    def test_connection(self) -> SyncConnectionResult:
        """Validate the feed URL and parse the feed."""
        if not self._feed_url:
            return SyncConnectionResult(
                success=False,
                message="Missing feed_url in connector config",
            )

        try:
            feed_meta, entries = self._fetch_feed()

            # Cache for subsequent calls
            self._feed_meta = feed_meta
            self._entries_cache = {e["resource_id"]: e for e in entries}

            self.logger.info(
                "rss_test_connection_ok",
                extra={
                    "feed_url": self._feed_url,
                    "feed_title": feed_meta.get("title", ""),
                    "entries_count": len(entries),
                },
            )
            return SyncConnectionResult(
                success=True,
                message=f"Connected to \"{feed_meta.get('title', self._feed_url)}\" — {len(entries)} entries",
                resources_count=len(entries),
            )
        except ValueError as exc:
            self.logger.warning("rss_config_error", extra={"error": str(exc)})
            return SyncConnectionResult(success=False, message=str(exc))
        except requests.ConnectionError as exc:
            self.logger.warning("rss_connection_error", extra={"error": str(exc)})
            return SyncConnectionResult(
                success=False,
                message=f"Cannot reach {self._feed_url}: connection failed",
            )
        except requests.Timeout:
            self.logger.warning("rss_timeout", extra={"feed_url": self._feed_url})
            return SyncConnectionResult(
                success=False,
                message=f"Timeout connecting to {self._feed_url}",
            )
        except requests.HTTPError as exc:
            self.logger.warning(
                "rss_http_error",
                extra={"feed_url": self._feed_url, "status": exc.response.status_code if exc.response else "unknown"},
            )
            return SyncConnectionResult(
                success=False,
                message=f"HTTP {exc.response.status_code if exc.response else 'error'} fetching {self._feed_url}",
            )
        except ElementTree.ParseError as exc:
            self.logger.warning("rss_xml_parse_error", extra={"error": str(exc)})
            return SyncConnectionResult(
                success=False,
                message=f"Failed to parse feed XML from {self._feed_url}",
            )
        except Exception as exc:
            self.logger.exception("rss_unexpected_error")
            return SyncConnectionResult(
                success=False,
                message=f"Unexpected error: {exc}",
            )

    def list_resources(self) -> list[SyncResource]:
        """Fetch and parse the feed, returning one SyncResource per entry."""
        try:
            feed_meta, entries = self._fetch_feed()
            self._feed_meta = feed_meta
            self._entries_cache = {e["resource_id"]: e for e in entries}

            resources: list[SyncResource] = []
            for e in entries:
                # Estimate size: UTF-8 byte length of content
                size_bytes = len(e["content"].encode("utf-8", errors="replace"))
                resources.append(SyncResource(
                    resource_id=e["resource_id"],
                    name=e["title"],
                    resource_type="article",
                    updated_at=e["pub_date"],
                    size_bytes=size_bytes,
                    metadata={
                        "link": e.get("link", ""),
                        "author": e.get("author", ""),
                        "guid": e.get("guid", ""),
                        "feed_title": feed_meta.get("title", ""),
                        "feed_type": feed_meta.get("feed_type", ""),
                    },
                ))

            self.logger.info(
                "rss_list_resources",
                extra={"feed_url": self._feed_url, "count": len(resources)},
            )
            return resources

        except Exception as exc:
            self.logger.exception("rss_list_resources_failed")
            return []

    def fetch_changes(self, since: datetime | None = None) -> list[dict]:
        """Return entries changed since *since* (by pubDate / updated).

        Returns a list of lightweight change descriptor dicts with keys:
          resource_id, title, change_type, updated_at, metadata.
        """
        if not self._feed_url:
            return []

        try:
            _feed_meta, entries = self._fetch_feed()
            changes: list[dict] = []

            for e in entries:
                pub_date = e.get("pub_date")

                # Timestamp pre-filter
                if since and pub_date and pub_date < since:
                    continue

                # Determine if this is new or updated based on whether we
                # have seen this resource_id before.
                seen = e["resource_id"] in self._entries_cache
                change_type = "updated" if seen else "new"

                changes.append({
                    "resource_id": e["resource_id"],
                    "title": e["title"],
                    "change_type": change_type,
                    "updated_at": pub_date,
                    "metadata": {
                        "link": e.get("link", ""),
                        "guid": e.get("guid", ""),
                        "content_hash": self.compute_hash(e["content"]),
                    },
                })

            # Detect deletions: entries in cache not in current feed
            current_ids = {e["resource_id"] for e in entries}
            for cached_id in self._entries_cache:
                if cached_id not in current_ids:
                    changes.append({
                        "resource_id": cached_id,
                        "title": self._entries_cache[cached_id].get("title", ""),
                        "change_type": "deleted",
                        "updated_at": self.now_utc(),
                        "metadata": {},
                    })

            # Update cache
            self._entries_cache = {e["resource_id"]: e for e in entries}

            return changes

        except Exception as exc:
            self.logger.exception("rss_fetch_changes_failed")
            return []

    def fetch_content(self, resource_id: str) -> dict:
        """Return full content for a single feed entry.

        Returns:
            {"content": str, "content_type": str, "metadata": dict}
        """
        # Serve from cache if available (populated by list_resources or
        # test_connection).
        if resource_id in self._entries_cache:
            entry = self._entries_cache[resource_id]
            return {
                "content": entry.get("content", ""),
                "content_type": entry.get("content_type", "text"),
                "metadata": {
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "author": entry.get("author", ""),
                    "guid": entry.get("guid", ""),
                    "pub_date": entry["pub_date"].isoformat() if entry.get("pub_date") else None,
                    "feed_title": self._feed_meta.get("title", ""),
                },
            }

        # Cache miss — refetch the feed
        try:
            _feed_meta, entries = self._fetch_feed()
            self._entries_cache = {e["resource_id"]: e for e in entries}

            entry = self._entries_cache.get(resource_id)
            if entry:
                return {
                    "content": entry.get("content", ""),
                    "content_type": entry.get("content_type", "text"),
                    "metadata": {
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "author": entry.get("author", ""),
                        "guid": entry.get("guid", ""),
                        "pub_date": entry["pub_date"].isoformat() if entry.get("pub_date") else None,
                        "feed_title": self._feed_meta.get("title", ""),
                    },
                }

            self.logger.warning(
                "rss_resource_not_found",
                extra={"resource_id": resource_id, "feed_url": self._feed_url},
            )
            return {"content": "", "content_type": "text", "metadata": {}}

        except Exception as exc:
            self.logger.exception("rss_fetch_content_failed")
            return {"content": "", "content_type": "text", "metadata": {"error": str(exc)}}


# ── Namespace helper ──────────────────────────────────────────────────────


def _strip_ns(tag: str) -> str:
    """Remove namespace prefix from an XML tag, returning the local name."""
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


# ── Registration ──────────────────────────────────────────────────────────

from src.sync import _register  # noqa: E402

_register("rss", RssConnector)
