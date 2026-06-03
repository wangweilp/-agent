"""CSV (.csv) file parser. Each row becomes one chunk."""

import csv
import os
from datetime import datetime, timezone

from src.parsers.base import DocumentChunk


def _extract_tags(text: str, max_terms: int = 5) -> list[str]:
    """Extract simple tags from text."""
    import re

    terms: list[str] = []
    code_terms = set(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", text))
    terms.extend(code_terms)
    seen: set[str] = set()
    unique = []
    for t in terms:
        t = t.strip().lower()
        if t and t not in seen and len(t) > 2:
            seen.add(t)
            unique.append(t)
    return unique[:max_terms]


class CSVParser:
    """Parse CSV files. Each row becomes one chunk; column headers become metadata keys."""

    def parse(self, file_path: str) -> list[DocumentChunk]:
        """Parse a CSV file. Never raises — returns empty list on error."""
        try:
            if not os.path.isfile(file_path):
                return []

            source_basename = os.path.basename(file_path)

            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    return []

                headers = reader.fieldnames
                rows = list(reader)

            if not rows:
                return []

            chunks: list[DocumentChunk] = []
            for idx, row in enumerate(rows):
                # Build content as key: value lines
                content_lines = [f"{k}: {v}" for k, v in row.items() if v]
                content = "\n".join(content_lines)

                if not content.strip():
                    continue

                title = content[:200].strip()
                tags = _extract_tags(content)
                tags.append("csv_row")

                # Include all column values in metadata under "csv_" prefix
                row_metadata = {
                    "char_count": len(content),
                    "source_file": file_path,
                    "parser": "csv",
                    "chunk_index": idx,
                    "row_index": idx,
                    "csv_headers": list(headers),
                }
                for key, value in row.items():
                    row_metadata[f"csv_{key}"] = value if value else ""

                chunks.append(
                    DocumentChunk(
                        id=f"{source_basename}_chunk_{idx}",
                        source=file_path,
                        title=title,
                        content=content,
                        tags=tags,
                        created_at=datetime.now(timezone.utc),
                        metadata=row_metadata,
                    )
                )

            return chunks

        except Exception:
            return []
