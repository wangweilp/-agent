"""JSON file importer — flattens JSON structures to readable text."""

from __future__ import annotations

import json
from pathlib import Path

from src.importers.base import ImportResult, chunk_text, extract_entities, generate_title


class JsonImporter:
    """Import JSON files, flattening nested structures into text chunks.

    Handles both array-of-objects (common for exports) and arbitrary JSON.
    """

    def __init__(self, max_keys_per_chunk: int = 20):
        self.max_keys_per_chunk = max_keys_per_chunk

    def import_data(self, source: str) -> ImportResult:
        path = Path(source)
        metadata: dict = {"file_path": str(path.absolute()), "format": "json"}

        if not path.is_file():
            return ImportResult(
                source="json",
                title=path.stem,
                error=f"File not found: {source}",
                metadata=metadata,
            )

        try:
            raw = path.read_text(encoding="utf-8")
        except Exception as exc:
            return ImportResult(
                source="json",
                title=path.stem,
                error=f"Read error: {exc}",
                metadata=metadata,
            )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return ImportResult(
                source="json",
                title=path.stem,
                error=f"JSON parse error: {exc}",
                metadata=metadata,
            )

        flat_items = _flatten_json(data)

        if not flat_items:
            return ImportResult(
                source="json",
                title=path.stem,
                chunks=[],
                entities=[],
                metadata=metadata,
            )

        metadata["item_count"] = len(flat_items)

        # Group flattened items into chunks
        chunks: list[dict] = []
        chunk_items: list[str] = []
        for item in flat_items:
            chunk_items.append(item)
            if len(chunk_items) >= self.max_keys_per_chunk:
                chunks.append({
                    "content": "\n".join(chunk_items),
                    "metadata": {"chunk_index": len(chunks), "source_file": path.name},
                })
                chunk_items = []

        if chunk_items:
            chunks.append({
                "content": "\n".join(chunk_items),
                "metadata": {"chunk_index": len(chunks), "source_file": path.name},
            })

        full_text = "\n".join(flat_items)
        title = generate_title(full_text, fallback=path.stem)
        entities = extract_entities(full_text)

        return ImportResult(
            source="json",
            title=title,
            chunks=chunks,
            entities=entities,
            memory_type="episodic",
            metadata=metadata,
        )


def _flatten_json(data, parent_key: str = "", sep: str = ".") -> list[str]:
    """Recursively flatten a JSON structure into key: value lines."""
    items: list[str] = []

    if isinstance(data, dict):
        for k, v in data.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, (dict, list)):
                items.extend(_flatten_json(v, new_key, sep))
            else:
                items.append(f"{new_key}: {v}")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_key = f"{parent_key}[{i}]"
            if isinstance(item, (dict, list)):
                items.extend(_flatten_json(item, new_key, sep))
            else:
                items.append(f"{new_key}: {item}")
    else:
        items.append(f"{parent_key}: {data}")

    return items
