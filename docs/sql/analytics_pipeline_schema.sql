-- Phase 25 — Dashboard V2 Analytics Pipeline Schema
--
-- 4 张独立 Analytics 表，Dashboard V2 不再依赖 metadata_json 推导。
-- 幂等 CREATE TABLE IF NOT EXISTS，与项目现有 schema 演进方式一致。
--
-- 用法:
--   sqlite3 data/agent_memory.db < docs/sql/analytics_pipeline_schema.sql
-- 或由 AnalyticsStore._init_schema() 自动执行。

-- ══════════════════════════════════════════════════════════════════════
-- 1. analytics_user_activity_daily — 用户日活聚合
--    用途: DAU / WAU / MAU / D1·D7·D30 留存 / 激活率
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS analytics_user_activity_daily (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    workspace_id    TEXT NOT NULL DEFAULT '',
    user_id         TEXT NOT NULL,
    event_date      TEXT NOT NULL,              -- YYYY-MM-DD
    sessions        INTEGER NOT NULL DEFAULT 0,
    messages        INTEGER NOT NULL DEFAULT 0,
    active_minutes  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_auad_tenant_date ON analytics_user_activity_daily(tenant_id, event_date);
CREATE INDEX IF NOT EXISTS idx_auad_user_date ON analytics_user_activity_daily(user_id, event_date);
CREATE INDEX IF NOT EXISTS idx_auad_date ON analytics_user_activity_daily(event_date);
CREATE INDEX IF NOT EXISTS idx_auad_workspace ON analytics_user_activity_daily(workspace_id, event_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_auad_unique ON analytics_user_activity_daily(tenant_id, user_id, event_date);

-- ══════════════════════════════════════════════════════════════════════
-- 2. analytics_agent_runs — Agent 运行记录
--    用途: Agent 成功率 / 失败率 / P50·P95·P99 / Agent 排行
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS analytics_agent_runs (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    workspace_id        TEXT NOT NULL DEFAULT '',
    agent_name          TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL,          -- success | failed
    duration_ms         REAL NOT NULL DEFAULT 0,
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    completion_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd            REAL NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_aar_tenant_created ON analytics_agent_runs(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_aar_status ON analytics_agent_runs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_aar_agent ON analytics_agent_runs(agent_name, created_at);
CREATE INDEX IF NOT EXISTS idx_aar_workspace ON analytics_agent_runs(workspace_id, created_at);

-- ══════════════════════════════════════════════════════════════════════
-- 3. analytics_memory_events — Memory 事件流
--    用途: Memory 增长 / 命中率 / 类型分布 / 净增
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS analytics_memory_events (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    workspace_id    TEXT NOT NULL DEFAULT '',
    memory_type     TEXT NOT NULL DEFAULT '',   -- episodic | semantic | reflect
    event_type      TEXT NOT NULL,               -- INSERT | UPDATE | DELETE | HIT
    hit             INTEGER NOT NULL DEFAULT 0,  -- 0 | 1
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ame_tenant_type ON analytics_memory_events(tenant_id, event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_ame_created ON analytics_memory_events(created_at);
CREATE INDEX IF NOT EXISTS idx_ame_workspace ON analytics_memory_events(workspace_id, created_at);

-- ══════════════════════════════════════════════════════════════════════
-- 4. analytics_token_usage_daily — Token 成本日聚合
--    用途: 日成本 / 月成本 / Burn Rate / Token 趋势
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS analytics_token_usage_daily (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    workspace_id        TEXT NOT NULL DEFAULT '',
    event_date          TEXT NOT NULL,          -- YYYY-MM-DD
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    completion_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd            REAL NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_atud_tenant_date ON analytics_token_usage_daily(tenant_id, event_date);
CREATE INDEX IF NOT EXISTS idx_atud_date ON analytics_token_usage_daily(event_date);
CREATE INDEX IF NOT EXISTS idx_atud_workspace ON analytics_token_usage_daily(workspace_id, event_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_atud_unique ON analytics_token_usage_daily(tenant_id, workspace_id, event_date);
