"""Submission Store 单元测试 — AgentManifest + AgentSubmission + AgentReviewRecord。

覆盖:
- Manifest 校验 (valid/invalid/empty/bad format)
- SecurityProfile 校验 (no_execution accepted, code execution blocked MVP)
- Submission 状态机 (draft→submit→review→approve→publish 完整通路)
- 状态机禁止流转 (draft→publish, rejected→publish 等)
- Review Records 保存和查询
- Store 开发者隔离 + tenant 隔离
- serialization roundtrip
"""

import json
import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.submission_store import SQLiteSubmissionStore
from src.open_platform.submission import (
    AgentManifest,
    AgentReviewRecord,
    AgentSubmission,
    ManifestValidationError,
    ManifestValidationResult,
    ReviewDecision,
    SecurityProfile,
    SubmissionNotFoundError,
    SubmissionPermissionError,
    SubmissionStateError,
    SubmissionStatus,
)


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════

@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def store(settings):
    return SQLiteSubmissionStore(settings, db_path=":memory:")


def _valid_manifest(name: str = "my-agent", **overrides) -> AgentManifest:
    """创建有效的 manifest 用于测试。"""
    kwargs = {
        "name": name,
        "display_name": "My Agent",
        "description": "A test agent",
        "version": "1.0.0",
        "capabilities": ["test"],
        "required_permissions": ["agent:execute"],
        "runtime_type": "manifest_only",
        "security_profile": SecurityProfile(
            requires_network=False,
            reads_user_data=False,
            writes_user_data=False,
            sandbox_level="no_execution",
        ),
    }
    kwargs.update(overrides)
    return AgentManifest(**kwargs)


def _create_draft_submission(store, developer_id="dev_001", tenant_id="tenant-a", **overrides) -> AgentSubmission:
    manifest = _valid_manifest()
    kwargs = {
        "developer_id": developer_id,
        "tenant_id": tenant_id,
        "agent_manifest": manifest,
        "source_type": "manifest",
        "status": SubmissionStatus.DRAFT,
    }
    kwargs.update(overrides)
    sub = AgentSubmission(**kwargs)
    return store.create_submission(sub)


# ═══════════════════════════════════════════
# Manifest Validation
# ═══════════════════════════════════════════


class TestManifestValidation:
    def test_valid_manifest_passes(self):
        m = _valid_manifest()
        result = m.validate()
        assert result.valid is True
        assert len(result.errors) == 0

    def test_missing_name_fails(self):
        m = _valid_manifest(name="")
        result = m.validate()
        assert result.valid is False
        assert any("name" in e for e in result.errors)

    def test_invalid_name_format_fails(self):
        m = _valid_manifest(name="Bad Name!")
        result = m.validate()
        assert result.valid is False
        assert any("name" in e for e in result.errors)

    def test_name_with_hyphens_ok(self):
        m = _valid_manifest(name="my-agent-v2")
        result = m.validate()
        assert result.valid is True

    def test_name_with_underscores_ok(self):
        m = _valid_manifest(name="my_agent_v3")
        result = m.validate()
        assert result.valid is True

    def test_missing_display_name_fails(self):
        m = _valid_manifest(display_name="")
        result = m.validate()
        assert result.valid is False
        assert any("display_name" in e for e in result.errors)

    def test_missing_description_fails(self):
        m = _valid_manifest(description="")
        result = m.validate()
        assert result.valid is False

    def test_missing_version_fails(self):
        m = _valid_manifest(version="")
        result = m.validate()
        assert result.valid is False

    def test_non_semver_version_warns(self):
        m = _valid_manifest(version="v1")
        result = m.validate()
        assert result.valid is True  # non-semver 只 warn 不 error
        assert len(result.warnings) >= 1

    def test_semver_version_ok(self):
        m = _valid_manifest(version="2.1.3-beta.1+build.42")
        result = m.validate()
        assert result.valid is True

    def test_empty_capabilities_fails(self):
        m = _valid_manifest(capabilities=[])
        result = m.validate()
        assert result.valid is False

    def test_empty_required_permissions_fails(self):
        m = _valid_manifest(required_permissions=[])
        result = m.validate()
        assert result.valid is False

    def test_missing_security_profile_fails(self):
        m = _valid_manifest(security_profile=None)
        result = m.validate()
        assert result.valid is False

    def test_unsupported_runtime_type_rejected(self):
        m = _valid_manifest(runtime_type="external")
        result = m.validate()
        assert result.valid is False
        assert any("runtime_type" in e for e in result.errors)

    def test_config_schema_must_be_dict(self):
        m = _valid_manifest(config_schema="not_a_dict")  # type: ignore
        result = m.validate()
        assert result.valid is False

    def test_usage_limits_must_be_dict(self):
        m = _valid_manifest(usage_limits="not_a_dict")  # type: ignore
        result = m.validate()
        assert result.valid is False

    def test_metadata_must_be_dict(self):
        m = _valid_manifest(metadata="not_a_dict")  # type: ignore
        result = m.validate()
        assert result.valid is False


class TestSecurityProfileValidation:
    def test_no_execution_accepted(self):
        sp = SecurityProfile(sandbox_level="no_execution")
        result = sp.validate()
        assert result.valid is True

    def test_restricted_has_warning(self):
        sp = SecurityProfile(sandbox_level="restricted")
        result = sp.validate()
        assert result.valid is True  # 只 warn
        assert any("MVP" in w for w in result.warnings)

    def test_to_dict_roundtrip(self):
        sp = SecurityProfile(
            requires_network=True,
            reads_user_data=True,
            writes_user_data=False,
            sandbox_level="no_execution",
            allowed_domains=["example.com"],
            data_access_scope=["tenant_data"],
            risk_notes="Low risk",
        )
        d = sp.to_dict()
        restored = SecurityProfile.from_dict(d)
        assert restored.requires_network is True
        assert restored.reads_user_data is True
        assert restored.writes_user_data is False
        assert restored.allowed_domains == ["example.com"]
        assert restored.risk_notes == "Low risk"


# ═══════════════════════════════════════════
# Manifest Serialization
# ═══════════════════════════════════════════


class TestManifestSerialization:
    def test_manifest_to_from_dict_roundtrip(self):
        m = _valid_manifest(
            name="roundtrip-agent",
            config_schema={"max": {"type": "integer"}},
            usage_limits={"max_calls": 100},
            metadata={"env": "prod"},
        )
        d = m.to_dict()
        restored = AgentManifest.from_dict(d)
        assert restored.name == m.name
        assert restored.config_schema == m.config_schema
        assert restored.usage_limits == m.usage_limits
        assert restored.metadata == m.metadata
        assert restored.security_profile is not None

    def test_from_dict_with_none_security_profile(self):
        d = _valid_manifest().to_dict()
        d["security_profile"] = None
        restored = AgentManifest.from_dict(d)
        assert restored.security_profile is None


# ═══════════════════════════════════════════
# Submission State Machine
# ═══════════════════════════════════════════


class TestSubmissionStateMachine:
    def test_create_draft(self, store):
        sub = _create_draft_submission(store)
        assert sub.submission_id.startswith("sub_")
        assert sub.status == SubmissionStatus.DRAFT
        assert sub.can_edit() is True
        assert sub.can_submit() is True
        assert sub.can_publish() is False

    def test_draft_can_edit(self, store):
        sub = _create_draft_submission(store)
        new_manifest = _valid_manifest(name="updated-agent", display_name="Updated")
        store.update_submission_manifest(sub.submission_id, "dev_001", new_manifest)
        updated = store.get_submission(sub.submission_id)
        assert updated.agent_manifest.name == "updated-agent"

    def test_draft_cannot_edit_by_other_developer(self, store):
        sub = _create_draft_submission(store)
        with pytest.raises(SubmissionPermissionError):
            store.update_submission_manifest(sub.submission_id, "dev_other", _valid_manifest())

    def test_submit_draft(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        updated = store.get_submission(sub.submission_id)
        assert updated.status == SubmissionStatus.SUBMITTED
        assert updated.submitted_at is not None
        assert updated.can_edit() is False

    def test_submit_invalid_manifest_fails(self, store):
        sub = _create_draft_submission(store, agent_manifest=_valid_manifest(capabilities=[]))
        with pytest.raises(ManifestValidationError):
            store.submit_submission(sub.submission_id, "dev_001")

    def test_submitted_cannot_edit_manifest(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        with pytest.raises(SubmissionStateError):
            store.update_submission_manifest(sub.submission_id, "dev_001", _valid_manifest())

    def test_submitted_can_withdraw(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.withdraw_submission(sub.submission_id, "dev_001")
        updated = store.get_submission(sub.submission_id)
        assert updated.status == SubmissionStatus.WITHDRAWN

    def test_submitted_can_start_review(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "reviewer-1")
        updated = store.get_submission(sub.submission_id)
        assert updated.status == SubmissionStatus.IN_REVIEW

    def test_in_review_can_approve(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "reviewer-1")
        store.approve_submission(sub.submission_id, "reviewer-1", "Looks good", {"manifest_valid": True})
        updated = store.get_submission(sub.submission_id)
        assert updated.status == SubmissionStatus.APPROVED
        assert updated.reviewed_by == "reviewer-1"
        assert updated.can_publish() is True

    def test_in_review_can_reject(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "reviewer-1")
        store.reject_submission(sub.submission_id, "reviewer-1", "Not safe", {"manifest_valid": False})
        updated = store.get_submission(sub.submission_id)
        assert updated.status == SubmissionStatus.REJECTED

    def test_in_review_can_request_changes(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "reviewer-1")
        store.request_changes(sub.submission_id, "reviewer-1", "Fix permissions", {"manifest_valid": True})
        updated = store.get_submission(sub.submission_id)
        assert updated.status == SubmissionStatus.REJECTED

    def test_approved_can_publish(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "reviewer-1")
        store.approve_submission(sub.submission_id, "reviewer-1", "OK", {"ok": True})
        store.publish_submission(sub.submission_id, "mkp_dev_001")
        updated = store.get_submission(sub.submission_id)
        assert updated.status == SubmissionStatus.PUBLISHED
        assert updated.marketplace_agent_id == "mkp_dev_001"
        assert updated.published_at is not None

    # ── Forbidden transitions ──

    def test_draft_cannot_publish(self, store):
        sub = _create_draft_submission(store)
        with pytest.raises(SubmissionStateError):
            store.publish_submission(sub.submission_id, "mkp_xxx")

    def test_rejected_cannot_publish(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "reviewer-1")
        store.reject_submission(sub.submission_id, "reviewer-1", "No", {"ok": False})
        with pytest.raises(SubmissionStateError):
            store.publish_submission(sub.submission_id, "mkp_xxx")

    def test_withdrawn_cannot_publish(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.withdraw_submission(sub.submission_id, "dev_001")
        with pytest.raises(SubmissionStateError):
            store.publish_submission(sub.submission_id, "mkp_xxx")

    def test_submitted_cannot_publish(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        with pytest.raises(SubmissionStateError):
            store.publish_submission(sub.submission_id, "mkp_xxx")

    def test_rejected_reopen_to_draft(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "reviewer-1")
        store.reject_submission(sub.submission_id, "reviewer-1", "Fix it", {"ok": False})
        updated = store.get_submission(sub.submission_id)
        updated.reopen_to_draft()
        store.update_submission(updated)
        final = store.get_submission(sub.submission_id)
        assert final.status == SubmissionStatus.DRAFT

    def test_published_cannot_reopen(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "reviewer-1")
        store.approve_submission(sub.submission_id, "reviewer-1", "OK", {"ok": True})
        store.publish_submission(sub.submission_id, "mkp_xxx")
        updated = store.get_submission(sub.submission_id)
        with pytest.raises(SubmissionStateError):
            updated.reopen_to_draft()


# ═══════════════════════════════════════════
# Review Records
# ═══════════════════════════════════════════


class TestReviewRecords:
    def test_approve_creates_review_record(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "reviewer-1")
        store.approve_submission(
            sub.submission_id, "reviewer-1", "Approved",
            {"manifest_valid": True, "permissions_declared": True},
        )
        records = store.list_review_records(sub.submission_id)
        assert len(records) == 1
        assert records[0].decision == ReviewDecision.APPROVE
        assert records[0].reviewer_id == "reviewer-1"

    def test_reject_creates_review_record(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "reviewer-2")
        store.reject_submission(
            sub.submission_id, "reviewer-2", "Bad security",
            {"no_remote_code_execution": False},
        )
        records = store.list_review_records(sub.submission_id)
        assert len(records) == 1
        assert records[0].decision == ReviewDecision.REJECT

    def test_request_changes_creates_review_record(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "reviewer-3")
        store.request_changes(
            sub.submission_id, "reviewer-3", "Need more details",
            {"security_profile_declared": True},
        )
        records = store.list_review_records(sub.submission_id)
        assert len(records) == 1
        assert records[0].decision == ReviewDecision.REQUEST_CHANGES

    def test_multiple_review_records(self, store):
        """同一 submission 可以有多次审核记录（如 reject 后重新提交再审核）。"""
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "r1")
        store.reject_submission(sub.submission_id, "r1", "First reject", {"v": False})

        # reopen_to_draft → 重新提交 → 再次审核
        updated = store.get_submission(sub.submission_id)
        updated.reopen_to_draft()
        store.update_submission(updated)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "r2")
        store.approve_submission(sub.submission_id, "r2", "Second pass", {"v": True})

        records = store.list_review_records(sub.submission_id)
        assert len(records) == 2

    def test_latest_review_record(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "r1")
        store.reject_submission(sub.submission_id, "r1", "reject-notes", {"c": 1})

        import time; time.sleep(0.01)  # ensure distinct timestamps

        updated = store.get_submission(sub.submission_id)
        updated.reopen_to_draft()
        store.update_submission(updated)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "r2")
        store.approve_submission(sub.submission_id, "r2", "approve-notes", {"c": 2})

        # 审核记录按时间降序，第一条应为最近的一条 (approve)
        records = store.list_review_records(sub.submission_id)
        assert len(records) == 2
        assert records[0].decision == ReviewDecision.APPROVE
        assert records[0].notes == "approve-notes"

        latest = store.get_latest_review_record(sub.submission_id)
        assert latest is not None
        assert latest.decision == ReviewDecision.APPROVE

    def test_checklist_persists(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "r1")
        checklist = {
            "manifest_valid": True,
            "permissions_declared": True,
            "security_profile_declared": True,
            "no_remote_code_execution": True,
            "package_not_executed": True,
            "tenant_isolation_considered": True,
            "required_permissions_reasonable": True,
        }
        store.approve_submission(sub.submission_id, "r1", "All good", checklist)
        latest = store.get_latest_review_record(sub.submission_id)
        assert latest.checklist == checklist

    def test_review_notes_persist(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "r1")
        store.reject_submission(sub.submission_id, "r1", "Insufficient permissions declaration", {})
        latest = store.get_latest_review_record(sub.submission_id)
        assert "permissions" in latest.notes

    def test_single_review_record_to_dict_roundtrip(self):
        record = AgentReviewRecord(
            submission_id="sub_001",
            reviewer_id="r1",
            decision=ReviewDecision.APPROVE,
            notes="OK",
            checklist={"a": 1},
            metadata={"source": "test"},
        )
        d = record.to_dict()
        assert d["review_id"] == record.review_id
        assert d["decision"] == "approve"
        assert d["checklist"] == {"a": 1}


# ═══════════════════════════════════════════
# Store Isolation
# ═══════════════════════════════════════════


class TestStoreIsolation:
    def test_list_by_developer(self, store):
        _create_draft_submission(store, developer_id="dev_a")
        _create_draft_submission(store, developer_id="dev_a")
        _create_draft_submission(store, developer_id="dev_b")

        result = store.list_submissions(developer_id="dev_a")
        assert len(result) == 2

        result = store.list_submissions(developer_id="dev_b")
        assert len(result) == 1

    def test_list_by_tenant(self, store):
        _create_draft_submission(store, tenant_id="t1")
        _create_draft_submission(store, tenant_id="t1")
        _create_draft_submission(store, tenant_id="t2")

        result = store.list_submissions(tenant_id="t1")
        assert len(result) == 2

    def test_list_by_status(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")

        drafts = store.list_submissions(status="draft")
        assert len(drafts) == 0

        submitted = store.list_submissions(status="submitted")
        assert len(submitted) == 1

    def test_get_nonexistent_returns_none(self, store):
        assert store.get_submission("nonexistent") is None

    def test_cannot_modify_other_developer_submission(self, store):
        _create_draft_submission(store, developer_id="dev_a")
        sub_b = _create_draft_submission(store, developer_id="dev_b")

        with pytest.raises(SubmissionPermissionError):
            store.update_submission_manifest(sub_b.submission_id, "dev_a", _valid_manifest())

    def test_cannot_submit_other_developer_submission(self, store):
        _create_draft_submission(store, developer_id="dev_a")
        sub_b = _create_draft_submission(store, developer_id="dev_b")

        with pytest.raises(SubmissionPermissionError):
            store.submit_submission(sub_b.submission_id, "dev_a")

    def test_cannot_withdraw_other_developer(self, store):
        sub = _create_draft_submission(store, developer_id="dev_a")
        store.submit_submission(sub.submission_id, "dev_a")

        with pytest.raises(SubmissionPermissionError):
            store.withdraw_submission(sub.submission_id, "dev_b")


# ═══════════════════════════════════════════
# Publish Boundary
# ═══════════════════════════════════════════


class TestPublishBoundary:
    def test_publish_only_stores_marketplace_agent_id(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "r1")
        store.approve_submission(sub.submission_id, "r1", "OK", {})
        store.publish_submission(sub.submission_id, "mkp_dev_001")

        updated = store.get_submission(sub.submission_id)
        assert updated.marketplace_agent_id == "mkp_dev_001"
        # 不创建 MarketplaceAgent — 只记录 marketplace_agent_id
        assert updated.status == SubmissionStatus.PUBLISHED

    def test_publish_does_not_create_marketplace_agent(self, store):
        """publish 只在 submission 表中记录 marketplace_agent_id，
        不调用 marketplace_store.create_agent。"""
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "r1")
        store.approve_submission(sub.submission_id, "r1", "OK", {})
        store.publish_submission(sub.submission_id, "mkp_test_001")

        # 确认 publish 只更新了 submission 记录
        updated = store.get_submission(sub.submission_id)
        assert updated.marketplace_agent_id == "mkp_test_001"

    def test_published_submission_to_dict(self, store):
        sub = _create_draft_submission(store)
        store.submit_submission(sub.submission_id, "dev_001")
        store.start_review(sub.submission_id, "r1")
        store.approve_submission(sub.submission_id, "r1", "OK", {})
        store.publish_submission(sub.submission_id, "mkp_pub_001")

        updated = store.get_submission(sub.submission_id)
        d = updated.to_dict()
        assert d["status"] == "published"
        assert d["marketplace_agent_id"] == "mkp_pub_001"
        assert d["published_at"] is not None
        assert d["submitted_at"] is not None
        assert d["reviewed_at"] is not None

    def test_package_url_stored_not_executed(self, store):
        """package_url 仅作为元数据存储，不被执行。"""
        sub = AgentSubmission(
            developer_id="dev_001",
            tenant_id="tenant-a",
            agent_manifest=_valid_manifest(),
            source_type="manifest",
            package_url="https://example.com/agent.zip",
            status=SubmissionStatus.DRAFT,
        )
        created = store.create_submission(sub)
        assert created.package_url == "https://example.com/agent.zip"
        # 不执行任何代码 — 验证 submission 仍然 draft
        retrieved = store.get_submission(created.submission_id)
        assert retrieved.package_url == "https://example.com/agent.zip"
        assert retrieved.status == SubmissionStatus.DRAFT


# ═══════════════════════════════════════════
# Validation via Store
# ═══════════════════════════════════════════


class TestStoreValidation:
    def test_validate_submission_manifest_valid(self, store):
        sub = _create_draft_submission(store)
        result = store.validate_submission_manifest(sub.submission_id)
        assert result.valid is True

    def test_validate_submission_manifest_invalid(self, store):
        sub = _create_draft_submission(store, agent_manifest=_valid_manifest(capabilities=[]))
        result = store.validate_submission_manifest(sub.submission_id)
        assert result.valid is False

    def test_validate_nonexistent(self, store):
        with pytest.raises(SubmissionNotFoundError):
            store.validate_submission_manifest("nonexistent")


# ═══════════════════════════════════════════
# Full E2E lifecycle
# ═══════════════════════════════════════════


class TestE2ESubmissionLifecycle:
    def test_full_lifecycle(self, store):
        """draft → submit → review → approve → publish 完整通路。"""
        # 1. Create
        sub = _create_draft_submission(store, developer_id="dev_full", tenant_id="t-e2e")
        assert sub.status == SubmissionStatus.DRAFT

        # 2. Submit
        store.submit_submission(sub.submission_id, "dev_full")
        sub = store.get_submission(sub.submission_id)
        assert sub.status == SubmissionStatus.SUBMITTED

        # 3. Start review
        store.start_review(sub.submission_id, "reviewer-e2e")
        sub = store.get_submission(sub.submission_id)
        assert sub.status == SubmissionStatus.IN_REVIEW

        # 4. Approve
        store.approve_submission(sub.submission_id, "reviewer-e2e", "Approved for production", {
            "manifest_valid": True,
            "permissions_declared": True,
            "security_profile_declared": True,
            "no_remote_code_execution": True,
            "package_not_executed": True,
            "tenant_isolation_considered": True,
            "required_permissions_reasonable": True,
        })
        sub = store.get_submission(sub.submission_id)
        assert sub.status == SubmissionStatus.APPROVED

        # 5. Publish
        store.publish_submission(sub.submission_id, "mkp_dev_full")
        sub = store.get_submission(sub.submission_id)
        assert sub.status == SubmissionStatus.PUBLISHED
        assert sub.marketplace_agent_id == "mkp_dev_full"

        # 6. Review records exist
        records = store.list_review_records(sub.submission_id)
        assert len(records) == 1
        assert records[0].decision == ReviewDecision.APPROVE
        assert records[0].reviewer_id == "reviewer-e2e"
