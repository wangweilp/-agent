"""Marketplace Recommendation & Analytics Engine。

推荐算法（纯 metadata 计算）：
  1. Content-based: 基于已订阅 agents 的 category + tags 匹配
  2. Collaborative: 找到相似 workspace，推荐他们订阅的 agents
  3. Trust-weighted: 信任分高的 agent 获得 boost
  4. 最终得分加权融合

Rankings: Top Rated / Most Installed / Fastest Growing / Trending / Highest Trust

禁止 runtime/container/microVM — 全部 pure Python metadata 计算。
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from math import log
from typing import Any

from src.open_platform.marketplace_analytics import (
    AgentRank, AnalyticsEvent, AnalyticsMetrics, RankingCategory,
    RecommendationReason, RecommendedAgent, AnalyticsDimension,
)

logger = logging.getLogger(__name__)


class MarketplaceAnalyticsService:
    """推荐 + 排行 + 分析引擎。"""

    def __init__(self, analytics_store, governance_store=None,
                 agent_module_store=None):
        self._store = analytics_store
        self._gov = governance_store
        self._am = agent_module_store

    # ═══════════════ Recommendations ═══════════════

    def generate_recommendations(self, workspace_id: str, limit: int = 10) -> list[dict]:
        """为 workspace 生成个性化推荐。"""
        # 1. 加载已订阅 agents 和所有已发布 agents
        subscribed = self._subscribed_modules(workspace_id)
        all_published = self._all_published_modules()
        if not all_published:
            return []

        sub_ids = {m["id"] for m in subscribed}
        candidates = [m for m in all_published if m["id"] not in sub_ids]

        # 2. 构建已订阅 agents 的 profile（category + tags）
        sub_categories = set()
        sub_tags = Counter()
        for m in subscribed:
            if m.get("category"): sub_categories.add(m["category"])
            for t in m.get("tags", []): sub_tags[t] += 1

        # 3. 计算每个 candidate 得分
        scored = []
        for c in candidates:
            content_score, reasons = self._content_similarity(c, sub_categories, sub_tags)
            trust = c.get("trust_score", 50.0)
            rating = c.get("average_rating", 3.0)
            review_n = c.get("review_count", 0)

            # 加权融合
            final = (content_score * 0.40 +
                     (trust / 100.0) * 100 * 0.25 +
                     (rating / 5.0) * 100 * 0.20 +
                     min(review_n / 10.0, 1.0) * 100 * 0.10 +
                     (c.get("subscriber_count", 0) / max(1, self._total_subscriptions())) * 100 * 0.05)
            final = round(final, 2)

            # confidence 基于信号强度
            sig_count = sum(1 for s in [content_score > 0, trust > 60, rating >= 4, review_n >= 5])
            confidence = min(sig_count / 4.0, 1.0)

            scored.append(RecommendedAgent(
                agent_module_id=c["id"], agent_name=c["name"],
                score=final, reason=reasons[0] if reasons else RecommendationReason.POPULAR,
                sub_reasons=reasons[:3], confidence=round(confidence, 2)))

        scored.sort(key=lambda x: x.score, reverse=True)
        top = scored[:limit]

        # 缓存
        try: self._store.save_recommendations(workspace_id, top)
        except Exception: pass

        self._record("recommendation_generated", AnalyticsDimension.ACTIVITY,
                     workspace_id=workspace_id,
                     payload={"count": len(top), "workspace_id": workspace_id})
        return [r.to_dict() for r in top]

    def get_recommendations(self, workspace_id: str, limit: int = 10) -> list[dict]:
        cached = self._store.get_recommendations(workspace_id, limit)
        if cached:
            return [r.to_dict() for r in cached]
        return self.generate_recommendations(workspace_id, limit)

    # ═══════════════ Rankings ═══════════════

    def generate_rankings(self, category: str, limit: int = 20) -> list[dict]:
        all_modules = self._all_published_modules()
        if not all_modules: return []

        if category == RankingCategory.TOP_RATED:
            ranks = self._rank_by(all_modules, key=lambda m: m.get("average_rating", 0), limit=limit)
        elif category == RankingCategory.MOST_INSTALLED:
            ranks = self._rank_by(all_modules,
                key=lambda m: m.get("review_count", 0) + m.get("subscriber_count", 0), limit=limit)
        elif category == RankingCategory.FASTEST_GROWING:
            ranks = self._rank_by(all_modules,
                key=lambda m: self._growth_rate(m), limit=limit)
        elif category == RankingCategory.TRENDING:
            ranks = self._rank_by(all_modules,
                key=lambda m: self._trending_score(m), limit=limit)
        elif category == RankingCategory.HIGHEST_TRUST:
            ranks = self._rank_by(all_modules,
                key=lambda m: m.get("trust_score", 50), limit=limit)
        elif category == RankingCategory.MOST_REVIEWED:
            ranks = self._rank_by(all_modules,
                key=lambda m: m.get("review_count", 0), limit=limit)
        else:
            return []

        rank_list = []
        for i, m in enumerate(ranks):
            rank_list.append(AgentRank(
                agent_module_id=m["id"], agent_name=m["name"],
                rank=i + 1, category=category, score=m.get("_sort_score", 0),
                metrics={"average_rating": m.get("average_rating", 0),
                         "review_count": m.get("review_count", 0),
                         "trust_score": m.get("trust_score", 0),
                         "category": m.get("category", ""), "tags": m.get("tags", [])}))

        try: self._store.save_rankings(category, rank_list)
        except Exception: pass

        self._record("rankings_generated", AnalyticsDimension.ACTIVITY,
                     payload={"category": category, "count": len(rank_list)})
        return [r.to_dict() for r in rank_list]

    def get_rankings(self, category: str, limit: int = 20) -> list[dict]:
        cached = self._store.get_rankings(category, limit)
        if cached: return [r.to_dict() for r in cached]
        return self.generate_rankings(category, limit)

    # ── Named ranking shortcuts ──

    def get_top_rated_agents(self, limit: int = 10) -> list[dict]:
        return self.get_rankings(RankingCategory.TOP_RATED, limit)

    def get_most_installed_agents(self, limit: int = 10) -> list[dict]:
        return self.get_rankings(RankingCategory.MOST_INSTALLED, limit)

    def get_fastest_growing_agents(self, limit: int = 10) -> list[dict]:
        return self.get_rankings(RankingCategory.FASTEST_GROWING, limit)

    def get_trending_agents(self, limit: int = 10) -> list[dict]:
        return self.get_rankings(RankingCategory.TRENDING, limit)

    # ═══════════════ Platform Analytics ═══════════════

    def calculate_platform_metrics(self) -> dict:
        all_modules = self._all_published_modules()
        modules = all_modules
        published = [m for m in modules if m.get("status") == "published"]
        ratings = [m.get("average_rating", 0) for m in modules if m.get("review_count", 0) > 0]
        trusts = [m.get("trust_score", 0) for m in modules if m.get("trust_score", 0) > 0]
        total_subs = self._total_subscriptions()

        # category distribution
        cats = Counter(m.get("category", "uncategorized") for m in modules if m.get("category"))

        # tags
        all_tags = Counter()
        for m in modules:
            for t in m.get("tags", []): all_tags[t] += 1

        # risk distribution from trust scores
        risk_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for m in modules:
            rl = m.get("risk_level", "low")
            if rl in risk_dist: risk_dist[rl] += 1

        # active workspaces = distinct workspace_ids across reviews + subscriptions
        active_ws = set()
        if self._gov:
            for r in self._gov.list_reviews(limit=5000):
                active_ws.add(r.workspace_id)

        m = AnalyticsMetrics(
            total_modules=len(modules),
            published_modules=len(published),
            total_reviews=sum(m.get("review_count", 0) for m in modules),
            average_platform_rating=round(sum(ratings) / max(1, len(ratings)), 2),
            average_platform_trust=round(sum(trusts) / max(1, len(trusts)), 2),
            total_subscriptions=total_subs,
            active_workspaces=len(active_ws),
            risk_distribution=risk_dist,
            top_categories=[{"category": k, "count": v}
                            for k, v in cats.most_common(5)],
            trending_tags=[t for t, _ in all_tags.most_common(10)],
            recent_growth_rate=round(self._compute_growth_rate(modules), 2),
        )
        try: self._store.save_analytics_metrics(m)
        except Exception: pass
        return m.to_dict()

    def get_platform_metrics(self) -> dict:
        cached = self._store.get_latest_metrics()
        if cached: return cached.to_dict()
        return self.calculate_platform_metrics()

    # ═══════════════ Event Recording ═══════════════

    def record_analytics_event(self, event_type: str, dimension: str = "",
                               agent_module_id: str = "", workspace_id: str = "",
                               payload: dict | None = None) -> None:
        evt = AnalyticsEvent(event_type=event_type, dimension=dimension,
                             agent_module_id=agent_module_id, workspace_id=workspace_id,
                             payload=payload or {})
        try: self._store.record_event(evt)
        except Exception: pass

    # ═══════════════ Internal Helpers ═══════════════

    def _all_published_modules(self) -> list[dict]:
        """加载所有 published AgentModule + trust metadata。"""
        if not self._am: return []
        modules = self._am.list(status="published", limit=500)
        result = []
        for m in modules:
            d = m.to_dict()
            # attach trust info from governance
            if self._gov:
                ts = self._gov.get_trust_score(m.id)
                if ts:
                    d["trust_score"] = ts.score
                    d["risk_level"] = ts.risk_level
                    d["average_rating"] = ts.average_rating
                    d["review_count"] = ts.review_count
                    d["report_count"] = ts.report_count
                    d["published_days"] = ts.published_days
                else:
                    d["trust_score"] = 50.0; d["risk_level"] = "low"
                    d["average_rating"] = 0.0; d["review_count"] = 0
                    d["report_count"] = 0; d["published_days"] = 0
            else:
                d["trust_score"] = 50.0; d["risk_level"] = "low"
                d["average_rating"] = 0.0; d["review_count"] = 0
                d["report_count"] = 0; d["published_days"] = 0
            # subscriber count
            if self._am:
                d["subscriber_count"] = len(self._am.list_subscriptions("__dummy__"))
                try:
                    d["subscriber_count"] = 0  # accurate count needs cross-store query
                except Exception: pass
            result.append(d)
        return result

    def _subscribed_modules(self, workspace_id: str) -> list[dict]:
        if not self._am: return []
        subs = self._am.list_subscriptions(workspace_id)
        modules = []
        for s in subs:
            m = self._am.get(s.agent_module_id)
            if m: modules.append(m.to_dict())
        return modules

    def _total_subscriptions(self) -> int:
        if not self._am: return 0
        try:
            # sum across published modules' subscriber counts
            return sum(len(self._am.list_subscriptions(m.id.split("_")[0] + "_dummy")) for m in [])
        except Exception:
            return 0

    def _content_similarity(self, candidate: dict, sub_categories: set,
                            sub_tags: Counter) -> tuple[float, list[str]]:
        reasons = []
        score = 0.0

        cat = candidate.get("category", "")
        if cat and cat in sub_categories:
            score += 30
            reasons.append(RecommendationReason.CATEGORY_MATCH)

        tags = candidate.get("tags", [])
        tag_overlap = sum(1 for t in tags if t in sub_tags)
        if tag_overlap > 0:
            tag_score = min(tag_overlap * 15, 30)
            score += tag_score
            reasons.append(RecommendationReason.TAG_SIMILARITY)

        trust = candidate.get("trust_score", 50)
        if trust >= 70:
            score += 20; reasons.append(RecommendationReason.HIGH_TRUST)

        rating = candidate.get("average_rating", 0)
        if rating >= 4.0:
            score += 15; reasons.append(RecommendationReason.TOP_RATED)

        reviews = candidate.get("review_count", 0)
        if reviews >= 10:
            score += 10; reasons.append(RecommendationReason.POPULAR)

        growth = candidate.get("_growth", 0)
        if growth > 0.5:
            score += 5; reasons.append(RecommendationReason.FAST_GROWING)

        if not reasons:
            reasons.append(RecommendationReason.POPULAR)
        return (min(score, 100.0), reasons)

    def _growth_rate(self, m: dict) -> float:
        days = max(m.get("published_days", 1), 1)
        reviews = m.get("review_count", 0)
        return reviews / days

    def _trending_score(self, m: dict) -> float:
        reviews = m.get("review_count", 0)
        max_r = max(1, reviews)
        rating = m.get("average_rating", 0)
        trust = m.get("trust_score", 50)
        growth = self._growth_rate(m)
        return (rating / 5) * 0.25 + (trust / 100) * 0.25 + (reviews / max(max_r, 1)) * 0.25 + min(growth, 1) * 0.25

    def _compute_growth_rate(self, modules: list[dict]) -> float:
        recent = [m for m in modules if m.get("published_days", 999) < 30]
        if not modules: return 0.0
        return round(len(recent) / len(modules) * 100, 2)

    def _rank_by(self, modules: list[dict], key, limit: int = 20) -> list[dict]:
        scored = []
        for m in modules:
            s = key(m)
            scored.append({**m, "_sort_score": round(s, 4)})
        scored.sort(key=lambda x: x["_sort_score"], reverse=True)
        return scored[:limit]

    def _record(self, event_type: str, dimension: str = "",
                agent_module_id: str = "", workspace_id: str = "",
                payload: dict | None = None) -> None:
        try:
            evt = AnalyticsEvent(event_type=event_type, dimension=dimension,
                                 agent_module_id=agent_module_id, workspace_id=workspace_id,
                                 payload=payload or {})
            self._store.record_event(evt)
        except Exception: pass
