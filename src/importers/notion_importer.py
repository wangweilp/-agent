"""Notion export importer — handles Markdown+CSV export format.

Notion exports come as a directory with .md files (page content) and optional .csv
files (database views). This importer processes the standard Notion export structure.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from src.importers.base import ImportResult, chunk_text, extract_entities, generate_title


class NotionImporter:
    """Import Notion exports (Markdown + CSV format).

    For a Notion export directory, recursively processes all .md and .csv files.
    """

    def import_data(self, source: str) -> ImportResult:
        path = Path(source)
        metadata: dict = {
            "source_path": str(path.absolute()),
            "format": "notion_export",
        }

        if not path.exists():
            return ImportResult(
                source="notion",
                title=path.stem,
                error=f"Path not found: {source}",
                metadata=metadata,
            )

        files_md, files_csv = self._collect_files(path)
        if not files_md and not files_csv:
            return ImportResult(
                source="notion",
                title=path.stem,
                error="No .md or .csv files found in Notion export",
                metadata=metadata,
            )

        metadata["md_count"] = len(files_md)
        metadata["csv_count"] = len(files_csv)

        all_chunks: list[dict] = []
        all_texts: list[str] = []

        # Process markdown pages
        for file_path in files_md:
            try:
                raw = file_path.read_text(encoding="utf-8")
            except Exception:
                continue
            if not raw.strip():
                continue
            clean = _clean_notion_md(raw)
            all_texts.append(clean)
            for ch in chunk_text(clean):
                all_chunks.append({
                    "content": ch,
                    "metadata": {
                        "chunk_index": len(all_chunks),
                        "source_file": file_path.name,
                        "type": "page",
                    },
                })

        # Process CSV databases
        for file_path in files_csv:
            try:
                raw = file_path.read_text(encoding="utf-8")
                reader = csv.DictReader(raw.splitlines())
                rows = list(reader)
                headers = reader.fieldnames or []
            except Exception:
                continue

            for i, row in enumerate(rows):
                fields = [f"{h}: {row.get(h, '')}" for h in headers if row.get(h, "").strip()]
                if not fields:
                    continue
                row_text = f"[{file_path.stem} row {i + 1}] " + " | ".join(fields)
                all_texts.append(row_text)
                all_chunks.append({
                    "content": row_text,
                    "metadata": {
                        "chunk_index": len(all_chunks),
                        "source_file": file_path.name,
                        "type": "database_row",
                        "row": i,
                    },
                })

        full_text = "\n\n".join(all_texts)
        title = path.name
        entities = extract_entities(full_text)

        return ImportResult(
            source="notion",
            title=title,
            chunks=all_chunks,
            entities=entities,
            memory_type="semantic",
            metadata=metadata,
        )

    @staticmethod
    def _collect_files(path: Path) -> tuple[list[Path], list[Path]]:
        """Collect .md and .csv files from a Notion export directory."""
        md_files: list[Path] = []
        csv_files: list[Path] = []
        for item in path.rglob("*"):
            if item.is_file():
                if item.suffix == ".md":
                    md_files.append(item)
                elif item.suffix == ".csv":
                    csv_files.append(item)
        return sorted(md_files), sorted(csv_files)


def _clean_notion_md(text: str) -> str:
    """Clean Notion-specific markdown artifacts."""
    # Remove Notion callout blocks (```...``` with language)
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)
    # Remove base64 image links (common in Notion exports)
    text = re.sub(r"!\[.*?\]\(data:image[^)]+\)", "[image]", text)
    return text
