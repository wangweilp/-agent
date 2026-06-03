"""API 数据模型。"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    content: str = Field(..., description="用户输入内容", min_length=1)


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Agent 回复内容")
    tool_calls: int = Field(default=0, description="工具调用次数")


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    size_bytes: int
    content_type: str
    tasks: list["MemoryTaskResponse"] = []


class MemoryTaskResponse(BaseModel):
    task_id: str
    memory_type: str  # working / episodic / semantic / conceptual / reflective
    content: str
    status: str = "pending"
    entities: list[str] = []
    importance: int = 5


# ── Dashboard 响应模型 ──


class DashboardSummary(BaseModel):
    """仪表盘总览摘要。"""
    total_memories: int = 0
    active_memories: int = 0
    archived_memories: int = 0
    merged_memories: int = 0
    deleted_memories: int = 0
    episodic_count: int = 0
    semantic_count: int = 0
    reflect_count: int = 0
    weekly_growth: int = 0
    queue_depth: int = 0
    dlq_count: int = 0


class TopicItem(BaseModel):
    """热门主题条目。"""
    name: str
    mention_count: int
    memory_count: int


class EntityItem(BaseModel):
    """实体条目。"""
    name: str
    entity_type: str
    mention_count: int
    first_seen: str | None = None


class RecentMemoryItem(BaseModel):
    """最近记忆条目（精简格式）。"""
    id: str
    content_preview: str
    source: str
    timestamp: str
    importance: int
    memory_type: str
    status: str
    entities: list[str] = []


class RecentReflectionItem(BaseModel):
    """最近反思条目。"""
    id: str
    topic: str
    finding: str
    importance: int
    timestamp: str
    entities: list[str] = []


class WeeklyReportPlaceholder(BaseModel):
    """周报占位响应（v0.4 实现完整周报）。"""
    status: str = "not_implemented"
    message: str = "周报功能计划在 v0.4 实现"
    stats: dict = {}


# ── Memory Search & Management 模型 ──


class MemoryUpdateRequest(BaseModel):
    """编辑记忆请求 — 所有字段可选，只更新传入的字段。"""
    content: str | None = None
    summary: str | None = None
    importance: int | None = Field(default=None, ge=1, le=10)
    entities: list[str] | None = None
    memory_type: str | None = None


class MemoryMergeRequest(BaseModel):
    """手动合并记忆请求。"""
    primary_id: str = Field(..., description="保留的主记忆 ID")
    secondary_ids: list[str] = Field(..., description="被合并的记忆 ID 列表", min_length=1)


# ── Timeline 模型 ──


class TimelineEvent(BaseModel):
    """时间轴事件 — 从已有记忆派生。"""
    id: str
    type: str  # memory_created | memory_archived | memory_merged | memory_promoted | image_uploaded | reflection_generated | weekly_report_generated
    content_preview: str
    memory_type: str
    importance: int
    entities: list[str] = []
    timestamp: str
    status: str = "active"


class TimelineDay(BaseModel):
    """某一天的事件汇总。"""
    date: str  # YYYY-MM-DD
    events: list[TimelineEvent]
    count: int


class TimelineStats(BaseModel):
    """时间轴的聚合统计。"""
    total_events: int = 0
    created_count: int = 0
    archived_count: int = 0
    merged_count: int = 0
    reflection_count: int = 0
    image_count: int = 0
    promoted_count: int = 0
    weekly_report_count: int = 0


# ── Graph 模型 ──


class GraphNode(BaseModel):
    """图谱节点。"""
    id: str
    label: str
    type: str  # entity | memory | concept | image
    importance: int = 5
    memory_count: int = 0
    group: str = ""  # 聚类分组标签


class GraphEdge(BaseModel):
    """图谱边。"""
    source: str
    target: str
    relation: str  # predicate 或 "co_occurrence" 或 "has_entity"
    weight: float = 1.0


class GraphData(BaseModel):
    """完整图谱数据。"""
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    stats: dict = {}


class EntityDetail(BaseModel):
    """实体详情。"""
    name: str
    entity_type: str
    mention_count: int
    first_seen: str | None = None
    related_memories: list[dict] = []
    related_entities: list[dict] = []
    recent_activity: list[dict] = []


# ── Import 模型 ──


class ImportJobRequest(BaseModel):
    """导入作业请求体 — multipart 上传外的额外元数据。"""
    title: str | None = None
    tags: list[str] = []


class ImportJobResponse(BaseModel):
    """导入作业响应体。"""
    job_id: str
    title: str
    file_type: str
    status: str
    total_chunks: int = 0
    processed_chunks: int = 0
    memories_created: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    progress_pct: float = 0.0
    error: str | None = None


class ImportJobListResponse(BaseModel):
    """导入作业列表响应。"""
    jobs: list[ImportJobResponse]
    total: int
