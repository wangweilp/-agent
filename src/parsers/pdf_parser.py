"""PDF (.pdf) file parser."""

import os
from datetime import datetime, timezone

from src.parsers.base import DocumentChunk


def _extract_tags(text: str, max_terms: int = 5) -> list[str]:
    """Extract simple tags from text."""
    import re

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


class PDFParser:
    """Parse PDF files into chunks. Uses PyPDF2 as primary, pdfplumber as fallback."""

    def parse(self, file_path: str) -> list[DocumentChunk]:
        """Parse a PDF file. Never raises — returns empty list on error."""
        try:
            if not os.path.isfile(file_path):
                return []

            text = self._extract_text(file_path)
            if not text.strip():
                return []

            source_basename = os.path.basename(file_path)

            # Split by paragraph breaks (double newlines)
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
                            "parser": "pdf",
                            "chunk_index": idx,
                        },
                    )
                )

            return chunks

        except Exception:
            return []

    @staticmethod
    def _extract_text(file_path: str) -> str:
        """Extract text from PDF. Tries PyPDF2 first, then pdfplumber."""
        # Try PyPDF2
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(file_path)
            pages: list[str] = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    pages.append(page_text)
            result = "\n\n".join(pages)
            if result.strip():
                return result
        except Exception:
            pass

        # Try pdfplumber
        try:
            import pdfplumber

            pages: list[str] = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        pages.append(page_text)
            result = "\n\n".join(pages)
            if result.strip():
                return result
        except Exception:
            pass

        return ""
