"""Agent Runtime Tenant + Permission Context 测试。"""
import pytest

from src.agents.runtime import (
    Agent,
    AgentContext,
    AgentResult,
    AgentStatus,
    AgentTask,
    BaseAgent,
    PermissionChecker,
    MemoryResult,
)
from src.agents.registry import AgentRegistry


# ═══════════════════════════════════════════
# Fake providers
# ═══════════════════════════════════════════


class FakeMemory:
    def search(self, query, top_k=5):
        return [MemoryResult(memory_id="m1", content=f"Result for: {query}", score=0.9)]
    def remember(self, content, metadata=None):
        return "mem-1"


class FakeKG:
    def query_entities(self, query, top_k=10):
        return []
    def query_relations(self, entity_id):
        return []
    def traverse(self, start_id, depth=2):
        return {"entities": [], "relations": []}


class AllowAllPermissionChecker:
    """开发模式：全部放行。"""
    def check(self, user_id, tenant_id, resource, action):
        return True


class DenyAllPermissionChecker:
    """安全测试：全部拒绝。"""
    def check(self, user_id, tenant_id, resource, action):
        return False


class RoleBasedPermissionChecker:
    """模拟 RBAC 权限检查。"""
    def __init__(self, allowed_roles=None):
        self._allowed = allowed_roles or ["admin", "agent_user"]

    def check(self, user_id, tenant_id, resource, action):
        # 模拟: 检查 user_roles
        return True  # 简化实现


class EchoAgent(BaseAgent):
    """简单 Echo Agent — PEOR 完整实现。"""
    def __init__(self, **kwargs):
        super().__init__(agent_id="echo-1", name="Echo Agent", description="Echo test agent", **kwargs)

    def plan(self, context, task):
        return ["读取输入", "返回 Echo"]

    def execute(self, context, task, plan):
        return f"Echo: {task.input_data.get('message', task.description)}"

    def observe(self, context, output):
        return [f"输出长度: {len(output)}"]

    def reflect(self, context, observations, output):
        return True, "完成"


# ═══════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════


class TestAgentContextTenant:
    """AgentContext 租户/用户上下文测试。"""

    def test_context_has_tenant_fields(self):
        ctx = AgentContext(agent_id="a1", agent_name="test")
        assert ctx.tenant_id == ""
        assert ctx.user_id == ""
        assert ctx.workspace_id == ""
        assert ctx.user_roles == []
        assert ctx.permission_checker is None

    def test_context_with_tenant_and_user(self):
        ctx = AgentContext(
            agent_id="a1",
            agent_name="test",
            tenant_id="tenant-42",
            user_id="user-7",
            workspace_id="ws-1",
            user_roles=["admin", "agent_user"],
            permission_checker=AllowAllPermissionChecker(),
        )
        assert ctx.tenant_id == "tenant-42"
        assert ctx.user_id == "user-7"
        assert ctx.workspace_id == "ws-1"
        assert "admin" in ctx.user_roles

    def test_check_permission_no_checker_allows(self):
        ctx = AgentContext(agent_id="a1", agent_name="test")
        result = ctx.check_permission("agent:echo", "execute")
        assert result is True  # 无检查器时默认放行

    def test_check_permission_with_checker_allows(self):
        ctx = AgentContext(
            agent_id="a1",
            agent_name="test",
            permission_checker=AllowAllPermissionChecker(),
        )
        result = ctx.check_permission("agent:echo", "execute")
        assert result is True

    def test_check_permission_with_checker_denies(self):
        ctx = AgentContext(
            agent_id="a1",
            agent_name="test",
            permission_checker=DenyAllPermissionChecker(),
        )
        result = ctx.check_permission("agent:echo", "execute")
        assert result is False

    def test_record_metric_and_add_to_history(self):
        ctx = AgentContext(agent_id="a1", agent_name="test")
        ctx.record_metric("test_key", 42)
        ctx.add_to_history("user", "hello")
        assert ctx.metrics["test_key"] == 42
        assert len(ctx.conversation_history) == 1
        assert ctx.conversation_history[0]["role"] == "user"


class TestAgentWithTenantContext:
    """Agent.run() 传递租户上下文测试。"""

    def test_run_passes_tenant_context(self):
        agent = EchoAgent(memory=FakeMemory())
        task = AgentTask(title="Test", description="test task", input_data={"message": "hello"})
        result = agent.run(
            task,
            tenant_id="tenant-99",
            user_id="user-1",
            workspace_id="ws-1",
            user_roles=["agent_user"],
        )
        assert result.success
        assert "Echo: hello" in result.output


class TestRegistryPermissionEnforcement:
    """Registry 权限强制执行测试。"""

    def test_registry_run_with_allow_permission(self):
        registry = AgentRegistry()
        registry.set_providers(memory=FakeMemory(), kg=FakeKG())
        registry.register(EchoAgent(memory=FakeMemory()))

        task = AgentTask(title="Test", description="test")
        result = registry.run(
            "echo-1", task,
            tenant_id="t1", user_id="u1",
            permission_checker=AllowAllPermissionChecker(),
        )
        assert result is not None
        assert result.success

    def test_registry_run_with_deny_permission(self):
        registry = AgentRegistry()
        registry.set_providers(memory=FakeMemory(), kg=FakeKG())
        registry.register(EchoAgent(memory=FakeMemory()))

        task = AgentTask(title="Test", description="test")
        result = registry.run(
            "echo-1", task,
            tenant_id="t1", user_id="u1",
            permission_checker=DenyAllPermissionChecker(),
        )
        assert result is not None
        assert result.success is False
        assert "权限不足" in result.error

    def test_registry_run_no_permission_checker_allows(self):
        """无 permission_checker 时应该放行（开发模式）。"""
        registry = AgentRegistry()
        registry.set_providers(memory=FakeMemory(), kg=FakeKG())
        registry.register(EchoAgent(memory=FakeMemory()))

        task = AgentTask(title="Test", description="test")
        result = registry.run("echo-1", task)
        assert result is not None
        assert result.success


class TestPermissionCheckerProtocol:
    """PermissionChecker 协议实现测试。"""

    def test_allow_all_checker(self):
        checker = AllowAllPermissionChecker()
        assert checker.check("u1", "t1", "agent:echo", "execute") is True

    def test_deny_all_checker(self):
        checker = DenyAllPermissionChecker()
        assert checker.check("u1", "t1", "agent:echo", "execute") is False
