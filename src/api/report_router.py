"""Report Router — 报告生成、列表、导出。"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from src.api.middleware import require_auth, require_manage
from src.api.saas_schemas import GenerateReportRequest, ReportResponse
from src.core.report import (
    Report,
    ReportData,
    ReportFormat,
    ReportStatus,
    ReportType,
    compute_period_range,
)
from src.core.usage import UsageResource

logger = logging.getLogger(__name__)


def create_report_router(report_store, usage_store, subscription_store) -> APIRouter:
    router = APIRouter(prefix="/reports", tags=["Reports"])

    # ── Helpers ─────────────────────────────────────────────────────

    def _collect_report_data(
        tenant_id: str, report_type: ReportType,
        period_start: str, period_end: str,
    ) -> ReportData:
        """从 usage_store 和 subscription_store 收集报告所需数据。"""
        from datetime import timedelta

        # 解析期间
        ps = datetime.fromisoformat(period_start)
        pe = datetime.fromisoformat(period_end)

        # 平台统计
        platform = usage_store.get_platform_stats()

        # 按资源汇总
        resource_counts: dict[str, int] = {}
        total_cost = 0
        for res in UsageResource:
            rows = usage_store._db.execute(
                """SELECT COALESCE(SUM(quantity), 0) AS qty,
                          COALESCE(SUM(cost_cents), 0) AS cost
                   FROM usage_events
                   WHERE tenant_id = ? AND resource = ?
                     AND timestamp >= ? AND timestamp < ?""",
                (tenant_id, res.value, period_start, period_end),
            ).fetchone()
            if rows:
                r = dict(rows)
                resource_counts[res.value] = int(r.get("qty", 0) or 0)
                total_cost += int(r.get("cost", 0) or 0)

        # 活跃用户
        user_row = usage_store._db.execute(
            """SELECT COUNT(DISTINCT user_id) AS cnt
               FROM usage_events
               WHERE tenant_id = ?
                 AND timestamp >= ? AND timestamp < ?""",
            (tenant_id, period_start, period_end),
        ).fetchone()
        active_users = int(dict(user_row).get("cnt", 0) or 0) if user_row else 0

        # 新用户（期间内首次出现）
        new_user_row = usage_store._db.execute(
            """SELECT COUNT(DISTINCT user_id) AS cnt
               FROM usage_events
               WHERE tenant_id = ?
                 AND timestamp >= ? AND timestamp < ?
                 AND user_id NOT IN (
                     SELECT DISTINCT user_id FROM usage_events
                     WHERE tenant_id = ? AND timestamp < ?
                 )""",
            (tenant_id, period_start, period_end, tenant_id, period_start),
        ).fetchone()
        new_users = int(dict(new_user_row).get("cnt", 0) or 0) if new_user_row else 0

        # 导入渠道
        import_channels = usage_store.get_import_channel_breakdown(
            tenant_id, days=(pe - ps).days or 30,
        )

        # 每日趋势
        daily_trend = []
        current = ps
        while current <= pe:
            d_str = current.strftime("%Y-%m-%d")
            next_d = current + timedelta(days=1)
            day_row = usage_store._db.execute(
                """SELECT resource, SUM(quantity) AS cnt
                   FROM usage_events
                   WHERE tenant_id = ? AND timestamp >= ? AND timestamp < ?
                   GROUP BY resource""",
                (tenant_id, d_str + "T00:00:00", next_d.strftime("%Y-%m-%d") + "T00:00:00"),
            ).fetchall()
            day_data: dict[str, object] = {"date": d_str}
            for r in day_row:
                rd = dict(r)
                day_data[rd["resource"]] = int(rd["cnt"] or 0)
            daily_trend.append(day_data)
            current += timedelta(days=1)

        # 订阅收入
        sub = subscription_store.get_subscription(tenant_id)
        from src.core.subscription import PLAN_PRICES, BillingCycle, PlanTier
        revenue = 0
        if sub:
            tier = PlanTier(sub.plan_tier) if hasattr(sub.plan_tier, "value") else PlanTier(str(sub.plan_tier))
            cycle = BillingCycle(sub.billing_cycle) if hasattr(sub.billing_cycle, "value") else BillingCycle(str(sub.billing_cycle))
            revenue = PLAN_PRICES.get(tier, {}).get(cycle, 0)

        # Top entities（从 usage metadata 中提取）
        top_entities: list[dict] = []

        return ReportData(
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            mrr_cents=platform.mrr_cents,
            arr_cents=platform.arr_cents,
            total_tenants=platform.total_tenants,
            active_tenants=platform.active_tenants,
            paying_tenants=platform.paying_tenants,
            trial_tenants=platform.trial_tenants,
            conversion_rate=platform.conversion_rate,
            churn_rate=platform.churn_rate,
            retention_rate=platform.retention_rate,
            total_memories_created=resource_counts.get(UsageResource.MEMORY.value, 0),
            total_llm_calls=resource_counts.get(UsageResource.LLM_CALL.value, 0),
            total_embedding_calls=resource_counts.get(UsageResource.EMBEDDING.value, 0),
            total_searches=resource_counts.get(UsageResource.SEARCH.value, 0),
            total_imports=resource_counts.get(UsageResource.IMPORT.value, 0),
            total_syncs=resource_counts.get(UsageResource.SYNC.value, 0),
            total_coach_sessions=resource_counts.get(UsageResource.COACH.value, 0),
            total_cost_cents=total_cost,
            total_revenue_cents=revenue,
            net_revenue_cents=revenue - total_cost,
            margin_percent=round((revenue - total_cost) / revenue * 100, 1) if revenue > 0 else 0.0,
            active_users=active_users,
            new_users=new_users,
            top_entities=top_entities,
            import_channels=import_channels.get("channels", {}),
            daily_usage_trend=daily_trend,
        )

    # ── 1. POST /reports/generate ───────────────────────────────────

    @router.post("/generate", status_code=201, response_model=ReportResponse)
    async def generate_report(
        body: GenerateReportRequest,
        token=Depends(require_auth),
    ):
        """生成报告（weekly/monthly/quarterly）。"""
        try:
            report_type = ReportType(body.report_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid report_type: '{body.report_type}'. Valid: weekly, monthly, quarterly",
            )
        try:
            report_format = ReportFormat(body.format)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid format: '{body.format}'. Valid: json, csv",
            )

        period_start, period_end = compute_period_range(report_type)

        report = Report(
            tenant_id=token.workspace_id,
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            format=report_format,
            status=ReportStatus.GENERATING,
        )

        try:
            report_id = report_store.create_report(report)

            # 收集数据
            data = _collect_report_data(
                token.workspace_id, report_type, period_start, period_end,
            )

            # 更新报告
            report.data = data
            report.status = ReportStatus.READY

            import json
            report_store.update_report(
                token.workspace_id, report_id,
                {"status": "ready", "data_json": json.dumps(data.as_dict(), ensure_ascii=False)},
            )

            # 如果请求 CSV，自动导出
            if report_format == ReportFormat.CSV:
                report.data = data
                filepath = report_store.export_csv(report)
                report_store.update_report(
                    token.workspace_id, report_id,
                    {"file_path": filepath, "format": "csv"},
                )
            elif report_format == ReportFormat.JSON:
                filepath = report_store.export_json(report)
                report_store.update_report(
                    token.workspace_id, report_id,
                    {"file_path": filepath, "format": "json"},
                )

            final = report_store.get_report(token.workspace_id, report_id)
            return final.as_dict() if final else report.as_dict()

        except Exception as e:
            logger.error("report:generate_failed", extra={"error": str(e), "tenant_id": token.workspace_id})
            # 尝试更新状态为 failed
            try:
                report_store.update_report(
                    token.workspace_id, report_id,
                    {"status": "failed"},
                )
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")

    # ── 2. GET /reports ─────────────────────────────────────────────

    @router.get("", response_model=list[ReportResponse])
    async def list_reports(
        report_type: str | None = Query(default=None, description="weekly | monthly | quarterly"),
        limit: int = Query(default=20, ge=1, le=100),
        token=Depends(require_auth),
    ):
        """列出报告。"""
        try:
            reports = report_store.list_reports(
                token.workspace_id, report_type=report_type, limit=limit,
            )
            return [r.as_dict() for r in reports]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to list reports: {str(e)}")

    # ── 3. GET /reports/{report_id} ─────────────────────────────────

    @router.get("/{report_id}", response_model=ReportResponse)
    async def get_report(report_id: str, token=Depends(require_auth)):
        """获取报告详情。"""
        report = report_store.get_report(token.workspace_id, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return report.as_dict()

    # ── 4. GET /reports/{report_id}/export ──────────────────────────

    @router.get("/{report_id}/export")
    async def export_report(
        report_id: str,
        format: str = Query(default="json", description="json | csv"),
        token=Depends(require_auth),
    ):
        """导出报告文件。"""
        report = report_store.get_report(token.workspace_id, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")

        try:
            fmt = ReportFormat(format)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid format: '{format}'")

        try:
            if fmt == ReportFormat.CSV:
                filepath = report_store.export_csv(report)
                media_type = "text/csv"
            else:
                filepath = report_store.export_json(report)
                media_type = "application/json"

            # 更新报告文件路径
            report_store.update_report(
                token.workspace_id, report_id,
                {"file_path": filepath, "format": format},
            )

            return FileResponse(
                path=filepath,
                media_type=media_type,
                filename=f"{report.report_type.value}_{report.period_start}_{report.period_end}.{format}",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to export: {str(e)}")

    # ── 5. DELETE /reports/{report_id} ──────────────────────────────

    @router.delete("/{report_id}")
    async def delete_report(report_id: str, token=Depends(require_manage)):
        """删除报告及导出文件。"""
        ok = report_store.delete_report(token.workspace_id, report_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Report not found")
        return {"status": "deleted", "report_id": report_id}

    return router
