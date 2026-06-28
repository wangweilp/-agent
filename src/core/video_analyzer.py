"""Video Analyzer — 视频文件解析管线。

Pipeline:
  1. 保存视频文件
  2. 关键帧抽取 (ffmpeg, 每 N 秒一帧或场景切换)
  3. 音频提取 (ffmpeg)
  4. LLM Vision OCR 关键帧 → 提取图中文字
  5. ASR 转录音频 → 文本
  6. LLM 综合分析 → VideoAnalysisResult
  7. 构建 5 层 MemoryTask

所有外部工具(ffmpeg)可选，缺失时优雅降级。
"""
import base64
import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.adapters.config import Settings
from src.core.memory import ChatModel

logger = logging.getLogger(__name__)

# ── Prompt Templates ──

_OCR_FRAME_PROMPT = """分析这张视频关键帧图片，严格返回 JSON（不要 markdown）：
{{
  "text_in_frame": "图中所有可见文字，逐行列出",
  "scene_description": "场景简要描述，中文 ≤40 字",
  "objects": ["物体1", "物体2"],
  "scene_type": "场景类型（演示/白板/聊天/代码/人物/文档/风景/其他）"
}}"""

_VIDEO_SUMMARY_PROMPT = """你正在分析一段视频的综合信息，请整合以下数据生成分析结果，严格返回 JSON（不要 markdown）：

## 视频元数据
文件名: {filename}
时长: {duration_seconds} 秒 ({duration_minutes:.1f} 分钟)
关键帧数量: {keyframe_count}

## OCR 文字提取 (关键帧中的文字)
{ocr_text}

## 音频转录
{transcription}

## 要求
{{
  "summary": "视频核心内容摘要，中文，≤120 字",
  "topic": "视频主题分类（教程/会议/演示/记录/其他）",
  "key_points": ["关键点1", "关键点2", "关键点3", "关键点4"],
  "entities": ["实体1", "实体2", "实体3"],
  "concepts": ["概念1", "概念2"],
  "suggested_use": "建议的记忆用途与关联，中文，≤80 字",
  "importance_hint": 1-10 重要性评估（整数）
}}"""

_PLACEHOLDER_PROMPT = """以下视频仅提供元数据，无法提取内容。请生成分析：

## 视频元数据
文件名: {filename}
文件大小: {size_mb} MB

## 要求
基于文件名推断内容，返回 JSON：
{{
  "summary": "基于文件名的推断摘要，≤60 字",
  "topic": "推断的主题",
  "key_points": ["推断的关键点"],
  "entities": [],
  "concepts": [],
  "suggested_use": "建议用途",
  "importance_hint": 3
}}
如果文件名无法推断，summary 填写"视频待分析"。"""


# ── Data Classes ──


@dataclass
class VideoAnalysisResult:
    """视频分析完整结果。"""
    summary: str = ""
    topic: str = ""
    entities: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    key_points: list[str] = field(default_factory=list)
    suggested_use: str = ""
    importance_hint: int = 5
    duration_seconds: float = 0.0
    keyframe_count: int = 0
    ocr_text: str = ""
    transcription: str = ""
    keyframe_paths: list[str] = field(default_factory=list)
    audio_path: str = ""
    raw_response: str = ""


# ── Video Analyzer ──


class VideoAnalyzer:
    """视频文件分析器。

    流程：
      1. 抽取关键帧 (ffmpeg)
      2. 提取音频轨道 (ffmpeg)
      3. LLM Vision OCR 关键帧
      4. ASR 转录音频
      5. LLM 综合分析
    """

    _SUPPORTED_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv", ".wmv"}
    _SUPPORTED_MIMES = {
        "video/mp4", "video/quicktime", "video/x-matroska",
        "video/webm", "video/x-msvideo", "video/x-flv",
    }

    def __init__(
        self, llm: ChatModel, settings: Settings | None = None, *, whisper_model: str = "base",
    ) -> None:
        self._llm = llm
        self._settings = settings
        self._frame_interval = (settings.video_keyframe_interval if settings else 5)
        self._whisper_model_name = whisper_model
        self._whisper = None  # lazy load

    # ── 公共 API ──

    def analyze(self, file_path: str, filename: str = "") -> VideoAnalysisResult:
        """完整视频分析管线。"""
        self._validate(file_path)
        if not filename:
            filename = os.path.basename(file_path)

        size_bytes = os.path.getsize(file_path)

        # 检查 ffmpeg 可用性
        has_ffmpeg = self._check_ffmpeg()
        if not has_ffmpeg:
            return self._analyze_placeholder(filename, size_bytes)

        # 获取时长
        duration = self._probe_duration(file_path)

        # Step 2: 关键帧抽取
        keyframe_paths = self._extract_keyframes(file_path)
        keyframe_count = len(keyframe_paths)

        # Step 3: OCR 关键帧 (LLM Vision)
        ocr_text = self._ocr_keyframes(keyframe_paths, filename)

        # Step 4: 音频提取 + ASR
        audio_path = self._extract_audio(file_path)
        transcription = ""
        if audio_path and os.path.getsize(audio_path) > 0:
            transcription = self._transcribe_audio(audio_path)

        # Step 5: LLM 综合分析
        result = self._analyze_comprehensive(
            filename=filename,
            duration=duration,
            keyframe_count=keyframe_count,
            ocr_text=ocr_text,
            transcription=transcription,
        )
        result.keyframe_paths = keyframe_paths
        result.audio_path = audio_path
        result.duration_seconds = duration
        result.keyframe_count = keyframe_count
        result.ocr_text = ocr_text
        result.transcription = transcription

        # 清理临时文件
        self._cleanup_tempfiles(keyframe_paths, audio_path)

        return result

    def analyze_batch(
        self, file_paths: list[str], filenames: list[str] | None = None
    ) -> list[VideoAnalysisResult]:
        """批量分析多个视频文件。"""
        names = filenames or [os.path.basename(p) for p in file_paths]
        return [self.analyze(p, n) for p, n in zip(file_paths, names)]

    # ── Pipeline Steps ──

    def _extract_keyframes(self, video_path: str) -> list[str]:
        """使用 ffmpeg 抽取关键帧。返回临时文件路径列表。"""
        temp_dir = tempfile.mkdtemp(prefix="video_keyframes_")
        output_pattern = os.path.join(temp_dir, "frame_%03d.jpg")

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", video_path,
            "-vf", f"fps=1/{self._frame_interval}",
            "-q:v", "6",
            output_pattern,
        ]
        try:
            subprocess.run(cmd, check=True, timeout=120, capture_output=True)
            frames = sorted(Path(temp_dir).glob("frame_*.jpg"))
            paths = [str(f) for f in frames]
            if paths:
                logger.info("video_keyframes_extracted", extra={"count": len(paths), "video": video_path[:40]})
            return paths
        except FileNotFoundError:
            logger.debug("ffmpeg_not_found")
            return []
        except Exception:
            logger.warning("keyframe_extraction_failed", exc_info=True)
            return []

    def _extract_audio(self, video_path: str) -> str:
        """使用 ffmpeg 提取音频轨道为 WAV。返回临时文件路径。"""
        fd, temp_path = tempfile.mkstemp(suffix=".wav", prefix="video_audio_")
        os.close(fd)

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            temp_path,
        ]
        try:
            subprocess.run(cmd, check=True, timeout=120, capture_output=True)
            if os.path.getsize(temp_path) > 0:
                logger.info("video_audio_extracted", extra={"path": temp_path[:60]})
                return temp_path
            return ""
        except FileNotFoundError:
            return ""
        except Exception:
            logger.warning("audio_extraction_failed", exc_info=True)
            return ""

    def _ocr_keyframes(self, frame_paths: list[str], filename: str) -> str:
        """使用 LLM Vision 对关键帧做 OCR。"""
        if not frame_paths:
            return ""

        # 限制关键帧数量（最多 12 帧）
        sample_paths = frame_paths[:12]
        all_text: list[str] = []

        for i, path in enumerate(sample_paths):
            try:
                data_url = self._file_to_data_url(path, "image/jpeg")
                messages: list[dict[str, Any]] = [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"帧 {i+1}/{len(sample_paths)}: {_OCR_FRAME_PROMPT}"},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }]
                response = self._llm.chat(
                    messages=messages, tools=None, tool_choice=None, max_tokens=300,
                )
                raw = response.choices[0].message.content or ""
                text = self._parse_ocr_response(raw)
                if text:
                    all_text.append(f"[帧{i+1}] {text}")
            except Exception:
                logger.debug("ocr_frame_failed", extra={"frame": i}, exc_info=True)

        return "\n".join(all_text)

    def _load_whisper(self):
        """Lazy-load Whisper 模型（与 AudioAnalyzer 一致）。"""
        if self._whisper is not None:
            return self._whisper
        try:
            import whisper
            self._whisper = whisper.load_model(self._whisper_model_name)
            logger.info("whisper_loaded", extra={"model": self._whisper_model_name})
            return self._whisper
        except ImportError:
            logger.debug("whisper_not_installed_for_video")
            self._whisper = False  # sentinel
            return None
        except Exception:
            logger.warning("whisper_load_failed", exc_info=True)
            self._whisper = False
            return None

    def _transcribe_audio(self, audio_path: str) -> str:
        """转录提取的音频轨道。复用 Whisper 模式（与 AudioAnalyzer 一致）。"""
        wh = self._load_whisper()
        if wh is None:
            return ""

        try:
            result = wh.transcribe(audio_path, verbose=False)
            text = result.get("text", "").strip()  # type: ignore[union-attr]
            if text:
                logger.info("video_audio_transcribed", extra={"length": len(text)})
            return text
        except Exception:
            logger.debug("video_transcription_failed", exc_info=True)
            return ""

    def _analyze_comprehensive(
        self,
        filename: str,
        duration: float,
        keyframe_count: int,
        ocr_text: str,
        transcription: str,
    ) -> VideoAnalysisResult:
        """LLM 综合分析所有数据源。"""
        prompt = _VIDEO_SUMMARY_PROMPT.format(
            filename=filename,
            duration_seconds=f"{duration:.0f}",
            duration_minutes=duration / 60.0,
            keyframe_count=keyframe_count,
            ocr_text=ocr_text[:2000] or "无",
            transcription=transcription[:2000] or "无",
        )

        try:
            response = self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=None, tool_choice=None, max_tokens=800,
            )
            raw = response.choices[0].message.content or ""
            return self._parse_response(raw)
        except Exception:
            logger.exception("video_comprehensive_analysis_failed")
            return VideoAnalysisResult(
                summary=f"视频: {filename}",
                topic="未知",
            )

    def _analyze_placeholder(self, filename: str, size_bytes: int) -> VideoAnalysisResult:
        """无 ffmpeg 时的回退分析。"""
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
            return self._parse_response(raw)
        except Exception:
            return VideoAnalysisResult(summary="视频分析失败", topic="未知")

    # ── 工具方法 ──

    @staticmethod
    def _check_ffmpeg() -> bool:
        """检查 ffmpeg 是否可用。"""
        return shutil.which("ffmpeg") is not None

    @staticmethod
    def _probe_duration(video_path: str) -> float:
        """获取视频时长（秒）。"""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        try:
            result = subprocess.run(cmd, check=True, timeout=30,
                                    capture_output=True, text=True)
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    @staticmethod
    def _file_to_data_url(file_path: str, content_type: str) -> str:
        with open(file_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{content_type};base64,{data}"

    @staticmethod
    def _parse_response(raw: str) -> VideoAnalysisResult:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if len(lines) > 1 else text
            if text.endswith("```"):
                text = text[:-3]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return VideoAnalysisResult(summary=raw[:120], topic="未知", raw_response=raw)

        return VideoAnalysisResult(
            summary=data.get("summary", "")[:120],
            topic=data.get("topic", "未知"),
            entities=data.get("entities", []),
            concepts=data.get("concepts", []),
            key_points=data.get("key_points", []),
            suggested_use=data.get("suggested_use", ""),
            importance_hint=int(data.get("importance_hint", 5)),
            raw_response=raw,
        )

    @staticmethod
    def _parse_ocr_response(raw: str) -> str:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
        try:
            data = json.loads(text)
            return data.get("text_in_frame", "")
        except json.JSONDecodeError:
            return raw[:200]

    @staticmethod
    def _cleanup_tempfiles(keyframe_paths: list[str], audio_path: str) -> None:
        """清理临时文件。"""
        try:
            if keyframe_paths and os.path.dirname(keyframe_paths[0]):
                temp_dir = os.path.dirname(keyframe_paths[0])
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.debug("video_temp_cleaned", extra={"dir": temp_dir})
        except Exception:
            pass
        try:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
        except Exception:
            pass

    # ── 校验 ──

    @classmethod
    def _validate(cls, file_path: str) -> None:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"视频文件不存在: {file_path}")
        if os.path.getsize(file_path) == 0:
            raise ValueError(f"视频文件为空: {file_path}")
        ext = Path(file_path).suffix.lower()
        if ext not in cls._SUPPORTED_EXTS:
            raise ValueError(
                f"不支持的视频格式: {ext} (支持: {', '.join(sorted(cls._SUPPORTED_EXTS))})"
            )
