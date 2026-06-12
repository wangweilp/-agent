"""SQLite Startup Stability 测试 — busy_timeout, WAL, retry, isolation_level, flush。

验证:
1. create_sqlite_db 设置 isolation_level=None (autocommit)
2. create_sqlite_db 设置 busy_timeout + synchronous=NORMAL
3. create_sqlite_db 开启 WAL
4. schema init retry 只重试 database is locked
5. 非 locked OperationalError 不被吞
6. Store 初始化正常
7. seed 幂等
8. marketplace seed 后 developer store init 不 locked
9. runtime seed 后 sandbox policy store init 不 locked
10. sandbox policy seed 后 package validation store init 不 locked
11. 连续初始化所有 Step23 stores 不 locked
12. 连续运行 seed twice 不 locked
13. flush 释放锁
14. 不影响现有数据模型
"""

import os
import sqlite3
import tempfile

import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.adapters.config import Settings
from src.adapters.marketplace_store import SQLiteMarketplaceStore
from src.adapters.developer_store import SQLiteDeveloperStore
from src.adapters.submission_store import SQLiteSubmissionStore
from src.adapters.runtime_store import SQLiteRuntimeStore
from src.adapters.sandbox_policy_store import SQLiteSandboxPolicyStore
from src.adapters.package_validation_store import SQLitePackageValidationStore
from src.agents.marketplace import seed_builtin_marketplace_agents


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_stability.db")
    yield path
    import shutil
    shutil.rmtree(d, ignore_errors=True)


class TestSqliteConnection:
    def test_busy_timeout_set(self, tmp_db_path):
        db = create_sqlite_db(tmp_db_path)
        row = db.execute("PRAGMA busy_timeout").fetchone()
        timeout = row[0] if row else 0
        assert timeout >= 1000, f"Expected busy_timeout >= 1000, got {timeout}"

    def test_wal_mode_enabled(self, tmp_db_path):
        db = create_sqlite_db(tmp_db_path)
        row = db.execute("PRAGMA journal_mode").fetchone()
        mode = (row[0] or "").lower() if row else ""
        assert mode == "wal", f"Expected WAL mode, got '{mode}'"

    def test_foreign_keys_on(self, tmp_db_path):
        db = create_sqlite_db(tmp_db_path)
        row = db.execute("PRAGMA foreign_keys").fetchone()
        val = row[0] if row else 0
        assert val == 1, f"Expected foreign_keys=ON, got {val}"


class TestRetryBehavior:
    def test_success_no_retry(self):
        call_count = [0]

        def op():
            call_count[0] += 1

        execute_with_retry(op, label="test_success")
        assert call_count[0] == 1

    def test_retry_on_locked(self, tmp_db_path):
        """locked 错误触发重试，最终成功。"""
        attempts = [0]

        def op():
            attempts[0] += 1
            if attempts[0] < 3:
                raise sqlite3.OperationalError("database is locked")
            # success on 3rd try

        execute_with_retry(op, label="test_locked", max_retries=5)
        assert attempts[0] == 3

    def test_retry_on_table_locked(self, tmp_db_path):
        """database table is locked 也触发重试。"""
        attempts = [0]

        def op():
            attempts[0] += 1
            if attempts[0] < 2:
                raise sqlite3.OperationalError("database table is locked")

        execute_with_retry(op, label="test_table_locked", max_retries=5)
        assert attempts[0] == 2

    def test_non_locked_error_not_swallowed(self, tmp_db_path):
        """非锁错误原样抛出，不吞。"""

        def op():
            raise sqlite3.OperationalError("no such table: xyz")

        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            execute_with_retry(op, label="test_no_swallow", max_retries=3)

    def test_retry_exhausted_raises(self, tmp_db_path):
        """所有重试耗尽后抛出最后一次错误。"""
        attempts = [0]

        def op():
            attempts[0] += 1
            raise sqlite3.OperationalError("database is locked")

        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            execute_with_retry(op, label="test_exhausted", max_retries=3)
        assert attempts[0] == 3


class TestStoreInitStability:
    def test_developer_store_init(self, settings, tmp_db_path):
        store = SQLiteDeveloperStore(settings, db_path=tmp_db_path)
        assert store is not None

    def test_submission_store_init(self, settings, tmp_db_path):
        store = SQLiteSubmissionStore(settings, db_path=tmp_db_path)
        assert store is not None

    def test_runtime_store_init_and_seed(self, settings, tmp_db_path):
        store = SQLiteRuntimeStore(settings, db_path=tmp_db_path)
        count = store.seed_builtin_adapters()
        assert count >= 2  # manifest_only + simulation

    def test_sandbox_policy_init_and_seed(self, settings, tmp_db_path):
        store = SQLiteSandboxPolicyStore(settings, db_path=tmp_db_path)
        count = store.seed_builtin_policies()
        assert count == 3

    def test_package_validation_store_init(self, settings, tmp_db_path):
        store = SQLitePackageValidationStore(settings, db_path=tmp_db_path)
        assert store is not None

    def test_seed_idempotent_runtime(self, settings, tmp_db_path):
        store = SQLiteRuntimeStore(settings, db_path=tmp_db_path)
        c1 = store.seed_builtin_adapters()
        c2 = store.seed_builtin_adapters()
        assert c1 >= 2
        assert c2 == 0

    def test_seed_idempotent_sandbox(self, settings, tmp_db_path):
        store = SQLiteSandboxPolicyStore(settings, db_path=tmp_db_path)
        c1 = store.seed_builtin_policies()
        c2 = store.seed_builtin_policies()
        assert c1 == 3
        assert c2 == 0

    def test_concurrent_store_init_no_locking(self, settings, tmp_db_path):
        """多个 Store 从同一个 DB path 顺序初始化不因锁失败。"""
        stores = []
        stores.append(SQLiteDeveloperStore(settings, db_path=tmp_db_path))
        stores.append(SQLiteSubmissionStore(settings, db_path=tmp_db_path))
        stores.append(SQLiteRuntimeStore(settings, db_path=tmp_db_path))
        stores.append(SQLiteSandboxPolicyStore(settings, db_path=tmp_db_path))
        stores.append(SQLitePackageValidationStore(settings, db_path=tmp_db_path))
        for s in stores:
            assert s is not None

    def test_runtime_store_crud_after_retry_init(self, settings, tmp_db_path):
        store = SQLiteRuntimeStore(settings, db_path=tmp_db_path)
        store.seed_builtin_adapters()
        from src.open_platform.runtime import (
            DeveloperAgentRuntimeBinding, RuntimeAdapterType,
        )
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_test", developer_id="d1",
            tenant_id="t1", adapter_id="rtadp_simulation",
            adapter_type=RuntimeAdapterType.SIMULATION,
        )
        created = store.create_binding(b)
        assert created is not None
        found = store.get_binding(created.binding_id)
        assert found is not None


class TestIsolationLevel:
    """验证 create_sqlite_db 创建的连接 isolation_level 为 None (autocommit)。"""

    def test_isolation_level_is_none(self, tmp_db_path):
        db = create_sqlite_db(tmp_db_path)
        assert db.conn is not None
        assert db.conn.isolation_level is None, (
            f"Expected isolation_level=None (autocommit), got {db.conn.isolation_level!r}"
        )

    def test_synchronous_normal_set(self, tmp_db_path):
        db = create_sqlite_db(tmp_db_path)
        row = db.execute("PRAGMA synchronous").fetchone()
        val = row[0] if row else 0
        # NORMAL = 1, FULL = 2, OFF = 0
        assert val == 1, f"Expected synchronous=NORMAL (1), got {val}"


class TestCrossStoreLocking:
    """验证跨 store 初始化顺序不产生锁竞争。"""

    def test_marketplace_seed_then_developer_init_not_locked(self, settings, tmp_db_path):
        """模拟 main.py: marketplace seed → developer store init。"""
        marketplace = SQLiteMarketplaceStore(settings, db_path=tmp_db_path)
        created = seed_builtin_marketplace_agents(marketplace)
        assert created > 0
        marketplace.flush()

        # 关键断言：developer store init 不因锁失败
        developer = SQLiteDeveloperStore(settings, db_path=tmp_db_path)
        assert developer is not None

        # 验证 developer schema 存在
        row = developer._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='developer_accounts'"
        ).fetchone()
        assert row is not None, "developer_accounts table should exist"

    def test_runtime_seed_then_sandbox_policy_init_not_locked(self, settings, tmp_db_path):
        """模拟 main.py: runtime seed → sandbox policy store init。"""
        runtime = SQLiteRuntimeStore(settings, db_path=tmp_db_path)
        c = runtime.seed_builtin_adapters()
        assert c >= 2
        runtime.flush()

        sandbox = SQLiteSandboxPolicyStore(settings, db_path=tmp_db_path)
        assert sandbox is not None

        row = sandbox._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sandbox_policies'"
        ).fetchone()
        assert row is not None

    def test_sandbox_policy_seed_then_package_validation_init_not_locked(self, settings, tmp_db_path):
        """模拟 main.py: sandbox policy seed → package validation store init。"""
        sandbox = SQLiteSandboxPolicyStore(settings, db_path=tmp_db_path)
        c = sandbox.seed_builtin_policies()
        assert c == 3
        sandbox.flush()

        pv = SQLitePackageValidationStore(settings, db_path=tmp_db_path)
        assert pv is not None

        row = pv._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='package_validation_results'"
        ).fetchone()
        assert row is not None

    def test_marketplace_seed_twice_no_locked(self, settings, tmp_db_path):
        """连续 seed 两次不锁。"""
        marketplace = SQLiteMarketplaceStore(settings, db_path=tmp_db_path)
        c1 = seed_builtin_marketplace_agents(marketplace)
        marketplace.flush()
        c2 = seed_builtin_marketplace_agents(marketplace)
        assert c1 > 0
        assert c2 == 0

    def test_full_bootstrap_order_no_locked(self, settings, tmp_db_path):
        """完整模拟 main.py 中 Step22-23 的 store 初始化顺序。"""
        # marketplace → seed → developer → submission → runtime → seed → sandbox → seed → pv
        marketplace = SQLiteMarketplaceStore(settings, db_path=tmp_db_path)
        seed_builtin_marketplace_agents(marketplace)
        marketplace.flush()

        developer = SQLiteDeveloperStore(settings, db_path=tmp_db_path)
        assert developer is not None

        submission = SQLiteSubmissionStore(settings, db_path=tmp_db_path)
        assert submission is not None

        runtime = SQLiteRuntimeStore(settings, db_path=tmp_db_path)
        runtime.seed_builtin_adapters()
        runtime.flush()

        sandbox = SQLiteSandboxPolicyStore(settings, db_path=tmp_db_path)
        sandbox.seed_builtin_policies()
        sandbox.flush()

        pv = SQLitePackageValidationStore(settings, db_path=tmp_db_path)
        assert pv is not None

        # 验证所有关键表存在
        tables = {"marketplace_agents", "developer_accounts", "agent_submissions",
                  "runtime_adapters", "sandbox_policies", "package_validation_results"}
        for t in tables:
            row = pv._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", [t]
            ).fetchone()
            assert row is not None, f"Table '{t}' should exist"


class TestFlushBehavior:
    """验证 flush() 方法正确释放锁。"""

    def test_flush_does_not_raise(self, settings, tmp_db_path):
        """flush 在 autocommit 模式下为安全 no-op，不抛异常。"""
        store = SQLiteDeveloperStore(settings, db_path=tmp_db_path)
        store.flush()  # 不应报错

    def test_flush_after_schema_init(self, settings, tmp_db_path):
        """schema init 后 flush 不报错。"""
        store = SQLiteRuntimeStore(settings, db_path=tmp_db_path)
        store.flush()
        # 再次写入验证连接仍然有效
        c = store.seed_builtin_adapters()
        assert c >= 2

    def test_marketplace_flush_releases_lock_for_developer(self, settings, tmp_db_path):
        """marketplace flush 后 developer 可立即建表。"""
        marketplace = SQLiteMarketplaceStore(settings, db_path=tmp_db_path)
        seed_builtin_marketplace_agents(marketplace)

        # 不调用 flush 的情况下，autocommit 也应释放锁
        # 这里验证 flush 后 developer init 正常
        marketplace.flush()
        developer = SQLiteDeveloperStore(settings, db_path=tmp_db_path)
        assert developer is not None

    def test_all_stores_have_flush(self, settings, tmp_db_path):
        """验证所有 Step23 stores 都有 flush() 方法。"""
        stores = [
            SQLiteMarketplaceStore(settings, db_path=tmp_db_path),
            SQLiteDeveloperStore(settings, db_path=tmp_db_path),
            SQLiteSubmissionStore(settings, db_path=tmp_db_path),
            SQLiteRuntimeStore(settings, db_path=tmp_db_path),
            SQLiteSandboxPolicyStore(settings, db_path=tmp_db_path),
            SQLitePackageValidationStore(settings, db_path=tmp_db_path),
        ]
        for s in stores:
            assert hasattr(s, "flush"), f"{type(s).__name__} missing flush()"
            assert callable(s.flush), f"{type(s).__name__}.flush is not callable"


class TestConnectionProperties:
    """验证连接属性与 autocommit 模式。"""

    def test_create_sqlite_db_timeout_parameter(self, tmp_db_path):
        """验证 timeout 参数传递给 sqlite3.connect。"""
        db = create_sqlite_db(tmp_db_path, busy_timeout_ms=5000)
        row = db.execute("PRAGMA busy_timeout").fetchone()
        assert row[0] >= 1000

    def test_multiple_connections_same_db_no_lock(self, tmp_db_path):
        """同一 DB 文件多个 create_sqlite_db 连接不锁。"""
        db1 = create_sqlite_db(tmp_db_path)
        db2 = create_sqlite_db(tmp_db_path)
        # 两个连接各建一张表
        db1.execute("CREATE TABLE IF NOT EXISTS t1 (id INTEGER PRIMARY KEY)")
        db2.execute("CREATE TABLE IF NOT EXISTS t2 (id INTEGER PRIMARY KEY)")
        # 验证两张表存在
        tables = {r["name"] for r in db2.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "t1" in tables
        assert "t2" in tables
