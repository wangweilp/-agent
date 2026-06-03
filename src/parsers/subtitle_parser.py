"""Subtitle parser for .srt and .vtt files."""

import os
import re
from datetime import datetime, timezone

from src.parsers.base import DocumentChunk

_SRT_BLOCK_RE = re.compile(
    r"(\d+)\s*\n"  # index
    r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*\n"  # timestamps
    r"((?:.+\n?)+?)(?=\n\d+\n|\Z)",  # text lines
    re.MULTILINE,
)

_VTT_BLOCK_RE = re.compile(
    r"((?:\d{2}:)?\d{2}:\d{2}\.\d{3}\s*-->\s*(?:\d{2}:)?\d{2}:\d{2}\.\d{3}.*?)\n"  # timestamp line
    r"((?:.+\n?)+?)(?=\n(?:\d{2}:)?\d{2}:\d{2}\.\d{3}|\Z)",  # text lines
    re.MULTILINE,
)


def _extract_tags(text: str, max_terms: int = 5) -> list[str]:
    """Extract simple tags from text."""
    terms: list[str] = []
    code_terms = set(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", text))
    terms.extend(code_terms)
    bracket_terms = re.findall(r"\[([^\]]+)\]", text)
    terms.extend(bracket_terms)
    seen: set[str] = set()
    unique = []
    for t in terms:
        t = t.strip().lower()
        if t and t not in seen and len(t) > 2:
            seen.add(t)
            unique.append(t)
    return unique[:max_terms]


class SubtitleParser:
    """Parse subtitle files (.srt, .vtt) into chunks with timestamps in metadata."""

    def parse(self, file_path: str) -> list[DocumentChunk]:
        """Parse a subtitle file. Never raises — returns empty list on error."""
        try:
            if not os.path.isfile(file_path):
                return []

            ext = os.path.splitext(file_path)[1].lower()
            if ext == ".srt":
                return self._parse_srt(file_path)
            elif ext == ".vtt":
                return self._parse_vtt(file_path)
            else:
                return []

        except Exception:
            return []

    # ------------------------------------------------------------------
    # SRT
    # ------------------------------------------------------------------
    def _parse_srt(self, file_path: str) -> list[DocumentChunk]:
        """Parse .srt subtitle file."""
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

        blocks = _SRT_BLOCK_RE.findall(text)
        if not blocks:
            return []

        return self._build_chunks(file_path, blocks, format_type="srt")

    # ------------------------------------------------------------------
    # VTT
    # ------------------------------------------------------------------
    def _parse_vtt(self, file_path: str) -> list[DocumentChunk]:
        """Parse .vtt subtitle file."""
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

        # Strip WEBVTT header
        text = re.sub(r"^WEBVTT.*?\n\n?", "", text, flags=re.IGNORECASE)

        blocks = _VTT_BLOCK_RE.findall(text)
        if not blocks:
            return []

        return self._build_chunks(file_path, blocks, format_type="vtt")

    # ------------------------------------------------------------------
    # Chunk building
    # ------------------------------------------------------------------
    def _build_chunks(
        self,
        file_path: str,
        blocks: list,
        format_type: str,
    ) -> list[DocumentChunk]:
        """Merge subtitle blocks into chunks of ~2000 chars with timestamps."""
        source_basename = os.path.basename(file_path)
        # blocks are tuples: (index_or_timestamp, start, end, text) for srt
        # or (timestamp_line, text) for vtt
        subs: list[dict] = []

        for block in blocks:
            if format_type == "srt":
                _, start_ts, end_ts, sub_text = block
            else:
                ts_line, sub_text = block
                # Parse start/end from timestamp line
                parts = ts_line.strip().split("-->")
                start_ts = parts[0].strip() if len(parts) >= 1 else ""
                end_ts = parts[1].strip() if len(parts) >= 2 else ""

            clean_text = sub_text.strip().replace("\n", " ")
            if clean_text:
                subs.append(
                    {
                        "start": start_ts,
                        "end": end_ts,
                        "text": clean_text,
                    }
                )

        if not subs:
            return []

        # Merge subs into chunks of ~2000 chars
        chunks: list[DocumentChunk] = []
        current_lines: list[str] = []
        current_len = 0
        chunk_start_ts = subs[0]["start"]
        chunk_idx = 0

        for sub in subs:
            sub_len = len(sub["text"])

            if current_len + sub_len > 2000 and current_lines:
                # Flush current chunk
                chunk_text = " ".join(current_lines)
                title = chunk_text[:200].strip()
                tags = _extract_tags(chunk_text)
                tags.append("subtitle")
                tags.append(format_type)

                chunks.append(
                    DocumentChunk(
                        id=f"{source_basename}_chunk_{chunk_idx}",
                        source=file_path,
                        title=title,
                        content=chunk_text,
                        tags=tags,
                        created_at=datetime.now(timezone.utc),
                        metadata={
                            "char_count": len(chunk_text),
                            "source_file": file_path,
                            "parser": "subtitle",
                            "format": format_type,
                            "chunk_index": chunk_idx,
                            "start_timestamp": chunk_start_ts,
                            "end_timestamp": sub["end"],
                            "subtitle_count": len(current_lines),
                        },
                    )
                )

                chunk_idx += 1
                # Carry last ~250 chars for overlap
                if len(chunk_text) > 250:
                    carry = chunk_text[-250:]
                    current_lines = [carry, sub["text"]]
                    current_len = len(carry) + 1 + sub_len
                else:
                    current_lines = [sub["text"]]
                    current_len = sub_len
                chunk_start_ts = sub["start"]
            else:
                if not current_lines:
                    chunk_start_ts = sub["start"]
                current_lines.append(sub["text"])
                current_len += sub_len + 1

        # Flush remaining
        if current_lines:
            chunk_text = " ".join(current_lines)
            title = chunk_text[:200].strip()
            tags = _extract_tags(chunk_text)
            tags.append("subtitle")
            tags.append(format_type)

            chunks.append(
                DocumentChunk(
                    id=f"{source_basename}_chunk_{chunk_idx}",
                    source=file_path,
                    title=title,
                    content=chunk_text,
                    tags=tags,
                    created_at=datetime.now(timezone.utc),
                    metadata={
                        "char_count": len(chunk_text),
                        "source_file": file_path,
                        "parser": "subtitle",
                        "format": format_type,
                        "chunk_index": chunk_idx,
                        "start_timestamp": chunk_start_ts,
                        "end_timestamp": subs[-1]["end"] if subs else "",
                        "subtitle_count": len(current_lines),
                    },
                )
            )

        return chunks
