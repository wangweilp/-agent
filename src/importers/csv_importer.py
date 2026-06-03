"""CSV file importer — treats each row as a potential memory chunk."""

from __future__ import annotations

import csv
from pathlib import Path

from src.importers.base import ImportResult, chunk_text, extract_entities, generate_title


class CsvImporter:
    """Import CSV files, converting each row into structured text.

    Large CSV files are batched: every *batch_size* rows become one chunk.
    """

    def __init__(self, batch_size: int = 20):
        self.batch_size = batch_size

    def import_data(self, source: str) -> ImportResult:
        path = Path(source)
        metadata: dict = {"file_path": str(path.absolute()), "format": "csv"}

        if not path.is_file():
            return ImportResult(
                source="csv",
                title=path.stem,
                error=f"File not found: {source}",
                metadata=metadata,
            )

        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                raw = path.read_text(encoding="gbk")
                metadata["encoding"] = "gbk"
            except Exception as exc:
                return ImportResult(
                    source="csv",
                    title=path.stem,
                    error=f"Encoding error: {exc}",
                    metadata=metadata,
                )
        except Exception as exc:
            return ImportResult(
                source="csv",
                title=path.stem,
                error=f"Read error: {exc}",
                metadata=metadata,
            )

        try:
            reader = csv.DictReader(raw.splitlines())
            headers = reader.fieldnames or []
            rows = list(reader)
        except Exception as exc:
            return ImportResult(
                source="csv",
                title=path.stem,
                error=f"CSV parse error: {exc}",
                metadata=metadata,
            )

        if not rows:
            return ImportResult(
                source="csv",
                title=path.stem,
                chunks=[],
                entities=[],
                metadata=metadata,
            )

        metadata["row_count"] = len(rows)
        metadata["headers"] = headers

        # Convert rows to text
        all_text_parts: list[str] = []
        for i, row in enumerate(rows):
            fields = [f"{h}: {row.get(h, '')}" for h in headers if row.get(h, '').strip()]
            if fields:
                all_text_parts.append(f"[Row {i + 1}] " + " | ".join(fields))

        full_text = "\n".join(all_text_parts)
        title = path.stem
        entities = extract_entities(full_text)

        # Batch rows into chunks
        chunks: list[dict] = []
        for batch_start in range(0, len(all_text_parts), self.batch_size):
            batch = all_text_parts[batch_start : batch_start + self.batch_size]
            batch_text = "\n".join(batch)
            chunks.append({
                "content": batch_text,
                "metadata": {
                    "chunk_index": len(chunks),
                    "row_start": batch_start,
                    "row_end": min(batch_start + self.batch_size, len(all_text_parts)),
                    "source_file": path.name,
                },
            })

        return ImportResult(
            source="csv",
            title=title,
            chunks=chunks,
            entities=entities,
            memory_type="episodic",
            metadata=metadata,
        )
