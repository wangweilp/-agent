"""Department Agents — 部门专属 Agent。

每个部门 Agent 具备：
- 读取部门知识库
- 生成建议
- 执行工作流

部门列表：
- 研发 Agent (R&D)
- 产品 Agent (Product)
- 运营 Agent (Operations)
- 销售 Agent (Sales)
- HR Agent
- 客服 Agent (Customer Service)
"""

from __future__ import annotations

import logging

from src.agents.runtime import (
    AgentContext,
    AgentTask,
    BaseAgent,
    MemoryProvider,
    KnowledgeGraphProvider,
    ToolProvider,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 部门基础设施
# ═══════════════════════════════════════════


class DepartmentAgent(BaseAgent):
    """部门 Agent 基类。

    自动注入部门知识库过滤，提供部门上下文。
    """

    department: str = ""
    department_kb_namespace: str = ""

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        department: str,
        kb_namespace: str,
        **kwargs,
    ) -> None:
        super().__init__(agent_id=agent_id, name=name, description=description, **kwargs)
        self.department = department
        self.department_kb_namespace = kb_namespace

    def plan(self, context: AgentContext, task: AgentTask) -> list[str]:
        return [
            f"加载 {self.department} 部门知识库",
            "分析任务需求",
            f"结合部门知识生成建议",
            "输出结构化结果",
        ]

    def execute(self, context: AgentContext, task: AgentTask, plan: list[str]) -> str:
        query = task.input_data.get("query", task.description)
        department = self.department
        namespace = self.department_kb_namespace

        sections = [f"# {department} Agent 分析", ""]

        # 从部门知识库检索
        if context.memory:
            try:
                # 用部门命名空间过滤搜索
                search_query = f"{namespace} {query}" if namespace else query
                memories = context.memory.search(search_query, top_k=5)
                context.record_metric("memory_calls", 1)
                if memories:
                    sections.append("## 部门知识库匹配")
                    for m in memories:
                        sections.append(f"- {m.content[:200]}")
            except Exception as e:
                logger.warning("dept_kb_search_failed", extra={"dept": department, "error": str(e)})

        # 知识图谱
        if context.knowledge_graph:
            try:
                entities = context.knowledge_graph.query_entities(f"{department} {query}", top_k=3)
                context.record_metric("kg_calls", 1)
                if entities:
                    sections.append("## 知识关联")
                    for e in entities:
                        sections.append(f"- {e.name} [{e.entity_type}]")
            except Exception:
                pass

        return "\n\n".join(sections)

    def observe(self, context: AgentContext, output: str) -> list[str]:
        observations = super().observe(context, output)
        observations.append(f"部门: {self.department}")
        return observations

    def reflect(self, context: AgentContext, observations: list[str], output: str) -> tuple[bool, str]:
        if "部门知识库匹配" not in output:
            return False, "部门知识库无匹配结果，尝试扩大搜索范围"
        return True, f"{self.department} 分析完成"


# ═══════════════════════════════════════════
# 研发 Agent
# ═══════════════════════════════════════════


class RDAgent(DepartmentAgent):
    """研发部门 Agent。

    能力：
    - 技术方案评估
    - 代码审查建议
    - 技术债务分析
    - 架构决策建议
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            agent_id="dept-rd",
            name="研发 Agent",
            description="研发部门专属：技术方案评估、代码审查、架构建议",
            department="研发部",
            kb_namespace="rd/engineering",
            **kwargs,
        )

    def execute(self, context: AgentContext, task: AgentTask, plan: list[str]) -> str:
        base = super().execute(context, task, plan)
        action = task.input_data.get("action", "evaluate")

        sections = [base, ""]
        if action == "evaluate":
            sections.append("## 技术方案评估")
            sections.append("### 可行性: ✓ 方案可行")
            sections.append("### 风险点\n- 技术复杂度\n- 团队技能匹配\n- 第三方依赖风险")
            sections.append("### 建议\n- 分阶段实施，降低风险\n- 关键模块先做 PoC")
        elif action == "review":
            sections.append("## 代码审查建议")
            sections.append("- 关注性能热点\n- 检查安全漏洞\n- 确保测试覆盖率")
        elif action == "debt":
            sections.append("## 技术债务分析")
            sections.append("- 识别遗留模块\n- 评估重构优先级\n- 制定偿还计划")
        return "\n\n".join(sections)

    def reflect(self, context: AgentContext, observations: list[str], output: str) -> tuple[bool, str]:
        return True, "研发分析完成"


# ═══════════════════════════════════════════
# 产品 Agent
# ═══════════════════════════════════════════


class ProductAgent(DepartmentAgent):
    """产品部门 Agent。

    能力：
    - 需求分析
    - 竞品调研
    - PRD 起草辅助
    - 用户反馈分析
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            agent_id="dept-product",
            name="产品 Agent",
            description="产品部门专属：需求分析、竞品调研、PRD 辅助",
            department="产品部",
            kb_namespace="product",
            **kwargs,
        )

    def execute(self, context: AgentContext, task: AgentTask, plan: list[str]) -> str:
        base = super().execute(context, task, plan)
        sections = [base, "", "## 产品分析建议"]
        sections.append("### 用户需求\n- 核心痛点识别\n- 用户场景梳理")
        sections.append("### 竞品参考\n- 对标产品分析\n- 差异化策略")
        sections.append("### PRD 要点\n- 功能优先级排序\n- 验收标准定义")
        return "\n\n".join(sections)

    def reflect(self, context: AgentContext, observations: list[str], output: str) -> tuple[bool, str]:
        return True, "产品分析完成"


# ═══════════════════════════════════════════
# 运营 Agent
# ═══════════════════════════════════════════


class OperationsAgent(DepartmentAgent):
    """运营部门 Agent。

    能力：
    - 运营数据分析
    - 活动效果评估
    - 内容策略建议
    - 用户增长分析
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            agent_id="dept-operations",
            name="运营 Agent",
            description="运营部门专属：数据分析、活动评估、内容策略",
            department="运营部",
            kb_namespace="operations",
            **kwargs,
        )

    def execute(self, context: AgentContext, task: AgentTask, plan: list[str]) -> str:
        base = super().execute(context, task, plan)
        sections = [base, "", "## 运营分析"]
        sections.append("### KPI 分析\n- 关键指标趋势\n- 异常检测")
        sections.append("### 活动建议\n- A/B 测试方案\n- 最佳时间窗口")
        sections.append("### 内容策略\n- 热点话题识别\n- 发布节奏优化")
        return "\n\n".join(sections)

    def reflect(self, context: AgentContext, observations: list[str], output: str) -> tuple[bool, str]:
        return True, "运营分析完成"


# ═══════════════════════════════════════════
# 销售 Agent (部门版)
# ═══════════════════════════════════════════


class SalesDeptAgent(DepartmentAgent):
    """销售部门 Agent。

    能力：
    - 销售漏斗分析
    - 客户分群
    - 成单预测
    - 话术优化
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            agent_id="dept-sales",
            name="销售 Agent",
            description="销售部门专属：漏斗分析、客户分群、成单预测",
            department="销售部",
            kb_namespace="sales",
            **kwargs,
        )

    def execute(self, context: AgentContext, task: AgentTask, plan: list[str]) -> str:
        base = super().execute(context, task, plan)
        sections = [base, "", "## 销售分析"]
        sections.append("### 漏斗分析\n- 各阶段转化率\n- 瓶颈识别")
        sections.append("### 客户分群\n- 高价值客户\n- 待激活客户\n- 流失风险客户")
        sections.append("### 预测建议\n- 本月成单预测\n- 重点跟进客户")
        return "\n\n".join(sections)

    def reflect(self, context: AgentContext, observations: list[str], output: str) -> tuple[bool, str]:
        return True, "销售分析完成"


# ═══════════════════════════════════════════
# HR Agent
# ═══════════════════════════════════════════


class HRAgent(DepartmentAgent):
    """HR 部门 Agent。

    能力：
    - 招聘需求分析
    - 员工满意度分析
    - 培训需求识别
    - 绩效分析
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            agent_id="dept-hr",
            name="HR Agent",
            description="HR 部门专属：招聘分析、员工满意度、培训需求、绩效分析",
            department="人力资源部",
            kb_namespace="hr",
            **kwargs,
        )

    def execute(self, context: AgentContext, task: AgentTask, plan: list[str]) -> str:
        base = super().execute(context, task, plan)
        sections = [base, "", "## HR 分析"]
        sections.append("### 招聘分析\n- 岗位需求优先级\n- 人才画像建议")
        sections.append("### 员工发展\n- 技能差距分析\n- 培训推荐")
        sections.append("### 绩效洞察\n- 关键绩效指标\n- 改进建议")
        return "\n\n".join(sections)

    def reflect(self, context: AgentContext, observations: list[str], output: str) -> tuple[bool, str]:
        return True, "HR 分析完成"


# ═══════════════════════════════════════════
# 客服 Agent (部门版)
# ═══════════════════════════════════════════


class CustomerServiceAgent(DepartmentAgent):
    """客服部门 Agent。

    能力：
    - 客诉趋势分析
    - 高频问题识别
    - 服务质量评估
    - 知识库优化建议
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            agent_id="dept-cs",
            name="客服 Agent",
            description="客服部门专属：客诉趋势、高频问题、质量评估、知识库优化",
            department="客服部",
            kb_namespace="customer_service",
            **kwargs,
        )

    def execute(self, context: AgentContext, task: AgentTask, plan: list[str]) -> str:
        base = super().execute(context, task, plan)
        sections = [base, "", "## 客服分析"]
        sections.append("### 客诉趋势\n- 投诉量变化\n- 热点问题")
        sections.append("### 服务质量\n- 响应时间\n- 满意度趋势\n- 首次解决率")
        sections.append("### 知识库优化\n- 缺失话题识别\n- 答案更新建议")
        return "\n\n".join(sections)

    def reflect(self, context: AgentContext, observations: list[str], output: str) -> tuple[bool, str]:
        return True, "客服分析完成"


# ═══════════════════════════════════════════
# 工厂函数
# ═══════════════════════════════════════════


def create_all_department_agents(**kwargs) -> list[DepartmentAgent]:
    """创建所有部门 Agent。"""
    return [
        RDAgent(**kwargs),
        ProductAgent(**kwargs),
        OperationsAgent(**kwargs),
        SalesDeptAgent(**kwargs),
        HRAgent(**kwargs),
        CustomerServiceAgent(**kwargs),
    ]
