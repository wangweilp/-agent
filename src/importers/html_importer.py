"""HTML file importer — extracts clean text via BeautifulSoup."""

from __future__ import annotations

from pathlib import Path

from src.importers.base import ImportResult, chunk_text, extract_entities, generate_title


class HtmlImporter:
    """Import .html files, stripping tags and scripts."""

    def import_data(self, source: str) -> ImportResult:
        path = Path(source)
        metadata: dict = {"file_path": str(path.absolute()), "format": "html"}

        if not path.is_file():
            return ImportResult(
                source="html",
                title=path.stem,
                error=f"File not found: {source}",
                metadata=metadata,
            )

        try:
            raw = path.read_text(encoding="utf-8")
        except Exception as exc:
            return ImportResult(
                source="html",
                title=path.stem,
                error=f"Read error: {exc}",
                metadata=metadata,
            )

        try:
            from bs4 import BeautifulSoup  # type: ignore[import-untyped]
        except ImportError:
            return ImportResult(
                source="html",
                title=path.stem,
                error="beautifulsoup4 is not installed",
                metadata=metadata,
            )

        soup = BeautifulSoup(raw, "html.parser")

        # Remove script, style, and nav elements
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()

        # Try to get the <title>
        title_tag = soup.find("title")
        doc_title = title_tag.get_text(strip=True) if title_tag else path.stem

        # Get body or root text
        body = soup.find("body") or soup
        text = body.get_text(separator="\n", strip=True)

        if not text:
            return ImportResult(
                source="html",
                title=doc_title,
                chunks=[],
                entities=[],
                metadata=metadata,
            )

        entities = extract_entities(text)
        text_chunks = chunk_text(text)

        chunks: list[dict] = []
        for text_segment in text_chunks:
            chunks.append({
                "content": text_segment,
                "metadata": {
                    "chunk_index": len(chunks),
                    "source_file": path.name,
                },
            })

        return ImportResult(
            source="html",
            title=doc_title,
            chunks=chunks,
            entities=entities,
            memory_type="episodic",
            metadata=metadata,
        )
