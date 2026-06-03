"""URL importer — fetches a page and extracts readable content."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from src.importers.base import ImportResult, chunk_text, extract_entities, generate_title


class UrlImporter:
    """Fetch a URL and extract main text content (readability-style).

    Uses httpx for HTTP and BeautifulSoup for HTML parsing.
    Strips navigation, ads, scripts, and extracts the main content body.
    """

    _UNWANTED_TAGS = {"script", "style", "nav", "footer", "header",
                      "aside", "noscript", "iframe", "form", "button"}

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    def import_data(self, source: str) -> ImportResult:
        """Fetch *source* URL and extract text content."""
        url = source.strip()
        metadata: dict = {"url": url, "format": "webpage"}

        # Basic URL validation
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ImportResult(
                source="url",
                title=url,
                error=f"Invalid URL: {url}",
                metadata=metadata,
            )

        # Fetch the page
        try:
            import httpx
        except ImportError:
            return ImportResult(
                source="url",
                title=url,
                error="httpx is not installed",
                metadata=metadata,
            )

        try:
            response = httpx.get(
                url,
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            )
            metadata["status_code"] = response.status_code
            metadata["final_url"] = str(response.url)

            if response.status_code >= 400:
                return ImportResult(
                    source="url",
                    title=url,
                    error=f"HTTP {response.status_code}: {response.reason_phrase}",
                    metadata=metadata,
                )

            html = response.text
        except httpx.TimeoutException:
            return ImportResult(
                source="url",
                title=url,
                error=f"Request timeout after {self.timeout}s",
                metadata=metadata,
            )
        except Exception as exc:
            return ImportResult(
                source="url",
                title=url,
                error=f"Fetch failed: {exc}",
                metadata=metadata,
            )

        # Parse HTML
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return ImportResult(
                source="url",
                title=url,
                error="beautifulsoup4 is not installed",
                metadata=metadata,
            )

        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else url

        # Remove unwanted elements
        for tag in soup(self._UNWANTED_TAGS):
            tag.decompose()

        # Readability-style: try common content containers first
        text = self._extract_main_content(soup)

        if not text.strip():
            return ImportResult(
                source="url",
                title=title,
                chunks=[],
                entities=[],
                metadata=metadata,
            )

        entities = extract_entities(text)
        text_chunks = chunk_text(text)

        chunks: list[dict] = []
        for text_segment in text_chunks:
            chunks.append({
                "content": text_segment,
                "metadata": {
                    "chunk_index": len(chunks),
                    "source_url": url,
                },
            })

        return ImportResult(
            source="url",
            title=title,
            chunks=chunks,
            entities=entities,
            memory_type="episodic",
            metadata=metadata,
        )

    def _extract_main_content(self, soup) -> str:
        """Extract the main text content from parsed HTML.

        Tries common content selectors first (article, main, .content),
        then falls back to body text.
        """
        # Priority selectors for main content
        selectors = [
            "article",
            "main",
            '[role="main"]',
            ".post-content",
            ".article-content",
            ".entry-content",
            ".content",
            "#content",
            ".markdown-body",
            ".post-body",
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(separator="\n", strip=True)
                if len(text) > 200:
                    return text

        # Fallback: get all body text, compress whitespace
        body = soup.find("body") or soup
        raw_text = body.get_text(separator="\n", strip=True)
        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", raw_text)
        return text
