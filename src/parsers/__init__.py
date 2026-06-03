"""Document parsers package.

Each parser implements the Parser protocol and returns list[DocumentChunk].
All parsers never raise — they return an empty list on failure.
"""

from src.parsers.base import DocumentChunk, Parser
from src.parsers.chunking import paragraph_chunks, sliding_window_chunks
from src.parsers.csv_parser import CSVParser
from src.parsers.docx_parser import DocxParser
from src.parsers.html_parser import HTMLParser
from src.parsers.markdown_parser import MarkdownParser
from src.parsers.ocr_parser import OCRParser
from src.parsers.pdf_parser import PDFParser
from src.parsers.subtitle_parser import SubtitleParser

__all__ = [
    "DocumentChunk",
    "Parser",
    "sliding_window_chunks",
    "paragraph_chunks",
    "MarkdownParser",
    "PDFParser",
    "DocxParser",
    "HTMLParser",
    "CSVParser",
    "OCRParser",
    "SubtitleParser",
]

# Mapping of file extensions to parser classes
PARSER_REGISTRY: dict[str, type] = {
    ".md": MarkdownParser,
    ".markdown": MarkdownParser,
    ".pdf": PDFParser,
    ".docx": DocxParser,
    ".doc": DocxParser,
    ".html": HTMLParser,
    ".htm": HTMLParser,
    ".csv": CSVParser,
    ".tsv": CSVParser,
    ".png": OCRParser,
    ".jpg": OCRParser,
    ".jpeg": OCRParser,
    ".bmp": OCRParser,
    ".tiff": OCRParser,
    ".tif": OCRParser,
    ".gif": OCRParser,
    ".srt": SubtitleParser,
    ".vtt": SubtitleParser,
}


def get_parser_for_file(file_path: str) -> Parser | None:
    """Return the appropriate parser instance for a given file, or None."""
    import os

    ext = os.path.splitext(file_path)[1].lower()
    parser_cls = PARSER_REGISTRY.get(ext)
    if parser_cls is None:
        return None
    return parser_cls()


def parse_file(file_path: str) -> list[DocumentChunk]:
    """Convenience: auto-detect and parse a file. Returns empty list on failure."""
    parser = get_parser_for_file(file_path)
    if parser is None:
        return []
    return parser.parse(file_path)
