# AudioService v2 — OS Event Source Module 设计

> 状态: `spec-frozen` | 日期: 2026-06-25 | 类型: feature

---

## 1. 目标

将 whisper 能力从 `AudioAnalyzer` / `VideoAnalyzer` 中抽离为独立的 `AudioService`，
使其成为 **Zhiwei OS 的 L1 Event Source Module**，满足：

- 全生命周期事件化（started / completed / failed）
- trace_id 因果链绑定
- EventStore / Snapshot / Replay 兼容
- 前端 SSE 可观测
- whisper model lazy + cached + thread-safe

---

## 2. 架构定位

```
┌──────────────────────────────────────────────┐
│  L4 OS Core (CausalKernel / Authority /       │
│             Enforcement / ControlLoop)         │
│  ❌ Audio 不进入此层                            │
└──────────────────────────────────────────────┘
                      ▲
                      │ SSE (observability only)
┌─────────────────────┼────────────────────────┐
│  L3 Observability   │                         │
│  StructuredEventEmitter → SSE → 前端 Dashboard │
│  Audio 事件作为 observability 数据展示          │
└─────────────────────┼────────────────────────┘
                      │
┌─────────────────────┼────────────────────────┐
│  L1 EventBus        │                         │
│  audio.transcription.{started,completed,failed}│
└─────────────────────┼────────────────────────┘
                      │ emit
┌─────────────────────┼────────────────────────┐
│  AudioService       │  Pure Capability         │
│  - whisper.load_model("base") lazy + cached    │
│  - transcribe(path, context) → str             │
│  - thread-safe (Lock)                          │
└─────────────────────┴────────────────────────┘
          ▲                   ▲
          │                   │
   AudioAnalyzer        VideoAnalyzer
   (LLM analysis)       (ffmpeg pipeline)
```

**核心决策**: Audio = Observability Layer, **不**进入 CausalKernel / Replay / Snapshot / Authority。

---

## 3. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/core/audio_service.py` | **NEW** | AudioService + TranscriptionContext + 事件常量 |
| `src/core/audio_analyzer.py` | MOD | 注入 AudioService，删除 `_load_whisper()`/`_transcribe()` |
| `src/core/video_analyzer.py` | MOD | 注入 AudioService，删除 `_load_whisper()`/`_transcribe_audio()` |
| `src/api/audio.py` | MOD | 创建 AudioService 并注入到 AudioAnalyzer |
| `src/api/video.py` | MOD | 注入 AudioService 到 VideoAnalyzer |
| `src/bootstrap/event_bridge.py` | MOD | `_BACKEND_EVENT_MAP` 追加 3 个 audio 事件映射 |
| `main.py` | MOD | 组装 AudioService → Analyzer 依赖链 |

---

## 4. 核心接口

### 4.1 AudioService

```python
class AudioService:
    """Whisper 音频转录服务 — OS Event Source Module.

    - whisper model lazy-load + cached + thread-safe
    - 通过 EventBus 发射全生命周期事件 (started/completed/failed)
    - EventBus 可选: None 时静默工作 (standalone mode)
    """

    def __init__(
        self,
        *,
        whisper_model: str = "base",
        event_bus: EventBus | None = None,
    ) -> None: ...

    def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = "zh",
        context: TranscriptionContext | None = None,
    ) -> str: ...
    # context=None → 不发事件 (standalone mode)
    # context 非 None → 发射 started/completed/failed

    def transcribe_batch(
        self,
        paths: list[str],
        *,
        language: str | None = "zh",
        context: TranscriptionContext | None = None,
    ) -> list[str]: ...

    @property
    def is_available(self) -> bool: ...
    # 检查 whisper 是否可加载 (不实际加载)
```

### 4.2 TranscriptionContext

```python
@dataclass
class TranscriptionContext:
    """调用方显式传入，控制事件粒度和因果链绑定。"""
    trace_id: str       # 关联调用链，对接前端 CausalKernel
    source: str         # "audio_analyzer" | "video_analyzer" | "cli"
    file_name: str      # 原始文件名（非临时路径）
```

### 4.3 事件常量

```python
# src/core/audio_service.py
AUDIO_TRANSCRIPTION_STARTED   = "audio.transcription.started"
AUDIO_TRANSCRIPTION_COMPLETED = "audio.transcription.completed"
AUDIO_TRANSCRIPTION_FAILED    = "audio.transcription.failed"
```

---

## 5. 事件 Schema（OS 标准化）

每个事件 payload 必须包含 `event_id` + `timestamp`，保证 replay ordering 稳定、snapshot diff 可计算。

### 5.1 started

```json
{
  "event_id": "uuid4",
  "timestamp": "2026-06-25T10:30:00.000Z",
  "trace_id": "trace_abc123",
  "source": "video_analyzer",
  "file_name": "meeting-2026.mp4",
  "model": "base"
}
```

### 5.2 completed

```json
{
  "event_id": "uuid4",
  "timestamp": "2026-06-25T10:30:12.000Z",
  "trace_id": "trace_abc123",
  "source": "video_analyzer",
  "file_name": "meeting-2026.mp4",
  "text_length": 1420,
  "language": "zh",
  "duration_ms": 11500,
  "model": "base"
}
```

### 5.3 failed（统一 error schema）

```json
{
  "event_id": "uuid4",
  "timestamp": "2026-06-25T10:30:05.000Z",
  "trace_id": "trace_abc123",
  "source": "audio_analyzer",
  "file_name": "lecture.mp3",
  "error_code": "WHISPER_NOT_AVAILABLE",
  "error_message": "openai-whisper package not installed"
}
```

**error_code 枚举**:
| code | 含义 |
|------|------|
| `WHISPER_NOT_AVAILABLE` | whisper 未安装或加载失败 |
| `TRANSCRIPTION_ERROR` | 转录过程异常 |

---

## 6. 事件桥接（后端 → 前端 SSE）

在 `src/bootstrap/event_bridge.py` 的 `_BACKEND_EVENT_MAP` 中追加：

```python
AUDIO_TRANSCRIPTION_STARTED: {
    "source": "observability",
    "type": "observability.audio.transcription_started",
    "severity": "info",
    "cause_type": "system_event",
},
AUDIO_TRANSCRIPTION_COMPLETED: {
    "source": "observability",
    "type": "observability.audio.transcription_completed",
    "severity": "info",
    "cause_type": "system_event",
},
AUDIO_TRANSCRIPTION_FAILED: {
    "source": "observability",
    "type": "observability.audio.transcription_failed",
    "severity": "error",
    "cause_type": "system_error",
},
```

前端效果：Dashboard / Debug Panel 可实时看到 audio 事件流，但不接入 CausalKernel。

---

## 7. 调用方适配

### 7.1 AudioAnalyzer（改造后）

```python
class AudioAnalyzer:
    def __init__(self, llm: ChatModel, audio_service: AudioService, settings=None):
        self._llm = llm
        self._audio = audio_service      # 注入，不再自己管理 whisper

    def _transcribe(self, file_path: str, trace_id: str = "") -> str:
        tid = trace_id or str(uuid4())
        return self._audio.transcribe(
            file_path,
            language="zh",
            context=TranscriptionContext(
                trace_id=tid,
                source="audio_analyzer",
                file_name=os.path.basename(file_path),
            ),
        )
    # 删除: _load_whisper()
```

### 7.2 VideoAnalyzer（改造后）

```python
class VideoAnalyzer:
    def __init__(self, llm: ChatModel, audio_service: AudioService, settings=None):
        self._llm = llm
        self._audio = audio_service      # 注入
        # ...其余不变

    def analyze(self, file_path: str, filename: str = "") -> VideoAnalysisResult:
        # trace_id 在 analyze() 入口生成一次，贯穿整个管线
        trace_id = str(uuid4())
        if not filename:
            filename = os.path.basename(file_path)
        # ... ffmpeg / OCR 等步骤 ...
        if audio_path and os.path.getsize(audio_path) > 0:
            transcription = self._transcribe_audio(audio_path, filename, trace_id)
        # ...

    def _transcribe_audio(self, audio_path: str, file_name: str, trace_id: str) -> str:
        return self._audio.transcribe(
            audio_path,
            language=None,      # 视频音频语言未知
            context=TranscriptionContext(
                trace_id=trace_id,
                source="video_analyzer",
                file_name=file_name,
            ),
        )
    # 删除: _load_whisper()
```

### 7.3 main.py 组装

```python
# 旧
audio_analyzer = AudioAnalyzer(llm, settings)
video_analyzer = VideoAnalyzer(llm, settings)

# 新
audio_service = AudioService(
    whisper_model="base",
    event_bus=system_runtime.event_bus,
)
audio_analyzer = AudioAnalyzer(llm, audio_service, settings)
video_analyzer = VideoAnalyzer(llm, audio_service, settings)
```

---

## 8. 线程安全

```python
class AudioService:
    def __init__(self, ...):
        self._lock = threading.Lock()

    def _load_whisper(self):
        if self._whisper is not None:
            return self._whisper
        with self._lock:
            if self._whisper is not None:    # double-check
                return self._whisper
            import whisper
            self._whisper = whisper.load_model(self._whisper_model_name)
        return self._whisper
```

---

## 9. 不做的边界

| ❌ 不做 | 原因 |
|---------|------|
| 不进入 CausalKernel | Audio = Observability, 非系统状态 |
| 不进入 Replay | Replay 只回放 OS state, 不重跑 whisper |
| 不进入 Snapshot | Audio 输出不纳入快照一致性 |
| 不进入 Authority Layer | Audio 不需要权威仲裁 |
| 不新增前端 EventType | 复用 `observability.metric.recorded` 通道 |

---

## 10. 测试要点

- [ ] `AudioService.transcribe()` standalone mode (event_bus=None)
- [ ] `AudioService.transcribe()` emits started/completed/failed via EventBus
- [ ] `AudioService.is_available` returns False when whisper not installed
- [ ] whisper model loaded once (second call uses cache)
- [ ] thread-safe: concurrent transcribe calls share one model instance
- [ ] `AudioAnalyzer` works with injected AudioService (no regression)
- [ ] `VideoAnalyzer` works with injected AudioService (no regression)
- [ ] SSE endpoint streams audio events to frontend
- [ ] failed event carries correct error_code

---

## 11. 风险 & Trade-off

| 风险 | 缓解 |
|------|------|
| whisper 首次加载耗时长 | lazy-load + 明确文档说明 |
| audio 不进入 CausalKernel → 不可因果追溯 | 正确的工程决策：audio 是观测数据，非系统状态 |
| EventBus 异步发射 → 事件可能延迟到达 SSE | 可接受（observability 非实时要求） |
