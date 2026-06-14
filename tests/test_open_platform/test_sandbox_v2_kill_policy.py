"""Test Step 7 — Kill Policy 测试。"""
import pytest
from src.open_platform.sandbox_v2.models import (
    SandboxKillRequest, SandboxV2KillTargetType, SandboxV2KillAction,
)
from src.open_platform.sandbox_v2.kill_policy import evaluate_kill_policy


class TestKillPolicyDefaultDeny:
    def test_unknown_target_rejected(self):
        d = evaluate_kill_policy(SandboxKillRequest(target_type="unknown"))
        assert d.allowed is False

    def test_missing_target_rejected(self):
        d = evaluate_kill_policy(SandboxKillRequest(target_type=SandboxV2KillTargetType.JOB, target_id="missing"), target_exists=False)
        assert d.allowed is False

    def test_not_sandbox_owned_rejected(self):
        d = evaluate_kill_policy(SandboxKillRequest(target_type=SandboxV2KillTargetType.JOB), target_exists=True, target_is_owned_by_sandbox=False)
        assert d.allowed is False
        assert "not_sandbox_owned" in d.matched_rules

    def test_exception_fail_closed(self):
        d = evaluate_kill_policy(None)  # type: ignore
        assert d.allowed is False
        assert d.fail_closed is True


class TestTerminalStates:
    def test_completed_returns_no_active(self):
        d = evaluate_kill_policy(SandboxKillRequest(target_type=SandboxV2KillTargetType.JOB), target_exists=True, target_status="completed")
        assert d.action == SandboxV2KillAction.NO_ACTIVE_EXECUTION

    def test_failed_returns_no_active(self):
        d = evaluate_kill_policy(SandboxKillRequest(target_type=SandboxV2KillTargetType.JOB), target_exists=True, target_status="failed")
        assert d.action == SandboxV2KillAction.NO_ACTIVE_EXECUTION


class TestActiveStates:
    def test_queued_allows_cancel_queue(self):
        d = evaluate_kill_policy(SandboxKillRequest(target_type=SandboxV2KillTargetType.JOB), target_exists=True, target_status="queued")
        assert d.action == SandboxV2KillAction.CANCEL_QUEUE_ITEM
        assert d.queue_cancel_allowed is True

    def test_running_simulation_allows_mark_canceled(self):
        d = evaluate_kill_policy(SandboxKillRequest(target_type=SandboxV2KillTargetType.JOB), target_exists=True, target_status="running_simulation")
        assert d.action == SandboxV2KillAction.MARK_CANCELED
        assert d.job_state_cancel_allowed is True


class TestContainerKill:
    def test_windows_container_kill_unsupported(self):
        d = evaluate_kill_policy(SandboxKillRequest(target_type=SandboxV2KillTargetType.CONTAINER), target_exists=True, target_status="running",
                                 container_execution_enabled=True, container_id_recorded=True)
        # Windows → should be rejected (if not Linux)
        import platform
        if platform.system() != "Linux":
            assert d.allowed is False

    def test_container_kill_not_enabled(self):
        d = evaluate_kill_policy(SandboxKillRequest(target_type=SandboxV2KillTargetType.CONTAINER), target_exists=True, target_status="running",
                                 container_execution_enabled=False, container_id_recorded=True)
        assert d.allowed is False

    def test_container_kill_no_container_id(self):
        d = evaluate_kill_policy(SandboxKillRequest(target_type=SandboxV2KillTargetType.CONTAINER), target_exists=True, target_status="running",
                                 container_execution_enabled=True, container_id_recorded=False)
        assert d.allowed is False
