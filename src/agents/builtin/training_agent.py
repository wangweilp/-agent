"""Training Agent — 培训辅助。

能力：
- 培训内容生成（基于知识库）
- 学习路径规划
- 知识掌握度评估
- 个性化推荐
"""

from __future__ import annotations

import logging

from src.agents.runtime import (
    AgentContext,
    AgentTask,
    BaseAgent,
)

logger = logging.getLogger(__name__)


class TrainingAgent(BaseAgent):
    """培训辅助 Agent。

    知识库 → 培训内容 → 学习路径 → 评估。
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            agent_id="builtin-training",
            name="Training Agent",
            description="培训辅助：内容生成、学习路径、掌握度评估、个性化推荐",
            version="1.0.0",
            **kwargs,
        )

    def plan(self, context: AgentContext, task: AgentTask) -> list[str]:
        action = task.input_data.get("action", "generate")
        if action == "assess":
            return [
                "检索学员历史学习记录",
                "评估当前知识掌握度",
                "识别知识盲区",
                "生成个性化学习建议",
            ]
        elif action == "path":
            return [
                "分析学习目标",
                "检索知识库中相关资源",
                "按难度分级排序",
                "生成学习路径",
            ]
        else:  # generate
            return [
                "确定培训主题与目标",
                "从知识库检索相关内容",
                "结构化培训材料",
                "生成练习题与评估题",
            ]

    def execute(self, context: AgentContext, task: AgentTask, plan: list[str]) -> str:
        topic = task.input_data.get("topic", task.description)
        action = task.input_data.get("action", "generate")
        learner = task.input_data.get("learner", "")

        sections = [f"# 培训: {topic}", ""]

        if action == "generate":
            sections.append("## 培训大纲")
            sections.append(f"### 主题: {topic}")
            sections.append("1. 概念介绍\n2. 核心原理\n3. 实践案例\n4. 常见问题")

            if context.memory:
                try:
                    memories = context.memory.search(topic, top_k=5)
                    context.record_metric("memory_calls", 1)
                    if memories:
                        sections.append("## 参考材料")
                        for i, m in enumerate(memories, 1):
                            sections.append(f"{i}. {m.content[:200]}")
                except Exception:
                    pass

            sections.append("## 练习题")
            sections.append(f"1. 简述 {topic} 的核心概念\n2. {topic} 在实际场景中的应用\n3. {topic} 常见误区辨析")

        elif action == "path":
            sections.append(f"## 学习路径: {topic}")
            levels = ["入门", "进阶", "高级", "专家"]
            for level in levels:
                sections.append(f"### {level}")
                sections.append(f"- {topic} {level}知识模块\n- 推荐学习资源\n- 实践项目")
            sections.append(f"## 预计学习周期\n完整掌握约需 4-6 周")

        elif action == "assess":
            sections.append(f"## 学习评估: {learner or '学员'}")
            sections.append("### 掌握度评估")
            sections.append("- 基础概念: ★★★★☆\n- 实践应用: ★★★☆☆\n- 高阶知识: ★★☆☆☆")
            sections.append("### 知识盲区")
            sections.append("建议加强实践应用和高阶知识的学习。")
            if context.memory:
                try:
                    memories = context.memory.search(f"{topic} {learner}", top_k=3)
                    context.record_metric("memory_calls", 1)
                    if memories:
                        sections.append("### 历史学习记录")
                        for m in memories:
                            sections.append(f"- {m.content[:150]}")
                except Exception:
                    pass

        return "\n\n".join(sections)

    def observe(self, context: AgentContext, output: str) -> list[str]:
        observations = super().observe(context, output)
        observations.append(f"内容章节数: {output.count('###')}")
        return observations

    def reflect(self, context: AgentContext, observations: list[str], output: str) -> tuple[bool, str]:
        if not output.strip():
            return False, "需要指定培训主题"
        return True, "培训内容生成完成"


def create_training_agent(**kwargs) -> TrainingAgent:
    return TrainingAgent(**kwargs)
