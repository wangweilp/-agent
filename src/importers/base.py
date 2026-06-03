"""Importer protocol and shared types.

All importers implement the Importer protocol: receive a source (file path or URL),
return an ImportResult with chunks, entities, and metadata.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ImportResult:
    """Unified result from any importer.

    Attributes:
        source: Importer identifier ("markdown", "pdf", "notion", ...).
        title: Human-readable title derived from content or filename.
        chunks: List of {content, metadata} dicts, each ~500 tokens.
        entities: Extracted entity names (people, orgs, concepts, ...).
        memory_type: Default memory type for stored chunks.
        error: If non-None, import failed and chunks/entities may be partial.
        metadata: Extra structured data (source path, page count, duration, ...).
    """

    source: str
    title: str
    chunks: list[dict] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    memory_type: str = "episodic"
    error: str | None = None
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class Importer(Protocol):
    """Protocol every importer must satisfy."""

    def import_data(self, source: str) -> ImportResult:
        """Import data from *source* (file path or URL) and return structured result."""
        ...


# ---------------------------------------------------------------------------
# Shared helpers used by concrete importers
# ---------------------------------------------------------------------------

# Simple regex-based token estimator (used for chunk sizing).
# Approx: 1 token ≈ 4 characters for English, ≈ 1.5 characters for CJK.
_TOKEN_ESTIMATE_CHARS = 1800  # ~500 tokens for mixed content


def chunk_text(text: str, max_chars: int = _TOKEN_ESTIMATE_CHARS) -> list[str]:
    """Split *text* into roughly equal chunks by paragraph boundaries.

    Tries to break at paragraph breaks first, then sentence boundaries,
    and finally falls back to hard character splits.
    """
    if not text or not text.strip():
        return []

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return [text.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > max_chars and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0

        # If a single paragraph exceeds max_chars, split by sentences
        if len(para) > max_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            sentence_chunks = _split_long_paragraph(para, max_chars)
            chunks.extend(sentence_chunks)
            continue

        current.append(para)
        current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def _split_long_paragraph(text: str, max_chars: int) -> list[str]:
    """Split a single long paragraph by sentence boundaries, then hard breaks."""
    sentences = re.split(r"(?<=[。！？.!?])\s*", text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sent in sentences:
        if not sent.strip():
            continue
        if current_len + len(sent) > max_chars and current:
            chunks.append("".join(current))
            current = []
            current_len = 0
        current.append(sent)
        current_len += len(sent)

    if current:
        chunks.append("".join(current))

    return chunks or [text]


_ENTITY_PATTERN = re.compile(
    r"(?:"
    r"[A-Z][a-z]+(?:\s[A-Z][a-z]+)*"              # English proper nouns
    r"|[一-鿿]{2,8}"                       # CJK named entities
    r"|[A-Z]{2,8}"                                  # Acronyms
    r")"
)


def extract_entities(text: str, max_entities: int = 30) -> list[str]:
    """Extract basic named entities from text using simple heuristics.

    This is a lightweight extractor for import-time enrichment.
    For production use, swap in a proper NER model.
    """
    if not text:
        return []

    # 1. Pattern-based candidates
    candidates = _ENTITY_PATTERN.findall(text)

    # 2. Frequency-based filtering
    freq: dict[str, int] = {}
    for c in candidates:
        c_lower = c.lower()
        # Skip overly common words disguised as entities
        if c_lower in _STOP_WORDS:
            continue
        freq[c_lower] = freq.get(c_lower, 0) + 1

    # Sort by frequency, deduplicate (case-normalized), return top
    sorted_items = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    result: list[str] = []
    seen: set[str] = set()
    for name, _ in sorted_items:
        if name not in seen and len(result) < max_entities:
            result.append(name)
            seen.add(name)

    return result


_STOP_WORDS: set[str] = {
    "the", "this", "that", "these", "those", "there", "their",
    "what", "when", "where", "which", "with", "will", "would",
    "have", "here", "been", "being", "some", "such", "about",
    "other", "first", "after", "still", "also", "into", "then",
    "most", "only", "over", "very", "just", "more", "each",
    "because", "before", "between", "through", "during", "without",
    "chapter", "section", "page", "figure", "table",
}


def generate_title(text: str, fallback: str = "Untitled") -> str:
    """Derive a title from the first meaningful line of text."""
    if not text:
        return fallback
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip markdown headings markers
        clean = re.sub(r"^#{1,6}\s*", "", line).strip()
        if clean and len(clean) >= 2:
            return clean[:120]
    return fallback


def hash_source(source: str) -> str:
    """Return a short hex digest of the source string for stable IDs."""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
