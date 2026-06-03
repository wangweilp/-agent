"""Import connectors for external data sources.

All importers implement the Importer protocol defined in .base.
Each accepts a source (file path or URL) and returns ImportResult.
"""

from src.importers.base import ImportResult, Importer, chunk_text, extract_entities, generate_title
from src.importers.markdown_importer import MarkdownImporter
from src.importers.txt_importer import TxtImporter
from src.importers.pdf_importer import PdfImporter
from src.importers.docx_importer import DocxImporter
from src.importers.html_importer import HtmlImporter
from src.importers.csv_importer import CsvImporter
from src.importers.json_importer import JsonImporter
from src.importers.obsidian_importer import ObsidianImporter
from src.importers.notion_importer import NotionImporter
from src.importers.logseq_importer import LogseqImporter
from src.importers.url_importer import UrlImporter
from src.importers.youtube_importer import YoutubeImporter
from src.importers.bilibili_importer import BilibiliImporter
from src.importers.feishu_importer import FeishuImporter
from src.importers.yuque_importer import YuqueImporter
from src.importers.wechat_importer import WechatImporter

# Registry: maps source type strings to importer classes
IMPORTER_REGISTRY: dict[str, type] = {
    "markdown": MarkdownImporter,
    "txt": TxtImporter,
    "pdf": PdfImporter,
    "docx": DocxImporter,
    "html": HtmlImporter,
    "csv": CsvImporter,
    "json": JsonImporter,
    "obsidian": ObsidianImporter,
    "notion": NotionImporter,
    "logseq": LogseqImporter,
    "url": UrlImporter,
    "youtube": YoutubeImporter,
    "bilibili": BilibiliImporter,
    "feishu": FeishuImporter,
    "yuque": YuqueImporter,
    "wechat": WechatImporter,
}

__all__ = [
    "ImportResult",
    "Importer",
    "chunk_text",
    "extract_entities",
    "generate_title",
    "MarkdownImporter",
    "TxtImporter",
    "PdfImporter",
    "DocxImporter",
    "HtmlImporter",
    "CsvImporter",
    "JsonImporter",
    "ObsidianImporter",
    "NotionImporter",
    "LogseqImporter",
    "UrlImporter",
    "YoutubeImporter",
    "BilibiliImporter",
    "FeishuImporter",
    "YuqueImporter",
    "WechatImporter",
    "IMPORTER_REGISTRY",
]
