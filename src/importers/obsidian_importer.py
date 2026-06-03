"""Obsidian vault importer — handles [[wikilinks]], tags, and frontmatter."""

from __future__ import annotations

import re
from pathlib import Path

from src.importers.base import ImportResult, chunk_text, extract_entities, generate_title


class ObsidianImporter:
    """Import .md files from an Obsidian vault, resolving [[wikilinks]] and #tags.

    For a full vault, pass the vault root directory; all .md files under it
    (excluding .obsidian/, .trash/, templates) will be imported.
    """

    _WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]")
    _TAG_PATTERN = re.compile(r"#[\w\-一-鿿/]+")
    _OBSIDIAN_IGNORE = {".obsidian", ".trash", ".git", "templates", "archive"}

    def import_data(self, source: str) -> ImportResult:
        """Import a single .md file or an entire Obsidian vault directory."""
        path = Path(source)
        metadata: dict = {
            "source_path": str(path.absolute()),
            "format": "obsidian",
        }

        if not path.exists():
            return ImportResult(
                source="obsidian",
                title=path.stem,
                error=f"Path not found: {source}",
                metadata=metadata,
            )

        files = self._collect_md_files(path)
        if not files:
            return ImportResult(
                source="obsidian",
                title=path.stem,
                error="No .md files found",
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

            clean = self._clean_wikilinks(raw)
            all_texts.append(clean)
            file_chunks = chunk_text(clean)
            for ch in file_chunks:
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

        # Also extract tags as entities
        tags = set()
        for file_path in files:
            try:
                raw = file_path.read_text(encoding="utf-8")
                tags.update(self._extract_tags(raw))
            except Exception:
                pass
        entities = list(dict.fromkeys(list(tags) + entities))  # preserve order, deduplicate

        metadata["tag_count"] = len(tags)

        return ImportResult(
            source="obsidian",
            title=title,
            chunks=all_chunks,
            entities=entities,
            memory_type="semantic",
            metadata=metadata,
        )

    def _collect_md_files(self, path: Path) -> list[Path]:
        """Collect .md files, respecting Obsidian directory conventions."""
        if path.is_file():
            return [path] if path.suffix == ".md" else []
        files: list[Path] = []
        for item in path.rglob("*.md"):
            # Skip ignored directories
            if any(ign in item.parts for ign in self._OBSIDIAN_IGNORE):
                continue
            files.append(item)
        return sorted(files)

    def _clean_wikilinks(self, text: str) -> str:
        """Replace [[wikilinks]] with their display text."""
        return self._WIKILINK_PATTERN.sub(r"\1", text)

    def _extract_tags(self, text: str) -> list[str]:
        """Extract #tags from text."""
        return list(set(m.lstrip("#") for m in self._TAG_PATTERN.findall(text)))
