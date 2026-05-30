"""Image Analyzer — 利用 LLM Vision 解析图片，输出结构化摘要。

DeepSeek API 支持 OpenAI 兼容的 vision 格式。
"""
import base64
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from src.core.memory import ChatModel

logger = logging.getLogger(__name__)

_VISION_PROMPT = """分析这张图片并严格返回以下 JSON 格式（不要 markdown 代码块，不要额外文字）：

{
  "summary": "图片一句话描述，中文，不超过 50 字",
  "detailed_description": "详细描述图片内容，包括主体、背景、动作、文字等，中文",
  "entities": ["命名实体1", "命名实体2"],
  "objects": ["物体1", "物体2"],
  "text_in_image": "图片中的文字内容（如有），否则为空字符串",
  "scene_type": "场景类型（文档/人像/风景/截图/代码/图表/白板/其他）",
  "suggested_use": "可能的用途或场景关联，中文",
  "structured_json": {
    "text_in_image": "图片中的文字内容",
    "entities": ["实体列表"],
    "scene_type": "场景类型",
    "object_list": ["物体列表"]
  }
}"""

# 多图批量分析 prompt（用于多轮上下文整合）
_MULTI_IMAGE_PROMPT = """你正在分析一批共 {total} 张图片。

这是第 {index} 张，请分析并返回 JSON（与单图格式相同）。

之前图片的分析摘要：{previous_summaries}

请特别关注：这张图片与之前图片之间是否存在关联（如：同一主题、连续文档、相关场景等）。如有，在 suggested_use 中注明。"""

_CONTEXT_AWARE_PROMPT = """你正在帮助分析用户上传的图片，结合对话上下文和历史记忆。

## 当前对话上下文
{conversation_context}

## 用户的相关历史记忆
{historical_memories}

## 多图上下文
{image_context}

请基于以上全部信息分析这张图片，严格返回 JSON（不要 markdown 代码块）：

{
  "summary": "≤50字摘要，必须关联上下文中的主题或实体",
  "detailed_description": "详细描述",
  "entities": ["实体列表，优先使用上下文和记忆中出现的实体"],
  "objects": ["物体列表"],
  "text_in_image": "图中文字",
  "scene_type": "场景类型",
  "suggested_use": "用途建议，说明与当前话题/历史记忆的关联",
  "structured_json": {
    "text_in_image": "...",
    "entities": [...],
    "scene_type": "...",
    "object_list": [...]
  }
}"""


@dataclass
class StructuredJson:
    """结构化分析结果，用于语义检索和概念图谱构建。"""
    text_in_image: str = ""
    entities: list[str] = field(default_factory=list)
    scene_type: str = ""
    object_list: list[str] = field(default_factory=list)


@dataclass
class ImageAnalysisResult:
    summary: str = ""
    detailed_description: str = ""
    entities: list[str] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)
    text_in_image: str = ""
    scene_type: str = ""
    suggested_use: str = ""
    structured_json: StructuredJson | None = None
    raw_response: str = ""


class ImageAnalyzer:
    """使用 LLM Vision 能力分析图片。

    支持的图片格式：PNG, JPEG, GIF, WebP。
    支持单图分析和批量分析（多图片上下文关联）。
    """

    _SUPPORTED_TYPES = {
        "image/png", "image/jpeg", "image/gif", "image/webp",
        "image/jpg",
    }

    def __init__(self, llm: ChatModel, model_name: str = "deepseek-chat") -> None:
        self._llm = llm
        self._model_name = model_name

    def analyze_file(self, file_path: str) -> ImageAnalysisResult:
        """读取单文件并通过 LLM Vision 分析。"""
        self._validate_file(file_path)
        content_type = self._detect_mime(file_path)
        data_url = self._file_to_data_url(file_path, content_type)
        return self.analyze_base64(data_url)

    def analyze_batch(self, file_paths: list[str]) -> list[ImageAnalysisResult]:
        """批量分析多张图片，整合上下文。

        每张图独立调用 LLM，但 prompt 中包含之前图片的摘要，
        以便发现跨图关联。
        """
        results: list[ImageAnalysisResult] = []
        previous: list[str] = []

        for i, path in enumerate(file_paths):
            self._validate_file(path)
            content_type = self._detect_mime(path)
            data_url = self._file_to_data_url(path, content_type)

            # 多图上下文 prompt
            if len(file_paths) > 1 and previous:
                ctx_prompt = _MULTI_IMAGE_PROMPT.format(
                    total=len(file_paths),
                    index=i + 1,
                    previous_summaries="; ".join(previous),
                )
            else:
                ctx_prompt = _VISION_PROMPT

            result = self.analyze_base64(data_url, prompt=ctx_prompt)
            results.append(result)
            previous.append(result.summary)

        return results

    def analyze_with_context(
        self,
        file_path: str,
        *,
        conversation_context: str = "",
        historical_memories: str = "",
        previous_image_summaries: list[str] | None = None,
    ) -> ImageAnalysisResult:
        """带对话上下文和历史记忆的图片分析。"""
        image_ctx = ""
        if previous_image_summaries:
            image_ctx = f"之前已分析的同批图片摘要：{'；'.join(previous_image_summaries)}"
        else:
            image_ctx = "这是本批次唯一一张图片"

        if not conversation_context:
            conversation_context = "暂无对话上下文"
        if not historical_memories:
            historical_memories = "暂无相关历史记忆"

        prompt = _CONTEXT_AWARE_PROMPT.format(
            conversation_context=conversation_context,
            historical_memories=historical_memories,
            image_context=image_ctx,
        )

        self._validate_file(file_path)
        content_type = self._detect_mime(file_path)
        data_url = self._file_to_data_url(file_path, content_type)
        return self.analyze_base64(data_url, prompt=prompt)

    def analyze_base64(self, data_url: str, prompt: str = "") -> ImageAnalysisResult:
        """通过 LLM Vision API 分析 base64 图片。"""
        effective_prompt = prompt or _VISION_PROMPT
        messages: list[dict[str, Any]] = [{
            "role": "user",
            "content": [
                {"type": "text", "text": effective_prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }]

        try:
            response = self._llm.chat(
                messages=messages,
                tools=None,
                tool_choice=None,
                max_tokens=1024,
            )
            raw = response.choices[0].message.content or ""
            return self._parse_response(raw)
        except Exception:
            logger.exception("image_analysis_failed")
            return ImageAnalysisResult(
                summary="图片分析失败",
                raw_response="",
            )

    # ── 内部 ──

    @staticmethod
    def _parse_response(raw: str) -> ImageAnalysisResult:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if len(lines) > 1 else text
            if text.endswith("```"):
                text = text[:-3]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("image_analysis_json_parse_failed", extra={"raw": raw[:200]})
            return ImageAnalysisResult(
                summary=raw[:100],
                detailed_description=raw,
                raw_response=raw,
            )

        # 解析 structured_json
        sj_data = data.get("structured_json", {})
        structured = StructuredJson(
            text_in_image=sj_data.get("text_in_image", data.get("text_in_image", "")),
            entities=sj_data.get("entities", data.get("entities", [])),
            scene_type=sj_data.get("scene_type", data.get("scene_type", "")),
            object_list=sj_data.get("object_list", data.get("objects", [])),
        )

        return ImageAnalysisResult(
            summary=data.get("summary", "")[:100],
            detailed_description=data.get("detailed_description", ""),
            entities=data.get("entities", []),
            objects=data.get("objects", []),
            text_in_image=data.get("text_in_image", ""),
            scene_type=data.get("scene_type", ""),
            suggested_use=data.get("suggested_use", ""),
            structured_json=structured,
            raw_response=raw,
        )

    @staticmethod
    def _validate_file(file_path: str) -> None:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        if os.path.getsize(file_path) == 0:
            raise ValueError(f"文件为空: {file_path}")

    @staticmethod
    def _file_to_data_url(file_path: str, content_type: str) -> str:
        with open(file_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{content_type};base64,{image_data}"

    @staticmethod
    def _detect_mime(file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        mapping = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mapping.get(ext, "application/octet-stream")
