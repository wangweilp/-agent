"""SQLite 记忆存储适配器 — 实现 MemoryStore 协议。

组合 embedding_provider 和 vector_store 实现语义搜索。
管理 notes / entities / memory_entities / relations 四张表。
"""
import json
import logging
import sqlite3
import threading
from datetime import datetime
from typing import Any

from sqlite_utils import Database

from src.adapters.config import Settings
from src.core.types import Memory

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS notes (
    id             TEXT PRIMARY KEY,
    content        TEXT NOT NULL,
    summary        TEXT,
    source         TEXT,
    timestamp      TEXT NOT NULL,
    importance     INTEGER NOT NULL DEFAULT 5,
    entities_json  TEXT NOT NULL DEFAULT '[]',
    relations_json TEXT NOT NULL DEFAULT '[]',
    memory_type    TEXT DEFAULT 'episodic',
    access_count   INTEGER NOT NULL DEFAULT 0,
    last_accessed  TEXT
);

CREATE TABLE IF NOT EXISTS entities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    entity_type   TEXT DEFAULT '',
    first_seen    TEXT NOT NULL DEFAULT (datetime('now')),
    mention_count INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);

CREATE TABLE IF NOT EXISTS memory_entities (
    memory_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    PRIMARY KEY (memory_id, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_me_memory ON memory_entities(memory_id);
CREATE INDEX IF NOT EXISTS idx_me_entity ON memory_entities(entity_id);

CREATE TABLE IF NOT EXISTS relations (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    subject   TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rel_memory ON relations(memory_id);
CREATE INDEX IF NOT EXISTS idx_rel_subject ON relations(subject);
CREATE INDEX IF NOT EXISTS idx_rel_object ON relations(object);
"""


class MemoryStoreError(Exception):
    """记忆存储错误。"""


class SQLiteStoreAdapter:
    """完整的 MemoryStore 实现，组合 SQLite + VectorStore + EmbeddingProvider。"""

    def __init__(
        self,
        config: Settings,
        embedding_provider: Any,
        vector_store: Any,
        db_path: str | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._write_lock = threading.Lock()

        path = db_path or config.sqlite_db_path
        if path == ":memory:":
            self._db = Database(memory=True)
        else:
            self._db = Database(path)

        self._init_schema()

    def _init_schema(self) -> None:
        self._db.conn.row_factory = sqlite3.Row
        for statement in _SCHEMA_SQL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                self._db.execute(stmt)

    # ── MemoryStore 协议 ──────────────────────────────────────────────

    def store(self, memory: Memory) -> str:
        embedding = memory.embedding
        if embedding is None:
            embedding = self._embedding_provider.get_embedding(memory.content)

        # 先写向量存储（避免 SQL 成功但向量失败的幽灵记录）
        try:
            self._vector_store.store(
                doc_id=memory.id,
                embedding=embedding,
                metadata={
                    "memory_type": memory.memory_type,
                    "summary": memory.summary or "",
                    "source": memory.source,
                },
            )
        except Exception:
            logger.exception("向量存储写入失败: %s", memory.id)

        with self._write_lock:
            with self._db.conn:
                self._db.execute(
                    """INSERT INTO notes (id, content, summary, source, timestamp,
                       importance, entities_json, relations_json, memory_type)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                       content=excluded.content, summary=excluded.summary,
                       source=excluded.source, timestamp=excluded.timestamp,
                       importance=excluded.importance,
                       entities_json=excluded.entities_json,
                       relations_json=excluded.relations_json,
                       memory_type=excluded.memory_type""",
                    (
                        memory.id, memory.content, memory.summary, memory.source,
                        memory.timestamp.isoformat(), memory.importance,
                        json.dumps(memory.entities, ensure_ascii=False),
                        json.dumps(memory.relations, ensure_ascii=False),
                        memory.memory_type,
                    ),
                )

                # 删除旧的关联记录，重新插入
                self._db.execute(
                    "DELETE FROM memory_entities WHERE memory_id = ?", (memory.id,)
                )
                self._db.execute(
                    "DELETE FROM relations WHERE memory_id = ?", (memory.id,)
                )

                for entity_name in memory.entities:
                    entity_id = self._ensure_entity(entity_name)
                    self._db.execute(
                        "INSERT INTO memory_entities (memory_id, entity_id) VALUES (?, ?)",
                        (memory.id, entity_id),
                    )

                for rel in memory.relations:
                    self._db.execute(
                        "INSERT INTO relations (memory_id, subject, predicate, object) "
                        "VALUES (?, ?, ?, ?)",
                        (memory.id, rel["s"], rel["p"], rel["o"]),
                    )

        return memory.id

    def search_semantic(self, query: str, top_k: int) -> list[Memory]:
        query_embedding = self._embedding_provider.get_embedding(query)
        candidates = self._vector_store.search(query_embedding, top_k)

        results: list[Memory] = []
        for candidate in candidates:
            memory = self.get_by_id(candidate["id"])
            if memory is not None:
                results.append(memory)
        return results

    def search_by_entity(self, entity_name: str) -> list[Memory]:
        rows = self._db.execute(
            """SELECT n.* FROM notes n
               JOIN memory_entities me ON n.id = me.memory_id
               JOIN entities e ON me.entity_id = e.id
               WHERE e.name = ?
               ORDER BY n.timestamp DESC""",
            (entity_name,),
        ).fetchall()

        return [self._row_to_memory(dict(r)) for r in rows]

    def get_by_id(self, memory_id: str) -> Memory | None:
        row = self._db.execute(
            "SELECT * FROM notes WHERE id = ?", (memory_id,)
        ).fetchone()
        if row is None:
            return None

        self._db.execute(
            """UPDATE notes SET access_count = access_count + 1,
               last_accessed = ? WHERE id = ?""",
            (datetime.now().isoformat(), memory_id),
        )
        # 重新读取以获取更新后的 access_count
        row = self._db.execute(
            "SELECT * FROM notes WHERE id = ?", (memory_id,)
        ).fetchone()
        return self._row_to_memory(dict(row))

    def get_recent(self, limit: int) -> list[Memory]:
        rows = self._db.execute(
            "SELECT * FROM notes ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_memory(dict(r)) for r in rows]

    # ── 内部方法 ──────────────────────────────────────────────────────

    def _ensure_entity(self, name: str) -> int:
        self._db.execute(
            """INSERT INTO entities (name) VALUES (?)
               ON CONFLICT(name) DO UPDATE SET mention_count = mention_count + 1""",
            (name,),
        )
        row = self._db.execute(
            "SELECT id FROM entities WHERE name = ?", (name,)
        ).fetchone()
        return row["id"]

    @staticmethod
    def _row_to_memory(row: dict) -> Memory:
        entities = json.loads(row.get("entities_json") or "[]")
        relations = json.loads(row.get("relations_json") or "[]")
        timestamp = datetime.fromisoformat(row["timestamp"])
        last_accessed = (
            datetime.fromisoformat(row["last_accessed"])
            if row.get("last_accessed")
            else None
        )
        return Memory(
            id=row["id"],
            content=row["content"],
            summary=row.get("summary"),
            source=row["source"] or "",
            timestamp=timestamp,
            importance=row.get("importance", 5),
            entities=entities,
            relations=relations,
            memory_type=row.get("memory_type", "episodic"),
            access_count=row.get("access_count", 0),
            last_accessed=last_accessed,
        )

    def close(self) -> None:
        if hasattr(self._db, "conn") and self._db.conn:
            self._db.conn.close()

    def __enter__(self) -> "SQLiteStoreAdapter":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
