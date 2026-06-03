"""Markdown file importer — splits by headings into semantic chunks."""

from __future__ import annotations

import re
from pathlib import Path

from src.importers.base import ImportResult, chunk_text, extract_entities, generate_title


class MarkdownImporter:
    """Import .md files, splitting on heading boundaries for semantic chunks."""

    def import_data(self, source: str) -> ImportResult:
        path = Path(source)
        metadata: dict = {"file_path": str(path.absolute()), "format": "markdown"}

        if not path.is_file():
            return ImportResult(
                source="markdown",
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
                    source="markdown",
                    title=path.stem,
                    error=f"Encoding error: {exc}",
                    metadata=metadata,
                )
        except Exception as exc:
            return ImportResult(
                source="markdown",
                title=path.stem,
                error=f"Read error: {exc}",
                metadata=metadata,
            )

        if not raw.strip():
            return ImportResult(
                source="markdown",
                title=path.stem,
                chunks=[],
                entities=[],
                metadata=metadata,
            )

        title = generate_title(raw, fallback=path.stem)
        entities = extract_entities(raw)
        sections = _split_by_headings(raw)
        metadata["section_count"] = len(sections)

        chunks: list[dict] = []
        for i, section in enumerate(sections):
            sub_chunks = chunk_text(section)
            for sub in sub_chunks:
                chunks.append({
                    "content": sub,
                    "metadata": {
                        "chunk_index": len(chunks),
                        "section_index": i,
                        "source_file": path.name,
                    },
                })

        return ImportResult(
            source="markdown",
            title=title,
            chunks=chunks,
            entities=entities,
            memory_type="semantic",
            metadata=metadata,
        )


def _split_by_headings(text: str) -> list[str]:
    """Split markdown text by ATX heading lines (##, ###, ...)."""
    # Use a heading pattern that captures the entire heading line
    parts = re.split(r"(\n(?=#{1,6}\s))", text)
    sections: list[str] = []
    current: list[str] = []

    for part in parts:
        line = part.strip()
        if not line:
            continue
        # Check if this part starts a new section
        if re.match(r"^#{1,6}\s", line):
            if current:
                sections.append("\n".join(current))
            current = [part]
        else:
            current.append(part)

    if current:
        sections.append("\n".join(current))

    return sections if sections else [text]
