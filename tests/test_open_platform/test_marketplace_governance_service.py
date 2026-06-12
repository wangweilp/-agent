"""Marketplace Governance Service 测试 — Review/Report/TrustScore/Risk Pipeline + Analytics。"""

from __future__ import annotations

import os, tempfile, pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
from src.adapters.config import Settings
from src.adapters.marketplace_governance_store import SQLiteMarketplaceGovernanceStore
from src.open_platform.marketplace_governance_service import MarketplaceGovernanceService
from src.open_platform.marketplace_governance import (
    ReviewAlreadyExistsError, ReviewNotFoundError, ReportStatus, RiskLevel,
)


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")
@pytest.fixture
def db():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_gvsvc.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)
@pytest.fixture
def store(settings, db): return SQLiteMarketplaceGovernanceStore(settings, db_path=db)
@pytest.fixture
def svc(store): return MarketplaceGovernanceService(store)


class TestReviewService:
    def test_create_review(self, svc):
        r = svc.create_review("ws-1", "agent_A", 5, "Great", created_by="u1")
        assert r.id.startswith("rev_") and r.rating == 5

    def test_duplicate_review_blocked(self, svc):
        svc.create_review("ws-1", "agent_A", 5, "Good", created_by="u1")
        with pytest.raises(ReviewAlreadyExistsError):
            svc.create_review("ws-1", "agent_A", 3, "Okay", created_by="u1")

    def test_update_review(self, svc):
        r = svc.create_review("ws-1", "agent_A", 4, "OK", created_by="u1")
        u = svc.update_review(r.id, rating=2, title="Bad")
        assert u.rating == 2 and u.title == "Bad"

    def test_delete_review(self, svc):
        r = svc.create_review("ws-1", "agent_A", 5, "Good", created_by="u1")
        svc.delete_review(r.id)
        assert svc._store.get_active_review("ws-1", "agent_A") is None

    def test_delete_nonexistent(self, svc):
        with pytest.raises(ReviewNotFoundError):
            svc.delete_review("rev_bad")

    def test_list_reviews(self, svc):
        svc.create_review("ws-1", "agent_A", 5, "R1", created_by="u1")
        svc.create_review("ws-2", "agent_A", 4, "R2", created_by="u2")
        assert len(svc.list_reviews(agent_module_id="agent_A")) == 2

    def test_rating_aggregation(self, svc):
        svc.create_review("ws-1", "agent_X", 5, "A", created_by="u1")
        svc.create_review("ws-2", "agent_X", 3, "B", created_by="u2")
        agg = svc.get_rating_aggregation("agent_X")
        assert agg["count"] == 2 and agg["average_rating"] == 4.0


class TestReportService:
    def test_create_report(self, svc):
        r = svc.create_report("ws-1", "agent_A", "spam", "Spammy", created_by="u1")
        assert r.id.startswith("rpt_") and r.report_type == "spam"

    def test_resolve_report(self, svc):
        r = svc.create_report("ws-1", "agent_A", "spam", "Spam", created_by="u1")
        resolved = svc.resolve_report(r.id, ReportStatus.RESOLVED, "admin", "cleaned")
        assert resolved.status == ReportStatus.RESOLVED

    def test_dismiss_report(self, svc):
        r = svc.create_report("ws-1", "agent_A", "spam", "Bad", created_by="u1")
        resolved = svc.resolve_report(r.id, ReportStatus.DISMISSED, "mod", "false alarm")
        assert resolved.status == ReportStatus.DISMISSED

    def test_list_reports(self, svc):
        svc.create_report("ws-1", "agent_A", "spam", "S", created_by="u1")
        svc.create_report("ws-2", "agent_A", "fraud", "F", created_by="u2")
        assert len(svc.list_reports(agent_module_id="agent_A")) == 2

    def test_list_reports_by_status(self, svc):
        r = svc.create_report("ws-1", "agent_A", "spam", "Open", created_by="u1")
        svc.resolve_report(r.id, ReportStatus.RESOLVED, "admin", "done")
        assert len(svc.list_reports(agent_module_id="agent_A", status=ReportStatus.RESOLVED)) == 1
        assert len(svc.list_reports(agent_module_id="agent_A", status=ReportStatus.OPEN)) == 0


class TestTrustScoreService:
    def test_calculate_default_trust_score(self, svc):
        """无 review/report 的新模块 — 默认 ~50 分（中性评分不惩罚）。"""
        ts = svc.calculate_trust_score("agent_NEW")
        assert 45 <= ts.score <= 65, f"expected ~50, got {ts.score}"
        assert ts.risk_level == RiskLevel.LOW

    def test_high_rated_module_has_higher_score(self, svc):
        for i in range(5):
            svc.create_review(f"ws-{i}", "agent_GOOD", 5, f"R{i}", created_by=f"u{i}")
        ts = svc.calculate_trust_score("agent_GOOD")
        assert ts.average_rating == 5.0
        assert ts.score > 55, f"score should be >55 for 5-star ratings: {ts.score}"

    def test_reported_module_has_lower_score(self, svc):
        svc.create_review("ws-1", "agent_BAD", 5, "Hidden gem", created_by="u1")
        for _ in range(3):
            svc.create_report(f"ws-{_+2}", "agent_BAD", "spam", "Spam", created_by=f"u{_}")
        ts = svc.calculate_trust_score("agent_BAD")
        assert ts.score < 55, f"score should be <55 with 3 reports: {ts.score}"

    def test_get_trust_score(self, svc):
        svc.calculate_trust_score("agent_A")
        ts = svc.get_trust_score("agent_A")
        assert ts is not None and ts.agent_module_id == "agent_A"

    def test_trust_score_nonexistent_returns_none(self, svc):
        assert svc.get_trust_score("nonexistent") is None


class TestRiskClassification:
    def test_low_risk_by_default(self, svc):
        assert svc.calculate_risk_level("agent_NEW") == RiskLevel.LOW

    def test_critical_risk(self, svc):
        for i in range(5):
            svc.create_report(f"ws-{i}", "agent_CRIT", "malicious", f"Bad", created_by=f"u{i}")
        assert svc.calculate_risk_level("agent_CRIT") == RiskLevel.CRITICAL

    def test_high_risk(self, svc):
        for i in range(3):
            svc.create_report(f"ws-{i}", "agent_HIGH", "fraud", f"F", created_by=f"u{i}")
        assert svc.calculate_risk_level("agent_HIGH") == RiskLevel.HIGH

    def test_medium_risk(self, svc):
        svc.create_report("ws-1", "agent_MED", "other", "issue", created_by="u1")
        assert svc.calculate_risk_level("agent_MED") == RiskLevel.MEDIUM

    def test_resolved_reports_lower_risk(self, svc):
        r1 = svc.create_report("ws-1", "agent_RESOLVED", "spam", "S", created_by="u1")
        r2 = svc.create_report("ws-2", "agent_RESOLVED", "spam", "S2", created_by="u2")
        svc.resolve_report(r1.id, ReportStatus.RESOLVED, "admin", "done")
        svc.resolve_report(r2.id, ReportStatus.RESOLVED, "admin", "done")
        assert svc.calculate_risk_level("agent_RESOLVED") == RiskLevel.LOW


class TestGovernanceTimeline:
    def test_timeline_records_events(self, svc):
        svc.create_review("ws-1", "agent_TL", 5, "Great", created_by="u1")
        r = svc.create_report("ws-2", "agent_TL", "spam", "S", created_by="u2")
        svc.resolve_report(r.id, ReportStatus.RESOLVED, "admin", "ok")
        tl = svc.get_governance_timeline("agent_TL")
        assert len(tl) >= 4  # review_created + trust_changed + report_created + resolved + trust_changed

    def test_timeline_empty_for_new_module(self, svc):
        assert svc.get_governance_timeline("agent_NEW_NEVER_TOUCHED") == []


class TestAnalytics:
    def test_top_rated(self, svc):
        for i, rating in enumerate([4, 5, 3, 5, 2], 1):
            svc.create_review(f"ws-{i}", "agent_A", rating, f"R{i}", created_by=f"u{i}")
            svc.create_review(f"ws-{i+10}", "agent_B", max(1, rating-1), f"R{i}", created_by=f"u{i+10}")
        top = svc.get_top_rated(2)
        assert len(top) <= 2

    def test_highest_trust(self, svc):
        svc.calculate_trust_score("agent_T1")
        svc.calculate_trust_score("agent_T2")
        ht = svc.get_highest_trust(5)
        assert len(ht) >= 2

    def test_analytics_dashboard(self, svc):
        svc.create_review("ws-1", "agent_D", 5, "Good", created_by="u1")
        svc.calculate_trust_score("agent_D")
        d = svc.get_analytics_dashboard()
        assert "top_rated" in d
        assert "risk_distribution" in d
        assert d["risk_distribution"]["low"] >= 0

    def test_most_installed(self, svc):
        svc.create_review("ws-1", "agent_P", 5, "Pop", created_by="u1")
        svc.create_review("ws-2", "agent_P", 4, "Good", created_by="u2")
        mi = svc.get_most_installed(5)
        assert len(mi) >= 1

    def test_fastest_growing(self, svc):
        svc.create_review("ws-1", "agent_G", 5, "Growing", created_by="u1")
        fg = svc.get_fastest_growing(5)
        assert len(fg) >= 1

    def test_trending(self, svc):
        svc.create_review("ws-1", "agent_TR", 5, "Trending", created_by="u1")
        svc.calculate_trust_score("agent_TR")
        tr = svc.get_trending(5)
        assert len(tr) >= 1
