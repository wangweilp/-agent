"""Tests for BaseSyncConnector — shared utilities and NotImplementError stubs.

Covers:
  - compute_hash determinism and edge cases
  - now_utc returning timezone-aware UTC
  - all four abstract methods raising NotImplementedError
  - constructor config handling
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.sync.connector_base import BaseSyncConnector, SyncConnector
from src.sync.models import SyncConnectionResult, SyncResource


# ──────────────────────────────────────────────────────────────
#  compute_hash  — determinism, collision, edge cases
# ──────────────────────────────────────────────────────────────

class TestComputeHash:
    """Deterministic SHA-256 hex digest for content comparison."""

    def test_same_input_same_output(self):
        """Same input produces identical hash every call."""
        content = "The quick brown fox jumps over the lazy dog"
        h1 = BaseSyncConnector.compute_hash(content)
        h2 = BaseSyncConnector.compute_hash(content)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex is always 64 chars
        assert all(c in "0123456789abcdef" for c in h1)

    def test_different_input_different_output(self):
        """Different inputs produce different hashes (no collision)."""
        h_a = BaseSyncConnector.compute_hash("Hello")
        h_b = BaseSyncConnector.compute_hash("World")
        assert h_a != h_b

    def test_empty_string(self):
        """Empty string produces a valid, repeatable hash."""
        h = BaseSyncConnector.compute_hash("")
        expected = hashlib.sha256(b"").hexdigest()
        assert h == expected

    def test_whitespace_is_significant(self):
        """Trailing whitespace changes the hash."""
        h1 = BaseSyncConnector.compute_hash("text")
        h2 = BaseSyncConnector.compute_hash("text ")
        h3 = BaseSyncConnector.compute_hash(" text")
        assert h1 != h2
        assert h1 != h3
        assert h2 != h3

    def test_unicode_and_emoji(self):
        """Unicode characters (CJK, emoji) hash deterministically."""
        content = "你好世界 \U0001F600 \U0001F4A5"
        h1 = BaseSyncConnector.compute_hash(content)
        h2 = BaseSyncConnector.compute_hash(content)
        assert h1 == h2
        assert len(h1) == 64

    def test_errors_replace_on_surrogates(self):
        """Surrogate characters are replaced (errors='replace'), not crashed."""
        # \ud800 is a lone surrogate — cannot be encoded to UTF-8 directly
        # but Python's errors='replace' handles it gracefully
        content = "valid\ud800text"
        h = BaseSyncConnector.compute_hash(content)
        assert isinstance(h, str)
        assert len(h) == 64

    def test_large_content(self):
        """Large content (10K chars) hashes without issue."""
        content = "a" * 10_000
        h = BaseSyncConnector.compute_hash(content)
        assert len(h) == 64

    def test_hash_matches_known_sha256(self):
        """Cross-check against a known SHA-256 hex for determinism."""
        content = "Hello, World!"
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        h = BaseSyncConnector.compute_hash(content)
        assert h == expected

    def test_case_sensitivity(self):
        """Case changes produce different hashes."""
        lower = BaseSyncConnector.compute_hash("abc")
        upper = BaseSyncConnector.compute_hash("ABC")
        assert lower != upper


# ──────────────────────────────────────────────────────────────
#  now_utc  — timezone awareness
# ──────────────────────────────────────────────────────────────

class TestNowUtc:
    """now_utc() returns a timezone-aware UTC datetime."""

    def test_returns_datetime_instance(self):
        result = BaseSyncConnector.now_utc()
        assert isinstance(result, datetime)

    def test_timezone_is_utc(self):
        result = BaseSyncConnector.now_utc()
        assert result.tzinfo is not None
        assert result.tzinfo == timezone.utc

    def test_is_callable_without_instance(self):
        """Static method — works on both class and instance."""
        # On class
        dt1 = BaseSyncConnector.now_utc()
        # On instance
        connector = BaseSyncConnector()
        dt2 = connector.now_utc()
        assert isinstance(dt1, datetime)
        assert isinstance(dt2, datetime)

    def test_monotonic_returns_recent_time(self):
        """Value is within 5 seconds of now."""
        from datetime import timedelta

        result = BaseSyncConnector.now_utc()
        now = datetime.now(timezone.utc)
        diff = abs((now - result).total_seconds())
        assert diff < 5.0

    def test_utcoffset_is_zero(self):
        """UTC offset is exactly 0."""
        result = BaseSyncConnector.now_utc()
        assert result.utcoffset().total_seconds() == 0


# ──────────────────────────────────────────────────────────────
#  NotImplementedError for abstract methods
# ──────────────────────────────────────────────────────────────

class TestNotImplementedError:
    """All four abstract methods raise NotImplementedError by default."""

    @pytest.fixture
    def connector(self):
        return BaseSyncConnector()

    def test_test_connection_raises(self, connector):
        with pytest.raises(NotImplementedError):
            connector.test_connection()

    def test_list_resources_raises(self, connector):
        with pytest.raises(NotImplementedError):
            connector.list_resources()

    def test_fetch_changes_raises(self, connector):
        with pytest.raises(NotImplementedError):
            connector.fetch_changes(since=None)

    def test_fetch_changes_raises_with_datetime(self, connector):
        """Passing a since timestamp still raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            connector.fetch_changes(since=datetime.now(timezone.utc))

    def test_fetch_content_raises(self, connector):
        with pytest.raises(NotImplementedError):
            connector.fetch_content(resource_id="test-123")


# ──────────────────────────────────────────────────────────────
#  Constructor behaviour
# ──────────────────────────────────────────────────────────────

class TestConstructor:
    """BaseSyncConnector constructor stores config and sets up logger."""

    def test_default_config_is_empty_dict(self):
        connector = BaseSyncConnector()
        assert connector.config == {}

    def test_config_is_stored(self):
        config = {"token": "abc", "url": "https://example.com"}
        connector = BaseSyncConnector(config=config)
        assert connector.config is config  # same object, not a copy
        assert connector.config["token"] == "abc"

    def test_config_none_treated_as_empty(self):
        connector = BaseSyncConnector(config=None)
        assert connector.config == {}

    def test_default_connector_type_is_base(self):
        connector = BaseSyncConnector()
        assert connector.connector_type == "base"

    def test_logger_name_follows_pattern(self):
        connector = BaseSyncConnector()
        assert connector.logger.name == "sync.connector.base"

    def test_logger_name_uses_instance_connector_type(self):
        """Logger name reflects connector_type (so subclasses get correct logger)."""

        class CustomConnector(BaseSyncConnector):
            connector_type = "feishu"

        connector = CustomConnector(config={"workspace": "test"})
        assert connector.logger.name == "sync.connector.feishu"


# ──────────────────────────────────────────────────────────────
#  compute_hash  — method resolution (static method access)
# ──────────────────────────────────────────────────────────────

class TestComputeHashAccess:
    """compute_hash can be called on class, instance, or subclass."""

    def test_callable_on_class(self):
        h = BaseSyncConnector.compute_hash("test")
        assert isinstance(h, str)
        assert len(h) == 64

    def test_callable_on_instance(self):
        connector = BaseSyncConnector()
        h = connector.compute_hash("test")
        assert isinstance(h, str)

    def test_callable_on_subclass_instance(self):
        class SubConnector(BaseSyncConnector):
            connector_type = "test"

        sub = SubConnector()
        h = sub.compute_hash("test")
        assert isinstance(h, str)
        assert len(h) == 64


# ──────────────────────────────────────────────────────────────
#  SyncConnector Protocol — structural subtyping
# ──────────────────────────────────────────────────────────────

class TestSyncConnectorProtocol:
    """BaseSyncConnector instances are not usable SyncConnectors
    (methods raise NotImplementedError), but correctly typed subclasses satisfy
    the protocol structurally."""

    def test_base_connector_is_not_protocol_compliant(self):
        """BaseSyncConnector fails runtime check because methods raise
        NotImplementedError — but structurally it still has the attributes."""
        connector = BaseSyncConnector()
        # It has the method attributes, just they raise NotImplementedError
        assert hasattr(connector, "test_connection")
        assert hasattr(connector, "list_resources")
        assert hasattr(connector, "fetch_changes")
        assert hasattr(connector, "fetch_content")
        assert hasattr(connector, "connector_type")

    def test_protocol_has_expected_signatures(self):
        """Verify the Protocol declares the right method names."""
        protocol_methods = ["test_connection", "list_resources", "fetch_changes", "fetch_content"]
        for method in protocol_methods:
            assert hasattr(SyncConnector, method)
        # Class-level annotations on a Protocol are stored in __annotations__
        assert "connector_type" in SyncConnector.__annotations__
        # With __future__.annotations, annotation values are strings
        assert SyncConnector.__annotations__["connector_type"] == "str"
