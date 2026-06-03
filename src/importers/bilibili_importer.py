"""Bilibili video importer — extracts video info and subtitles.

Parses video pages for metadata; extracts CC subtitles when available.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from src.importers.base import ImportResult, chunk_text, extract_entities


class BilibiliImporter:
    """Import Bilibili video info and subtitles.

    Pass a Bilibili video URL (BV or av format). Extracts:
    - Video title, description, uploader
    - CC subtitles if present
    - Basic entities from combined text
    """

    _BV_PATTERN = re.compile(r"BV[\w]{10}")
    _AV_PATTERN = re.compile(r"av(\d+)", re.IGNORECASE)
    _URL_PATTERNS = [
        re.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/video/(BV[\w]{10})"),
        re.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/video/(av\d+)", re.IGNORECASE),
        re.compile(r"(?:https?://)?b23\.tv/(\w+)"),
        re.compile(r"BV[\w]{10}"),
        re.compile(r"av\d+", re.IGNORECASE),
    ]

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    def import_data(self, source: str) -> ImportResult:
        url = source.strip()
        video_id = self._extract_video_id(url)

        metadata: dict = {
            "url": url,
            "format": "bilibili",
            "video_id": video_id,
            "platform": "bilibili",
        }

        if not video_id:
            return ImportResult(
                source="bilibili",
                title=url,
                error=f"Could not extract Bilibili video ID from: {url}",
                metadata=metadata,
            )

        # Build proper URL if we got a bare ID
        if not url.startswith("http"):
            url = f"https://www.bilibili.com/video/{video_id}"

        info = self._fetch_video_info(url, video_id)
        if info is None:
            return ImportResult(
                source="bilibili",
                title=video_id,
                error="Failed to fetch video info. The video may be unavailable.",
                metadata=metadata,
            )

        title = info.get("title") or video_id
        metadata["title"] = title
        metadata["uploader"] = info.get("uploader")
        metadata["duration_seconds"] = info.get("duration")

        # Build full text
        parts: list[str] = []
        if info.get("title"):
            parts.append(f"# {info['title']}")
        if info.get("uploader"):
            parts.append(f"UP主: {info['uploader']}")
        if info.get("description"):
            parts.append(info["description"])
        if info.get("tags"):
            parts.append("标签: " + ", ".join(info["tags"]))
        if info.get("subtitles"):
            parts.append(info["subtitles"])

        full_text = "\n\n".join(parts)

        if not full_text.strip():
            return ImportResult(
                source="bilibili",
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
            source="bilibili",
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

    def _fetch_video_info(self, url: str, video_id: str) -> dict | None:
        """Fetch video metadata from Bilibili API.

        Uses the public info API: https://api.bilibili.com/x/web-interface/view
        """
        try:
            import httpx
        except ImportError:
            return None

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.bilibili.com/",
        }

        result: dict = {}

        # Step 1: Get video info via API
        if video_id.startswith("BV"):
            api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={video_id}"
        else:
            api_url = f"https://api.bilibili.com/x/web-interface/view?aid={video_id.lstrip('av')}"

        try:
            resp = httpx.get(api_url, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    vdata = data.get("data", {})
                    result["title"] = vdata.get("title")
                    result["description"] = vdata.get("desc")
                    result["duration"] = vdata.get("duration")
                    owner = vdata.get("owner", {})
                    result["uploader"] = owner.get("name")
                    result["tags"] = [
                        t.get("tag_name", "")
                        for t in vdata.get("taggings", [])
                    ]
        except Exception:
            pass

        # Step 2: Try to get subtitles
        try:
            subtitle_url = (
                f"https://api.bilibili.com/x/player/v2?bvid={video_id}"
                if video_id.startswith("BV")
                else f"https://api.bilibili.com/x/player/v2?aid={video_id.lstrip('av')}"
            )
            resp = httpx.get(subtitle_url, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    subtitle_info = (
                        data.get("data", {})
                        .get("subtitle", {})
                        .get("subtitles", [])
                    )
                    if subtitle_info:
                        subtitle_parts: list[str] = []
                        for sub in subtitle_info:
                            sub_url = sub.get("subtitle_url")
                            if not sub_url:
                                continue
                            if sub_url.startswith("//"):
                                sub_url = "https:" + sub_url
                            try:
                                sub_resp = httpx.get(
                                    sub_url, headers=headers, timeout=self.timeout
                                )
                                if sub_resp.status_code == 200:
                                    sub_data = sub_resp.json()
                                    for item in sub_data.get("body", []):
                                        content = item.get("content", "")
                                        if content.strip():
                                            subtitle_parts.append(content.strip())
                            except Exception:
                                continue
                        if subtitle_parts:
                            result["subtitles"] = "\n".join(subtitle_parts)
        except Exception:
            pass

        # If we got at least a title, return result
        if result.get("title") or result.get("description"):
            return result

        # Step 3: Fall back to page scraping
        try:
            resp = httpx.get(url, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                html = resp.text

                # Extract title from og:title or <title>
                title_match = re.search(
                    r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html
                )
                if not title_match:
                    title_match = re.search(r"<title>([^<]+)</title>", html)
                if title_match:
                    result["title"] = title_match.group(1).replace("_哔哩哔哩_bilibili", "").strip()

                # Extract description
                desc_match = re.search(
                    r'<meta[^>]+name="description"[^>]+content="([^"]+)"', html
                )
                if desc_match:
                    result["description"] = desc_match.group(1)

                # Extract author
                author_match = re.search(
                    r'<meta[^>]+name="author"[^>]+content="([^"]+)"', html
                )
                if author_match:
                    result["uploader"] = author_match.group(1)
        except Exception:
            pass

        return result if (result.get("title") or result.get("description")) else None
