"""OCR parser for image files (.png, .jpg, .jpeg, .bmp, .tiff) using pytesseract."""

import os
import re
from datetime import datetime, timezone

from src.parsers.base import DocumentChunk

_SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".gif"}


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


class OCRParser:
    """Parse image files into chunks using OCR (pytesseract)."""

    def parse(self, file_path: str) -> list[DocumentChunk]:
        """Parse an image file via OCR. Never raises — returns empty list on error."""
        try:
            if not os.path.isfile(file_path):
                return []

            ext = os.path.splitext(file_path)[1].lower()
            if ext not in _SUPPORTED_EXTENSIONS:
                return []

            text = self._ocr_extract(file_path)
            if not text or not text.strip():
                return []

            source_basename = os.path.basename(file_path)

            # Split by paragraph breaks
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

            from src.parsers.chunking import paragraph_chunks

            chunk_texts = paragraph_chunks(paragraphs, chunk_size=2000, overlap=250)

            chunks: list[DocumentChunk] = []
            for idx, chunk_text in enumerate(chunk_texts):
                title = chunk_text[:200].strip()
                tags = _extract_tags(chunk_text)
                tags.append("ocr")
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
                            "parser": "ocr",
                            "ocr_engine": "pytesseract",
                            "chunk_index": idx,
                            "image_extension": ext,
                        },
                    )
                )

            return chunks

        except Exception:
            return []

    @staticmethod
    def _ocr_extract(file_path: str) -> str:
        """Run OCR on an image file and return extracted text."""
        try:
            from PIL import Image

            image = Image.open(file_path)

            # Try pytesseract
            try:
                import pytesseract

                text = pytesseract.image_to_string(image)
                if text.strip():
                    return text
            except Exception:
                pass

            # Fallback: try easyocr
            try:
                import easyocr

                reader = easyocr.Reader(["en"], gpu=False)
                results = reader.readtext(file_path, detail=False)
                if results:
                    return "\n".join(results)
            except Exception:
                pass

            return ""

        except Exception:
            return ""
