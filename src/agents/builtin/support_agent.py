"""Support Agent — 客户支持。

能力：
- 工单自动分类与路由
- 知识库答案检索
- 解决方案推荐
- 升级判断（需要人工介入时自动升级）
"""

from __future__ import annotations

import logging

from src.agents.runtime import (
    AgentContext,
    AgentTask,
    BaseAgent,
)

logger = logging.getLogger(__name__)


class SupportAgent(BaseAgent):
    """客户支持 Agent。

    问题分类 → 知识检索 → 方案推荐 → 升级判断。
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            agent_id="builtin-support",
            name="Support Agent",
            description="客户支持：工单分类、答案检索、方案推荐、升级判断",
            version="1.0.0",
            **kwargs,
        )

    def plan(self, context: AgentContext, task: AgentTask) -> list[str]:
        return [
            "分析客户问题，自动分类",
            "检索知识库中的相关解决方案",
            "生成回复建议",
            "评估是否需要人工升级",
        ]

    def execute(self, context: AgentContext, task: AgentTask, plan: list[str]) -> str:
        issue = task.input_data.get("issue", task.description)
        customer = task.input_data.get("customer", "")

        sections = []

        # 问题分类
        category = self._classify_issue(issue)
        sections.append(f"## 问题分类\n**类型**: {category}")

        # 知识库检索
        if context.memory:
            try:
                memories = context.memory.search(issue, top_k=5)
                context.record_metric("memory_calls", 1)
                if memories:
                    sections.append("## 相关解决方案")
                    for i, m in enumerate(memories, 1):
                        sections.append(f"{i}. {m.content[:200]}")
            except Exception:
                pass

        # 回复建议
        sections.append("## 建议回复")
        if "bug" in category.lower() or "故障" in category:
            sections.append("该问题涉及技术故障，建议如下：")
            sections.append("1. 确认问题复现步骤\n2. 提供临时解决方案\n3. 创建 Bug 工单跟踪")
        elif "question" in category.lower() or "咨询" in category:
            sections.append("该问题为信息咨询：")
            sections.append("1. 直接回答客户疑问\n2. 提供相关文档链接\n3. 确认客户满意")
        else:
            sections.append("1. 了解客户问题详情\n2. 提供针对性解决方案\n3. 记录到知识库")

        # 升级判断
        sections.append("## 升级评估")
        needs_escalation = self._needs_escalation(issue, category)
        if needs_escalation:
            sections.append("⚠️ **建议升级到人工处理**")
            sections.append(f"原因: {needs_escalation}")
        else:
            sections.append("✓ 可自动处理")

        return "\n\n".join(sections)

    @staticmethod
    def _classify_issue(issue: str) -> str:
        issue_lower = issue.lower()
        if any(kw in issue_lower for kw in ["bug", "错误", "故障", "崩溃", "不能", "无法", "报错"]):
            return "技术故障"
        elif any(kw in issue_lower for kw in ["怎么", "如何", "什么", "能不能", "可以"]):
            return "信息咨询"
        elif any(kw in issue_lower for kw in ["投诉", "不满", "退款", "赔偿"]):
            return "投诉处理"
        elif any(kw in issue_lower for kw in ["建议", "希望", "最好"]):
            return "产品建议"
        return "一般咨询"

    @staticmethod
    def _needs_escalation(issue: str, category: str) -> str:
        if "投诉" in category:
            return "投诉类问题需人工优先处理"
        if any(kw in issue.lower() for kw in ["退款", "法律", "隐私", "数据丢失"]):
            return "涉及敏感/法律问题，需人工处理"
        if len(issue) > 500:
            return "问题描述复杂，建议人工介入"
        return ""

    def observe(self, context: AgentContext, output: str) -> list[str]:
        observations = super().observe(context, output)
        observations.append(f"问题分类: {self._classify_issue(context.conversation_history[-1]['content'] if context.conversation_history else '')}")
        return observations

    def reflect(self, context: AgentContext, observations: list[str], output: str) -> tuple[bool, str]:
        if not output.strip():
            return False, "需要客户问题描述"
        return True, "支持处理完成"


def create_support_agent(**kwargs) -> SupportAgent:
    return SupportAgent(**kwargs)
