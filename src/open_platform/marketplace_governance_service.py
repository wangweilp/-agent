"""Marketplace Governance Service — Review/Report/TrustScore/Risk。

TrustScore 计算公式（纯 Metadata）：
  base = 50
  + min(published_days / 30 * 5, 15)                  # 存活天数奖励 (max +15)
  + min(review_count * 2, 20)                         # 评价数量奖励 (max +20)
  + (average_rating - 3) * 5                          # 评分调整 (-10 ~ +10)
  - min(report_count * 5, 15)                         # 举报惩罚 (max -15)
  - min(open_report_count * 10, 20)                   # 未解决举报惩罚 (max -20)
  clamped to [0, 100]

RiskLevel 判定：
  CRITICAL: unresolved_reports >= 5
  HIGH:     unresolved_reports >= 3 or trust_score < 30
  MEDIUM:   unresolved_reports >= 1 or trust_score < 50
  LOW:      否则

禁止 runtime/container/microVM — 全部 pure metadata 计算。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.open_platform.marketplace_governance import (
    Review, ReviewAlreadyExistsError, ReviewNotFoundError,
    ReviewStatus, ReviewValidationError,
    Report, ReportNotFoundError, ReportStatus, ReportValidationError,
    TrustScore, GovernanceEvent, GovernanceEventType, RiskLevel,
)

logger = logging.getLogger(__name__)


class MarketplaceGovernanceService:
    def __init__(self, governance_store, agent_module_store=None):
        self._store = governance_store
        self._am_store = agent_module_store

    # ═══════════════ Review ═══════════════

    def create_review(self, workspace_id: str, agent_module_id: str,
                      rating: int, title: str, content: str = "",
                      created_by: str = "") -> Review:
        r = Review(workspace_id=workspace_id, agent_module_id=agent_module_id,
                   rating=rating, title=title, content=content, created_by=created_by)
        created = self._store.create_review(r)
        self._record(agent_module_id, GovernanceEventType.REVIEW_CREATED,
                     f"用户 {workspace_id} 评价 {rating} 星",
                     {"review_id": created.id, "rating": rating})
        self._recalculate(agent_module_id)
        return created

    def update_review(self, review_id: str, rating: int = None,
                      title: str = None, content: str = None) -> Review:
        r = self._store.get_review(review_id)
        if r is None: raise ReviewNotFoundError(f"Review 不存在: {review_id}")
        if rating is not None: r.rating = rating
        if title is not None: r.title = title
        if content is not None: r.content = content
        self._store.update_review(r)
        updated = self._store.get_review(review_id)
        self._record(updated.agent_module_id, GovernanceEventType.REVIEW_UPDATED,
                     f"用户 {updated.workspace_id} 更新评价",
                     {"review_id": updated.id})
        self._recalculate(updated.agent_module_id)
        return updated

    def delete_review(self, review_id: str) -> None:
        r = self._store.get_review(review_id)
        if r is None: raise ReviewNotFoundError(f"Review 不存在: {review_id}")
        self._store.delete_review(review_id)
        self._record(r.agent_module_id, GovernanceEventType.REVIEW_DELETED,
                     f"用户 {r.workspace_id} 删除评价", {"review_id": review_id})
        self._recalculate(r.agent_module_id)

    def get_review(self, review_id: str) -> Review | None:
        return self._store.get_review(review_id)

    def list_reviews(self, *, agent_module_id="", workspace_id="",
                     limit=50, offset=0) -> list[Review]:
        return self._store.list_reviews(agent_module_id=agent_module_id,
            workspace_id=workspace_id, limit=limit, offset=offset)

    def get_rating_aggregation(self, agent_module_id: str) -> dict:
        return self._store.get_rating_aggregation(agent_module_id)

    # ═══════════════ Report ═══════════════

    def create_report(self, workspace_id: str, agent_module_id: str,
                      report_type: str, title: str, description: str = "",
                      created_by: str = "") -> Report:
        r = Report(workspace_id=workspace_id, agent_module_id=agent_module_id,
                   report_type=report_type, title=title, description=description,
                   created_by=created_by)
        created = self._store.create_report(r)
        self._record(agent_module_id, GovernanceEventType.REPORT_CREATED,
                     f"用户 {workspace_id} 举报 [{report_type}]",
                     {"report_id": created.id, "report_type": report_type})
        self._recalculate(agent_module_id)
        return created

    def resolve_report(self, report_id: str, status: str, resolved_by: str,
                       resolution_note: str = "") -> Report:
        if status not in (ReportStatus.RESOLVED, ReportStatus.DISMISSED):
            raise ReportValidationError(f"resolve status 只能是 resolved/dismissed: {status}")
        self._store.resolve_report(report_id, status, resolved_by, resolution_note)
        r = self._store.get_report(report_id)
        evt_type = (GovernanceEventType.REPORT_RESOLVED if status == ReportStatus.RESOLVED
                    else GovernanceEventType.REPORT_DISMISSED)
        self._record(r.agent_module_id, evt_type,
                     f"举报 {report_id} {status}", {"report_id": report_id, "resolved_by": resolved_by})
        self._recalculate(r.agent_module_id)
        return r

    def get_report(self, report_id: str) -> Report | None:
        return self._store.get_report(report_id)

    def list_reports(self, *, agent_module_id="", status="",
                     limit=50, offset=0) -> list[Report]:
        return self._store.list_reports(agent_module_id=agent_module_id,
            status=status, limit=limit, offset=offset)

    # ═══════════════ TrustScore & Risk ═══════════════

    def calculate_trust_score(self, agent_module_id: str) -> TrustScore:
        """纯 Metadata 计算 TrustScore。"""
        agg = self._store.get_rating_aggregation(agent_module_id)
        review_count = agg["count"]
        average_rating = agg["average_rating"]
        reports = self._store.list_reports(agent_module_id=agent_module_id, limit=1000)
        total_reports = len(reports)
        open_reports = len([r for r in reports
                            if r.status in (ReportStatus.OPEN, ReportStatus.INVESTIGATING)])
        resolved_reports = total_reports - open_reports
        published_days = self._estimate_published_days(agent_module_id)

        score = 50.0
        score += min(published_days / 30.0 * 5, 15)
        score += min(review_count * 2, 20)
        effective_rating = average_rating if review_count > 0 else 3.0
        score += (effective_rating - 3) * 5
        score -= min(open_reports * 5, 15)
        score -= min(open_reports * 10, 20)
        score = max(0.0, min(100.0, score))

        risk = self._classify_risk(open_reports, score)
        prev = self._store.get_trust_score(agent_module_id)
        ts = TrustScore(agent_module_id=agent_module_id, score=round(score, 1),
            published_days=published_days, review_count=review_count,
            average_rating=average_rating, report_count=total_reports,
            resolved_report_count=resolved_reports, risk_level=risk)
        self._store.upsert_trust_score(ts)
        if prev is None or abs(prev.score - score) > 0.5 or prev.risk_level != risk:
            self._record(agent_module_id, GovernanceEventType.TRUST_SCORE_CHANGED,
                         f"信任分: {score:.1f}, 风险: {risk}",
                         {"score": score, "risk": risk})
        return ts

    def get_trust_score(self, agent_module_id: str) -> TrustScore | None:
        return self._store.get_trust_score(agent_module_id)

    def calculate_risk_level(self, agent_module_id: str) -> str:
        reports = self._store.list_reports(agent_module_id=agent_module_id, limit=1000)
        unresolved = len([r for r in reports
                          if r.status in (ReportStatus.OPEN, ReportStatus.INVESTIGATING)])
        ts = self._store.get_trust_score(agent_module_id)
        score = ts.score if ts else 50.0
        return self._classify_risk(unresolved, score)

    def _classify_risk(self, unresolved_reports: int, trust_score: float) -> str:
        if unresolved_reports >= 5: return RiskLevel.CRITICAL
        if unresolved_reports >= 3 or trust_score < 25: return RiskLevel.HIGH
        if unresolved_reports >= 1 or trust_score < 40: return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _estimate_published_days(self, agent_module_id: str) -> int:
        if not self._am_store: return 0
        m = self._am_store.get(agent_module_id)
        if m and m.published_at:
            return max(0, (datetime.now(timezone.utc) - m.published_at).days)
        return 0

    # ═══════════════ Governance Timeline ═══════════════

    def get_governance_timeline(self, agent_module_id: str, limit=50) -> list[dict]:
        events = self._store.get_timeline(agent_module_id, limit=limit)
        return [e.to_dict() for e in events]

    # ═══════════════ Analytics ═══════════════

    def get_top_rated(self, limit=10) -> list[dict]:
        return self._ranked_list(
            self._store.list_trust_scores(min_score=0, limit=limit * 3),
            key=lambda x: x.average_rating, limit=limit)

    def get_highest_trust(self, limit=10) -> list[dict]:
        scores = self._store.list_trust_scores(min_score=0, limit=limit)
        return [{"agent_module_id": s.agent_module_id, "trust_score": s.score,
                 "risk_level": s.risk_level, "reviews": s.review_count,
                 "average_rating": s.average_rating} for s in scores]

    def get_most_installed(self, limit=10) -> list[dict]:
        """按评价数排序（review_count 作为受欢迎度近似）。"""
        scores = list(self._store.list_trust_scores(min_score=0, limit=limit * 3))
        scores.sort(key=lambda x: x.review_count, reverse=True)
        return [{"agent_module_id": s.agent_module_id, "review_count": s.review_count,
                 "average_rating": s.average_rating, "trust_score": s.score}
                for s in scores[:limit]]

    def get_fastest_growing(self, limit=10) -> list[dict]:
        """按发布天数短 + 评价多 近似增长。"""
        scores = list(self._store.list_trust_scores(min_score=0, limit=limit * 3))
        # growth ≈ review_count / max(published_days, 1)
        scored = [(s, s.review_count / max(s.published_days, 1)) for s in scores]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [{"agent_module_id": s.agent_module_id, "reviews": s.review_count,
                 "growth_rate": round(g, 3), "published_days": s.published_days}
                for s, g in scored[:limit]]

    def get_trending(self, limit=10) -> list[dict]:
        """综合 trending = trust * 0.4 + rating * 0.3 + review_count * 0.3（归一化）。"""
        scores = list(self._store.list_trust_scores(min_score=0, limit=limit * 3))
        if not scores: return []
        max_r = max(1, max(s.review_count for s in scores))
        trending = []
        for s in scores:
            t = (s.score / 100) * 0.4 + (s.average_rating / 5) * 0.3 + (s.review_count / max_r) * 0.3
            trending.append((s, round(t, 3)))
        trending.sort(key=lambda x: x[1], reverse=True)
        return [{"agent_module_id": s.agent_module_id, "trending_score": t,
                 "trust": s.score, "rating": s.average_rating, "reviews": s.review_count}
                for s, t in trending[:limit]]

    def get_analytics_dashboard(self) -> dict[str, Any]:
        """综合治理分析面板。"""
        all_scores = list(self._store.list_trust_scores(min_score=0, limit=1000))
        return {
            "top_rated": self.get_top_rated(5),
            "highest_trust": self.get_highest_trust(5),
            "most_installed": self.get_most_installed(5),
            "fastest_growing": self.get_fastest_growing(5),
            "trending": self.get_trending(5),
            "total_modules_with_scores": len(all_scores),
            "average_platform_trust": round(
                sum(s.score for s in all_scores) / max(1, len(all_scores)), 1),
            "risk_distribution": {
                RiskLevel.LOW: len([s for s in all_scores if s.risk_level == RiskLevel.LOW]),
                RiskLevel.MEDIUM: len([s for s in all_scores if s.risk_level == RiskLevel.MEDIUM]),
                RiskLevel.HIGH: len([s for s in all_scores if s.risk_level == RiskLevel.HIGH]),
                RiskLevel.CRITICAL: len([s for s in all_scores if s.risk_level == RiskLevel.CRITICAL]),
            },
        }

    # ═══════════════ Internal ═══════════════

    def _recalculate(self, agent_module_id: str) -> None:
        try: self.calculate_trust_score(agent_module_id)
        except Exception: logger.debug("recalculate_failed", exc_info=True)

    def _record(self, agent_module_id: str, event_type: str, description: str,
                metadata: dict | None = None) -> None:
        try:
            evt = GovernanceEvent(agent_module_id=agent_module_id,
                event_type=event_type, description=description, metadata=metadata or {})
            self._store.record_event(evt)
        except Exception: logger.debug("record_event_failed", exc_info=True)

    def _ranked_list(self, items, key, limit):
        sorted_items = sorted(items, key=key, reverse=True)
        return [{"agent_module_id": s.agent_module_id, "average_rating": s.average_rating,
                 "review_count": s.review_count, "trust_score": s.score}
                for s in sorted_items[:limit]]
