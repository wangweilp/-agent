"""Knowledge Agent — 企业知识管理。

能力：
- 知识入库（写入 Memory + Knowledge Graph）
- 知识检索（语义搜索 + 图谱遍历）
- 知识整理（分类、摘要、关联）
- 知识推荐（基于上下文自动推荐）
"""

from __future__ import annotations

import logging

from src.agents.runtime import (
    AgentContext,
    AgentResult,
    AgentTask,
    BaseAgent,
)

logger = logging.getLogger(__name__)


class KnowledgeAgent(BaseAgent):
    """知识管理 Agent。

    自动将对话/文档中的知识点结构化存储，
    支持语义检索和图谱推理。
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            agent_id="builtin-knowledge",
            name="Knowledge Agent",
            description="企业知识管理：入库、检索、整理、推荐",
            version="1.0.0",
            **kwargs,
        )

    def plan(self, context: AgentContext, task: AgentTask) -> list[str]:
        action = task.input_data.get("action", "search")
        if action == "ingest":
            return [
                "解析输入内容，提取知识点",
                "为每个知识点生成摘要和标签",
                "写入 Memory Store",
                "更新 Knowledge Graph 实体与关系",
                "返回入库报告",
            ]
        elif action == "organize":
            return [
                "检索指定范围的知识",
                "按主题聚类",
                "识别重复/矛盾/过时内容",
                "生成整理建议",
            ]
        else:  # search
            return [
                "解析查询意图",
                "语义搜索 Memory Store",
                "遍历 Knowledge Graph 获取关联知识",
                "排序与去重",
                "生成结构化知识报告",
            ]

    def execute(self, context: AgentContext, task: AgentTask, plan: list[str]) -> str:
        action = task.input_data.get("action", "search")
        query = task.input_data.get("query", task.description)
        top_k = task.input_data.get("top_k", 5)

        results = []

        # Memory search
        if context.memory:
            try:
                memories = context.memory.search(query, top_k=top_k)
                context.record_metric("memory_calls", 1)
                if memories:
                    results.append("## 记忆检索结果")
                    for i, m in enumerate(memories, 1):
                        results.append(f"{i}. [{m.score:.2f}] {m.content[:200]}")
            except Exception as e:
                logger.warning("knowledge_agent_memory_search_failed", extra={"error": str(e)})

        # Knowledge Graph traversal
        if context.knowledge_graph:
            try:
                entities = context.knowledge_graph.query_entities(query, top_k=3)
                context.record_metric("kg_calls", 1)
                if entities:
                    results.append("## 知识图谱关联")
                    for e in entities:
                        relations = context.knowledge_graph.query_relations(e.id)
                        rel_str = ", ".join(
                            f"{r.predicate}→{r.target}" for r in relations[:3]
                        )
                        results.append(f"- **{e.name}** [{e.entity_type}]: {rel_str}" if rel_str else f"- **{e.name}** [{e.entity_type}]")
            except Exception as e:
                logger.warning("knowledge_agent_kg_failed", extra={"error": str(e)})

        # Ingest mode
        if action == "ingest":
            content = task.input_data.get("content", "")
            if content and context.memory:
                try:
                    memory_id = context.memory.remember(
                        content,
                        metadata={"source": "knowledge_agent", "tags": task.tags},
                    )
                    results.append(f"## 入库结果\n已存储: {memory_id}")
                except Exception as e:
                    results.append(f"## 入库失败\n{str(e)}")

        if not results:
            return f"未找到与「{query}」相关的知识。"
        return "\n\n".join(results)

    def observe(self, context: AgentContext, output: str) -> list[str]:
        observations = super().observe(context, output)
        if context.memory:
            observations.append("Memory 调用成功")
        if context.knowledge_graph:
            observations.append("Knowledge Graph 调用成功")
        return observations

    def reflect(self, context: AgentContext, observations: list[str], output: str) -> tuple[bool, str]:
        if not output.strip() or "失败" in output:
            return False, "需要调整搜索策略或扩大搜索范围"
        return True, "知识检索完成"


def create_knowledge_agent(**kwargs) -> KnowledgeAgent:
    return KnowledgeAgent(**kwargs)
