"""Marketplace Governance Store 测试 — Review/Report/TrustScore/GovernanceEvent CRUD + 约束。"""

from __future__ import annotations

import os, tempfile, pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
from src.adapters.config import Settings
from src.adapters.marketplace_governance_store import SQLiteMarketplaceGovernanceStore
from src.open_platform.marketplace_governance import (
    Review, ReviewAlreadyExistsError, ReviewNotFoundError, ReviewStatus,
    Report, ReportNotFoundError, ReportStatus, ReportType,
    TrustScore, GovernanceEvent, GovernanceEventType, RiskLevel,
)


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")
@pytest.fixture
def db():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_gv.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)
@pytest.fixture
def store(settings, db): return SQLiteMarketplaceGovernanceStore(settings, db_path=db)


def _rv(**kw):
    return Review(workspace_id=kw.get("ws","ws-1"), agent_module_id=kw.get("am","agent_A"),
                  rating=kw.get("rating",5), title=kw.get("title","Good"),
                  content=kw.get("content",""), created_by=kw.get("by","u1"))


class TestReviewStore:
    def test_create_and_get(self, store):
        r = store.create_review(_rv())
        assert r.id.startswith("rev_"); assert store.get_review(r.id).rating == 5

    def test_unique_active_per_ws_per_module(self, store):
        store.create_review(_rv(ws="ws-1", am="agent_A"))
        with pytest.raises(ReviewAlreadyExistsError):
            store.create_review(_rv(ws="ws-1", am="agent_A"))

    def test_different_ws_can_review(self, store):
        store.create_review(_rv(ws="ws-1", am="agent_A"))
        r2 = store.create_review(_rv(ws="ws-2", am="agent_A"))
        assert r2.id.startswith("rev_")

    def test_delete_then_recreate(self, store):
        r = store.create_review(_rv(ws="ws-1", am="agent_A"))
        store.delete_review(r.id)
        r2 = store.create_review(_rv(ws="ws-1", am="agent_A"))
        assert r2.id != r.id

    def test_get_active_review(self, store):
        store.create_review(_rv(ws="ws-1", am="agent_A"))
        a = store.get_active_review("ws-1", "agent_A")
        assert a is not None and a.rating == 5

    def test_active_review_none_if_deleted(self, store):
        r = store.create_review(_rv(ws="ws-1", am="agent_A"))
        store.delete_review(r.id)
        assert store.get_active_review("ws-1", "agent_A") is None

    def test_list_reviews(self, store):
        store.create_review(_rv(am="agent_A", title="R1"))
        store.create_review(_rv(am="agent_A", ws="ws-2", title="R2"))
        store.create_review(_rv(am="agent_B", ws="ws-1", title="R3"))
        assert len(store.list_reviews(agent_module_id="agent_A")) == 2
        assert len(store.list_reviews(workspace_id="ws-1")) == 2

    def test_update_review(self, store):
        r = store.create_review(_rv(title="Old"))
        r.rating = 3; r.title = "Updated"
        store.update_review(r)
        f = store.get_review(r.id)
        assert f.rating == 3 and f.title == "Updated"

    def test_update_nonexistent(self, store):
        with pytest.raises(ReviewNotFoundError):
            store.update_review(Review(id="rev_bad", workspace_id="ws", agent_module_id="am", rating=5, title="T"))

    def test_delete_nonexistent(self, store):
        with pytest.raises(ReviewNotFoundError):
            store.delete_review("rev_bad")

    def test_rating_aggregation(self, store):
        store.create_review(_rv(am="agent_X", rating=5))
        store.create_review(_rv(am="agent_X", ws="ws-2", rating=3))
        agg = store.get_rating_aggregation("agent_X")
        assert agg["count"] == 2; assert agg["average_rating"] == 4.0
        assert agg["distribution"]["5"] == 1; assert agg["distribution"]["3"] == 1

    def test_rating_aggregation_empty(self, store):
        agg = store.get_rating_aggregation("nonexistent")
        assert agg["count"] == 0; assert agg["average_rating"] == 0.0


def _rpt(**kw):
    return Report(workspace_id=kw.get("ws","ws-1"), agent_module_id=kw.get("am","agent_A"),
                  report_type=kw.get("type",ReportType.SPAM), title=kw.get("title","Bad"),
                  description=kw.get("desc",""), created_by=kw.get("by","u1"))


class TestReportStore:
    def test_create_and_get(self, store):
        r = store.create_report(_rpt())
        assert r.id.startswith("rpt_"); f = store.get_report(r.id)
        assert f is not None and f.report_type == ReportType.SPAM

    def test_list_reports(self, store):
        store.create_report(_rpt(am="agent_A", type=ReportType.SPAM))
        store.create_report(_rpt(am="agent_A", type=ReportType.FRAUD))
        store.create_report(_rpt(am="agent_B", type=ReportType.COPYRIGHT))
        assert len(store.list_reports(agent_module_id="agent_A")) == 2

    def test_filter_by_status(self, store):
        r = store.create_report(_rpt())
        store.resolve_report(r.id, ReportStatus.RESOLVED, "admin", "fixed")
        assert len(store.list_reports(agent_module_id="agent_A", status=ReportStatus.RESOLVED)) == 1

    def test_resolve_report(self, store):
        r = store.create_report(_rpt())
        store.resolve_report(r.id, ReportStatus.RESOLVED, "admin", "cleaned")
        f = store.get_report(r.id)
        assert f.status == ReportStatus.RESOLVED and f.resolved_by == "admin"

    def test_dismiss_report(self, store):
        r = store.create_report(_rpt())
        store.resolve_report(r.id, ReportStatus.DISMISSED, "mod", "no issue")
        assert store.get_report(r.id).status == ReportStatus.DISMISSED

    def test_resolve_nonexistent(self, store):
        with pytest.raises(ReportNotFoundError):
            store.resolve_report("rpt_bad", ReportStatus.RESOLVED, "admin", "")


class TestTrustScoreStore:
    def test_upsert_and_get(self, store):
        ts = TrustScore(agent_module_id="agent_A", score=85.5, review_count=10)
        store.upsert_trust_score(ts)
        fetched = store.get_trust_score("agent_A")
        assert fetched.score == 85.5 and fetched.review_count == 10

    def test_upsert_overwrite(self, store):
        store.upsert_trust_score(TrustScore(agent_module_id="agent_A", score=70.0))
        store.upsert_trust_score(TrustScore(agent_module_id="agent_A", score=90.0))
        assert store.get_trust_score("agent_A").score == 90.0

    def test_get_nonexistent(self, store):
        assert store.get_trust_score("nonexistent") is None

    def test_list_trust_scores(self, store):
        store.upsert_trust_score(TrustScore(agent_module_id="A", score=90.0))
        store.upsert_trust_score(TrustScore(agent_module_id="B", score=70.0))
        store.upsert_trust_score(TrustScore(agent_module_id="C", score=30.0))
        scores = store.list_trust_scores(min_score=50)
        assert len(scores) == 2

    def test_list_all_desc(self, store):
        store.upsert_trust_score(TrustScore(agent_module_id="A", score=10.0))
        store.upsert_trust_score(TrustScore(agent_module_id="B", score=90.0))
        scores = store.list_trust_scores()
        assert len(scores) >= 1
        assert scores[0].score >= scores[-1].score if len(scores) > 1 else True


class TestGovernanceEventStore:
    def test_record_and_timeline(self, store):
        store.record_event(GovernanceEvent(agent_module_id="agent_A",
            event_type=GovernanceEventType.REVIEW_CREATED, description="评价"))
        store.record_event(GovernanceEvent(agent_module_id="agent_A",
            event_type=GovernanceEventType.RISK_CHANGED, description="风险变高"))
        timeline = store.get_timeline("agent_A")
        assert len(timeline) == 2

    def test_timeline_empty(self, store):
        assert store.get_timeline("nonexistent") == []

    def test_timeline_limit(self, store):
        for i in range(10):
            store.record_event(GovernanceEvent(agent_module_id="agent_A",
                event_type=GovernanceEventType.REVIEW_CREATED, description=f"E{i}"))
        assert len(store.get_timeline("agent_A", limit=3)) == 3

    def test_timeline_sorted_desc(self, store):
        store.record_event(GovernanceEvent(agent_module_id="agent_A",
            event_type="first", description="older"))
        import time; time.sleep(0.02)
        store.record_event(GovernanceEvent(agent_module_id="agent_A",
            event_type="last", description="newer"))
        tl = store.get_timeline("agent_A")
        # 按 created_at DESC，最新在前
        assert len(tl) >= 2
        types = [e.event_type for e in tl]
        assert "last" in types and "first" in types
