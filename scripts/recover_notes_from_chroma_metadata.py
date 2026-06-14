"""Restore lost SQLite notes from local Chroma metadata plus screenshot evidence.

The project treats SQLite `notes` as the source of truth and Chroma as a
derived vector index. In this workspace the Chroma vectors still exist, but
their documents are empty. The only local evidence for the original note text
is `screenshots/video/03_03_memory.png`, which shows five memory cards.

This script restores those five visible records by combining:
- stable note ids, timestamps, entities and importance from Chroma metadata
- visible card text from the local screenshot

Text that was truncated in the screenshot is kept truncated with "...".
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adapters.config import Settings
from src.adapters.sqlite_store import SQLiteStoreAdapter
from src.core.types import Memory


@dataclass(frozen=True)
class ScreenshotNote:
    id: str
    content: str
    summary: str
    fallback_entities: tuple[str, ...]


SCREENSHOT_NOTES: dict[str, ScreenshotNote] = {
    "147bb63a-70e4-47bd-96fd-753b7bb5f873": ScreenshotNote(
        id="147bb63a-70e4-47bd-96fd-753b7bb5f873",
        content="用户是一名大二的学生，人工智能专业",
        summary="从 screenshots/video/03_03_memory.png 可见文本恢复的用户基础信息。",
        fallback_entities=("大二学生", "人工智能专业"),
    ),
    "bc0567cf-3f8c-4c05-93d2-83625ac1c9a9": ScreenshotNote(
        id="bc0567cf-3f8c-4c05-93d2-83625ac1c9a9",
        content=(
            "用户是一名大二人工智能专业学生，行动力极强的全栈实践型开发者。"
            "已掌握：ROS机器人（MobaXterm SSH连接小车、RViz建图定位、小车运动测试）、"
            "Linux终端命令、curl API调用、JWT认..."
        ),
        summary=(
            "从 screenshots/video/03_03_memory.png 可见文本恢复的技能画像；"
            "末尾省略号表示截图中正文被截断。"
        ),
        fallback_entities=(
            "ROS",
            "MobaXterm",
            "RViz",
            "Linux",
            "curl",
            "JWT",
            "人工智能专业",
        ),
    ),
    "09f00cb0-877d-405a-9e64-4d65f86e8663": ScreenshotNote(
        id="09f00cb0-877d-405a-9e64-4d65f86e8663",
        content=(
            "用户具备的完整技能体系：代码与开发辅助（多语言编程 "
            "Rust/Python/C++/JS-TS/Flutter/Shell/HTML-CSS、代码调试排错、"
            "代码审查优化、项目架构设计、机器人ROS开发、Tauri桌面应用、..."
        ),
        summary=(
            "从 screenshots/video/03_03_memory.png 可见文本恢复的用户技能体系；"
            "末尾省略号表示截图中正文被截断。"
        ),
        fallback_entities=("用户技能体系", "Rust", "Python", "ROS", "Tauri"),
    ),
    "ef3a64fa-1638-4079-b35b-fdd28cd276a6": ScreenshotNote(
        id="ef3a64fa-1638-4079-b35b-fdd28cd276a6",
        content=(
            "[视频记忆-工作区] 全图运行视频.mp4 主题: 全图运行演示 摘要: "
            "文件名暗示视频展示了某种全局或整体系统的运行过程，可能涉及软件、地图或流程演示。 "
            "时长: 0s | 关键帧: 0 OCR: 无 转录: 无 [更新] [视..."
        ),
        summary=(
            "从 screenshots/video/03_03_memory.png 可见文本恢复的视频工作区记忆；"
            "末尾省略号表示截图中正文被截断。"
        ),
        fallback_entities=("系统流程", "全图运行", "动态演示"),
    ),
    "d810342f-edee-4ba6-b299-1939ba993367": ScreenshotNote(
        id="d810342f-edee-4ba6-b299-1939ba993367",
        content=(
            '[视频记忆-概念] 主题=全图运行演示 | 实体=["全图运行", "动态演示", "系统流程"] '
            '| 概念=["全图运行", "动态演示", "系统流程"] | 用途=可用于软件演示、流程说明或培训材料'
        ),
        summary="从 screenshots/video/03_03_memory.png 可见文本恢复的视频概念记忆。",
        fallback_entities=("全图运行", "动态演示", "系统流程"),
    ),
}


def _parse_created_at(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _split_entities(value: object, fallback: tuple[str, ...]) -> list[str]:
    entities: list[str] = []
    if value:
        entities.extend(
            item.strip()
            for item in str(value).split(",")
            if item.strip()
        )
    entities.extend(fallback)
    return list(dict.fromkeys(entities))


def _load_chroma_metadata(chroma_db: Path) -> dict[str, dict]:
    conn = sqlite3.connect(chroma_db)
    conn.row_factory = sqlite3.Row
    try:
        embeddings = conn.execute(
            "SELECT id, embedding_id, created_at FROM embeddings ORDER BY created_at ASC, id ASC"
        ).fetchall()
        recovered: dict[str, dict] = {}
        for embedding in embeddings:
            metadata_rows = conn.execute(
                "SELECT key, string_value, int_value, float_value, bool_value "
                "FROM embedding_metadata WHERE id = ?",
                (embedding["id"],),
            ).fetchall()
            metadata: dict[str, object] = {}
            for row in metadata_rows:
                value = row["string_value"]
                if value is None:
                    value = row["int_value"]
                if value is None:
                    value = row["float_value"]
                if value is None and row["bool_value"] is not None:
                    value = bool(row["bool_value"])
                metadata[row["key"]] = value
            recovered[embedding["embedding_id"]] = {
                "created_at": embedding["created_at"],
                "metadata": metadata,
            }
        return recovered
    finally:
        conn.close()


def _backup_sqlite(sqlite_db: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = sqlite_db.with_name(
        f"{sqlite_db.stem}.before-memory-restore.{timestamp}{sqlite_db.suffix}"
    )
    source = sqlite3.connect(f"file:{sqlite_db}?mode=ro", uri=True)
    target = sqlite3.connect(backup)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup


def restore_notes(sqlite_db: Path, chroma_db: Path, *, create_backup: bool = True) -> dict:
    backup_path = _backup_sqlite(sqlite_db) if create_backup else None
    chroma_items = _load_chroma_metadata(chroma_db)
    settings = Settings(sqlite_db_path=str(sqlite_db))
    store = SQLiteStoreAdapter(settings, db_path=str(sqlite_db))

    restored: list[str] = []
    missing_chroma: list[str] = []
    try:
        for note_id, note in SCREENSHOT_NOTES.items():
            chroma_item = chroma_items.get(note_id)
            if chroma_item is None:
                missing_chroma.append(note_id)
                metadata: dict[str, object] = {}
                created_at = None
            else:
                metadata = chroma_item["metadata"]
                created_at = chroma_item["created_at"]

            entities = _split_entities(metadata.get("entities"), note.fallback_entities)
            memory = Memory(
                id=note.id,
                content=note.content,
                summary=note.summary,
                source=str(metadata.get("source") or "user"),
                timestamp=_parse_created_at(created_at),
                importance=int(metadata.get("importance") or 5),
                entities=entities,
                relations=[],
                memory_type=str(metadata.get("memory_type") or "episodic"),
            )
            store.store(memory)
            restored.append(note_id)
        return {
            "backup": str(backup_path) if backup_path else None,
            "restored": restored,
            "restored_count": len(restored),
            "missing_chroma": missing_chroma,
        }
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-db", default="data/agent_memory.db")
    parser.add_argument("--chroma-db", default="data/chroma_db/chroma.sqlite3")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    result = restore_notes(
        Path(args.sqlite_db),
        Path(args.chroma_db),
        create_backup=not args.no_backup,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
