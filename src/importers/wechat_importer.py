"""WeChat (微信公众号) article importer.

Handles:
- Direct article URLs (mp.weixin.qq.com)
- Exported article text files
- Batch imports from a directory of saved articles
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from src.importers.base import ImportResult, chunk_text, extract_entities


class WechatImporter:
    """Import WeChat Official Account articles.

    Supports:
    - Article URL: fetches and extracts article content
    - Single file: imports saved .html or .txt article
    - Directory: batch imports saved articles
    """

    _WECHAT_URL_PATTERN = re.compile(
        r"https?://mp\.weixin\.qq\.com/s[/?].*"
    )

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    def import_data(self, source: str) -> ImportResult:
        metadata: dict = {"source": source, "format": "wechat"}

        if self._WECHAT_URL_PATTERN.match(source):
            return self._import_from_url(source, metadata)
        else:
            return self._import_from_file(source, metadata)

    # ------------------------------------------------------------------
    # URL mode
    # ------------------------------------------------------------------

    def _import_from_url(self, source: str, metadata: dict) -> ImportResult:
        try:
            import httpx
        except ImportError:
            return ImportResult(
                source="wechat",
                title=source,
                error="httpx is not installed",
                metadata=metadata,
            )

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return ImportResult(
                source="wechat",
                title=source,
                error="beautifulsoup4 is not installed",
                metadata=metadata,
            )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        try:
            resp = httpx.get(
                source,
                headers=headers,
                timeout=self.timeout,
                follow_redirects=True,
            )
            metadata["status_code"] = resp.status_code
            metadata["final_url"] = str(resp.url)

            if resp.status_code >= 400:
                return ImportResult(
                    source="wechat",
                    title=source,
                    error=f"HTTP {resp.status_code}",
                    metadata=metadata,
                )
        except Exception as exc:
            return ImportResult(
                source="wechat",
                title=source,
                error=f"Fetch failed: {exc}",
                metadata=metadata,
            )

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract article metadata
        title = self._extract_wechat_title(soup)
        account_name = self._extract_account_name(soup)
        publish_time = self._extract_publish_time(soup)

        metadata["title"] = title
        metadata["account_name"] = account_name
        metadata["publish_time"] = publish_time

        # Extract article body
        body_text = self._extract_article_body(soup)

        if not body_text.strip():
            return ImportResult(
                source="wechat",
                title=title or source,
                chunks=[],
                entities=[],
                metadata=metadata,
            )

        # Build full text with metadata header
        parts: list[str] = []
        if title:
            parts.append(f"# {title}")
        if account_name:
            parts.append(f"公众号: {account_name}")
        if publish_time:
            parts.append(f"发布时间: {publish_time}")
        parts.append(body_text)

        full_text = "\n\n".join(parts)
        entities = extract_entities(full_text)
        text_chunks = chunk_text(full_text)

        chunks: list[dict] = []
        for ch in text_chunks:
            chunks.append({
                "content": ch,
                "metadata": {
                    "chunk_index": len(chunks),
                    "source_url": source,
                    "title": title,
                    "account_name": account_name,
                },
            })

        return ImportResult(
            source="wechat",
            title=title or source,
            chunks=chunks,
            entities=entities,
            memory_type="episodic",
            metadata=metadata,
        )

    @staticmethod
    def _extract_wechat_title(soup) -> str | None:
        """Extract article title from WeChat article page."""
        # Try og:title first
        tag = soup.find("meta", property="og:title")
        if tag and tag.get("content"):
            return tag["content"].strip()

        # Try <h1 class="rich_media_title">
        h1 = soup.find("h1", class_="rich_media_title")
        if h1:
            return h1.get_text(strip=True)

        # Try <title>
        title_tag = soup.find("title")
        if title_tag:
            t = title_tag.get_text(strip=True)
            # Strip trailing " - WeChat" or similar
            t = re.sub(r"\s*[|\\-–—]\s*微信.*$", "", t)
            t = re.sub(r"\s*[|\\-–—]\s*WeChat.*$", "", t, flags=re.IGNORECASE)
            return t.strip()

        return None

    @staticmethod
    def _extract_account_name(soup) -> str | None:
        """Extract the official account name."""
        # Try meta tag
        tag = soup.find("meta", attrs={"name": "author"})
        if tag and tag.get("content"):
            return tag["content"].strip()

        # Try profile name element
        profile = soup.find(class_="rich_media_meta_nickname")
        if profile:
            return profile.get_text(strip=True)

        # Try js_name span
        js_name = soup.find(id="js_name")
        if js_name:
            return js_name.get_text(strip=True)

        return None

    @staticmethod
    def _extract_publish_time(soup) -> str | None:
        """Extract publish time from the article."""
        time_tag = soup.find(id="publish_time")
        if time_tag:
            return time_tag.get_text(strip=True)

        # Try meta tags
        for prop in ["article:published_time", "og:article:published_time"]:
            tag = soup.find("meta", property=prop)
            if tag and tag.get("content"):
                return tag["content"].strip()

        return None

    @staticmethod
    def _extract_article_body(soup) -> str:
        """Extract the main article text from a WeChat page."""
        # Primary content container
        content = soup.find(id="js_content")
        if not content:
            content = soup.find(class_="rich_media_content")
        if not content:
            content = soup.find("article")

        if content:
            # Remove hidden elements
            for hidden in content.find_all(style=re.compile(r"display\s*:\s*none")):
                hidden.decompose()

            # Replace images with placeholders
            for img in content.find_all("img"):
                alt = img.get("alt", "") or img.get("data-src", "[image]")
                img.replace_with(f"[image: {alt}]")

            text = content.get_text(separator="\n", strip=True)
        else:
            # Fallback: get body text
            body = soup.find("body") or soup
            text = body.get_text(separator="\n", strip=True)

        # Collapse excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    # ------------------------------------------------------------------
    # File mode
    # ------------------------------------------------------------------

    def _import_from_file(self, source: str, metadata: dict) -> ImportResult:
        path = Path(source)

        if not path.exists():
            return ImportResult(
                source="wechat",
                title=path.stem,
                error=f"Path not found: {source}",
                metadata=metadata,
            )

        files = self._collect_files(path)
        if not files:
            return ImportResult(
                source="wechat",
                title=path.stem,
                error="No readable article files found",
                metadata=metadata,
            )

        metadata["file_count"] = len(files)
        all_chunks: list[dict] = []
        all_texts: list[str] = []

        for file_path in files:
            try:
                if file_path.suffix in (".html", ".htm"):
                    raw = file_path.read_text(encoding="utf-8")
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(raw, "html.parser")
                        body = soup.find("body") or soup
                        text = body.get_text(separator="\n", strip=True)
                    except ImportError:
                        text = re.sub(r"<[^>]+>", "", raw)
                else:
                    text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    text = file_path.read_text(encoding="gbk")
                except Exception:
                    continue
            except Exception:
                continue

            if not text.strip():
                continue

            all_texts.append(text)
            for ch in chunk_text(text):
                all_chunks.append({
                    "content": ch,
                    "metadata": {
                        "chunk_index": len(all_chunks),
                        "source_file": file_path.name,
                        "type": "wechat_article",
                    },
                })

        if not all_chunks:
            return ImportResult(
                source="wechat",
                title=path.stem,
                error="No readable content found",
                metadata=metadata,
            )

        full_text = "\n\n".join(all_texts)
        title = _derive_wechat_title_from_text(full_text, fallback=path.stem)
        entities = extract_entities(full_text)

        return ImportResult(
            source="wechat",
            title=title,
            chunks=all_chunks,
            entities=entities,
            memory_type="episodic",
            metadata=metadata,
        )

    @staticmethod
    def _collect_files(path: Path) -> list[Path]:
        if path.is_file():
            return [path]
        files: list[Path] = []
        for ext in ("*.html", "*.htm", "*.txt", "*.md"):
            files.extend(path.rglob(ext))
        return sorted(files)


def _derive_wechat_title_from_text(text: str, fallback: str) -> str:
    """Try to extract a title from saved article text."""
    lines = text.strip().splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip lines that look like metadata
        if line.startswith(("http://", "https://", "公众号:", "发布时间:", "作者:")):
            continue
        if len(line) >= 2 and len(line) <= 100:
            return line
    return fallback
