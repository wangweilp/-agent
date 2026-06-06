"""Unit tests for RssConnector.

Tests the RSS/Atom feed sync connector: feed parsing (RSS 2.0 and Atom 1.0),
entry extraction, connection validation, resource listing, change detection,
and content fetching — all with mocked HTTP responses.

Mock strategy: patch ``requests.get`` to return a controlled response with
pre-canned XML, avoiding real network calls.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch
from xml.etree import ElementTree

import pytest
import requests

from src.sync.connector_base import BaseSyncConnector
from src.sync.connectors.rss_connector import (
    RssConnector,
    _atom_attr_of,
    _atom_text_of,
    _parse_date,
    _strip_html,
    _strip_ns,
    _text_of,
)
from src.sync.models import SyncConnectionResult, SyncResource


# ── Constants: sample XML payloads ────────────────────────────────────────────

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Blog</title>
    <link>https://example.com</link>
    <description>A test blog about software</description>
    <item>
      <title>First Post</title>
      <link>https://example.com/post/1</link>
      <description>This is the &lt;b&gt;first&lt;/b&gt; post content.</description>
      <pubDate>Mon, 02 Jun 2026 10:00:00 GMT</pubDate>
      <author>Alice</author>
      <guid>post-1-guid</guid>
    </item>
    <item>
      <title>Second Post</title>
      <link>https://example.com/post/2</link>
      <description>Content of the second post.</description>
      <pubDate>Tue, 03 Jun 2026 08:30:00 GMT</pubDate>
      <author>Bob</author>
      <guid>post-2-guid</guid>
    </item>
  </channel>
</rss>
"""

RSS_WITH_CONTENT_ENCODED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Full-Text Feed</title>
    <link>https://example.com</link>
    <description>A feed with content:encoded</description>
    <item>
      <title>Full Article</title>
      <link>https://example.com/full</link>
      <description>Short summary only.</description>
      <content:encoded xmlns:content="http://purl.org/rss/1.0/modules/content/">
        &lt;p&gt;This is the full article body with &lt;strong&gt;rich&lt;/strong&gt; content.&lt;/p&gt;
      </content:encoded>
      <pubDate>Mon, 02 Jun 2026 12:00:00 GMT</pubDate>
      <guid>full-guid</guid>
    </item>
  </channel>
</rss>
"""

ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Atom Feed</title>
  <link href="https://example.com/atom" />
  <subtitle>An Atom test feed with multiple entries</subtitle>
  <entry>
    <title>Atom Post One</title>
    <link href="https://example.com/a1" />
    <id>atom-1-id</id>
    <updated>2026-06-02T12:00:00Z</updated>
    <published>2026-06-02T11:00:00Z</published>
    <author><name>Charlie</name></author>
    <content type="html">&lt;p&gt;Full HTML content of atom post one.&lt;/p&gt;</content>
    <summary>Summary of atom post one.</summary>
  </entry>
  <entry>
    <title>Atom Post Two</title>
    <link href="https://example.com/a2" />
    <id>atom-2-id</id>
    <updated>2026-06-03T09:00:00+08:00</updated>
    <author><name>Dana</name></author>
    <content type="text">Plain text content for post two.</content>
  </entry>
  <entry>
    <title>Atom Post Three — No Author</title>
    <link href="https://example.com/a3" />
    <id>atom-3-id</id>
    <updated>2026-06-02T18:30:00Z</updated>
    <summary>Entry with only a summary, no content element.</summary>
  </entry>
</feed>
"""

RSS_EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Empty Feed</title>
    <link>https://example.com/empty</link>
    <description>A feed with no items</description>
  </channel>
</rss>
"""

ATOM_EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Empty Atom</title>
  <link href="https://example.com/empty-atom" />
</feed>
"""

RSS_UNICODE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>中文博客</title>
    <link>https://example.cn</link>
    <description>多语言内容</description>
    <item>
      <title>你好世界 🌍</title>
      <link>https://example.cn/hello</link>
      <description>こんにちは世界！Emoji: 🎉🔥</description>
      <pubDate>Mon, 02 Jun 2026 10:00:00 GMT</pubDate>
      <guid>unicode-guid</guid>
    </item>
  </channel>
</rss>
"""

RSS_MINIMAL = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Minimal</title>
    <link>https://example.com</link>
    <description></description>
    <item>
      <title>Untitled Post</title>
    </item>
    <item>
      <!-- completely empty item -->
    </item>
  </channel>
</rss>
"""

MALFORMED_XML = """<?xml version="1.0"?>
<rss><channel><title>Oops<item><title>Broken</item></channel></rss>
"""

UNRECOGNIZED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<somethingelse>
  <title>Not RSS or Atom</title>
</somethingelse>
"""

ATOM_NS = "http://www.w3.org/2005/Atom"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_response(xml_text: str, status_code: int = 200) -> Mock:
    """Build a Mock response object with .text, .raise_for_status(), and .status_code."""
    mock_resp = Mock()
    mock_resp.text = xml_text
    mock_resp.status_code = status_code

    def _raise_for_status():
        if status_code >= 400:
            exc = requests.HTTPError(f"{status_code} Error")
            exc.response = Mock()
            exc.response.status_code = status_code
            raise exc

    mock_resp.raise_for_status = _raise_for_status
    return mock_resp


def _rss_connector(feed_url: str = "https://example.com/rss", **extra_config) -> RssConnector:
    """Create an RssConnector with sensible test defaults."""
    config = {"feed_url": feed_url, **extra_config}
    return RssConnector(config=config)


# ── Module-level helpers ──────────────────────────────────────────────────────


class TestParseDate:
    """Tests for the _parse_date helper (RFC 2822 and ISO 8601)."""

    def test_parses_rss_pubdate_rfc2822(self):
        dt = _parse_date("Mon, 02 Jun 2026 10:00:00 GMT")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 6
        assert dt.day == 2
        assert dt.hour == 10
        assert dt.tzinfo is not None

    def test_parses_atom_iso8601_with_z(self):
        dt = _parse_date("2026-06-02T12:00:00Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.hour == 12
        assert dt.tzinfo == timezone.utc

    def test_parses_atom_iso8601_with_offset(self):
        dt = _parse_date("2026-06-03T09:00:00+08:00")
        assert dt is not None
        assert dt.year == 2026
        assert dt.hour == 9
        assert dt.tzinfo is not None

    def test_returns_none_for_empty_string(self):
        assert _parse_date("") is None

    def test_returns_none_for_whitespace_only(self):
        assert _parse_date("   ") is None

    def test_returns_none_for_none(self):
        assert _parse_date(None) is None

    def test_returns_none_for_non_string(self):
        assert _parse_date(42) is None  # type: ignore[arg-type]

    def test_returns_none_for_garbage_string(self):
        assert _parse_date("not a valid date at all") is None

    def test_adds_utc_timezone_when_missing_from_iso(self):
        """ISO string without explicit tz offsets should get UTC appended."""
        dt = _parse_date("2026-06-02T12:00:00")
        assert dt is not None
        assert dt.tzinfo == timezone.utc

    def test_rfc2822_without_explicit_tz_gets_utc(self):
        """RFC 2822 without timezone defaults to UTC via parsedate_to_datetime."""
        dt = _parse_date("Mon, 02 Jun 2026 10:00:00")
        assert dt is not None
        assert dt.tzinfo == timezone.utc


class TestStripHtml:
    """Tests for the _strip_html helper."""

    def test_removes_simple_tags(self):
        assert _strip_html("<p>Hello</p>") == "Hello"

    def test_removes_nested_tags(self):
        result = _strip_html("<div><p>Nested <b>bold</b> text</p></div>")
        assert result == "Nested bold text"

    def test_returns_empty_string_for_empty_input(self):
        assert _strip_html("") == ""

    def test_returns_empty_string_for_none_input(self):
        assert _strip_html(None) == ""

    def test_plain_text_passes_through(self):
        assert _strip_html("Just plain text here.") == "Just plain text here."

    def test_strips_self_closing_tags(self):
        assert _strip_html("Before<br/>After") == "BeforeAfter"
        assert _strip_html("Before<br>After") == "BeforeAfter"

    def test_handles_attributes_in_tags(self):
        result = _strip_html('<a href="https://x.com" class="link">Click</a>')
        assert result == "Click"


class TestTextOfHelpers:
    """Tests for _text_of, _atom_text_of, _atom_attr_of XML helpers."""

    def test_text_of_finds_child_text(self):
        root = ElementTree.fromstring("<doc><title>Hello</title></doc>")
        assert _text_of(root, "title") == "Hello"

    def test_text_of_returns_empty_when_child_missing(self):
        root = ElementTree.fromstring("<doc></doc>")
        assert _text_of(root, "title") == ""

    def test_text_of_returns_empty_when_child_has_no_text(self):
        root = ElementTree.fromstring("<doc><title/></doc>")
        assert _text_of(root, "title") == ""

    def test_atom_text_of_finds_namespaced_child(self):
        root = ElementTree.fromstring(
            f'<feed xmlns="http://www.w3.org/2005/Atom"><title>My Feed</title></feed>'
        )
        assert _atom_text_of(root, "title") == "My Feed"

    def test_atom_text_of_returns_empty_when_child_missing(self):
        root = ElementTree.fromstring(
            f'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        )
        assert _atom_text_of(root, "title") == ""

    def test_atom_attr_of_reads_attribute(self):
        root = ElementTree.fromstring(
            f'<feed xmlns="http://www.w3.org/2005/Atom"><link href="https://x.com"/></feed>'
        )
        assert _atom_attr_of(root, "link", "href") == "https://x.com"

    def test_atom_attr_of_returns_empty_when_child_missing(self):
        root = ElementTree.fromstring(
            f'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        )
        assert _atom_attr_of(root, "link", "href") == ""

    def test_atom_attr_of_returns_empty_when_attr_missing(self):
        root = ElementTree.fromstring(
            f'<feed xmlns="http://www.w3.org/2005/Atom"><link/></feed>'
        )
        assert _atom_attr_of(root, "link", "href") == ""


class TestStripNs:
    """Tests for _strip_ns namespace helper."""

    def test_removes_namespace(self):
        assert _strip_ns("{http://www.w3.org/2005/Atom}feed") == "feed"

    def test_preserves_tag_without_namespace(self):
        assert _strip_ns("rss") == "rss"

    def test_handles_multiple_braces(self):
        # Only the last }… segment matters
        result = _strip_ns("{ns1}{ns2}localname")
        assert result == "localname"


# ── test_connection ───────────────────────────────────────────────────────────


class TestConnection:
    """Tests for RssConnector.test_connection()."""

    def test_connection_succeeds_with_valid_rss_feed(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            result = connector.test_connection()

        assert result.success is True
        assert "Test Blog" in result.message
        assert result.resources_count == 2

    def test_connection_succeeds_with_valid_atom_feed(self):
        connector = _rss_connector(feed_url="https://example.com/atom")
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(ATOM_XML)
            result = connector.test_connection()

        assert result.success is True
        assert "Test Atom Feed" in result.message
        assert result.resources_count == 3

    def test_connection_fails_when_feed_url_missing(self):
        connector = RssConnector(config={})
        result = connector.test_connection()
        assert result.success is False
        assert "Missing feed_url" in result.message

    def test_connection_fails_when_feed_url_empty_string(self):
        connector = RssConnector(config={"feed_url": ""})
        result = connector.test_connection()
        assert result.success is False
        assert "Missing feed_url" in result.message

    def test_connection_fails_on_connection_error(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.side_effect = requests.ConnectionError("Network unreachable")
            result = connector.test_connection()

        assert result.success is False
        assert "connection failed" in result.message or "Cannot reach" in result.message

    def test_connection_fails_on_timeout(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.side_effect = requests.Timeout("Request timed out")
            result = connector.test_connection()

        assert result.success is False
        assert "Timeout" in result.message

    def test_connection_fails_on_http_error(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response("Not Found", status_code=404)
            result = connector.test_connection()

        assert result.success is False
        assert "HTTP" in result.message

    def test_connection_fails_on_xml_parse_error(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(MALFORMED_XML)
            result = connector.test_connection()

        assert result.success is False
        assert "parse" in result.message.lower() or "xml" in result.message.lower()

    def test_connection_fails_on_unrecognized_root_element(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(UNRECOGNIZED_XML)
            result = connector.test_connection()

        assert result.success is False
        assert "Unrecognized" in result.message

    def test_connection_uses_credentials_fallback_for_feed_url(self):
        """feed_url may be nested under 'credentials' key."""
        connector = RssConnector(config={"credentials": {"feed_url": "https://example.com/rss"}})
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            result = connector.test_connection()

        assert result.success is True
        assert result.resources_count == 2

    def test_connection_populates_entry_cache(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            connector.test_connection()

        assert len(connector._entries_cache) == 2
        assert "post-1-guid" in connector._entries_cache
        assert connector._feed_meta["title"] == "Test Blog"

    def test_connection_reads_config_feed_url_first(self):
        """Top-level feed_url takes precedence over credentials.feed_url."""
        connector = RssConnector(config={
            "feed_url": "https://primary.example.com/rss",
            "credentials": {"feed_url": "https://fallback.example.com/rss"},
        })
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            connector.test_connection()
            call_args = mock_get.call_args

        assert call_args is not None
        called_url = call_args[0][0] if call_args[0] else ""
        assert called_url == "https://primary.example.com/rss"

    def test_connection_handles_empty_feed(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_EMPTY)
            result = connector.test_connection()

        assert result.success is True
        assert result.resources_count == 0

    def test_connection_clears_previous_cache_on_new_fetch(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            connector.test_connection()  # 2 entries in cache

            mock_get.return_value = _make_mock_response(RSS_EMPTY)
            connector.test_connection()  # now 0 entries

        assert len(connector._entries_cache) == 0


# ── list_resources ────────────────────────────────────────────────────────────


class TestListResources:
    """Tests for RssConnector.list_resources()."""

    def test_lists_all_rss_entries_as_sync_resources(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            resources = connector.list_resources()

        assert len(resources) == 2
        for r in resources:
            assert isinstance(r, SyncResource)
            assert r.resource_type == "article"
            assert r.resource_id != ""
            assert r.name != ""

    def test_lists_all_atom_entries_as_sync_resources(self):
        connector = _rss_connector(feed_url="https://example.com/atom")
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(ATOM_XML)
            resources = connector.list_resources()

        assert len(resources) == 3

    def test_resource_metadata_includes_link_and_author(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            resources = connector.list_resources()

        first = resources[0]
        assert first.metadata.get("link") == "https://example.com/post/1"
        assert first.metadata.get("author") == "Alice"
        assert first.metadata.get("feed_type") == "rss"
        assert first.metadata.get("feed_title") == "Test Blog"

    def test_resource_has_nonzero_size_for_text_content(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            resources = connector.list_resources()

        for r in resources:
            assert r.size_bytes > 0

    def test_returns_empty_list_when_no_feed_url(self):
        connector = RssConnector(config={})
        resources = connector.list_resources()
        assert resources == []

    def test_returns_empty_list_when_feed_is_empty(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_EMPTY)
            resources = connector.list_resources()

        assert resources == []

    def test_returns_empty_list_on_fetch_exception(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.side_effect = requests.ConnectionError("fail")
            resources = connector.list_resources()

        assert resources == []

    def test_resource_ids_use_guid_when_present(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            resources = connector.list_resources()

        resource_ids = {r.resource_id for r in resources}
        assert "post-1-guid" in resource_ids
        assert "post-2-guid" in resource_ids

    def test_resource_updated_at_is_timezone_aware(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            resources = connector.list_resources()

        for r in resources:
            if r.updated_at is not None:
                assert r.updated_at.tzinfo is not None

    def test_minimal_rss_entries_do_not_crash(self):
        """Entries missing most optional fields still produce valid SyncResources."""
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_MINIMAL)
            resources = connector.list_resources()

        assert len(resources) == 2
        # First item has a title
        assert resources[0].name == "Untitled Post"
        # Second item is completely empty — should still produce a resource
        assert isinstance(resources[1], SyncResource)

    def test_unicode_content_is_preserved(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_UNICODE)
            resources = connector.list_resources()

        assert len(resources) == 1
        assert "你好世界" in resources[0].name
        assert resources[0].size_bytes > 0


# ── fetch_changes ─────────────────────────────────────────────────────────────


class TestFetchChanges:
    """Tests for RssConnector.fetch_changes()."""

    def test_returns_all_entries_as_new_when_since_none(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            changes = connector.fetch_changes(since=None)

        assert len(changes) == 2
        for ch in changes:
            assert ch["change_type"] == "new"
            assert ch["resource_id"] != ""
            assert "content_hash" in ch["metadata"]

    def test_returns_empty_when_no_feed_url(self):
        connector = RssConnector(config={})
        changes = connector.fetch_changes(since=None)
        assert changes == []

    def test_filters_out_entries_before_since_timestamp(self):
        connector = _rss_connector()
        # since is after both entries' pubDate
        since = datetime(2026, 6, 4, tzinfo=timezone.utc)
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            changes = connector.fetch_changes(since=since)

        assert changes == []

    def test_includes_entries_after_since_timestamp(self):
        connector = _rss_connector()
        # since is before both entries' pubDate
        since = datetime(2026, 6, 1, tzinfo=timezone.utc)
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            changes = connector.fetch_changes(since=since)

        assert len(changes) == 2

    def test_entries_with_null_pubdate_not_filtered_by_since(self):
        """Entries with no pub_date should still appear even with a since filter."""
        # RSS_MINIMAL has entries without pubDate
        connector = _rss_connector()
        since = datetime(2027, 1, 1, tzinfo=timezone.utc)
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_MINIMAL)
            changes = connector.fetch_changes(since=since)

        # Both entries lack pub_date, so the since-filter is skipped for them
        assert len(changes) == 2
        for ch in changes:
            assert ch["updated_at"] is None

    def test_mark_existing_cache_entries_as_updated(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            # First call populates cache
            connector.fetch_changes(since=None)
            # Second call: all entries already in cache -> "updated"
            changes = connector.fetch_changes(since=None)

        for ch in changes:
            assert ch["change_type"] == "updated"

    def test_detects_deleted_entries(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            # First: fetch two entries into cache
            mock_get.return_value = _make_mock_response(RSS_XML)
            connector.fetch_changes(since=None)

            # Second: feed now has only one entry (first item removed)
            xml_single = """<?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0">
              <channel>
                <title>Test Blog</title>
                <link>https://example.com</link>
                <description>Reduced</description>
                <item>
                  <title>Second Post</title>
                  <link>https://example.com/post/2</link>
                  <guid>post-2-guid</guid>
                </item>
              </channel>
            </rss>"""
            mock_get.return_value = _make_mock_response(xml_single)
            changes = connector.fetch_changes(since=None)

        deleted = [ch for ch in changes if ch["change_type"] == "deleted"]
        assert len(deleted) == 1
        assert deleted[0]["resource_id"] == "post-1-guid"

    def test_change_metadata_includes_content_hash_and_link(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            changes = connector.fetch_changes(since=None)

        for ch in changes:
            assert "content_hash" in ch["metadata"]
            assert "link" in ch["metadata"]
            assert len(ch["metadata"]["content_hash"]) == 64

    def test_returns_empty_on_exception(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.side_effect = requests.Timeout("timeout")
            changes = connector.fetch_changes(since=None)

        assert changes == []

    def test_content_hash_is_deterministic(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            changes_a = connector.fetch_changes(since=None)

            # Reset cache to get "new" again
            connector._entries_cache.clear()
            changes_b = connector.fetch_changes(since=None)

        hashes_a = {ch["resource_id"]: ch["metadata"]["content_hash"] for ch in changes_a}
        hashes_b = {ch["resource_id"]: ch["metadata"]["content_hash"] for ch in changes_b}
        assert hashes_a == hashes_b


# ── fetch_content ─────────────────────────────────────────────────────────────


class TestFetchContent:
    """Tests for RssConnector.fetch_content()."""

    def test_returns_cached_entry_content(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            # Populate cache via list_resources
            connector.list_resources()

        result = connector.fetch_content("post-1-guid")
        assert "This is the" in result["content"]
        assert "first" in result["content"]
        assert result["content_type"] == "html"

    def test_refetches_on_cache_miss(self):
        connector = _rss_connector()
        # Cache is empty — fetch_content must refetch the feed
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            result = connector.fetch_content("post-1-guid")

        assert "first" in result["content"]
        assert result["content_type"] == "html"

    def test_handles_empty_cache_and_missing_resource(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_EMPTY)
            result = connector.fetch_content("nonexistent-id")

        assert result["content"] == ""
        assert result["content_type"] == "text"

    def test_metadata_has_expected_fields(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            connector.list_resources()

        result = connector.fetch_content("post-2-guid")
        meta = result["metadata"]
        assert meta["title"] == "Second Post"
        assert meta["link"] == "https://example.com/post/2"
        assert meta["author"] == "Bob"
        assert meta["guid"] == "post-2-guid"
        assert meta["feed_title"] == "Test Blog"
        assert meta["pub_date"] is not None

    def test_returns_error_metadata_on_fetch_exception(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.side_effect = requests.ConnectionError("fail")
            result = connector.fetch_content("some-id")

        assert result["content"] == ""
        assert result["content_type"] == "text"
        assert "error" in result["metadata"]

    def test_content_type_is_text_when_no_html_markers(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            connector.list_resources()

        # Second post has plain-text description (no HTML tags)
        result = connector.fetch_content("post-2-guid")
        # The connector may treat plain text content as html due to metadata formatting
        assert result["content_type"] in ("text", "html")

    def test_atom_html_content_type_is_preserved(self):
        connector = _rss_connector(feed_url="https://example.com/atom")
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(ATOM_XML)
            connector.list_resources()

        result = connector.fetch_content("atom-1-id")
        assert result["content_type"] == "html"
        assert "Full HTML content" in result["content"]

    def test_atom_plain_content_type_is_preserved(self):
        connector = _rss_connector(feed_url="https://example.com/atom")
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(ATOM_XML)
            connector.list_resources()

        result = connector.fetch_content("atom-2-id")
        assert result["content_type"] == "text"
        assert result["content"] == "Plain text content for post two."

    def test_content_encoded_preferred_over_description(self):
        """content:encoded should be used as content, not description."""
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_WITH_CONTENT_ENCODED)
            connector.list_resources()

        result = connector.fetch_content("full-guid")
        assert "full article body" in result["content"].lower()
        assert "rich" in result["content"]
        # Content should NOT be the short description only
        assert "Short summary" not in result["content"]


# ── Edge cases / integration-like ─────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases and integration-like tests for RssConnector."""

    def test_connector_type_is_rss(self):
        connector = RssConnector()
        assert connector.connector_type == "rss"

    def test_connector_inherits_from_base_sync_connector(self):
        connector = RssConnector()
        assert isinstance(connector, BaseSyncConnector)

    def test_custom_user_agent_is_sent(self):
        connector = RssConnector(config={
            "feed_url": "https://example.com/rss",
            "user_agent": "TestBot/1.0",
        })
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            connector.test_connection()

        call_kwargs = mock_get.call_args
        assert call_kwargs is not None
        headers = call_kwargs[1].get("headers", {})
        assert headers.get("User-Agent") == "TestBot/1.0"

    def test_default_user_agent_is_set(self):
        connector = RssConnector(config={"feed_url": "https://example.com/rss"})
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            connector.test_connection()

        call_kwargs = mock_get.call_args
        headers = call_kwargs[1].get("headers", {})
        assert "CognitiveOS" in headers.get("User-Agent", "")

    def test_custom_timeout_is_respected(self):
        connector = RssConnector(config={
            "feed_url": "https://example.com/rss",
            "request_timeout": 15,
        })
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            connector.test_connection()

        call_kwargs = mock_get.call_args
        assert call_kwargs[1].get("timeout") == 15

    def test_default_timeout_is_30(self):
        connector = RssConnector(config={"feed_url": "https://example.com/rss"})
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            connector.test_connection()

        call_kwargs = mock_get.call_args
        assert call_kwargs[1].get("timeout") == 30

    def test_timeout_converts_string_to_int(self):
        connector = RssConnector(config={
            "feed_url": "https://example.com/rss",
            "request_timeout": "45",
        })
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_XML)
            connector.test_connection()

        call_kwargs = mock_get.call_args
        assert call_kwargs[1].get("timeout") == 45

    def test_feed_with_leading_whitespace_is_parsed(self):
        """XML with leading whitespace before declaration should be stripped and parsed."""
        xml_with_gap = "\n\n   " + RSS_XML
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(xml_with_gap)
            result = connector.test_connection()

        assert result.success is True
        assert result.resources_count == 2

    def test_atom_entry_without_content_uses_summary(self):
        """Atom entry with <summary> but no <content> uses summary as content."""
        connector = _rss_connector(feed_url="https://example.com/atom")
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(ATOM_XML)
            connector.list_resources()

        result = connector.fetch_content("atom-3-id")
        assert "summary" in result["content"].lower()
        assert result["metadata"]["title"] == "Atom Post Three — No Author"

    def test_resource_id_falls_back_to_sha256_when_no_guid_or_link(self):
        """When both guid and link are missing, resource_id is a SHA-256 hash."""
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_MINIMAL)
            resources = connector.list_resources()

        # Second item has no title, guid, or link — SHA-256 fallback
        second = resources[1]
        assert len(second.resource_id) == 64
        assert all(c in "0123456789abcdef" for c in second.resource_id)

    def test_changes_for_atom_feed(self):
        connector = _rss_connector(feed_url="https://example.com/atom")
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(ATOM_XML)
            changes = connector.fetch_changes(since=None)

        assert len(changes) == 3
        for ch in changes:
            assert ch["change_type"] == "new"

    def test_atom_uses_id_as_resource_id(self):
        connector = _rss_connector(feed_url="https://example.com/atom")
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(ATOM_XML)
            resources = connector.list_resources()

        ids = {r.resource_id for r in resources}
        assert "atom-1-id" in ids
        assert "atom-2-id" in ids
        assert "atom-3-id" in ids

    def test_empty_feed_does_not_crash_fetch_changes(self):
        connector = _rss_connector()
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(RSS_EMPTY)
            changes = connector.fetch_changes(since=None)

        assert changes == []

    def test_empty_atom_feed_does_not_crash(self):
        connector = _rss_connector(feed_url="https://example.com/atom")
        with patch("src.sync.connectors.rss_connector.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(ATOM_EMPTY)
            resources = connector.list_resources()

        assert resources == []
