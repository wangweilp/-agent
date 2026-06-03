"""Yuque (语雀) document importer — handles Yuque doc exports and API access.

Yuque exports include:
- .md files (Markdown format, including image references)
- .lakebook format (proprietary Yuque book export)
- API access via personal token

This importer handles all three.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.importers.base import ImportResult, chunk_text, extract_entities, generate_title


class YuqueImporter:
    """Import Yuque (语雀) documents from exports or API.

    Modes:
    - File: .md export file
    - Directory: a directory of exported .md files (lakebook format)
    - URL: Yuque doc URL (requires YUQUE_TOKEN env var)
    """

    _YUQUE_URL_PATTERN = re.compile(
        r"https?://(?:www\.)?yuque\.com/([\w-]+)/([\w-]+)/([\w-]+)"
    )

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    def import_data(self, source: str) -> ImportResult:
        metadata: dict = {"source": source, "format": "yuque"}

        if self._YUQUE_URL_PATTERN.match(source):
            return self._import_from_url(source, metadata)
        else:
            return self._import_from_file(source, metadata)

    # ------------------------------------------------------------------
    # File mode
    # ------------------------------------------------------------------

    def _import_from_file(self, source: str, metadata: dict) -> ImportResult:
        path = Path(source)

        if not path.exists():
            return ImportResult(
                source="yuque",
                title=path.stem,
                error=f"Path not found: {source}",
                metadata=metadata,
            )

        files = self._collect_md_files(path)
        if not files:
            return ImportResult(
                source="yuque",
                title=path.stem,
                error="No .md or .lakebook files found",
                metadata=metadata,
            )

        metadata["file_count"] = len(files)
        all_chunks: list[dict] = []
        all_texts: list[str] = []

        for file_path in files:
            try:
                raw = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    raw = file_path.read_text(encoding="gbk")
                except Exception:
                    continue
            except Exception:
                continue

            if not raw.strip():
                continue

            # Clean Yuque-specific markdown
            clean = self._clean_yuque_md(raw)
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

        if not all_chunks:
            return ImportResult(
                source="yuque",
                title=path.stem,
                error="No readable content found",
                metadata=metadata,
            )

        full_text = "\n\n".join(all_texts)
        title = generate_title(full_text, fallback=path.stem)
        entities = extract_entities(full_text)

        return ImportResult(
            source="yuque",
            title=title,
            chunks=all_chunks,
            entities=entities,
            memory_type="semantic",
            metadata=metadata,
        )

    @staticmethod
    def _collect_md_files(path: Path) -> list[Path]:
        """Collect .md files (and .lakebook JSON index)."""
        if path.is_file():
            if path.suffix in (".md",):
                return [path]
            if path.suffix == ".lakebook":
                return _parse_lakebook(path)
            return []

        files: list[Path] = []
        for item in path.rglob("*.md"):
            files.append(item)
        return sorted(files)

    @staticmethod
    def _clean_yuque_md(text: str) -> str:
        """Clean Yuque-specific artifacts in markdown."""
        # Remove Yuque's proprietary embed tags
        text = re.sub(r"<a name=\"[^\"]+\" class=\"lake-embed\">.*?</a>", "", text, flags=re.DOTALL)
        # Remove empty Yuque image references
        text = re.sub(r"!\[.*?\]\(https?://cdn\.yuque\.com/[^)]+\)", "[image]", text)
        return text

    # ------------------------------------------------------------------
    # URL / API mode
    # ------------------------------------------------------------------

    def _import_from_url(self, source: str, metadata: dict) -> ImportResult:
        import os

        token = os.environ.get("YUQUE_TOKEN", "")
        if not token:
            return ImportResult(
                source="yuque",
                title=source,
                error="YUQUE_TOKEN environment variable not set",
                metadata=metadata,
            )

        match = self._YUQUE_URL_PATTERN.match(source)
        if not match:
            return ImportResult(
                source="yuque",
                title=source,
                error="Invalid Yuque URL format",
                metadata=metadata,
            )

        namespace = f"{match.group(1)}/{match.group(2)}"
        slug = match.group(3)
        metadata["namespace"] = namespace
        metadata["slug"] = slug

        content = self._fetch_via_api(namespace, slug, token)
        if content is None:
            return ImportResult(
                source="yuque",
                title=slug,
                error="Failed to fetch Yuque document via API",
                metadata=metadata,
            )

        title = content.get("title", slug)
        body = content.get("body", "")

        # Clean HTML body to text
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(body, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
        except ImportError:
            text = re.sub(r"<[^>]+>", "", body)

        if not text.strip():
            return ImportResult(
                source="yuque",
                title=title,
                chunks=[],
                entities=[],
                metadata=metadata,
            )

        entities = extract_entities(text)
        text_chunks = chunk_text(text)

        chunks: list[dict] = []
        for ch in text_chunks:
            chunks.append({
                "content": ch,
                "metadata": {
                    "chunk_index": len(chunks),
                    "namespace": namespace,
                    "slug": slug,
                    "source_url": source,
                },
            })

        metadata["title"] = title
        return ImportResult(
            source="yuque",
            title=title,
            chunks=chunks,
            entities=entities,
            memory_type="semantic",
            metadata=metadata,
        )

    def _fetch_via_api(self, namespace: str, slug: str, token: str) -> dict | None:
        """Fetch Yuque doc via API."""
        try:
            import httpx
        except ImportError:
            return None

        api_url = f"https://www.yuque.com/api/v2/repos/{namespace}/docs/{slug}"
        headers = {
            "User-Agent": "CognitiveOS/1.0",
            "X-Auth-Token": token,
        }

        try:
            resp = httpx.get(api_url, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                return data
        except Exception:
            pass

        return None


def _parse_lakebook(lakebook_path: Path) -> list[Path]:
    """Parse a .lakebook JSON file for referenced .md entries."""
    base_dir = lakebook_path.parent
    try:
        data = json.loads(lakebook_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    files: list[Path] = []
    if isinstance(data, dict):
        entries = data.get("entries") or data.get("pages") or []
        for entry in entries:
            file_path = entry.get("file") or entry.get("path") or ""
            if file_path:
                full = base_dir / file_path
                if full.exists():
                    files.append(full)

    return files or [lakebook_path]
