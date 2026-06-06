"""Tests for Alert Domain + AlertStore Adapter + Alert Router.

覆盖:
- AlertRule CRUD
- AlertEvent 记录与查询
- 预设规则初始化
- 条件评估逻辑
"""
import pytest
from datetime import datetime, timezone, timedelta

from src.core.alert import (
    AlertCondition,
    AlertEvent,
    AlertMetric,
    AlertRule,
    AlertSeverity,
    NotificationChannel,
    get_preset_rules,
)
from src.adapters.alert_store import AlertStoreAdapter
from src.adapters.config import Settings


class TestAlertDomain:
    """核心域：AlertRule / AlertEvent 数据类。"""

    def test_alert_rule_creation(self):
        rule = AlertRule(
            tenant_id="tnt_test",
            name="test-rule",
            metric=AlertMetric.QUEUE_DEPTH,
            condition=AlertCondition.GT,
            threshold=100.0,
        )
        assert rule.tenant_id == "tnt_test"
        assert rule.name == "test-rule"
        assert rule.metric == AlertMetric.QUEUE_DEPTH
        assert rule.severity == AlertSeverity.WARNING  # default
        assert rule.cooldown_minutes == 60  # default
        assert rule.enabled is True

        d = rule.as_dict()
        assert d["id"].startswith("alr_")
        assert d["metric"] == "queue_depth"
        assert d["condition"] == "gt"

    def test_alert_event_creation(self):
        event = AlertEvent(
            tenant_id="tnt_test",
            rule_id="alr_abc",
            rule_name="test-rule",
            metric=AlertMetric.MEMORY_USAGE_PCT,
            current_value=85.0,
            threshold=80.0,
            severity=AlertSeverity.WARNING,
            channel=NotificationChannel.SYSTEM,
            message="Memory usage exceeded 80%",
        )
        assert event.id.startswith("ale_")
        assert event.metric == AlertMetric.MEMORY_USAGE_PCT
        assert event.current_value == 85.0
        assert event.acknowledged is False

        d = event.as_dict()
        assert d["severity"] == "warning"
        assert d["channel"] == "system"

    def test_get_preset_rules(self):
        rules = get_preset_rules("tnt_test")
        assert len(rules) == 6
        rule_names = {r.name for r in rules}
        assert "memory-limit" in rule_names
        assert "memory-critical" in rule_names
        assert "queue-delay" in rule_names
        assert "dlq-backlog" in rule_names
        assert "cost-spike" in rule_names
        assert "anomaly-calls" in rule_names

        # 检查严重度
        critical_rules = [r for r in rules if r.severity == AlertSeverity.CRITICAL]
        assert len(critical_rules) == 2  # memory-critical + dlq-backlog

    def test_condition_evaluation(self):
        """测试条件评估逻辑。"""
        from src.adapters.usage_collector import UsageCollector

        rule_gt = AlertRule(
            tenant_id="tnt", name="test", metric=AlertMetric.QUEUE_DEPTH,
            condition=AlertCondition.GT, threshold=100.0,
        )
        assert UsageCollector._evaluate_condition(rule_gt, 150.0) is True
        assert UsageCollector._evaluate_condition(rule_gt, 100.0) is False
        assert UsageCollector._evaluate_condition(rule_gt, 50.0) is False

        rule_gte = AlertRule(
            tenant_id="tnt", name="test", metric=AlertMetric.QUEUE_DEPTH,
            condition=AlertCondition.GTE, threshold=100.0,
        )
        assert UsageCollector._evaluate_condition(rule_gte, 100.0) is True

        rule_lt = AlertRule(
            tenant_id="tnt", name="test", metric=AlertMetric.QUEUE_DEPTH,
            condition=AlertCondition.LT, threshold=100.0,
        )
        assert UsageCollector._evaluate_condition(rule_lt, 50.0) is True
        assert UsageCollector._evaluate_condition(rule_lt, 100.0) is False

        rule_lte = AlertRule(
            tenant_id="tnt", name="test", metric=AlertMetric.QUEUE_DEPTH,
            condition=AlertCondition.LTE, threshold=100.0,
        )
        assert UsageCollector._evaluate_condition(rule_lte, 100.0) is True


class TestAlertStoreAdapter:
    """AlertStoreAdapter 集成测试（使用内存数据库）。"""

    @pytest.fixture
    def store(self):
        settings = Settings(sqlite_db_path=":memory:")
        s = AlertStoreAdapter(settings)
        yield s
        s.close()

    def test_create_and_get_rule(self, store):
        rule = AlertRule(
            tenant_id="tnt_001",
            name="dlq-alert",
            metric=AlertMetric.DLQ_BACKLOG,
            condition=AlertCondition.GT,
            threshold=20.0,
            severity=AlertSeverity.CRITICAL,
            channel=NotificationChannel.BOTH,
        )
        rid = store.create_rule(rule)
        assert rid == rule.id

        fetched = store.get_rule("tnt_001", rule.id)
        assert fetched is not None
        assert fetched.name == "dlq-alert"
        assert fetched.severity == AlertSeverity.CRITICAL

    def test_list_rules(self, store):
        store.create_rule(AlertRule(tenant_id="tnt_001", name="r1", metric=AlertMetric.QUEUE_DEPTH, condition=AlertCondition.GT, threshold=10))
        store.create_rule(AlertRule(tenant_id="tnt_001", name="r2", metric=AlertMetric.DLQ_BACKLOG, condition=AlertCondition.GT, threshold=20))
        store.create_rule(AlertRule(tenant_id="tnt_002", name="r3", metric=AlertMetric.QUEUE_DEPTH, condition=AlertCondition.GT, threshold=30))

        rules_tnt1 = store.list_rules("tnt_001")
        assert len(rules_tnt1) == 2

        rules_tnt2 = store.list_rules("tnt_002")
        assert len(rules_tnt2) == 1

        # 跨租户隔离
        for r in rules_tnt1:
            assert r.tenant_id == "tnt_001"

    def test_update_rule(self, store):
        rule = AlertRule(tenant_id="tnt_001", name="original", metric=AlertMetric.QUEUE_DEPTH, condition=AlertCondition.GT, threshold=50)
        store.create_rule(rule)

        updated = store.update_rule("tnt_001", rule.id, {"threshold": 200.0, "severity": "critical"})
        assert updated is not None
        assert updated.threshold == 200.0
        assert updated.severity == AlertSeverity.CRITICAL

        # 不可更新的 ID
        assert store.update_rule("tnt_001", "nonexistent", {}) is None

    def test_delete_rule(self, store):
        rule = AlertRule(tenant_id="tnt_001", name="to-delete", metric=AlertMetric.QUEUE_DEPTH, condition=AlertCondition.GT, threshold=10)
        store.create_rule(rule)
        assert store.delete_rule("tnt_001", rule.id) is True
        assert store.get_rule("tnt_001", rule.id) is None
        assert store.delete_rule("tnt_001", "nonexistent") is False

    def test_record_and_list_events(self, store):
        rule = AlertRule(tenant_id="tnt_001", name="test-rule", metric=AlertMetric.QUEUE_DEPTH, condition=AlertCondition.GT, threshold=100)
        store.create_rule(rule)

        e1 = AlertEvent(
            tenant_id="tnt_001", rule_id=rule.id, rule_name=rule.name,
            metric=AlertMetric.QUEUE_DEPTH, current_value=150.0, threshold=100.0,
            severity=AlertSeverity.WARNING, channel=NotificationChannel.SYSTEM,
            message="Queue depth exceeded",
        )
        store.record_event(e1)

        e2 = AlertEvent(
            tenant_id="tnt_001", rule_id=rule.id, rule_name=rule.name,
            metric=AlertMetric.QUEUE_DEPTH, current_value=200.0, threshold=100.0,
            severity=AlertSeverity.CRITICAL, channel=NotificationChannel.BOTH,
            message="Queue depth critical",
        )
        store.record_event(e2)

        events = store.list_events("tnt_001")
        assert len(events) == 2

        # 按严重度过滤
        critical_events = store.list_events("tnt_001", severity="critical")
        assert len(critical_events) == 1
        assert critical_events[0].severity == AlertSeverity.CRITICAL

        # 按规则过滤
        rule_events = store.list_events("tnt_001", rule_id=rule.id)
        assert len(rule_events) == 2

    def test_acknowledge_event(self, store):
        rule = AlertRule(tenant_id="tnt_001", name="test", metric=AlertMetric.QUEUE_DEPTH, condition=AlertCondition.GT, threshold=10)
        store.create_rule(rule)

        event = AlertEvent(
            tenant_id="tnt_001", rule_id=rule.id, rule_name=rule.name,
            metric=AlertMetric.QUEUE_DEPTH, current_value=50, threshold=10,
            severity=AlertSeverity.WARNING, channel=NotificationChannel.SYSTEM,
            message="Test",
        )
        store.record_event(event)
        assert store.acknowledge_event("tnt_001", event.id) is True
        assert store.acknowledge_event("tnt_001", "nonexistent") is False

        events = store.list_events("tnt_001")
        assert events[0].acknowledged is True

    def test_seed_presets(self, store):
        """预设规则初始化：仅在无规则时执行。"""
        # 首次
        ids = store.seed_presets("tnt_001")
        assert len(ids) == 6
        rules = store.list_rules("tnt_001")
        assert len(rules) == 6

        # 第二次：跳过
        ids2 = store.seed_presets("tnt_001")
        assert len(ids2) == 0
        rules2 = store.list_rules("tnt_001")
        assert len(rules2) == 6  # 不重复

    def test_tenant_isolation(self, store):
        """跨租户数据隔离。"""
        store.create_rule(AlertRule(tenant_id="tnt_a", name="a-rule", metric=AlertMetric.QUEUE_DEPTH, condition=AlertCondition.GT, threshold=10))
        store.create_rule(AlertRule(tenant_id="tnt_b", name="b-rule", metric=AlertMetric.QUEUE_DEPTH, condition=AlertCondition.GT, threshold=20))

        assert len(store.list_rules("tnt_a")) == 1
        assert len(store.list_rules("tnt_b")) == 1
        assert store.get_rule("tnt_a", store.list_rules("tnt_b")[0].id) is None

    def test_active_rules(self, store):
        """get_active_rules: 已启用且冷却期外。"""
        now = datetime.now(timezone.utc)
        # 活跃规则
        rule1 = AlertRule(tenant_id="tnt_001", name="active", metric=AlertMetric.QUEUE_DEPTH, condition=AlertCondition.GT, threshold=10)
        store.create_rule(rule1)

        # 禁用规则
        rule2 = AlertRule(tenant_id="tnt_001", name="disabled", metric=AlertMetric.QUEUE_DEPTH, condition=AlertCondition.GT, threshold=10, enabled=False)
        store.create_rule(rule2)

        # 冷却期内的规则
        rule3 = AlertRule(
            tenant_id="tnt_001", name="cooldown", metric=AlertMetric.QUEUE_DEPTH,
            condition=AlertCondition.GT, threshold=10,
            last_triggered_at=now,
        )
        store.create_rule(rule3)

        active = store.get_active_rules("tnt_001")
        assert len(active) == 1
        assert active[0].name == "active"
