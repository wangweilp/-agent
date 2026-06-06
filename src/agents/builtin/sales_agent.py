"""Sales Agent — 销售支持。

能力：
- 客户画像生成（基于历史互动）
- 销售建议与话术推荐
- 竞品对比分析
- 跟进提醒
"""

from __future__ import annotations

import logging

from src.agents.runtime import (
    AgentContext,
    AgentTask,
    BaseAgent,
)

logger = logging.getLogger(__name__)


class SalesAgent(BaseAgent):
    """销售支持 Agent。

    客户分析 → 策略建议 → 话术生成。
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            agent_id="builtin-sales",
            name="Sales Agent",
            description="销售支持：客户画像、建议、话术、竞品分析",
            version="1.0.0",
            **kwargs,
        )

    def plan(self, context: AgentContext, task: AgentTask) -> list[str]:
        action = task.input_data.get("action", "analyze")
        if action == "script":
            return [
                "检索客户历史互动",
                "分析客户需求与痛点",
                "生成话术建议",
                "提供异议处理方案",
            ]
        elif action == "competitor":
            return [
                "检索竞品相关信息",
                "对比产品/服务差异",
                "生成竞品应对策略",
            ]
        else:  # analyze
            return [
                "检索客户信息与历史",
                "生成客户画像",
                "推荐销售策略",
                "标记跟进机会",
            ]

    def execute(self, context: AgentContext, task: AgentTask, plan: list[str]) -> str:
        customer = task.input_data.get("customer", task.description)
        action = task.input_data.get("action", "analyze")

        sections = []

        # 客户背景检索
        if context.memory:
            try:
                memories = context.memory.search(customer, top_k=5)
                context.record_metric("memory_calls", 1)
                if memories:
                    sections.append("## 客户历史互动")
                    for m in memories:
                        sections.append(f"- {m.content[:200]}")
            except Exception:
                pass

        if action == "script":
            sections.append("## 销售话术建议")
            sections.append("### 开场")
            sections.append(f"针对 {customer}，建议以行业痛点切入，强调解决方案价值。")
            sections.append("### 核心价值主张")
            sections.append("- 量化收益（ROI）\n- 差异化优势\n- 客户成功案例")
            sections.append("### 异议处理")
            sections.append("- 价格异议：聚焦长期价值\n- 竞品对比：强调独特优势\n- 决策延迟：提供限时激励")

        elif action == "competitor":
            sections.append("## 竞品分析")
            sections.append(f"针对 {customer} 所在行业，分析竞品格局。")
            sections.append("### 建议策略")
            sections.append("1. 强调差异化能力\n2. 提供对标案例\n3. 准备竞品对比表")

        else:
            sections.append("## 客户画像")
            sections.append(f"**客户**: {customer}")
            sections.append("### 销售策略建议")
            sections.append("- 识别关键决策人\n- 明确客户痛点\n- 准备定制化方案")
            sections.append("### 跟进建议")
            sections.append("24小时内发送方案摘要邮件，3天内安排产品演示。")

        return "\n\n".join(sections)

    def observe(self, context: AgentContext, output: str) -> list[str]:
        observations = super().observe(context, output)
        observations.append(f"策略建议数: {output.count('- ')}")
        return observations

    def reflect(self, context: AgentContext, observations: list[str], output: str) -> tuple[bool, str]:
        if not output.strip():
            return False, "缺少客户信息"
        return True, "销售分析完成"


def create_sales_agent(**kwargs) -> SalesAgent:
    return SalesAgent(**kwargs)
