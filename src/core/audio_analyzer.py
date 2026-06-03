"""Audio Analyzer — 音频文件解析、ASR 转录、结构化分析。

支持：
  - 本地 Whisper 模型转录（如果已安装 openai-whisper）
  - LLM 文本分析（摘要、实体提取、概念生成）
  - 回退方案：无 Whisper 时基于文件名和时长生成占位分析

所有分析结果统一为 AudioAnalysisResult，供 5 层 MemoryTask 构建。
"""
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.adapters.config import Settings
from src.core.memory import ChatModel

logger = logging.getLogger(__name__)

# ── LLM Prompt ──

_AUDIO_ANALYSIS_PROMPT = """分析以下音频转录文本，严格返回 JSON（不要 markdown 代码块）：

## 音频元数据
文件名: {filename}
时长: {duration_seconds} 秒

## 转录文本
{transcription}

## 要求
请基于以上信息分析，返回：
{{
  "summary": "音频核心内容，中文，≤80 字",
  "topic": "音频主题分类（会议/学习/采访/个人笔记/灵感/教程/其他）",
  "key_points": ["关键点1", "关键点2", "关键点3"],
  "entities": ["提到的实体名1", "实体名2"],
  "sentiment": "整体情绪基调（积极/中性/消极/激动/平静）",
  "action_items": ["待办项1", "待办项2"],
  "suggested_use": "建议的记忆用途，中文，≤60 字",
  "importance_hint": 1-10 的重要性评估（整数）
}}"""

_PLACEHOLDER_PROMPT = """以下音频尚未转录，仅提供元数据。请生成分析：

## 音频元数据
文件名: {filename}
文件大小: {size_mb} MB

## 要求
如该文件名暗示了内容主题，请尽力推断。返回 JSON：
{{
  "summary": "基于文件名的推断摘要，中文，≤50 字",
  "topic": "推断的主题分类",
  "key_points": ["推断的关键点"],
  "entities": ["可能的实体"],
  "sentiment": "中性",
  "action_items": [],
  "suggested_use": "建议用途",
  "importance_hint": 3
}}

如果文件名无法推断，summary 填写"音频待转录"，topic 填写"未知"。
"""

# ── Data Classes ──


@dataclass
class AudioAnalysisResult:
    """音频分析结果 — 统一接口。"""
    summary: str = ""
    topic: str = ""
    transcription: str = ""
    entities: list[str] = field(default_factory=list)
    key_points: list[str] = field(default_factory=list)
    sentiment: str = "中性"
    action_items: list[str] = field(default_factory=list)
    suggested_use: str = ""
    importance_hint: int = 5
    duration_seconds: float = 0.0
    raw_response: str = ""


# ── Audio Analyzer ──


class AudioAnalyzer:
    """音频分析器。

    流程：
      1. 尝试加载 Whisper 进行语音转文字
      2. 将转录文本送入 LLM 做结构化分析
      3. 若无 Whisper，用 LLM 基于文件名做推断分析
    """

    _SUPPORTED_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".webm", ".opus"}
    _SUPPORTED_MIMES = {
        "audio/mpeg", "audio/wav", "audio/mp4", "audio/ogg",
        "audio/flac", "audio/aac", "audio/webm", "audio/opus",
        "audio/mp3", "audio/x-wav", "audio/x-m4a",
    }

    def __init__(
        self,
        llm: ChatModel,
        settings: Settings | None = None,
        *,
        whisper_model: str = "base",
    ) -> None:
        self._llm = llm
        self._settings = settings
        self._whisper_model_name = whisper_model
        self._whisper = None  # lazy load

    # ── 公共 API ──

    def analyze(self, file_path: str, filename: str = "") -> AudioAnalysisResult:
        """分析音频文件：转录 + LLM 结构化分析。"""
        self._validate(file_path)
        size_bytes = os.path.getsize(file_path)

        # 尝试 Whisper 转录
        transcription = self._transcribe(file_path)

        if transcription:
            return self._analyze_with_transcription(
                transcription=transcription,
                filename=filename or os.path.basename(file_path),
                file_path=file_path,
            )
        else:
            return self._analyze_placeholder(
                filename=filename or os.path.basename(file_path),
                size_bytes=size_bytes,
            )

    def analyze_batch(
        self, file_paths: list[str], filenames: list[str] | None = None
    ) -> list[AudioAnalysisResult]:
        """批量分析多个音频文件。"""
        names = filenames or [os.path.basename(p) for p in file_paths]
        results: list[AudioAnalysisResult] = []
        previous_summaries: list[str] = []

        for path, name in zip(file_paths, names):
            result = self.analyze(path, name)
            if result.summary:
                previous_summaries.append(result.summary)
            results.append(result)

        return results

    def transcribe_only(self, file_path: str) -> str:
        """仅转录音频，不做分析。"""
        self._validate(file_path)
        return self._transcribe(file_path)

    # ── 内部 ──

    def _transcribe(self, file_path: str) -> str:
        """使用 Whisper 转录音频。返回空字符串表示转录失败。"""
        wh = self._load_whisper()
        if wh is None:
            return ""

        try:
            # Lazy-load result type for type narrowing
            result: Any = wh.transcribe(file_path, language="zh", verbose=False)
            text = result.get("text", "").strip()
            if text:
                logger.info("audio_transcription_ok", extra={"length": len(text)})
            return text
        except Exception:
            # 回退：不指定语言
            try:
                result = wh.transcribe(file_path, verbose=False)
                text = result.get("text", "").strip()
                return text
            except Exception:
                logger.warning("audio_transcription_failed", exc_info=True)
                return ""

    def _load_whisper(self):
        """Lazy-load Whisper 模型。"""
        if self._whisper is not None:
            return self._whisper
        try:
            import whisper
            self._whisper = whisper.load_model(self._whisper_model_name)
            logger.info("whisper_loaded", extra={"model": self._whisper_model_name})
            return self._whisper
        except ImportError:
            logger.debug("whisper_not_installed")
            self._whisper = False  # sentinel
            return None
        except Exception:
            logger.warning("whisper_load_failed", exc_info=True)
            self._whisper = False
            return None

    def _analyze_with_transcription(
        self,
        transcription: str,
        filename: str,
        file_path: str,
    ) -> AudioAnalysisResult:
        """使用 LLM 分析已转录文本。"""
        # 估算时长（中文约 3 字/秒）
        est_duration = len(transcription) / 3.0
        prompt = _AUDIO_ANALYSIS_PROMPT.format(
            filename=filename,
            duration_seconds=f"{est_duration:.0f}",
            transcription=transcription[:3000],
        )

        try:
            response = self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=None, tool_choice=None, max_tokens=800,
            )
            raw = response.choices[0].message.content or ""
            return self._parse_response(raw, transcription, est_duration)
        except Exception:
            logger.exception("audio_llm_analysis_failed")
            return AudioAnalysisResult(
                summary=transcription[:100],
                transcription=transcription,
                duration_seconds=est_duration,
                raw_response="",
            )

    def _analyze_placeholder(
        self, filename: str, size_bytes: int
    ) -> AudioAnalysisResult:
        """无转录时的回退分析。"""
        prompt = _PLACEHOLDER_PROMPT.format(
            filename=filename,
            size_mb=f"{size_bytes / 1024 / 1024:.1f}",
        )
        try:
            response = self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=None, tool_choice=None, max_tokens=400,
            )
            raw = response.choices[0].message.content or ""
            return self._parse_response(raw, "", 0.0)
        except Exception:
            logger.exception("audio_placeholder_analysis_failed")
            return AudioAnalysisResult(summary="音频分析失败", topic="未知")

    @staticmethod
    def _parse_response(
        raw: str, transcription: str, duration: float
    ) -> AudioAnalysisResult:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if len(lines) > 1 else text
            if text.endswith("```"):
                text = text[:-3]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return AudioAnalysisResult(
                summary=raw[:100],
                transcription=transcription,
                duration_seconds=duration,
                raw_response=raw,
            )

        return AudioAnalysisResult(
            summary=data.get("summary", "")[:100],
            topic=data.get("topic", "未知"),
            transcription=transcription,
            entities=data.get("entities", []),
            key_points=data.get("key_points", []),
            sentiment=data.get("sentiment", "中性"),
            action_items=data.get("action_items", []),
            suggested_use=data.get("suggested_use", ""),
            importance_hint=int(data.get("importance_hint", 5)),
            duration_seconds=duration,
            raw_response=raw,
        )

    # ── 校验 ──

    @classmethod
    def _validate(cls, file_path: str) -> None:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"音频文件不存在: {file_path}")
        if os.path.getsize(file_path) == 0:
            raise ValueError(f"音频文件为空: {file_path}")
        ext = Path(file_path).suffix.lower()
        if ext not in cls._SUPPORTED_EXTS:
            raise ValueError(f"不支持的音频格式: {ext} (支持: {', '.join(sorted(cls._SUPPORTED_EXTS))})")
