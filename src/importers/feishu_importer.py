"""Feishu (飞书) document importer — handles Feishu doc exports.

Feishu exports typically come as:
- Single .docx files (exported documents)
- .csv files (exported Bitable / spreadsheets)
- API-accessed docs via Feishu Open API

This importer handles all three modes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.importers.base import ImportResult, chunk_text, extract_entities, generate_title


class FeishuImporter:
    """Import Feishu documents from exports or API.

    Modes:
    - File: .docx export or .csv export from Feishu
    - URL: Feishu doc URL (requires API credentials from env: FEISHU_APP_ID, FEISHU_APP_SECRET)
    - Directory: batch process a directory of exported files
    """

    _FEISHU_URL_PATTERN = re.compile(
        r"https?://[\w.-]*feishu\.cn/(?:docs|docx|sheet|base)/([\w]+)"
    )

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    def import_data(self, source: str) -> ImportResult:
        metadata: dict = {"source": source, "format": "feishu"}

        # Determine mode: URL, single file, or directory
        if self._FEISHU_URL_PATTERN.match(source):
            return self._import_from_url(source, metadata)
        else:
            return self._import_from_file(source, metadata)

    # ------------------------------------------------------------------
    # File mode
    # ------------------------------------------------------------------

    def _import_from_file(self, source: str, metadata: dict) -> ImportResult:
        path = Path(source)

        if not path.exists():
            return ImportResult(
                source="feishu",
                title=path.stem,
                error=f"Path not found: {source}",
                metadata=metadata,
            )

        # Collect files
        if path.is_dir():
            files = list(path.rglob("*"))
        else:
            files = [path]

        metadata["file_count"] = len(files)
        all_chunks: list[dict] = []
        all_texts: list[str] = []

        for file_path in files:
            if not file_path.is_file():
                continue
            suffix = file_path.suffix.lower()

            try:
                if suffix in (".docx",):
                    text = self._read_docx(file_path)
                elif suffix in (".csv",):
                    text = self._read_csv_as_text(file_path)
                elif suffix in (".txt", ".md"):
                    text = self._read_text(file_path)
                elif suffix in (".xlsx",):
                    text = self._read_xlsx(file_path)
                else:
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
                        "type": "feishu_export",
                    },
                })

        if not all_chunks:
            return ImportResult(
                source="feishu",
                title=path.stem,
                error="No readable files found",
                metadata=metadata,
            )

        full_text = "\n\n".join(all_texts)
        title = generate_title(full_text, fallback=path.stem)
        entities = extract_entities(full_text)

        return ImportResult(
            source="feishu",
            title=title,
            chunks=all_chunks,
            entities=entities,
            memory_type="semantic",
            metadata=metadata,
        )

    @staticmethod
    def _read_text(file_path: Path) -> str:
        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return file_path.read_text(encoding="gbk")

    @staticmethod
    def _read_docx(file_path: Path) -> str:
        try:
            import docx  # type: ignore[import-untyped]
        except ImportError:
            return ""
        doc = docx.Document(str(file_path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)

    @staticmethod
    def _read_csv_as_text(file_path: Path) -> str:
        import csv
        try:
            raw = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = file_path.read_text(encoding="gbk")
        reader = csv.reader(raw.splitlines())
        rows = ["\t".join(row) for row in reader if any(c.strip() for c in row)]
        return "\n".join(rows)

    @staticmethod
    def _read_xlsx(file_path: Path) -> str:
        try:
            import openpyxl  # type: ignore[import-untyped]
        except ImportError:
            return ""
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        texts: list[str] = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            texts.append(f"--- Sheet: {sheet_name} ---")
            for row in ws.iter_rows(values_only=True):
                row_vals = [str(c) if c is not None else "" for c in row]
                if any(v.strip() for v in row_vals):
                    texts.append("\t".join(row_vals))
        wb.close()
        return "\n".join(texts)

    # ------------------------------------------------------------------
    # URL / API mode
    # ------------------------------------------------------------------

    def _import_from_url(self, source: str, metadata: dict) -> ImportResult:
        match = self._FEISHU_URL_PATTERN.match(source)
        if not match:
            return ImportResult(
                source="feishu",
                title=source,
                error="Invalid Feishu URL format",
                metadata=metadata,
            )

        doc_token = match.group(1)
        metadata["doc_token"] = doc_token

        content = self._fetch_via_api(doc_token)
        if content is None:
            return ImportResult(
                source="feishu",
                title=doc_token,
                error=(
                    "Failed to fetch Feishu doc via API. "
                    "Set FEISHU_APP_ID and FEISHU_APP_SECRET env vars."
                ),
                metadata=metadata,
            )

        full_text = _flatten_feishu_blocks(content)
        if not full_text.strip():
            return ImportResult(
                source="feishu",
                title=doc_token,
                chunks=[],
                entities=[],
                metadata=metadata,
            )

        title = content.get("title", doc_token)
        entities = extract_entities(full_text)
        text_chunks = chunk_text(full_text)

        chunks: list[dict] = []
        for text in text_chunks:
            chunks.append({
                "content": text,
                "metadata": {
                    "chunk_index": len(chunks),
                    "doc_token": doc_token,
                    "source_url": source,
                },
            })

        metadata["title"] = title
        return ImportResult(
            source="feishu",
            title=title,
            chunks=chunks,
            entities=entities,
            memory_type="semantic",
            metadata=metadata,
        )

    def _fetch_via_api(self, doc_token: str) -> dict | None:
        """Fetch Feishu doc content via Open API."""
        import os

        app_id = os.environ.get("FEISHU_APP_ID", "")
        app_secret = os.environ.get("FEISHU_APP_SECRET", "")
        if not app_id or not app_secret:
            return None

        try:
            import httpx
        except ImportError:
            return None

        # Step 1: Get tenant access token
        try:
            token_resp = httpx.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": app_id, "app_secret": app_secret},
                timeout=self.timeout,
            )
            token_data = token_resp.json()
            access_token = token_data.get("tenant_access_token", "")
        except Exception:
            return None

        if not access_token:
            return None

        # Step 2: Get document content
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            resp = httpx.get(
                f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_token}",
                headers=headers,
                timeout=self.timeout,
            )
            doc_info = resp.json().get("data", {}).get("document", {})
            title = doc_info.get("title", doc_token)

            # Step 3: Get all blocks
            blocks_resp = httpx.get(
                f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_token}/blocks",
                headers=headers,
                params={"page_size": 500},
                timeout=self.timeout,
            )
            blocks_data = blocks_resp.json().get("data", {})
            return {
                "title": title,
                "blocks": blocks_data.get("items", []),
            }
        except Exception:
            return None


def _flatten_feishu_blocks(data: dict) -> str:
    """Flatten Feishu block tree to readable text."""
    blocks = data.get("blocks", [])
    if not blocks:
        return ""

    lines: list[str] = []
    if data.get("title"):
        lines.append(f"# {data['title']}")

    for block in blocks:
        block_type = block.get("block_type", "")
        text_content = _extract_block_text(block)
        if text_content:
            if block_type == 3:  # heading1
                lines.append(f"# {text_content}")
            elif block_type == 4:  # heading2
                lines.append(f"## {text_content}")
            elif block_type == 5:  # heading3
                lines.append(f"### {text_content}")
            elif block_type == 9:  # bullet
                lines.append(f"- {text_content}")
            elif block_type == 10:  # ordered
                lines.append(f"1. {text_content}")
            elif block_type == 11:  # code
                lines.append(f"```\n{text_content}\n```")
            elif block_type == 12:  # quote
                lines.append(f"> {text_content}")
            else:
                lines.append(text_content)

    return "\n".join(lines)


def _extract_block_text(block: dict) -> str:
    """Extract plain text from a Feishu block."""
    text_elements = (
        block.get("text", {})
        .get("elements", [])
    )
    # Also try alternate text paths
    if not text_elements:
        text_elements = block.get("heading1", {}).get("elements", [])
        if not text_elements:
            text_elements = block.get("heading2", {}).get("elements", [])
        if not text_elements:
            text_elements = block.get("heading3", {}).get("elements", [])
        if not text_elements:
            text_elements = block.get("bullet", {}).get("elements", [])
        if not text_elements:
            text_elements = block.get("ordered", {}).get("elements", [])

    parts: list[str] = []
    for elem in text_elements:
        run = elem.get("text_run", {})
        content = run.get("content", "")
        if content:
            parts.append(content)

    return "".join(parts)
