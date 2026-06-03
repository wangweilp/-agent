"""Logseq graph importer — processes Logseq .md files with block references."""

from __future__ import annotations

import re
from pathlib import Path

from src.importers.base import ImportResult, chunk_text, extract_entities, generate_title


class LogseqImporter:
    """Import .md files from a Logseq graph.

    Logseq uses bullet-based outlines, block references ((...)), and properties.
    Similar to Obsidian but with block-oriented structure.
    """

    _BLOCK_REF_PATTERN = re.compile(r"\(\(([a-f0-9-]+)\)\)")
    _PROPERTY_PATTERN = re.compile(r"^([\w-]+)::\s*(.*)$", re.MULTILINE)
    _TAG_PATTERN = re.compile(r"#[\w\-一-鿿]+")
    _LOGSESQ_IGNORE = {".git", "logseq", "assets", "journals"}

    def import_data(self, source: str) -> ImportResult:
        """Import a single Logseq .md file or an entire graph directory."""
        path = Path(source)
        metadata: dict = {
            "source_path": str(path.absolute()),
            "format": "logseq",
        }

        if not path.exists():
            return ImportResult(
                source="logseq",
                title=path.stem,
                error=f"Path not found: {source}",
                metadata=metadata,
            )

        files = self._collect_files(path)
        if not files:
            return ImportResult(
                source="logseq",
                title=path.stem,
                error="No .md files found in Logseq graph",
                metadata=metadata,
            )

        metadata["file_count"] = len(files)
        all_chunks: list[dict] = []
        all_texts: list[str] = []

        for file_path in files:
            try:
                raw = file_path.read_text(encoding="utf-8")
            except Exception:
                continue
            if not raw.strip():
                continue

            clean = self._clean_logseq_md(raw)
            all_texts.append(clean)
            for ch in chunk_text(clean):
                all_chunks.append({
                    "content": ch,
                    "metadata": {
                        "chunk_index": len(all_chunks),
                        "source_file": file_path.name,
                        "relative_path": str(file_path.relative_to(path))
                        if path.is_dir()
                        else file_path.name,
                    },
                })

        full_text = "\n\n".join(all_texts)
        title = generate_title(full_text, fallback=path.stem)
        entities = extract_entities(full_text)

        # Extract tags as additional entities
        tags = set()
        for file_path in files:
            try:
                raw = file_path.read_text(encoding="utf-8")
                tags.update(self._TAG_PATTERN.findall(raw))
            except Exception:
                pass
        entities = list(dict.fromkeys([t.lstrip("#") for t in tags] + entities))

        return ImportResult(
            source="logseq",
            title=title,
            chunks=all_chunks,
            entities=entities,
            memory_type="semantic",
            metadata=metadata,
        )

    def _collect_files(self, path: Path) -> list[Path]:
        """Collect .md files, respecting Logseq directory conventions."""
        if path.is_file():
            return [path] if path.suffix == ".md" else []
        files: list[Path] = []
        for item in path.rglob("*.md"):
            if any(ign in item.parts for ign in self._LOGSESQ_IGNORE):
                continue
            files.append(item)
        return sorted(files)

    def _clean_logseq_md(self, text: str) -> str:
        """Clean Logseq-specific markdown artifacts.

        Removes block references, collapses bullet indentation, strips properties.
        """
        # Replace block references with placeholder
        clean = self._BLOCK_REF_PATTERN.sub("[ref]", text)

        # Strip leading bullet markers and collapse hierarchy
        clean = re.sub(r"^\s*[-*+]\s+", "", clean, flags=re.MULTILINE)

        return clean
