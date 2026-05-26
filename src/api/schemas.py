"""API 数据模型。"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    content: str = Field(..., description="用户输入内容", min_length=1)


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Agent 回复内容")
    tool_calls: int = Field(default=0, description="工具调用次数")
