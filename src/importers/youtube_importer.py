"""YouTube importer — extracts video metadata and subtitles/transcript.

Uses yt-dlp for metadata extraction and subtitle download.
Falls back to youtube-transcript-api for direct transcript access.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.importers.base import ImportResult, chunk_text, extract_entities


class YoutubeImporter:
    """Import YouTube video info and subtitles.

    Pass a YouTube URL (watch, short, or youtu.be). Extracts:
    - Video title, description, channel name
    - Auto-generated or manual subtitles (if available)
    - Basic entities from title + description + transcript
    """

    _URL_PATTERNS = [
        re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([\w-]+)"),
        re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([\w-]+)"),
        re.compile(r"(?:https?://)?youtu\.be/([\w-]+)"),
    ]

    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout

    def import_data(self, source: str) -> ImportResult:
        url = source.strip()

        # Extract video ID
        video_id = self._extract_video_id(url)
        metadata: dict = {
            "url": url,
            "format": "youtube",
            "video_id": video_id,
        }

        if not video_id:
            return ImportResult(
                source="youtube",
                title=url,
                error=f"Could not extract YouTube video ID from: {url}",
                metadata=metadata,
            )

        # Try yt-dlp first
        info = self._extract_with_ytdlp(url)
        if info is None:
            # Fall back to transcript API
            info = self._extract_with_transcript_api(video_id)

        if info is None:
            return ImportResult(
                source="youtube",
                title=video_id,
                error="Failed to extract video info. Install yt-dlp or youtube-transcript-api.",
                metadata=metadata,
            )

        title = info.get("title") or video_id
        metadata["title"] = title
        metadata["channel"] = info.get("channel")
        metadata["duration_seconds"] = info.get("duration")

        # Build full text for chunking
        parts: list[str] = []
        if info.get("title"):
            parts.append(f"# {info['title']}")
        if info.get("channel"):
            parts.append(f"Channel: {info['channel']}")
        if info.get("description"):
            parts.append(info["description"])
        if info.get("transcript"):
            parts.append(info["transcript"])

        full_text = "\n\n".join(parts)

        if not full_text.strip():
            return ImportResult(
                source="youtube",
                title=title,
                chunks=[],
                entities=[],
                metadata=metadata,
            )

        entities = extract_entities(full_text)
        text_chunks = chunk_text(full_text)

        chunks: list[dict] = []
        for text in text_chunks:
            chunks.append({
                "content": text,
                "metadata": {
                    "chunk_index": len(chunks),
                    "video_id": video_id,
                    "source_url": url,
                },
            })

        return ImportResult(
            source="youtube",
            title=title,
            chunks=chunks,
            entities=entities,
            memory_type="episodic",
            metadata=metadata,
        )

    def _extract_video_id(self, url: str) -> str | None:
        for pattern in self._URL_PATTERNS:
            match = pattern.search(url)
            if match:
                return match.group(1)
        return None

    def _extract_with_ytdlp(self, url: str) -> dict | None:
        """Extract metadata and subtitles using yt-dlp."""
        try:
            import yt_dlp  # type: ignore[import-untyped]
        except ImportError:
            return None

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en", "zh-Hans", "zh-CN", "zh"],
            "skip_download": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception:
            return None

        result: dict = {
            "title": info.get("title"),
            "channel": info.get("uploader") or info.get("channel"),
            "description": info.get("description", ""),
            "duration": info.get("duration"),
        }

        # Extract subtitles
        subtitles = info.get("subtitles") or info.get("automatic_captions") or {}
        transcript_parts: list[str] = []
        for lang in ["zh-Hans", "zh-CN", "zh", "en"]:
            sub_list = subtitles.get(lang, [])
            if sub_list:
                for sub_info in sub_list:
                    sub_url = sub_info.get("url")
                    if sub_url:
                        try:
                            import httpx
                            resp = httpx.get(sub_url, timeout=self.timeout)
                            sub_json = resp.json()
                            if "events" in sub_json:
                                for event in sub_json["events"]:
                                    segs = event.get("segs", [])
                                    line = "".join(s.get("utf8", "") for s in segs)
                                    if line.strip():
                                        transcript_parts.append(line.strip())
                            else:
                                # SRT-like format
                                text = resp.text
                                lines = text.strip().split("\n")
                                for line in lines:
                                    line = line.strip()
                                    if line and not line.isdigit() and "-->" not in line:
                                        transcript_parts.append(line)
                        except Exception:
                            continue
                break  # Use first available language

        result["transcript"] = "\n".join(transcript_parts)
        return result

    def _extract_with_transcript_api(self, video_id: str) -> dict | None:
        """Fall back to youtube-transcript-api."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore[import-untyped]
        except ImportError:
            return None

        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        except Exception:
            return None

        # Prefer manual transcript, then auto-generated
        transcript = None
        try:
            transcript = transcript_list.find_manually_created_transcript(["zh-Hans", "zh-CN", "zh", "en"])
        except Exception:
            try:
                transcript = transcript_list.find_generated_transcript(["zh-Hans", "zh-CN", "zh", "en"])
            except Exception:
                return None

        if transcript is None:
            return None

        try:
            transcript_data = transcript.fetch()
        except Exception:
            return None

        transcript_text = " ".join(
            item.text for item in transcript_data if hasattr(item, "text")
        )

        return {
            "title": None,
            "channel": None,
            "description": None,
            "duration": None,
            "transcript": transcript_text,
        }
