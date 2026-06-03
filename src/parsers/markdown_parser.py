"""Markdown (.md) file parser."""

import os
import re
from datetime import datetime, timezone

from src.parsers.base import DocumentChunk


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _extract_key_terms(text: str, max_terms: int = 5) -> list[str]:
    """Extract simple key terms from text (capitalized words, technical terms)."""
    terms: list[str] = []
    # Capitalized CamelCase or snake_case identifiers
    code_terms = set(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", text))
    terms.extend(code_terms)
    # Hashtag-like or bracketed categories
    bracket_terms = re.findall(r"\[([^\]]+)\]", text)
    terms.extend(bracket_terms)
    # Emphasized **terms**
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


class MarkdownParser:
    """Parse .md files into chunks split by ## headings."""

    def parse(self, file_path: str) -> list[DocumentChunk]:
        """Parse a markdown file. Never raises — returns empty list on error."""
        try:
            if not os.path.isfile(file_path):
                return []

            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()

            if not text.strip():
                return []

            source_basename = os.path.basename(file_path)

            # Split by ## headings (h2). Also capture h1 as first section.
            # Strategy: split on any heading line, then chunk each section.
            sections = self._split_by_headings(text)

            chunks: list[DocumentChunk] = []
            carry = ""

            for idx, (heading, body) in enumerate(sections):
                content = carry + body
                title = heading if heading else content[:200].strip()

                # Extract tags from heading + body
                tags = _extract_key_terms(heading + " " + body) if heading else _extract_key_terms(body)

                # If content fits in one chunk
                if len(content) <= 2000:
                    chunk_id = f"{source_basename}_chunk_{idx}"
                    chunks.append(
                        DocumentChunk(
                            id=chunk_id,
                            source=file_path,
                            title=title,
                            content=content,
                            tags=tags,
                            created_at=datetime.now(timezone.utc),
                            metadata={
                                "char_count": len(content),
                                "source_file": file_path,
                                "parser": "markdown",
                                "heading": heading,
                                "section_index": idx,
                            },
                        )
                    )
                    carry = ""
                else:
                    # Sub-chunk with sliding window
                    from src.parsers.chunking import sliding_window_chunks

                    sub_chunks = sliding_window_chunks(content, chunk_size=2000, overlap=250)
                    for sub_idx, sub_text in enumerate(sub_chunks):
                        chunk_id = f"{source_basename}_chunk_{idx}_{sub_idx}"
                        sub_tags = tags + _extract_key_terms(sub_text)
                        chunks.append(
                            DocumentChunk(
                                id=chunk_id,
                                source=file_path,
                                title=title,
                                content=sub_text,
                                tags=list(dict.fromkeys(sub_tags)),  # deduplicate preserving order
                                created_at=datetime.now(timezone.utc),
                                metadata={
                                    "char_count": len(sub_text),
                                    "source_file": file_path,
                                    "parser": "markdown",
                                    "heading": heading,
                                    "section_index": idx,
                                    "sub_chunk_index": sub_idx,
                                },
                            )
                        )
                    # Carry last ~250 chars as overlap for next section
                    if len(content) > 250:
                        carry = content[-250:] + "\n\n"
                    else:
                        carry = content + "\n\n"

            return chunks

        except Exception:
            return []

    @staticmethod
    def _split_by_headings(text: str) -> list[tuple[str, str]]:
        """Split markdown text into (heading, body) pairs by heading lines.

        Returns list of (heading_text, section_body) tuples.
        """
        lines = text.split("\n")
        sections: list[tuple[str, str]] = []
        current_heading = ""
        current_body: list[str] = []

        for line in lines:
            m = _HEADING_RE.match(line)
            if m:
                # Save previous section
                if current_body or current_heading:
                    body_text = "\n".join(current_body).strip()
                    sections.append((current_heading, body_text))
                current_heading = m.group(2).strip()
                current_body = []
            else:
                current_body.append(line)

        # Last section
        body_text = "\n".join(current_body).strip()
        sections.append((current_heading, body_text))

        return sections
