"""Meeting Agent — 会议全流程处理。

能力：
- 会前：议程生成、材料准备
- 会中：实时记录、要点提取
- 会后：纪要生成、行动项提取、知识沉淀
"""

from __future__ import annotations

import logging

from src.agents.runtime import (
    AgentContext,
    AgentTask,
    BaseAgent,
)

logger = logging.getLogger(__name__)


class MeetingAgent(BaseAgent):
    """会议处理 Agent。

    会议记录 → 要点提取 → 行动项 → 知识沉淀。
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            agent_id="builtin-meeting",
            name="Meeting Agent",
            description="会议全流程处理：议程、记录、纪要、行动项",
            version="1.0.0",
            **kwargs,
        )

    def plan(self, context: AgentContext, task: AgentTask) -> list[str]:
        stage = task.input_data.get("stage", "full")
        if stage == "before":
            return [
                "检索上次会议相关记忆",
                "生成本次会议议程建议",
                "准备相关背景材料",
            ]
        elif stage == "after":
            return [
                "解析会议记录原文",
                "提取关键要点与决策",
                "识别行动项与负责人",
                "生成结构化会议纪要",
                "将要点写入 Knowledge Graph",
            ]
        else:  # full
            return [
                "会前：生成议程",
                "会中：提取要点",
                "会后：生成纪要与行动项",
            ]

    def execute(self, context: AgentContext, task: AgentTask, plan: list[str]) -> str:
        transcript = task.input_data.get("transcript", task.description)
        stage = task.input_data.get("stage", "full")

        lines = []

        # 会前：检索相关背景
        if stage in ("before", "full"):
            lines.append("## 会前准备")
            if context.memory:
                try:
                    memories = context.memory.search(
                        task.input_data.get("topic", task.title), top_k=3
                    )
                    if memories:
                        lines.append("### 相关历史")
                        for m in memories:
                            lines.append(f"- {m.content[:150]}")
                except Exception:
                    pass
            lines.append("### 建议议程")
            agenda = task.input_data.get("agenda", "")
            if agenda:
                for item in agenda.split("\n"):
                    if item.strip():
                        lines.append(f"1. {item.strip()}")
            else:
                lines.append("1. 回顾上次行动项\n2. 本次议题讨论\n3. 决议与下一步")

        # 会后：解析与结构化
        if stage in ("after", "full"):
            lines.append("## 会议纪要")
            if transcript:
                # 提取要点
                lines.append("### 关键要点")
                points = self._extract_key_points(transcript)
                for p in points:
                    lines.append(f"- {p}")

                # 行动项
                lines.append("### 行动项")
                actions = self._extract_action_items(transcript)
                if actions:
                    for a in actions:
                        lines.append(f"- [ ] {a}")
                else:
                    lines.append("- 无明确行动项")

                # 写入知识库
                if context.memory:
                    try:
                        context.memory.remember(
                            f"会议纪要: {task.title}\n{transcript[:500]}",
                            metadata={"source": "meeting_agent", "type": "meeting_minutes"},
                        )
                        context.record_metric("memory_calls", 1)
                    except Exception:
                        pass
            else:
                lines.append("无会议记录输入")

        if not lines:
            return "会议处理完成，无输出。"
        return "\n\n".join(lines)

    @staticmethod
    def _extract_key_points(text: str) -> list[str]:
        """从文本中提取关键要点。"""
        points = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            # 识别决策关键词
            keywords = ["决定", "结论", "同意", "确认", "计划", "目标", "问题", "方案"]
            if any(kw in line for kw in keywords):
                points.append(line[:200])
        if not points:
            # 取前5个非空行
            points = [l for l in text.split("\n") if l.strip()][:5]
        return points[:10]

    @staticmethod
    def _extract_action_items(text: str) -> list[str]:
        """从文本中提取行动项。"""
        actions = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            keywords = ["负责", "跟进", "完成", "执行", "@", "TODO", "待办", "任务", "action"]
            if any(kw.lower() in line.lower() for kw in keywords):
                actions.append(line[:200])
        return actions[:10]

    def observe(self, context: AgentContext, output: str) -> list[str]:
        observations = super().observe(context, output)
        if "行动项" in output:
            observations.append("已提取行动项")
        if "关键要点" in output:
            observations.append("已提取关键要点")
        return observations

    def reflect(self, context: AgentContext, observations: list[str], output: str) -> tuple[bool, str]:
        if not output.strip():
            return False, "需要会议记录输入"
        return True, "会议处理完成"


def create_meeting_agent(**kwargs) -> MeetingAgent:
    return MeetingAgent(**kwargs)
