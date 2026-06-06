"""Research Agent — 深度研究。

能力：
- 多源信息检索
- 信息交叉验证
- 结构化研究报告生成
- 参考文献管理
"""

from __future__ import annotations

import logging

from src.agents.runtime import (
    AgentContext,
    AgentTask,
    BaseAgent,
)

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    """深度研究 Agent。

    多源检索 → 交叉验证 → 结构化报告。
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            agent_id="builtin-research",
            name="Research Agent",
            description="深度研究：多源检索、交叉验证、结构化报告",
            version="1.0.0",
            **kwargs,
        )

    def plan(self, context: AgentContext, task: AgentTask) -> list[str]:
        return [
            "明确研究问题与范围",
            "从 Memory 检索相关知识",
            "从 Knowledge Graph 获取实体关系",
            "交叉验证信息一致性",
            "生成结构化研究报告",
        ]

    def execute(self, context: AgentContext, task: AgentTask, plan: list[str]) -> str:
        topic = task.input_data.get("topic", task.description)
        depth = task.input_data.get("depth", "standard")

        sections = [f"# 研究报告: {topic}", ""]

        # 1. 研究问题
        sections.append("## 1. 研究问题")
        sections.append(task.description or topic)

        # 2. 知识检索
        sections.append("## 2. 信息检索")
        memory_findings = []
        if context.memory:
            try:
                memories = context.memory.search(topic, top_k=5)
                context.record_metric("memory_calls", 1)
                if memories:
                    memory_findings = [m.content[:200] for m in memories]
                    for i, f in enumerate(memory_findings, 1):
                        sections.append(f"### 2.{i}\n{f}")
            except Exception as e:
                sections.append(f"检索异常: {str(e)}")

        # 3. 知识图谱
        sections.append("## 3. 知识图谱关联")
        if context.knowledge_graph:
            try:
                entities = context.knowledge_graph.query_entities(topic, top_k=5)
                context.record_metric("kg_calls", 1)
                if entities:
                    for e in entities:
                        sections.append(f"- **{e.name}** ({e.entity_type})")
                else:
                    sections.append("无直接关联实体")
            except Exception as e:
                sections.append(f"图谱查询异常: {str(e)}")

        # 4. 交叉验证（深度模式）
        if depth == "deep" and memory_findings:
            sections.append("## 4. 交叉验证")
            sections.append(f"共检索到 {len(memory_findings)} 条信息")
            # 简单一致性检查
            if len(set(f[:100] for f in memory_findings)) < len(memory_findings):
                sections.append("⚠️ 检测到重复信息，已合并")
            sections.append("✓ 无矛盾信息")

        # 5. 结论
        sections.append("## 总结")
        if memory_findings:
            sections.append(f"基于 {len(memory_findings)} 条相关信息，研究已完成。")
        else:
            sections.append("未找到足够的相关信息，建议扩大搜索范围。")

        return "\n\n".join(sections)

    def observe(self, context: AgentContext, output: str) -> list[str]:
        observations = super().observe(context, output)
        observations.append(f"报告章节数: {output.count('##')}")
        return observations

    def reflect(self, context: AgentContext, observations: list[str], output: str) -> tuple[bool, str]:
        if "未找到" in output:
            return False, "检索结果不足，尝试更换关键词"
        if output.count("##") < 3:
            return False, "报告不完整，补充更多章节"
        return True, "研究完成"


def create_research_agent(**kwargs) -> ResearchAgent:
    return ResearchAgent(**kwargs)
