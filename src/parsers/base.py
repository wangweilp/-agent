"""Base types and protocol for document parsers."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable


@dataclass
class DocumentChunk:
    """A single chunk of parsed document content."""

    id: str
    source: str  # file path or URL
    title: str
    content: str
    tags: list[str]
    created_at: datetime
    metadata: dict


@runtime_checkable
class Parser(Protocol):
    """Protocol that all document parsers must implement."""

    def parse(self, file_path: str) -> list[DocumentChunk]:
        """Parse a file into a list of document chunks.

        Must never raise — return empty list on failure.
        """
        ...
