"""Developer Store 单元测试 — DeveloperAccount + DeveloperApiKey。

覆盖:
- DeveloperAccount CRUD + tenant isolation
- API Key 生成 / hash / verify 安全
- raw key 不在 DB / hash 不在 public dict
- revoked / expired key 验证
- 错误类 (duplicate, scope, cross-developer revoke)
"""

import os
import time
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.developer_store import SQLiteDeveloperStore
from src.open_platform.developer import (
    ApiKeyScopeError,
    DeveloperAccount,
    DeveloperAlreadyExistsError,
    DeveloperApiKey,
    DeveloperNotFoundError,
    DeveloperStatus,
    DuplicateApiKeyError,
    generate_api_key,
    get_api_key_prefix,
    hash_api_key,
    verify_api_key,
)


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════

@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def store(settings):
    store = SQLiteDeveloperStore(settings, db_path=":memory:")
    return store


@pytest.fixture
def dev1():
    return DeveloperAccount(
        user_id="user-001",
        tenant_id="tenant-a",
        display_name="Test Dev 1",
        contact_email="dev1@example.com",
        organization_name="Org One",
        website="https://org1.example.com",
    )


@pytest.fixture
def dev2():
    return DeveloperAccount(
        user_id="user-002",
        tenant_id="tenant-a",
        display_name="Test Dev 2",
        contact_email="dev2@example.com",
    )


def _make_key(developer_id: str = "dev_001", scopes: list[str] | None = None) -> DeveloperApiKey:
    raw = generate_api_key()
    return DeveloperApiKey(
        developer_id=developer_id,
        key_prefix=get_api_key_prefix(raw),
        key_hash=hash_api_key(raw),
        name="Test Key",
        scopes=scopes or ["agent:read"],
    )


# ═══════════════════════════════════════════
# DeveloperAccount Tests
# ═══════════════════════════════════════════


class TestDeveloperAccount:
    def test_create_developer(self, store, dev1):
        created = store.create_developer(dev1)
        assert created.developer_id == dev1.developer_id
        assert created.developer_id.startswith("dev_")

    def test_get_developer_by_id(self, store, dev1):
        store.create_developer(dev1)
        found = store.get_developer(dev1.developer_id)
        assert found is not None
        assert found.display_name == "Test Dev 1"
        assert found.tenant_id == "tenant-a"
        assert found.organization_name == "Org One"
        assert found.website == "https://org1.example.com"

    def test_get_developer_by_user_and_tenant(self, store, dev1):
        store.create_developer(dev1)
        found = store.get_developer_by_user("user-001", "tenant-a")
        assert found is not None
        assert found.developer_id == dev1.developer_id

    def test_get_developer_nonexistent(self, store):
        assert store.get_developer("nonexistent") is None
        assert store.get_developer_by_user("no-user", "no-tenant") is None

    def test_duplicate_user_tenant_rejected(self, store, dev1):
        store.create_developer(dev1)
        dup = DeveloperAccount(
            user_id="user-001",
            tenant_id="tenant-a",
            display_name="Dup",
            contact_email="dup@example.com",
        )
        with pytest.raises(DeveloperAlreadyExistsError):
            store.create_developer(dup)

    def test_same_user_different_tenant_allowed(self, store, dev1):
        store.create_developer(dev1)
        dev_diff_tenant = DeveloperAccount(
            user_id="user-001",
            tenant_id="tenant-b",
            display_name="Same User Diff Tenant",
            contact_email="same@example.com",
        )
        created = store.create_developer(dev_diff_tenant)
        assert created.developer_id != dev1.developer_id

    def test_list_developers_by_tenant(self, store, dev1, dev2):
        store.create_developer(dev1)
        store.create_developer(dev2)
        # tenant-a should have both
        result = store.list_developers(tenant_id="tenant-a")
        assert len(result) == 2

        # tenant-b should have none
        result = store.list_developers(tenant_id="tenant-b")
        assert len(result) == 0

    def test_list_developers_by_status(self, store, dev1, dev2):
        store.create_developer(dev1)
        store.create_developer(dev2)
        store.update_developer_status(dev1.developer_id, DeveloperStatus.SUSPENDED)

        active = store.list_developers(tenant_id="tenant-a", status="active")
        assert len(active) == 1

        suspended = store.list_developers(tenant_id="tenant-a", status="suspended")
        assert len(suspended) == 1

    def test_list_all_developers(self, store, dev1, dev2):
        store.create_developer(dev1)
        store.create_developer(dev2)
        result = store.list_developers()
        assert len(result) == 2

    def test_update_developer(self, store, dev1):
        store.create_developer(dev1)
        dev1.display_name = "Updated Name"
        dev1.website = "https://new.example.com"
        store.update_developer(dev1)
        found = store.get_developer(dev1.developer_id)
        assert found.display_name == "Updated Name"
        assert found.website == "https://new.example.com"

    def test_verify_developer(self, store, dev1):
        store.create_developer(dev1)
        assert dev1.verified is False
        ok = store.verify_developer(dev1.developer_id)
        assert ok is True
        found = store.get_developer(dev1.developer_id)
        assert found.verified is True

    def test_verify_nonexistent_developer(self, store):
        assert store.verify_developer("nonexistent") is False

    def test_suspend_developer(self, store, dev1):
        store.create_developer(dev1)
        ok = store.suspend_developer(dev1.developer_id)
        assert ok is True
        found = store.get_developer(dev1.developer_id)
        assert found.status == DeveloperStatus.SUSPENDED

    def test_suspend_nonexistent_developer(self, store):
        assert store.suspend_developer("nonexistent") is False

    def test_update_developer_status(self, store, dev1):
        store.create_developer(dev1)
        ok = store.update_developer_status(dev1.developer_id, DeveloperStatus.REJECTED)
        assert ok is True
        found = store.get_developer(dev1.developer_id)
        assert found.status == DeveloperStatus.REJECTED

    def test_update_status_nonexistent(self, store):
        assert store.update_developer_status("nonexistent", DeveloperStatus.ACTIVE) is False

    def test_to_dict_developer(self, store, dev1):
        d = dev1.to_dict()
        assert d["developer_id"] == dev1.developer_id
        assert d["status"] == "active"
        assert d["verified"] is False
        assert "created_at" in d


# ═══════════════════════════════════════════
# API Key Security Tests
# ═══════════════════════════════════════════


class TestApiKeySecurity:
    def test_generate_api_key_format(self):
        key = generate_api_key()
        assert key.startswith("cos_dev_")
        parts = key.split("_")
        assert len(parts) == 4  # cos, dev, prefix, secret
        assert len(parts[2]) == 8  # key_prefix is 8 hex chars
        assert len(parts[3]) == 64  # secret is 64 hex chars

    def test_hash_does_not_equal_raw_key(self):
        raw = generate_api_key()
        hashed = hash_api_key(raw)
        assert raw != hashed
        assert raw not in hashed

    def test_verify_success(self):
        raw = generate_api_key()
        hashed = hash_api_key(raw)
        assert verify_api_key(raw, hashed) is True

    def test_verify_wrong_key_fails(self):
        raw = generate_api_key()
        hashed = hash_api_key(raw)
        assert verify_api_key("wrong_key", hashed) is False
        assert verify_api_key(raw + "x", hashed) is False

    def test_verify_garbage_hash_fails(self):
        raw = generate_api_key()
        assert verify_api_key(raw, "not_a_hash") is False
        assert verify_api_key(raw, "") is False

    def test_verify_different_key_same_prefix(self):
        """两个不同 key 且 prefix 不同，互相验证失败。"""
        raw1 = generate_api_key()
        raw2 = generate_api_key()
        hash1 = hash_api_key(raw1)
        assert verify_api_key(raw2, hash1) is False

    def test_get_api_key_prefix(self):
        raw = generate_api_key()
        prefix = get_api_key_prefix(raw)
        assert len(prefix) == 8
        assert prefix in raw

    def test_prefix_consistency(self):
        raw = generate_api_key()
        prefix1 = get_api_key_prefix(raw)
        prefix2 = get_api_key_prefix(raw)
        assert prefix1 == prefix2

    def test_key_prefix_unique_per_generation(self):
        prefixes = set()
        for _ in range(20):
            raw = generate_api_key()
            prefixes.add(get_api_key_prefix(raw))
        assert len(prefixes) == 20  # all unique


# ═══════════════════════════════════════════
# API Key Store Tests
# ═══════════════════════════════════════════


class TestApiKeyStore:
    def test_create_api_key(self, store):
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="Production Key",
            scopes=["agent:read", "agent:submit"],
        )
        created = store.create_api_key(key)
        assert created.api_key_id == key.api_key_id
        assert created.api_key_id.startswith("apk_")

    def test_create_api_key_empty_scopes_rejected(self, store):
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="Bad Key",
            scopes=[],
        )
        with pytest.raises(ApiKeyScopeError):
            store.create_api_key(key)

    def test_scopes_persist(self, store):
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="Scoped Key",
            scopes=["agent:read", "agent:submit", "memory:read"],
        )
        store.create_api_key(key)
        found = store.get_api_key(key.api_key_id)
        assert found.scopes == ["agent:read", "agent:submit", "memory:read"]

    def test_to_dict_does_not_expose_hash(self, store):
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="Secret Key",
            scopes=["agent:read"],
        )
        store.create_api_key(key)
        found = store.get_api_key(key.api_key_id)
        d = found.to_dict()
        assert "key_hash" not in d
        assert "api_key_id" in d
        assert "key_prefix" in d
        assert "scopes" in d

    def test_raw_key_never_stored_in_db(self, store):
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="NoRaw",
            scopes=["agent:read"],
        )
        store.create_api_key(key)

        # Direct DB query — verify no raw key
        row = next(store._exec("SELECT * FROM developer_api_keys WHERE api_key_id=?", [key.api_key_id]), None)
        d = dict(row)
        # key_hash should be present but not equal to raw
        assert d["key_hash"] != raw
        # raw key must NOT appear anywhere
        assert raw not in d["key_hash"]
        assert raw not in str(d.values())

    def test_list_api_keys_by_developer(self, store):
        for i in range(3):
            raw = generate_api_key()
            key = DeveloperApiKey(
                developer_id="dev_001",
                key_prefix=get_api_key_prefix(raw),
                key_hash=hash_api_key(raw),
                name=f"Key-{i}",
                scopes=["agent:read"],
            )
            store.create_api_key(key)

        result = store.list_api_keys("dev_001")
        assert len(result) == 3

        # other developer has none
        result = store.list_api_keys("dev_other")
        assert len(result) == 0

    def test_list_api_keys_excludes_revoked_by_default(self, store):
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="To Revoke",
            scopes=["agent:read"],
        )
        store.create_api_key(key)
        store.revoke_api_key(key.api_key_id, "dev_001")

        result = store.list_api_keys("dev_001")
        assert len(result) == 0  # revoked excluded

    def test_list_api_keys_include_revoked(self, store):
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="Revoked Key",
            scopes=["agent:read"],
        )
        store.create_api_key(key)
        store.revoke_api_key(key.api_key_id, "dev_001")

        result = store.list_api_keys("dev_001", include_revoked=True)
        assert len(result) == 1
        assert result[0].status == "revoked"

    def test_revoke_api_key(self, store):
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="Revocable",
            scopes=["agent:read"],
        )
        store.create_api_key(key)
        ok = store.revoke_api_key(key.api_key_id, "dev_001")
        assert ok is True

        found = store.get_api_key(key.api_key_id)
        assert found.status == "revoked"

    def test_cannot_revoke_other_developer_key(self, store):
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="Mine",
            scopes=["agent:read"],
        )
        store.create_api_key(key)

        # dev_002 tries to revoke dev_001's key
        ok = store.revoke_api_key(key.api_key_id, "dev_002")
        assert ok is False

        # key should still be active
        found = store.get_api_key(key.api_key_id)
        assert found.status == "active"

    def test_revoked_key_fails_verify(self, store):
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="ActiveThenRevoked",
            scopes=["agent:read"],
        )
        store.create_api_key(key)

        # Verify works before revoke
        found = store.verify_and_lookup_api_key(raw)
        assert found is not None

        # Revoke
        store.revoke_api_key(key.api_key_id, "dev_001")

        # Verify fails after revoke
        found = store.verify_and_lookup_api_key(raw)
        assert found is None

    def test_expired_key_fails_verify(self, store):
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="Expiring",
            scopes=["agent:read"],
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        store.create_api_key(key)

        found = store.verify_and_lookup_api_key(raw)
        assert found is None

    def test_verify_updates_last_used(self, store):
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="Tracker",
            scopes=["agent:read"],
        )
        store.create_api_key(key)

        # Before verify, last_used_at is None
        found = store.get_api_key(key.api_key_id)
        assert found.last_used_at is None

        # After verify, last_used_at is set
        store.verify_and_lookup_api_key(raw)
        found = store.get_api_key(key.api_key_id)
        assert found.last_used_at is not None

    def test_verify_wrong_raw_key_fails(self, store):
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="Test",
            scopes=["agent:read"],
        )
        store.create_api_key(key)

        other_raw = generate_api_key()
        found = store.verify_and_lookup_api_key(other_raw)
        assert found is None

    def test_verify_nonexistent_prefix(self, store):
        found = store.verify_and_lookup_api_key("cos_dev_deadbeef_somesecret")
        assert found is None

    def test_delete_api_key_behaves_as_revoke(self, store):
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="DeleteMe",
            scopes=["agent:read"],
        )
        store.create_api_key(key)

        ok = store.delete_api_key(key.api_key_id, "dev_001")
        assert ok is True

        found = store.get_api_key(key.api_key_id)
        assert found.status == "revoked"

    def test_key_prefix_unique(self, store):
        raw = generate_api_key()
        prefix = get_api_key_prefix(raw)
        key1 = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=prefix,
            key_hash=hash_api_key(raw),
            name="First",
            scopes=["agent:read"],
        )
        store.create_api_key(key1)

        # Same prefix should fail
        key2 = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=prefix,
            key_hash=hash_api_key("different_raw"),
            name="Second",
            scopes=["agent:read"],
        )
        with pytest.raises(DuplicateApiKeyError):
            store.create_api_key(key2)

    def test_get_by_prefix(self, store):
        raw = generate_api_key()
        prefix = get_api_key_prefix(raw)
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=prefix,
            key_hash=hash_api_key(raw),
            name="PrefixKey",
            scopes=["agent:read"],
        )
        store.create_api_key(key)

        found = store.get_api_key_by_prefix(prefix)
        assert found is not None
        assert found.api_key_id == key.api_key_id

    def test_expires_at_persists(self, store):
        expires = datetime(2027, 1, 1, tzinfo=timezone.utc)
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="WithExpiry",
            scopes=["agent:read"],
            expires_at=expires,
        )
        store.create_api_key(key)
        found = store.get_api_key(key.api_key_id)
        assert found.expires_at is not None
        assert found.expires_at.year == 2027

    def test_is_expired_helper(self):
        key_future = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix="fx123456",
            key_hash="hash",
            name="Future",
            scopes=["agent:read"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        assert key_future.is_expired() is False

        key_past = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix="px123456",
            key_hash="hash",
            name="Past",
            scopes=["agent:read"],
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        assert key_past.is_expired() is True

        key_never = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix="nx123456",
            key_hash="hash",
            name="NoExpiry",
            scopes=["agent:read"],
        )
        assert key_never.is_expired() is False

    def test_is_usable(self):
        key_active = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix="ax123456",
            key_hash="hash",
            name="Active",
            scopes=["agent:read"],
        )
        assert key_active.is_usable() is True

        key_revoked = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix="rx123456",
            key_hash="hash",
            name="Revoked",
            scopes=["agent:read"],
            status="revoked",
        )
        assert key_revoked.is_usable() is False

    def test_metadata_on_developer_persists(self, store, dev1):
        dev1.metadata = {"company": "TestCo", "plan": "free"}
        store.create_developer(dev1)
        found = store.get_developer(dev1.developer_id)
        assert found.metadata == {"company": "TestCo", "plan": "free"}

    def test_metadata_on_apikey_persists(self, store):
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id="dev_001",
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="MetaKey",
            scopes=["agent:read"],
            metadata={"env": "prod", "source": "ci"},
        )
        store.create_api_key(key)
        found = store.get_api_key(key.api_key_id)
        assert found.metadata == {"env": "prod", "source": "ci"}


# ═══════════════════════════════════════════
# Tenant Isolation Tests
# ═══════════════════════════════════════════


class TestTenantIsolation:
    def test_list_developers_does_not_cross_tenant(self, store):
        """tenant-a 的列表不应包含 tenant-b 的 developer。"""
        store.create_developer(DeveloperAccount(
            user_id="u1", tenant_id="tenant-a", display_name="A", contact_email="a@a.com",
        ))
        store.create_developer(DeveloperAccount(
            user_id="u2", tenant_id="tenant-b", display_name="B", contact_email="b@b.com",
        ))

        result = store.list_developers(tenant_id="tenant-a")
        assert len(result) == 1
        assert result[0].tenant_id == "tenant-a"

        result = store.list_developers(tenant_id="tenant-b")
        assert len(result) == 1
        assert result[0].tenant_id == "tenant-b"

    def test_get_developer_by_user_respects_tenant(self, store):
        """同一个 user_id 在不同 tenant 应有不同的 developer。"""
        store.create_developer(DeveloperAccount(
            user_id="cross-user", tenant_id="t1", display_name="X1", contact_email="x@x.com",
        ))
        store.create_developer(DeveloperAccount(
            user_id="cross-user", tenant_id="t2", display_name="X2", contact_email="x@x.com",
        ))

        d1 = store.get_developer_by_user("cross-user", "t1")
        assert d1.display_name == "X1"

        d2 = store.get_developer_by_user("cross-user", "t2")
        assert d2.display_name == "X2"

    def test_api_keys_isolated_by_developer(self, store):
        """不同 developer 的 API key 互相不可见。"""
        raw1 = generate_api_key()
        store.create_api_key(DeveloperApiKey(
            developer_id="dev_a", key_prefix=get_api_key_prefix(raw1),
            key_hash=hash_api_key(raw1), name="KeyA", scopes=["agent:read"],
        ))
        raw2 = generate_api_key()
        store.create_api_key(DeveloperApiKey(
            developer_id="dev_b", key_prefix=get_api_key_prefix(raw2),
            key_hash=hash_api_key(raw2), name="KeyB", scopes=["agent:read"],
        ))

        keys_a = store.list_api_keys("dev_a")
        assert len(keys_a) == 1

        keys_b = store.list_api_keys("dev_b")
        assert len(keys_b) == 1


# ═══════════════════════════════════════════
# Full E2E: create developer → generate key → verify
# ═══════════════════════════════════════════


class TestE2ELifecycle:
    def test_full_developer_key_lifecycle(self, store, dev1):
        """完整流程：注册 developer → 生成 key → verify → revoke → verify fail。"""
        # 1. Create developer
        store.create_developer(dev1)

        # 2. Generate API key
        raw = generate_api_key()
        key = DeveloperApiKey(
            developer_id=dev1.developer_id,
            key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw),
            name="E2E Key",
            scopes=["agent:read", "agent:submit"],
        )
        store.create_api_key(key)

        # 3. Verify: should succeed
        found = store.verify_and_lookup_api_key(raw)
        assert found is not None
        assert found.api_key_id == key.api_key_id
        assert found.scopes == ["agent:read", "agent:submit"]

        # 4. Verify wrong key: should fail
        other_raw = generate_api_key()
        assert store.verify_and_lookup_api_key(other_raw) is None

        # 5. Revoke
        ok = store.revoke_api_key(key.api_key_id, dev1.developer_id)
        assert ok is True

        # 6. Verify after revoke: should fail
        found = store.verify_and_lookup_api_key(raw)
        assert found is None

        # 7. List should not include revoked (default)
        keys = store.list_api_keys(dev1.developer_id)
        assert len(keys) == 0

        # 8. But include_revoked should show it
        keys = store.list_api_keys(dev1.developer_id, include_revoked=True)
        assert len(keys) == 1
        assert keys[0].status == "revoked"
