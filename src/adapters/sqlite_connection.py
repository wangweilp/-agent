"""统一 SQLite 连接工厂。

所有 SQLite Store 应通过此工厂创建连接，确保:
- busy_timeout = 30000ms（等待其他连接释放写锁）
- journal_mode = WAL（读写并发，减少锁冲突）
- foreign_keys = ON
- check_same_thread = False（FastAPI 异步兼容）
"""

from __future__ import annotations

import logging
import sqlite3
import time

from sqlite_utils import Database as SqliteDB

logger = logging.getLogger(__name__)

_DEFAULT_BUSY_TIMEOUT_MS = 30_000
_MAX_RETRIES = 5
_RETRY_BACKOFF_BASE = 0.2  # seconds


def create_sqlite_db(
    db_path: str,
    *,
    busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    wal: bool = True,
    foreign_keys: bool = True,
) -> SqliteDB:
    """创建带稳定性配置的 SQLite Database。

    - 设置 busy_timeout，遇到锁等待而非立即报错
    - 开启 WAL 模式，读写并发，减少锁冲突
    - 开启 foreign_keys 约束
    """
    conn = sqlite3.connect(
        db_path,
        timeout=30,
        check_same_thread=False,
        isolation_level=None,  # 自动提交模式，每条语句立即 commit，不持有隐式事务
    )
    conn.row_factory = sqlite3.Row

    # 设置 busy_timeout — 遇到锁时等待而非立即报 "database is locked"
    conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
    # 同步模式降低 fsync 频率，WAL 下数据安全已有保障
    conn.execute("PRAGMA synchronous = NORMAL")

    if wal:
        conn.execute("PRAGMA journal_mode = WAL")

    if foreign_keys:
        conn.execute("PRAGMA foreign_keys = ON")

    db = SqliteDB(conn)
    logger.debug("sqlite_connection_created", extra={
        "db_path": db_path,
        "busy_timeout_ms": busy_timeout_ms,
        "wal": wal,
    })
    return db


def commit_sqlite_database(db: SqliteDB) -> None:
    """安全提交 sqlite_utils.Database 的底层连接。

    在 autocommit 模式下 commit 为 no-op，不会出错。
    仅在需要显式释放事务时使用。
    """
    try:
        if hasattr(db, "conn") and db.conn:
            db.conn.commit()
    except Exception:
        pass  # autocommit 模式下 commit 可能无操作，安全忽略


def execute_with_retry(
    operation,
    label: str = "sqlite_operation",
    max_retries: int = _MAX_RETRIES,
) -> None:
    """对 SQLite schema init / seed 等启动写操作做轻量重试。

    只重试 "database is locked" 错误。
    其他错误原样抛出，不吞。
    使用递增 backoff。
    """
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            operation()
            if attempt > 0:
                logger.info("sqlite_retry_succeeded", extra={
                    "label": label, "attempt": attempt + 1,
                })
            return
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "database is locked" not in msg and "database table is locked" not in msg:
                raise  # 非锁错误，原样抛出
            last_error = e
            delay = _RETRY_BACKOFF_BASE * (2 ** attempt)
            logger.warning("sqlite_locked_retrying", extra={
                "label": label, "attempt": attempt + 1, "max_retries": max_retries,
                "delay_seconds": round(delay, 2),
            })
            time.sleep(delay)

    raise last_error  # type: ignore[misc]
