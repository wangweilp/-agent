"""Agent Registry 单元测试。"""

import pytest

from src.agents.registry import AgentRegistry, AgentRegistration
from src.agents.runtime import Agent, AgentTask, TaskPriority
from src.agents.builtin.knowledge_agent import KnowledgeAgent
from src.agents.builtin.meeting_agent import MeetingAgent
from src.agents.builtin.research_agent import ResearchAgent
from src.agents.builtin.sales_agent import SalesAgent
from src.agents.builtin.support_agent import SupportAgent
from src.agents.builtin.training_agent import TrainingAgent
from src.agents.department import (
    RDAgent, ProductAgent, OperationsAgent,
    SalesDeptAgent, HRAgent, CustomerServiceAgent,
)
from tests.test_agents.test_runtime import FakeMemoryProvider, FakeKGProvider


@pytest.fixture
def registry():
    reg = AgentRegistry()
    reg.set_providers(
        memory=FakeMemoryProvider(),
        kg=FakeKGProvider(),
    )
    return reg


@pytest.fixture
def registered_registry(registry):
    """预注册了 6 个内置 Agent 的注册中心。"""
    for agent_cls in [
        KnowledgeAgent, MeetingAgent, ResearchAgent,
        SalesAgent, SupportAgent, TrainingAgent,
    ]:
        registry.register(agent_cls(
            memory=FakeMemoryProvider(),
            knowledge_graph=FakeKGProvider(),
        ))
    return registry


# ═══════════════════════════════════════════
# 注册/注销
# ═══════════════════════════════════════════


class TestRegistration:
    def test_register_single_agent(self, registry):
        agent = KnowledgeAgent(memory=FakeMemoryProvider(), knowledge_graph=FakeKGProvider())
        registry.register(agent)
        assert "builtin-knowledge" in registry
        assert registry.get("builtin-knowledge") is agent
        assert len(registry) == 1

    def test_register_duplicate_no_error(self, registry):
        agent = KnowledgeAgent(memory=FakeMemoryProvider(), knowledge_graph=FakeKGProvider())
        registry.register(agent)
        registry.register(agent)  # 不报错，只警告
        assert len(registry) == 1

    def test_unregister(self, registry):
        agent = KnowledgeAgent(memory=FakeMemoryProvider(), knowledge_graph=FakeKGProvider())
        registry.register(agent)
        assert registry.unregister("builtin-knowledge") is True
        assert "builtin-knowledge" not in registry
        assert len(registry) == 0

    def test_unregister_nonexistent(self, registry):
        assert registry.unregister("nonexistent") is False

    def test_register_with_config(self, registry):
        agent = KnowledgeAgent()
        registry.register(agent, config={"top_k": 10})
        cfg = registry.get_config("builtin-knowledge")
        assert cfg == {"top_k": 10}


# ═══════════════════════════════════════════
# 启用/停用
# ═══════════════════════════════════════════


class TestEnableDisable:
    def test_disable_and_enable(self, registered_registry):
        assert registered_registry.disable("builtin-knowledge") is True
        reg = registered_registry.get_registration("builtin-knowledge")
        assert reg.enabled is False

        assert registered_registry.enable("builtin-knowledge") is True
        reg = registered_registry.get_registration("builtin-knowledge")
        assert reg.enabled is True

    def test_disable_nonexistent(self, registry):
        assert registry.disable("nonexistent") is False

    def test_disabled_agent_cannot_run(self, registered_registry):
        registered_registry.disable("builtin-knowledge")
        task = AgentTask(title="test", description="test query")
        result = registered_registry.run("builtin-knowledge", task)
        assert result is None


# ═══════════════════════════════════════════
# 执行
# ═══════════════════════════════════════════


class TestRun:
    def test_run_knowledge_agent(self, registered_registry):
        task = AgentTask(
            title="搜索测试",
            description="人工智能",
            input_data={"action": "search", "query": "AI", "top_k": 3},
        )
        result = registered_registry.run("builtin-knowledge", task)
        assert result is not None
        assert result.success
        assert "记忆检索结果" in result.output or "Knowledge" in result.output

    def test_run_meeting_agent(self, registered_registry):
        task = AgentTask(
            title="会议记录处理",
            description="测试会议内容",
            input_data={
                "stage": "after",
                "transcript": "我们决定本周五发布。张三负责跟进技术问题。",
            },
        )
        result = registered_registry.run("builtin-meeting", task)
        assert result is not None
        assert result.success

    def test_run_research_agent(self, registered_registry):
        task = AgentTask(
            title="研究AI趋势",
            description="人工智能发展趋势",
            input_data={"topic": "AI trends", "depth": "standard"},
        )
        result = registered_registry.run("builtin-research", task)
        assert result is not None
        assert result.success

    def test_run_sales_agent(self, registered_registry):
        task = AgentTask(
            title="客户分析",
            description="某大型企业客户",
            input_data={"action": "analyze", "customer": "ABC Corp"},
        )
        result = registered_registry.run("builtin-sales", task)
        assert result is not None
        assert result.success

    def test_run_support_agent(self, registered_registry):
        task = AgentTask(
            title="客户问题",
            description="系统无法登录",
            input_data={"issue": "登录时提示错误500"},
        )
        result = registered_registry.run("builtin-support", task)
        assert result is not None
        assert result.success

    def test_run_training_agent(self, registered_registry):
        task = AgentTask(
            title="培训生成",
            description="Python入门",
            input_data={"action": "generate", "topic": "Python编程"},
        )
        result = registered_registry.run("builtin-training", task)
        assert result is not None
        assert result.success

    def test_run_nonexistent_agent(self, registry):
        task = AgentTask(title="test")
        result = registry.run("nonexistent", task)
        assert result is None

    def test_run_updates_usage_stats(self, registered_registry):
        task = AgentTask(title="test")
        registered_registry.run("builtin-knowledge", task)
        reg = registered_registry.get_registration("builtin-knowledge")
        assert reg.usage_count == 1
        assert reg.success_count == 1
        assert reg.success_rate == 1.0

    def test_run_failed_updates_stats(self, registered_registry):
        # 注册一个会失败的 agent
        from tests.test_agents.test_runtime import FailingAgent
        failing = FailingAgent(memory=FakeMemoryProvider())
        registered_registry.register(failing)
        task = AgentTask(title="test")
        result = registered_registry.run("test-failing", task)
        assert result is not None
        assert not result.success
        reg = registered_registry.get_registration("test-failing")
        assert reg.usage_count == 1
        assert reg.success_count == 0


# ═══════════════════════════════════════════
# 查询
# ═══════════════════════════════════════════


class TestQuery:
    def test_list_all(self, registered_registry):
        agents = registered_registry.list_all()
        assert len(agents) == 6

    def test_list_enabled(self, registered_registry):
        registered_registry.disable("builtin-knowledge")
        enabled = registered_registry.list_enabled()
        assert len(enabled) == 5
        assert all(r.enabled for r in enabled)

    def test_list_by_tag(self, registered_registry):
        # 给 knowledge agent 加 tag
        registered_registry.update_config("builtin-knowledge", {})
        reg = registered_registry.get_registration("builtin-knowledge")
        reg.tags = ["knowledge", "core"]
        result = registered_registry.list_by_tag("knowledge")
        assert len(result) == 1

    def test_list_by_name(self, registered_registry):
        result = registered_registry.list_by_name("Knowledge")
        assert len(result) == 1

    def test_get_registration(self, registered_registry):
        reg = registered_registry.get_registration("builtin-knowledge")
        assert reg is not None
        assert reg.name == "Knowledge Agent"

    def test_get_nonexistent(self, registry):
        assert registry.get("no-such-agent") is None
        assert registry.get_registration("no-such-agent") is None


# ═══════════════════════════════════════════
# 配置管理
# ═══════════════════════════════════════════


class TestConfig:
    def test_update_config(self, registered_registry):
        registered_registry.update_config("builtin-knowledge", {"max_results": 20})
        cfg = registered_registry.get_config("builtin-knowledge")
        assert cfg["max_results"] == 20

    def test_update_config_nonexistent(self, registry):
        assert registry.update_config("nope", {"a": 1}) is False

    def test_get_config_nonexistent(self, registry):
        assert registry.get_config("nope") is None


# ═══════════════════════════════════════════
# 版本管理
# ═══════════════════════════════════════════


class TestVersioning:
    def test_upgrade_version(self, registered_registry):
        new_agent = KnowledgeAgent(
            memory=FakeMemoryProvider(),
            knowledge_graph=FakeKGProvider(),
        )
        new_agent.version = "2.0.0"
        assert registered_registry.upgrade("builtin-knowledge", new_agent) is True
        reg = registered_registry.get_registration("builtin-knowledge")
        assert reg.version == "2.0.0"

    def test_upgrade_nonexistent(self, registry):
        agent = KnowledgeAgent()
        assert registry.upgrade("nonexistent", agent) is False


# ═══════════════════════════════════════════
# 统计
# ═══════════════════════════════════════════


class TestStats:
    def test_get_stats(self, registered_registry):
        stats = registered_registry.get_stats()
        assert stats["total_agents"] == 6
        assert stats["enabled_agents"] == 6
        assert stats["disabled_agents"] == 0
        assert "agents" in stats

    def test_get_stats_with_disabled(self, registered_registry):
        registered_registry.disable("builtin-knowledge")
        stats = registered_registry.get_stats()
        assert stats["enabled_agents"] == 5
        assert stats["disabled_agents"] == 1


# ═══════════════════════════════════════════
# AgentRegistration 测试
# ═══════════════════════════════════════════


class TestAgentRegistration:
    def test_to_dict(self):
        reg = AgentRegistration(
            agent_id="test",
            name="Test Agent",
            description="desc",
        )
        d = reg.to_dict()
        assert d["agent_id"] == "test"
        assert d["success_rate"] == 1.0

    def test_record_usage_success(self):
        from src.agents.runtime import AgentResult
        reg = AgentRegistration(agent_id="test", name="Test", description="test")
        result = AgentResult(task_id="t1", agent_id="test", agent_name="Test", success=True, duration_ms=100)
        reg.record_usage(result)
        assert reg.usage_count == 1
        assert reg.success_count == 1
        assert reg.avg_duration_ms == 100

    def test_record_usage_ema(self):
        from src.agents.runtime import AgentResult
        reg = AgentRegistration(agent_id="test", name="Test", description="test")
        reg.record_usage(AgentResult(task_id="t1", agent_id="test", agent_name="Test", success=True, duration_ms=100))
        reg.record_usage(AgentResult(task_id="t2", agent_id="test", agent_name="Test", success=True, duration_ms=200))
        # EMA: 0.1*200 + 0.9*100 = 110
        assert 105 < reg.avg_duration_ms < 115


# ═══════════════════════════════════════════
# 6 个内置 Agent 基础验证
# ═══════════════════════════════════════════


class TestBuiltinAgents:
    def test_knowledge_agent_creation(self):
        a = KnowledgeAgent()
        assert a.agent_id == "builtin-knowledge"
        assert a.name == "Knowledge Agent"
        assert a.version == "1.0.0"

    def test_knowledge_agent_ingest(self):
        a = KnowledgeAgent(memory=FakeMemoryProvider(), knowledge_graph=FakeKGProvider())
        task = AgentTask(title="入库", description="test", input_data={"action": "ingest", "content": "重要知识点"})
        result = a.run(task)
        assert result.success

    def test_knowledge_agent_organize(self):
        a = KnowledgeAgent(memory=FakeMemoryProvider(), knowledge_graph=FakeKGProvider())
        task = AgentTask(title="整理", description="test", input_data={"action": "organize", "query": "AI"})
        result = a.run(task)
        assert result.success

    def test_knowledge_agent_no_memory(self):
        a = KnowledgeAgent()
        task = AgentTask(title="搜索", description="AI")
        result = a.run(task)
        assert result.success

    def test_meeting_agent_creation(self):
        a = MeetingAgent()
        assert a.agent_id == "builtin-meeting"

    def test_meeting_agent_before_stage(self):
        a = MeetingAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="准备会议", description="产品评审", input_data={"stage": "before", "topic": "产品评审"})
        result = a.run(task)
        assert result.success
        assert "会前准备" in result.output

    def test_meeting_agent_full_stage(self):
        a = MeetingAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="完整会议", description="讨论产品发布", input_data={"stage": "full", "transcript": "我们决定下周发布v2.0"})
        result = a.run(task)
        assert result.success

    def test_meeting_agent_no_transcript(self):
        a = MeetingAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="空会议", description="", input_data={"stage": "after"})
        result = a.run(task)
        assert result.success
        assert "无会议记录输入" in result.output

    def test_meeting_extract_key_points(self):
        points = MeetingAgent._extract_key_points("我们决定采用方案A。确认下周开始。这个问题需要跟进。")
        assert len(points) >= 1

    def test_meeting_extract_action_items(self):
        actions = MeetingAgent._extract_action_items("张三负责前端。TODO: 更新文档。@李四 跟进测试。")
        assert len(actions) >= 1

    def test_research_agent_creation(self):
        a = ResearchAgent()
        assert a.agent_id == "builtin-research"

    def test_research_agent_deep_mode(self):
        a = ResearchAgent(memory=FakeMemoryProvider(), knowledge_graph=FakeKGProvider())
        task = AgentTask(title="深度研究", description="AI趋势", input_data={"topic": "AI", "depth": "deep"})
        result = a.run(task)
        assert result.success
        assert "交叉验证" in result.output

    def test_research_agent_no_providers(self):
        a = ResearchAgent()
        task = AgentTask(title="研究", description="AI")
        result = a.run(task)
        assert result.success

    def test_sales_agent_creation(self):
        a = SalesAgent()
        assert a.agent_id == "builtin-sales"

    def test_sales_agent_script_action(self):
        a = SalesAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="话术", description="客户ABC", input_data={"action": "script", "customer": "ABC Corp"})
        result = a.run(task)
        assert result.success
        assert "话术" in result.output

    def test_sales_agent_competitor_action(self):
        a = SalesAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="竞品", description="竞品分析", input_data={"action": "competitor", "customer": "某客户"})
        result = a.run(task)
        assert result.success

    def test_sales_agent_no_memory(self):
        a = SalesAgent()
        task = AgentTask(title="分析", description="客户X")
        result = a.run(task)
        assert result.success

    def test_support_agent_creation(self):
        a = SupportAgent()
        assert a.agent_id == "builtin-support"

    def test_support_bug_issue(self):
        a = SupportAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="Bug", description="系统崩溃了", input_data={"issue": "应用启动时报错，无法正常使用"})
        result = a.run(task)
        assert result.success

    def test_support_complaint_issue(self):
        a = SupportAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="投诉", description="不满意", input_data={"issue": "我要投诉退款，服务质量太差"})
        result = a.run(task)
        assert result.success
        assert "升级" in result.output

    def test_support_suggestion_issue(self):
        a = SupportAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="建议", description="建议改进", input_data={"issue": "希望能增加导出功能"})
        result = a.run(task)
        assert result.success

    def test_support_legal_escalation(self):
        assert SupportAgent._needs_escalation("涉及隐私数据泄露", "投诉处理") != ""

    def test_support_long_issue_escalation(self):
        long_issue = "x" * 600
        assert SupportAgent._needs_escalation(long_issue, "技术故障") != ""

    def test_support_classify_question(self):
        assert "咨询" in SupportAgent._classify_issue("怎么使用这个功能")

    def test_support_classify_suggestion(self):
        assert "建议" in SupportAgent._classify_issue("希望能改进界面")

    def test_training_agent_creation(self):
        a = TrainingAgent()
        assert a.agent_id == "builtin-training"

    def test_training_assess_action(self):
        a = TrainingAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="评估", description="Python", input_data={"action": "assess", "topic": "Python", "learner": "张三"})
        result = a.run(task)
        assert result.success
        assert "评估" in result.output

    def test_training_path_action(self):
        a = TrainingAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="学习路径", description="Python", input_data={"action": "path", "topic": "Python"})
        result = a.run(task)
        assert result.success
        assert "学习路径" in result.output

    def test_training_no_providers(self):
        a = TrainingAgent()
        task = AgentTask(title="培训", description="Python")
        result = a.run(task)
        assert result.success

    def test_training_empty_topic(self):
        a = TrainingAgent()
        task = AgentTask(title="空", description="")
        result = a.run(task)
        # 即使 topic 为空，agent 也会生成基本框架
        assert result.success

    def test_all_agents_extend_base_agent(self):
        for cls in [KnowledgeAgent, MeetingAgent, ResearchAgent, SalesAgent, SupportAgent, TrainingAgent]:
            a = cls()
            assert isinstance(a, Agent)

    def test_all_agents_implement_peor(self):
        """每个 built-in agent 都应该能成功 run。"""
        for cls in [KnowledgeAgent, MeetingAgent, ResearchAgent, SalesAgent, SupportAgent, TrainingAgent]:
            a = cls(memory=FakeMemoryProvider(), knowledge_graph=FakeKGProvider())
            task = AgentTask(title="smoke test", description="test")
            result = a.run(task)
            assert result.success, f"{cls.__name__} 执行失败: {result.error}"
            assert result.duration_ms >= 0
            assert len(result.plan) > 0


# ═══════════════════════════════════════════
# Department Agents 基础验证
# ═══════════════════════════════════════════


class TestDepartmentAgents:
    @pytest.mark.parametrize("cls,expected_id,expected_dept", [
        (RDAgent, "dept-rd", "研发部"),
        (ProductAgent, "dept-product", "产品部"),
        (OperationsAgent, "dept-operations", "运营部"),
        (SalesDeptAgent, "dept-sales", "销售部"),
        (HRAgent, "dept-hr", "人力资源部"),
        (CustomerServiceAgent, "dept-cs", "客服部"),
    ])
    def test_department_agent_creation(self, cls, expected_id, expected_dept):
        a = cls(memory=FakeMemoryProvider(), knowledge_graph=FakeKGProvider())
        assert a.agent_id == expected_id
        assert a.department == expected_dept

    def test_all_department_agents_run(self):
        for cls in [RDAgent, ProductAgent, OperationsAgent, SalesDeptAgent, HRAgent, CustomerServiceAgent]:
            a = cls(memory=FakeMemoryProvider(), knowledge_graph=FakeKGProvider())
            task = AgentTask(
                title=f"{a.department}测试",
                description="分析部门情况",
                input_data={"action": "evaluate", "query": "test"},
            )
            result = a.run(task)
            assert result.success, f"{cls.__name__} 执行失败: {result.error}"

    def test_department_kb_namespace(self):
        a = RDAgent()
        assert a.department_kb_namespace == "rd/engineering"
        b = HRAgent()
        assert b.department_kb_namespace == "hr"

    def test_rd_agent_review_action(self):
        a = RDAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="代码审查", description="审查代码", input_data={"action": "review"})
        result = a.run(task)
        assert result.success

    def test_rd_agent_debt_action(self):
        a = RDAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="技术债务", description="分析", input_data={"action": "debt"})
        result = a.run(task)
        assert result.success

    def test_product_agent_run(self):
        a = ProductAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="需求", description="新需求")
        result = a.run(task)
        assert result.success

    def test_operations_agent_run(self):
        a = OperationsAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="运营", description="数据分析")
        result = a.run(task)
        assert result.success

    def test_sales_dept_agent_run(self):
        a = SalesDeptAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="销售分析", description="漏斗")
        result = a.run(task)
        assert result.success

    def test_hr_agent_run(self):
        a = HRAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="HR", description="招聘")
        result = a.run(task)
        assert result.success

    def test_cs_agent_run(self):
        a = CustomerServiceAgent(memory=FakeMemoryProvider())
        task = AgentTask(title="客服", description="客诉")
        result = a.run(task)
        assert result.success

    def test_department_agent_no_providers(self):
        a = RDAgent()
        task = AgentTask(title="test", description="分析")
        result = a.run(task)
        assert result.success
