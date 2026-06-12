"""Marketplace Governance Domain 单元测试。Review / Report / TrustScore / GovernanceEvent。"""

from __future__ import annotations

import pytest
from src.open_platform.marketplace_governance import (
    Review, Report, TrustScore, GovernanceEvent, GovernanceEventType,
    ReviewStatus, ReportStatus, ReportType, RiskLevel,
    ReviewValidationError, ReportValidationError, ReviewAlreadyExistsError,
)


class TestReviewDomain:
    def test_defaults(self):
        r = Review()
        assert r.id.startswith("rev_"); assert r.rating == 5
        assert r.status == ReviewStatus.ACTIVE

    def test_validate_valid(self, r=None):
        r = r or Review(workspace_id="ws-1", agent_module_id="agent_1", rating=4, title="Great")
        assert r.is_valid()

    def test_validate_missing_ws(self):
        r = Review(agent_module_id="am", rating=5, title="T")
        errors = r.validate()
        assert any("workspace_id 必填" in e for e in errors)

    def test_validate_missing_am(self):
        r = Review(workspace_id="ws", rating=5, title="T")
        errors = r.validate()
        assert any("agent_module_id 必填" in e for e in errors)

    def test_validate_rating_range(self):
        for bad in [0, 6, -1, 10]:
            r = Review(workspace_id="ws", agent_module_id="am", rating=bad, title="T")
            assert any("rating" in e for e in r.validate()), f"rating={bad} should fail"

    def test_validate_missing_title(self):
        r = Review(workspace_id="ws", agent_module_id="am", rating=3)
        assert any("title 必填" in e for e in r.validate())

    def test_validate_invalid_status(self):
        r = Review(workspace_id="ws", agent_module_id="am", rating=5, title="T", status="bad")
        assert any("status 无效" in e for e in r.validate())

    def test_to_dict(self):
        r = Review(workspace_id="ws", agent_module_id="am", rating=4, title="Good", content="nice")
        d = r.to_dict()
        assert d["workspace_id"] == "ws"; assert d["rating"] == 4

    def test_from_dict_roundtrip(self):
        r = Review(workspace_id="ws", agent_module_id="am", rating=5, title="T")
        r2 = Review.from_dict(r.to_dict())
        assert r2.id == r.id; assert r2.rating == 5


class TestReportDomain:
    def test_defaults(self):
        r = Report()
        assert r.id.startswith("rpt_"); assert r.status == ReportStatus.OPEN
        assert r.report_type == ReportType.OTHER

    def test_validate_valid(self):
        r = Report(workspace_id="ws-1", agent_module_id="am_1", title="Report",
                   report_type=ReportType.SPAM)
        assert r.is_valid()

    def test_validate_missing_ws(self):
        r = Report(agent_module_id="am", title="T")
        assert any("workspace_id 必填" in e for e in r.validate())

    def test_validate_missing_am(self):
        r = Report(workspace_id="ws", title="T")
        assert any("agent_module_id 必填" in e for e in r.validate())

    def test_validate_invalid_type(self):
        r = Report(workspace_id="ws", agent_module_id="am", title="T", report_type="hack")
        assert any("report_type 无效" in e for e in r.validate())

    def test_validate_missing_title(self):
        r = Report(workspace_id="ws", agent_module_id="am")
        assert any("title 必填" in e for e in r.validate())

    def test_all_report_types_valid(self):
        for rt in ReportType:
            r = Report(workspace_id="ws", agent_module_id="am", title="Rpt", report_type=rt)
            assert r.is_valid(), f"ReportType.{rt.name} should be valid"

    def test_to_dict_from_dict(self):
        r = Report(workspace_id="ws", agent_module_id="am", report_type=ReportType.FRAUD,
                   title="Scam", description="bad module")
        r2 = Report.from_dict(r.to_dict())
        assert r2.report_type == ReportType.FRAUD
        assert r2.description == "bad module"


class TestTrustScoreDomain:
    def test_defaults(self):
        ts = TrustScore()
        assert ts.score == 50.0; assert ts.risk_level == RiskLevel.LOW

    def test_to_dict(self):
        ts = TrustScore(agent_module_id="agent_1", score=85.5, review_count=10,
                        average_rating=4.2, risk_level=RiskLevel.LOW)
        d = ts.to_dict()
        assert d["score"] == 85.5; assert d["risk_level"] == "low"

    def test_from_dict(self):
        d = {"agent_module_id": "ag", "score": 90.0, "risk_level": "low"}
        ts = TrustScore.from_dict(d)
        assert ts.score == 90.0


class TestGovernanceEventDomain:
    def test_defaults(self):
        evt = GovernanceEvent()
        assert evt.id.startswith("govevt_")

    def test_to_dict(self):
        evt = GovernanceEvent(agent_module_id="ag", event_type=GovernanceEventType.REVIEW_CREATED,
                              description="测试", metadata={"k": "v"})
        d = evt.to_dict()
        assert d["event_type"] == "review_created"; assert d["metadata"] == {"k": "v"}

    def test_from_dict(self):
        d = {"id": "gvt_1", "agent_module_id": "ag", "event_type": "risk_changed"}
        evt = GovernanceEvent.from_dict(d)
        assert evt.agent_module_id == "ag"


class TestEnums:
    def test_review_status(self):
        assert ReviewStatus.ACTIVE in list(ReviewStatus)
    def test_report_status(self):
        assert ReportStatus.OPEN in list(ReportStatus)
        assert ReportStatus.RESOLVED in list(ReportStatus)
    def test_report_types(self):
        assert len(list(ReportType)) == 5
    def test_risk_levels(self):
        assert len(list(RiskLevel)) == 4
    def test_event_types(self):
        assert len(list(GovernanceEventType)) == 8
