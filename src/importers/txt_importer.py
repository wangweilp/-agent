"""Plain text file importer."""

from __future__ import annotations

from pathlib import Path

from src.importers.base import ImportResult, chunk_text, extract_entities, generate_title


class TxtImporter:
    """Import .txt files as text chunks."""

    def import_data(self, source: str) -> ImportResult:
        path = Path(source)
        metadata: dict = {"file_path": str(path.absolute()), "format": "txt"}

        if not path.is_file():
            return ImportResult(
                source="txt",
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
                    source="txt",
                    title=path.stem,
                    error=f"Encoding error: {exc}",
                    metadata=metadata,
                )
        except Exception as exc:
            return ImportResult(
                source="txt",
                title=path.stem,
                error=f"Read error: {exc}",
                metadata=metadata,
            )

        if not raw.strip():
            return ImportResult(
                source="txt",
                title=path.stem,
                chunks=[],
                entities=[],
                metadata=metadata,
            )

        title = generate_title(raw, fallback=path.stem)
        entities = extract_entities(raw)
        text_chunks = chunk_text(raw)

        chunks: list[dict] = []
        for text in text_chunks:
            chunks.append({
                "content": text,
                "metadata": {
                    "chunk_index": len(chunks),
                    "source_file": path.name,
                },
            })

        return ImportResult(
            source="txt",
            title=title,
            chunks=chunks,
            entities=entities,
            memory_type="episodic",
            metadata=metadata,
        )
