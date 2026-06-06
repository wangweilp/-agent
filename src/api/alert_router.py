"""Alert Router — 告警规则管理 + 告警历史查询。"""

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.middleware import require_auth, require_manage
from src.api.saas_schemas import (
    AlertEventResponse,
    AlertRuleResponse,
    CreateAlertRuleRequest,
    TestAlertResponse,
    UpdateAlertRuleRequest,
)
from src.core.alert import (
    AlertCondition,
    AlertEvent,
    AlertMetric,
    AlertRule,
    AlertSeverity,
    NotificationChannel,
)


def create_alert_router(alert_store, usage_store) -> APIRouter:
    router = APIRouter(prefix="/alerts", tags=["Alerts"])

    # ── 1. POST /alerts/rules ───────────────────────────────────────

    @router.post("/rules", status_code=201, response_model=AlertRuleResponse)
    async def create_rule(
        body: CreateAlertRuleRequest,
        token=Depends(require_manage),
    ):
        """创建告警规则。"""
        try:
            metric = AlertMetric(body.metric)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid metric: '{body.metric}'. Valid: {[m.value for m in AlertMetric]}",
            )
        try:
            condition = AlertCondition(body.condition)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid condition: '{body.condition}'. Valid: {[c.value for c in AlertCondition]}",
            )

        rule = AlertRule(
            tenant_id=token.workspace_id,
            name=body.name,
            metric=metric,
            condition=condition,
            threshold=body.threshold,
            severity=AlertSeverity(body.severity),
            channel=NotificationChannel(body.channel),
            cooldown_minutes=body.cooldown_minutes,
        )
        try:
            alert_store.create_rule(rule)
            return rule.as_dict()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create rule: {str(e)}")

    # ── 2. GET /alerts/rules ────────────────────────────────────────

    @router.get("/rules", response_model=list[AlertRuleResponse])
    async def list_rules(
        enabled_only: bool = Query(default=False),
        token=Depends(require_auth),
    ):
        """列出当前租户的告警规则。"""
        try:
            rules = alert_store.list_rules(token.workspace_id, enabled_only=enabled_only)
            return [r.as_dict() for r in rules]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to list rules: {str(e)}")

    # ── 3. GET /alerts/rules/{rule_id} ──────────────────────────────

    @router.get("/rules/{rule_id}", response_model=AlertRuleResponse)
    async def get_rule(rule_id: str, token=Depends(require_auth)):
        """获取单个告警规则。"""
        rule = alert_store.get_rule(token.workspace_id, rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        return rule.as_dict()

    # ── 4. PATCH /alerts/rules/{rule_id} ────────────────────────────

    @router.patch("/rules/{rule_id}", response_model=AlertRuleResponse)
    async def update_rule(
        rule_id: str,
        body: UpdateAlertRuleRequest,
        token=Depends(require_manage),
    ):
        """更新告警规则。"""
        updates = body.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        rule = alert_store.update_rule(token.workspace_id, rule_id, updates)
        if rule is None:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        return rule.as_dict()

    # ── 5. DELETE /alerts/rules/{rule_id} ───────────────────────────

    @router.delete("/rules/{rule_id}")
    async def delete_rule(rule_id: str, token=Depends(require_manage)):
        """删除告警规则。"""
        ok = alert_store.delete_rule(token.workspace_id, rule_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        return {"status": "deleted", "rule_id": rule_id}

    # ── 6. GET /alerts/events ───────────────────────────────────────

    @router.get("/events", response_model=list[AlertEventResponse])
    async def list_events(
        rule_id: str | None = None,
        severity: str | None = None,
        acknowledged: bool | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        token=Depends(require_auth),
    ):
        """列出告警历史事件。"""
        try:
            events = alert_store.list_events(
                tenant_id=token.workspace_id,
                rule_id=rule_id,
                severity=severity,
                acknowledged=acknowledged,
                limit=limit,
                offset=offset,
            )
            return [e.as_dict() for e in events]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to list events: {str(e)}")

    # ── 7. POST /alerts/events/{event_id}/acknowledge ───────────────

    @router.post("/events/{event_id}/acknowledge")
    async def acknowledge_event(event_id: str, token=Depends(require_auth)):
        """确认告警。"""
        ok = alert_store.acknowledge_event(token.workspace_id, event_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Alert event not found")
        return {"status": "acknowledged", "event_id": event_id}

    # ── 8. POST /alerts/test ─────────────────────────────────────────

    @router.post("/test", response_model=TestAlertResponse)
    async def test_alert(
        channel: str = Query(default="system", description="system | email | both"),
        token=Depends(require_manage),
    ):
        """测试告警通道。"""
        try:
            ch = NotificationChannel(channel)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid channel: '{channel}'. Valid: system, email, both",
            )

        test_event = AlertEvent(
            tenant_id=token.workspace_id,
            rule_id="test",
            rule_name="test-alert",
            metric=AlertMetric.QUEUE_DEPTH,
            current_value=0,
            threshold=0,
            severity=AlertSeverity.INFO,
            channel=ch,
            message="This is a test alert from the Growth & Analytics Center.",
        )

        try:
            alert_store.record_event(test_event)
            return {
                "success": True,
                "message": f"Test alert sent via {ch.value}",
                "channel": ch.value,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Test alert failed: {str(e)}",
                "channel": ch.value,
            }

    # ── 9. POST /alerts/rules/presets ────────────────────────────────

    @router.post("/rules/presets", status_code=201)
    async def seed_presets(token=Depends(require_manage)):
        """为当前租户初始化预设告警规则。"""
        try:
            ids = alert_store.seed_presets(token.workspace_id)
            return {"status": "seeded" if ids else "skipped", "rule_ids": ids}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to seed presets: {str(e)}")

    return router
