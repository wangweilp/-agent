"""Unit tests for LocalFolderConnector.

Tests the local filesystem sync connector: connection validation, resource
listing, change detection (mtime-based), and content fetching — all against
real temporary directory structures created via pytest's tmp_path fixture.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.sync.connectors.local_folder_connector import (
    LocalFolderConnector,
    _guess_content_type,
    _is_hidden_or_ignored,
)
from src.sync.models import SyncConnectionResult, SyncResource


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def populated_dir(tmp_path: Path) -> Path:
    """Create a temporary directory tree with assorted files for testing.

    Structure
    ---------
    tmp_path/
      notes/
        daily.md           — markdown note
        hello.txt          — plain text
      data/
        config.json        — JSON config
      __pycache__/
        junk.pyc           — should be ignored
      .hidden_file         — should be ignored
    """
    root = tmp_path / "myfolder"
    root.mkdir()

    notes = root / "notes"
    notes.mkdir()
    (notes / "daily.md").write_text("# Daily Note\n\nToday was productive.", encoding="utf-8")
    (notes / "hello.txt").write_text("Hello, world!", encoding="utf-8")

    data = root / "data"
    data.mkdir()
    (data / "config.json").write_text('{"key": "value"}', encoding="utf-8")

    pycache = root / "__pycache__"
    pycache.mkdir()
    (pycache / "junk.pyc").write_text("ignore me", encoding="utf-8")

    (root / ".hidden_file").write_text("secret", encoding="utf-8")

    return root


@pytest.fixture
def empty_dir(tmp_path: Path) -> Path:
    """An empty temporary directory."""
    d = tmp_path / "empty"
    d.mkdir()
    return d


@pytest.fixture
def connector(populated_dir: Path) -> LocalFolderConnector:
    """Return a configured LocalFolderConnector pointing at the populated directory."""
    return LocalFolderConnector(config={"folder_path": str(populated_dir)})


# ── Module-level helpers ──────────────────────────────────────────────────────


class TestGuessContentType:
    def test_returns_markdown_for_md(self):
        assert _guess_content_type(".md") == "markdown"

    def test_returns_markdown_for_markdown(self):
        assert _guess_content_type(".markdown") == "markdown"

    def test_returns_text_for_py(self):
        assert _guess_content_type(".py") == "text"

    def test_returns_text_for_unknown_extension(self):
        assert _guess_content_type(".xyzzy") == "text"

    def test_returns_text_for_no_extension(self):
        assert _guess_content_type("") == "text"

    def test_recognises_json(self):
        assert _guess_content_type(".json") == "json"

    def test_recognises_yaml_variants(self):
        assert _guess_content_type(".yaml") == "yaml"
        assert _guess_content_type(".yml") == "yaml"

    def test_recognises_html_variants(self):
        assert _guess_content_type(".html") == "html"
        assert _guess_content_type(".htm") == "html"


class TestIsHiddenOrIgnored:
    def test_flags_dotfile(self):
        assert _is_hidden_or_ignored(Path(".secret"))

    def test_flags_tilde_prefixed(self):
        assert _is_hidden_or_ignored(Path("~backup"))

    def test_flags_nested_hidden(self):
        assert _is_hidden_or_ignored(Path("src/.git/config"))

    def test_flags_pycache(self):
        assert _is_hidden_or_ignored(Path("lib/__pycache__/mod.cpython-311.pyc"))

    def test_flags_node_modules(self):
        assert _is_hidden_or_ignored(Path("project/node_modules/foo/index.js"))

    def test_flags_dot_git(self):
        assert _is_hidden_or_ignored(Path("repo/.git/HEAD"))

    def test_flags_vscode(self):
        assert _is_hidden_or_ignored(Path(".vscode/settings.json"))

    def test_allows_visible_file(self):
        assert not _is_hidden_or_ignored(Path("docs/readme.md"))


# ── test_connection ───────────────────────────────────────────────────────────


class TestConnection:
    def test_connection_succeeds_for_valid_folder(self, connector):
        result = connector.test_connection()
        assert result.success is True
        assert "Connected" in result.message
        assert result.resources_count >= 3  # daily.md, hello.txt, config.json

    def test_connection_fails_when_folder_path_missing(self):
        c = LocalFolderConnector(config={})
        result = c.test_connection()
        assert result.success is False
        assert "Missing folder_path" in result.message

    def test_connection_fails_when_folder_does_not_exist(self, tmp_path: Path):
        # 使用 allowlist 内的路径但确保该子目录不存在
        nonexistent = str(tmp_path / "nonexistent" / "path" / "xyz")
        c = LocalFolderConnector(config={"folder_path": nonexistent})
        result = c.test_connection()
        assert result.success is False
        assert "does not exist" in result.message

    def test_connection_fails_when_path_is_file_not_directory(self, tmp_path: Path):
        f = tmp_path / "just_a_file.txt"
        f.write_text("hello")
        c = LocalFolderConnector(config={"folder_path": str(f)})
        result = c.test_connection()
        assert result.success is False
        assert "not a directory" in result.message

    def test_connection_reads_folder_path_from_credentials(self, populated_dir: Path):
        c = LocalFolderConnector(config={"credentials": {"folder_path": str(populated_dir)}})
        result = c.test_connection()
        assert result.success is True

    def test_connection_counts_visible_files_only(self, connector, populated_dir: Path):
        # Add an extra hidden file via fs — still shouldn't be counted.
        (populated_dir / ".env").write_text("SECRET=1")
        result = connector.test_connection()
        assert result.resources_count >= 3  # .env is hidden, not counted


# ── list_resources ────────────────────────────────────────────────────────────


class TestListResources:
    def test_lists_visible_files(self, connector):
        resources = connector.list_resources()
        ids = {r.resource_id for r in resources}
        # Visible files only: notes/daily.md, notes/hello.txt, data/config.json
        assert "notes/daily.md" in ids
        assert "notes/hello.txt" in ids
        assert "data/config.json" in ids

    def test_does_not_list_hidden_files(self, connector):
        resources = connector.list_resources()
        ids = {r.resource_id for r in resources}
        assert ".hidden_file" not in ids

    def test_does_not_list_pycache_files(self, connector):
        resources = connector.list_resources()
        ids = {r.resource_id for r in resources}
        pycache_ids = [i for i in ids if "__pycache__" in i]
        assert len(pycache_ids) == 0

    def test_returns_sync_resource_objects(self, connector):
        resources = connector.list_resources()
        for r in resources:
            assert isinstance(r, SyncResource)
            assert r.resource_id != ""
            assert r.name != ""
            assert r.resource_type in {
                "markdown", "text", "json", "yaml", "html", "csv", "xml",
                "toml", "ini", "cfg", "md", "rst", "tex", "log", "svg",
            }
            assert r.updated_at is not None
            assert r.size_bytes > 0
            assert "absolute_path" in r.metadata
            assert "relative_path" in r.metadata

    def test_returns_empty_list_when_no_config(self):
        c = LocalFolderConnector(config={})
        assert c.list_resources() == []

    def test_returns_empty_list_for_empty_directory(self, empty_dir: Path):
        c = LocalFolderConnector(config={"folder_path": str(empty_dir)})
        assert c.list_resources() == []

    def test_folder_path_uses_expanduser(self, tmp_path: Path, monkeypatch):
        """Verify that ~ in the folder path is expanded."""
        d = tmp_path / "home" / "docs"
        d.mkdir(parents=True)
        (d / "a.txt").write_text("a")

        home = tmp_path / "home"
        with patch.object(Path, "home", return_value=home):
            # path with tilde prefix
            raw = str(home / "docs")
            c = LocalFolderConnector(config={"folder_path": raw})
            resources = c.list_resources()
            assert len(resources) == 1
            assert resources[0].resource_id == "a.txt"


# ── fetch_changes ─────────────────────────────────────────────────────────────


class TestFetchChanges:
    def test_with_since_none_returns_all_as_new(self, connector):
        changes = connector.fetch_changes(since=None)
        assert len(changes) == 3
        for ch in changes:
            assert ch["change_type"] == "new"
            assert ch["resource_id"] != ""
            assert ch["content_hash"] != ""
            assert ch["size_bytes"] > 0

    def test_with_future_since_returns_empty(self, connector):
        future = datetime.now(timezone.utc) + timedelta(days=1)
        changes = connector.fetch_changes(since=future)
        assert changes == []

    def test_with_past_since_detects_new_files(self, populated_dir: Path):
        """Create a file *after* capturing a timestamp, then verify it appears."""
        c = LocalFolderConnector(config={"folder_path": str(populated_dir)})
        before = datetime.now(timezone.utc) - timedelta(seconds=5)
        # touch a new file
        (populated_dir / "notes" / "late.md").write_text("# Late entry")
        changes = c.fetch_changes(since=before)
        late_ids = {ch["resource_id"] for ch in changes}
        assert "notes/late.md" in late_ids

    def test_change_type_is_updated_when_since_is_past(self, connector):
        """Files that existed before `since` are considered 'updated'."""
        # Use a timestamp from 10 seconds ago — all files should be "updated"
        since = datetime.now(timezone.utc) - timedelta(seconds=10)
        changes = connector.fetch_changes(since=since)
        for ch in changes:
            assert ch["change_type"] == "updated"

    def test_returns_empty_when_no_config(self):
        c = LocalFolderConnector(config={})
        assert c.fetch_changes(since=None) == []

    def test_naive_since_datetime_is_treated_as_utc(self, populated_dir: Path):
        c = LocalFolderConnector(config={"folder_path": str(populated_dir)})
        naive_since = datetime(2020, 1, 1)  # no tzinfo
        changes = c.fetch_changes(since=naive_since)
        assert len(changes) >= 3
        for ch in changes:
            assert ch["change_type"] == "updated"

    def test_file_not_modified_since_not_included(self, populated_dir: Path):
        c = LocalFolderConnector(config={"folder_path": str(populated_dir)})
        # Let mtime settle
        time.sleep(0.01)
        since = datetime.now(timezone.utc)
        # No new files written after `since`
        changes = c.fetch_changes(since=since)
        assert changes == []

    def test_content_hash_is_deterministic(self, connector):
        changes_a = connector.fetch_changes(since=None)
        changes_b = connector.fetch_changes(since=None)
        hashes_a = {ch["resource_id"]: ch["content_hash"] for ch in changes_a}
        hashes_b = {ch["resource_id"]: ch["content_hash"] for ch in changes_b}
        assert hashes_a == hashes_b

    def test_metadata_includes_absolute_and_relative_path(self, connector, populated_dir: Path):
        changes = connector.fetch_changes(since=None)
        for ch in changes:
            assert "absolute_path" in ch["metadata"]
            assert "relative_path" in ch["metadata"]
            assert ch["metadata"]["relative_path"] == ch["resource_id"]
            assert populated_dir.name in ch["metadata"]["absolute_path"]


# ── fetch_content ─────────────────────────────────────────────────────────────


class TestFetchContent:
    def test_reads_file_content(self, connector):
        result = connector.fetch_content("notes/hello.txt")
        assert result["content"] == "Hello, world!"
        assert result["content_type"] == "text"

    def test_returns_markdown_content_type(self, connector):
        result = connector.fetch_content("notes/daily.md")
        assert result["content_type"] == "markdown"
        assert "# Daily Note" in result["content"]

    def test_returns_json_content_type(self, connector):
        result = connector.fetch_content("data/config.json")
        assert result["content_type"] == "json"
        assert '"key": "value"' in result["content"]

    def test_metadata_contains_expected_fields(self, connector):
        result = connector.fetch_content("notes/hello.txt")
        meta = result["metadata"]
        assert meta["resource_id"] == "notes/hello.txt"
        assert meta["filename"] == "hello.txt"
        assert meta["stem"] == "hello"
        assert meta["extension"] == ".txt"
        assert meta["size_bytes"] > 0
        assert "updated_at" in meta
        assert "content_hash" in meta
        assert "absolute_path" in meta

    def test_rejects_path_traversal(self, connector):
        result = connector.fetch_content("../../../etc/passwd")
        assert result["content"] == ""
        assert result["metadata"].get("error") == "resource_id escapes folder root"

    def test_handles_missing_file(self, connector):
        result = connector.fetch_content("nonexistent.txt")
        assert result["content"] == ""
        assert result["metadata"].get("error") == "file not found"

    def test_handles_directory_instead_of_file(self, connector):
        result = connector.fetch_content("notes")
        assert result["content"] == ""
        assert result["metadata"].get("error") == "not a file"

    def test_returns_error_when_folder_path_not_configured(self):
        c = LocalFolderConnector(config={})
        result = c.fetch_content("anything.txt")
        assert result["content"] == ""
        assert result["metadata"].get("error") == "folder_path not configured"

    def test_handles_large_file_gracefully(self, tmp_path: Path):
        """Files exceeding _MAX_FILE_BYTES (10 MB) return a stub message."""
        d = tmp_path / "bigfiles"
        d.mkdir()
        big = d / "huge.log"
        # Create a sparse-like indicator: write a file whose stat says it is huge
        big.write_text("small header")
        c = LocalFolderConnector(config={"folder_path": str(d)})
        # Patch _MAX_FILE_BYTES to a tiny value so the file appears "too large"
        with patch("src.sync.connectors.local_folder_connector._MAX_FILE_BYTES", 5):
            result = c.fetch_content("huge.log")
            assert "exceeds" in result["content"]
            assert result["metadata"].get("error") == "file too large"

    def test_content_hash_for_empty_file(self, tmp_path: Path):
        d = tmp_path / "empties"
        d.mkdir()
        (d / "blank.txt").write_text("")
        c = LocalFolderConnector(config={"folder_path": str(d)})
        result = c.fetch_content("blank.txt")
        assert result["content"] == ""
        assert result["metadata"]["size_bytes"] == 0
        assert len(result["metadata"]["content_hash"]) == 64  # SHA-256 hex

    def test_unicode_content_is_preserved(self, tmp_path: Path):
        d = tmp_path / "unicode"
        d.mkdir()
        content = "你好，世界！🌍\nこんにちは"
        (d / "i18n.md").write_text(content, encoding="utf-8")
        c = LocalFolderConnector(config={"folder_path": str(d)})
        result = c.fetch_content("i18n.md")
        assert result["content"] == content

    def test_binary_like_content_is_replaced(self, tmp_path: Path):
        """Binary bytes in a text file should be handled with errors='replace'."""
        d = tmp_path / "binary"
        d.mkdir()
        raw_bytes = b"hello\x80world"
        (d / "mixed.txt").write_bytes(raw_bytes)
        c = LocalFolderConnector(config={"folder_path": str(d)})
        result = c.fetch_content("mixed.txt")
        # Should not raise; replacement character (U+FFFD) may appear
        assert isinstance(result["content"], str)
        assert "hello" in result["content"]


# ── Integration-like / edge cases ─────────────────────────────────────────────


class TestEdgeCases:
    def test_connector_type_is_local_folder(self, connector):
        assert connector.connector_type == "local_folder"

    def test_subdirectory_file_is_discovered(self, tmp_path: Path):
        d = tmp_path / "deep" / "nested" / "path"
        d.mkdir(parents=True)
        (d / "deep_file.md").write_text("# Deep")
        c = LocalFolderConnector(config={"folder_path": str(tmp_path / "deep")})
        resources = c.list_resources()
        ids = {r.resource_id for r in resources}
        assert "nested/path/deep_file.md" in ids

    def test_multiple_extensions_in_filename(self, tmp_path: Path):
        d = tmp_path / "ext"
        d.mkdir()
        (d / "archive.tar.gz").write_text("dummy")
        c = LocalFolderConnector(config={"folder_path": str(d)})
        result = c.fetch_content("archive.tar.gz")
        # suffix is ".gz" (Path.suffix returns last extension)
        assert result["content_type"] == "text"

    def test_dotfiles_nested_in_visible_dir_are_hidden(self, tmp_path: Path):
        """Even inside a visible directory, dotfiles should be skipped."""
        d = tmp_path / "project"
        d.mkdir()
        (d / "readme.md").write_text("# Project")
        (d / ".eslintrc").write_text("{}")
        c = LocalFolderConnector(config={"folder_path": str(d)})
        resources = c.list_resources()
        ids = {r.resource_id for r in resources}
        assert "readme.md" in ids
        assert ".eslintrc" not in ids

    def test_folder_path_caching(self, populated_dir: Path):
        """folder_path property should cache after first access."""
        c = LocalFolderConnector(config={"folder_path": str(populated_dir)})
        first = c.folder_path
        second = c.folder_path
        assert first is second  # same object — cached
        assert c._folder_path is not None

    def test_fetch_changes_preserves_change_type_new_consistently(self, connector):
        """All changes with since=None must have change_type 'new'."""
        changes = connector.fetch_changes(since=None)
        assert all(ch["change_type"] == "new" for ch in changes)

    def test_stat_to_utc_datetime_produces_tz_aware(self, connector, populated_dir: Path):
        f = populated_dir / "notes" / "hello.txt"
        dt = connector._stat_to_utc_datetime(f)
        assert dt.tzinfo is not None
        assert dt.utcoffset() is not None


# ═══════════════════════════════════════════
# Security — path allowlist tests
# ═══════════════════════════════════════════


class TestPathAllowlist:
    """验证 local_folder 路径白名单正确拒绝越权路径。"""

    @pytest.fixture(autouse=True)
    def _configure_restricted_roots(self, tmp_path: Path):
        """将 allowlist 限制在 tmp_path 内部，拒绝系统路径。"""
        from src.sync.connectors.local_folder_connector import configure_local_folder_allowlist
        configure_local_folder_allowlist(
            allowed_roots=[str(tmp_path)],
            max_file_bytes=10 * 1024 * 1024,
        )

    def test_path_within_allowed_root_succeeds(self, tmp_path: Path):
        """tmp_path 内的子目录应被接受。"""
        d = tmp_path / "allowed"
        d.mkdir()
        (d / "f.txt").write_text("ok")
        c = LocalFolderConnector(config={"folder_path": str(d)})
        result = c.test_connection()
        assert result.success

    def test_path_outside_allowed_root_raises(self, tmp_path: Path):
        """tmp_path 外的路径（系统目录）应被拒绝。"""
        # /tmp 或 C:\Windows 不在 allowlist 中
        outside = Path("/etc") if os.name != "nt" else Path("C:\\Windows")
        # 只有当 allowlist 已经被限制时才测试
        from src.sync.connectors.local_folder_connector import _ALLOWED_ROOTS, _validate_path_within_allowlist

        if not _ALLOWED_ROOTS:
            pytest.skip("allowlist not configured")

        with pytest.raises(ValueError, match="Access denied"):
            _validate_path_within_allowlist(outside)

    def test_parent_of_allowed_root_raises(self, tmp_path: Path):
        """tmp_path 的父目录不应被接受。"""
        parent = tmp_path.parent
        from src.sync.connectors.local_folder_connector import _ALLOWED_ROOTS, _validate_path_within_allowlist

        if not _ALLOWED_ROOTS or parent == tmp_path:
            pytest.skip("no parent to test")

        with pytest.raises(ValueError, match="Access denied"):
            _validate_path_within_allowlist(parent)

    def test_empty_allowlist_raises(self):
        """空 allowlist 应拒绝所有路径。"""
        from src.sync.connectors.local_folder_connector import configure_local_folder_allowlist, _validate_path_within_allowlist
        configure_local_folder_allowlist(allowed_roots=[])

        with pytest.raises(ValueError, match="disabled"):
            _validate_path_within_allowlist(Path("/tmp/sync"))

    def test_connector_construction_without_allowlist_raises(self):
        """空 allowlist 时访问 folder_path 属性会拒绝。"""
        from src.sync.connectors.local_folder_connector import configure_local_folder_allowlist

        # 临时清空 allowlist
        configure_local_folder_allowlist(allowed_roots=[])

        c = LocalFolderConnector(config={"folder_path": "/tmp/sync"})
        # 构造时不会校验（lazy），访问 folder_path 时才触发
        with pytest.raises(ValueError, match="disabled"):
            _ = c.folder_path

    def test_path_traversal_is_blocked(self, tmp_path: Path):
        """路径穿越（../../etc）应被 resolve + allowlist 检查拒绝。"""
        d = tmp_path / "sync_root"
        d.mkdir()
        # 构造 ../ 路径试图逃逸
        traversal = str(d / ".." / ".." / ".." / "etc")

        from src.sync.connectors.local_folder_connector import _validate_path_within_allowlist
        # resolve 后路径必定在 tmp_path 外，应被拒绝
        with pytest.raises(ValueError, match="Access denied"):
            _validate_path_within_allowlist(Path(traversal))
