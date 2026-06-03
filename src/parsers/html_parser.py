"""HTML (.html, .htm) file parser using BeautifulSoup."""

import os
import re
from datetime import datetime, timezone

from src.parsers.base import DocumentChunk


def _extract_tags(text: str, max_terms: int = 5) -> list[str]:
    """Extract simple tags from text."""
    terms: list[str] = []
    code_terms = set(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", text))
    terms.extend(code_terms)
    bracket_terms = re.findall(r"\[([^\]]+)\]", text)
    terms.extend(bracket_terms)
    bold_terms = re.findall(r"\*\*([^*]+)\*\*", text)
    terms.extend(bold_terms)
    seen: set[str] = set()
    unique = []
    for t in terms:
        t = t.strip().lower()
        if t and t not in seen and len(t) > 2:
            seen.add(t)
            unique.append(t)
    return unique[:max_terms]


class HTMLParser:
    """Parse HTML files into chunks by section/paragraph breaks."""

    def parse(self, file_path: str) -> list[DocumentChunk]:
        """Parse an HTML file. Never raises — returns empty list on error."""
        try:
            if not os.path.isfile(file_path):
                return []

            text = self._extract_text(file_path)
            if not text.strip():
                return []

            source_basename = os.path.basename(file_path)

            # Split by section breaks (multiple newlines)
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

            from src.parsers.chunking import paragraph_chunks

            chunk_texts = paragraph_chunks(paragraphs, chunk_size=2000, overlap=250)

            chunks: list[DocumentChunk] = []
            for idx, chunk_text in enumerate(chunk_texts):
                title = chunk_text[:200].strip()
                tags = _extract_tags(chunk_text)
                chunks.append(
                    DocumentChunk(
                        id=f"{source_basename}_chunk_{idx}",
                        source=file_path,
                        title=title,
                        content=chunk_text,
                        tags=tags,
                        created_at=datetime.now(timezone.utc),
                        metadata={
                            "char_count": len(chunk_text),
                            "source_file": file_path,
                            "parser": "html",
                            "chunk_index": idx,
                        },
                    )
                )

            return chunks

        except Exception:
            return []

    @staticmethod
    def _extract_text(file_path: str) -> str:
        """Extract readable text from HTML, removing scripts and styles."""
        try:
            from bs4 import BeautifulSoup

            with open(file_path, "r", encoding="utf-8") as f:
                html = f.read()

            soup = BeautifulSoup(html, "html.parser")

            # Remove script, style, and other non-content tags
            for tag_name in ["script", "style", "nav", "footer", "header", "noscript", "iframe"]:
                for tag in soup.find_all(tag_name):
                    tag.decompose()

            # Try to extract title
            title_tag = soup.find("title")
            title_text = title_tag.get_text(strip=True) if title_tag else ""

            # Get body text
            body = soup.find("body")
            if body:
                # Try to split by block elements for natural section boundaries
                block_tags = ["h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "div"]
                for tag_name in block_tags:
                    for tag in body.find_all(tag_name):
                        # Insert double newline before block elements for section splitting
                        tag.insert_before("\n\n")
                text = body.get_text(separator="\n", strip=True)
            else:
                text = soup.get_text(separator="\n", strip=True)

            # Prepend title as h1 if found
            if title_text:
                text = f"# {title_text}\n\n{text}"

            # Collapse excessive whitespace
            text = re.sub(r"\n{3,}", "\n\n", text)

            return text

        except Exception:
            return ""
