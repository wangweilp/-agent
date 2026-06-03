"""PDF file importer — extracts text via pdfplumber (preferred) or PyPDF2 fallback."""

from __future__ import annotations

from pathlib import Path

from src.importers.base import ImportResult, chunk_text, extract_entities, generate_title


class PdfImporter:
    """Import PDF files, extracting text page by page.

    Tries pdfplumber first for higher-quality extraction;
    falls back to PyPDF2 if pdfplumber is not available.
    """

    def import_data(self, source: str) -> ImportResult:
        path = Path(source)
        metadata: dict = {
            "file_path": str(path.absolute()),
            "format": "pdf",
            "extraction_method": "unknown",
        }

        if not path.is_file():
            return ImportResult(
                source="pdf",
                title=path.stem,
                error=f"File not found: {source}",
                metadata=metadata,
            )

        try:
            text, page_count, method = _extract_pdf_text(path)
            metadata["extraction_method"] = method
            metadata["page_count"] = page_count
        except Exception as exc:
            return ImportResult(
                source="pdf",
                title=path.stem,
                error=f"PDF extraction failed: {exc}",
                metadata=metadata,
            )

        if not text.strip():
            return ImportResult(
                source="pdf",
                title=path.stem,
                chunks=[],
                entities=[],
                metadata=metadata,
            )

        title = generate_title(text, fallback=path.stem)
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
            source="pdf",
            title=title,
            chunks=chunks,
            entities=entities,
            memory_type="semantic",
            metadata=metadata,
        )


def _extract_pdf_text(path: Path) -> tuple[str, int, str]:
    """Extract text from a PDF. Returns (text, page_count, method)."""

    # Try pdfplumber first
    try:
        import pdfplumber  # type: ignore[import-untyped]

        text_parts: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts), page_count, "pdfplumber"
    except ImportError:
        pass
    except Exception:
        # pdfplumber installed but failed — try PyPDF2
        pass

    # Fall back to PyPDF2
    import PyPDF2  # type: ignore[import-untyped]

    with open(path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        page_count = len(reader.pages)
        text_parts: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts), page_count, "PyPDF2"
