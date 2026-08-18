# 分步提示词使用说明

## 为什么分步？

整个项目文档量很大（CLAUDE.md + 4 份设计文档 ≈ 2 万 token），一次性全喂给 Claude Code 会严重压缩有效工作上下文。

## 怎么用？

**每次开新的 Claude Code 对话，粘贴对应 step 文件内容即可。** 每个 step 自包含——所需的所有架构约束、代码示例、验收标准都写在里面，不需要前一步的完整上下文。

## 投喂顺序

| 步骤 | 文件 | 投喂内容 |
|------|------|---------|
| 第 1 步 | `step-1-init.md` | 粘贴全文 |
| 第 2 步 | `step-2-architecture.md` | 粘贴全文 |
| 第 3 步 | `step-3-infrastructure.md` | 粘贴全文 |
| 第 4 步 | `step-4-core-engines.md` | 粘贴全文 |
| 第 5 步 | `step-5-agents-api-dashboard.md` | 粘贴全文 |
| 第 6 步 | `step-6-final.md` | 粘贴全文 |

## 规则

- **严格按顺序**：步骤 3 依赖步骤 2 产出的文件，不可跳步
- **每个 step 一个对话**：不要在同一个对话里连续投喂两个 step（会累积上下文污染）
- **每步投喂前检查**：确认上一步的代码已 `git commit`
- **遇到问题就停**：不要埋头继续下一步，先修好当前步骤的问题

## 额外可投（非必须）

如果某一步需要更详细的规范参考，可以选择性追加投喂：
- `docs/ARCHITECTURE.md` — 当需要确认模块边界时
- `docs/DESIGN.md` — 当需要确认 Memory 字段或 Agent 循环细节时
- `CLAUDE.md` — 当 Claude 违反了架构隔离规则时（作为追加约束）

---
## Quick Start: Enterprise AI Agent Demo

```bash
# Activate the project virtualenv first (required — bare `python` must point to .venv)
cd D:\dma\day2
.\.venv\Scripts\Activate.ps1        # PowerShell
# or: source .venv/bin/activate      # bash/Linux

# Verify it points to the venv
python -c "import sys; print(sys.executable)"   # -> D:\dma\day2\.venv\Scripts\python.exe

# First-time setup — install dependencies (must match Python 3.11, see .python-version)
# Build venv once:  python -m venv .venv   &&  .\.venv\Scripts\Activate.ps1
# Production deps only:
python -m pip install -r requirements.txt
# Dev + test deps (adds pytest / pytest-asyncio on top of production deps):
python -m pip install -r requirements-dev.txt

# Run the test suite (full suite: tests/)
python -m pytest

# Start backend (ASGI entry is main:app)
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# Start frontend (in separate terminal)
cd frontend && npm run dev

# Initialize demo data
python scripts/seed_agent_demo.py --apply

# Open browser
# http://localhost:3000/agents/scenarios

# API health checks
# http://127.0.0.1:8000/health/unified
# http://127.0.0.1:8000/openapi.json
# http://127.0.0.1:8000/docs
```

> **解释器说明**：本项目使用 `.venv`（Python 3.11.9）。若在项目目录直接执行 `python` 仍指到其他 Python（如 TRAE SOLO 内置 3.10），是因为该 shell 未激活 venv。执行上面的 `Activate.ps1` 即可。若已配置 PowerShell profile 自动激活（`~Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1`），进入 `D:\dma\day2` 后 `python` 会自动指向 `.venv`。

See [Step 20-D Demo Script](docs/STEP20D_DEMO_SCRIPT.md) for full demo walkthrough.

---

## Agent Marketplace Quick Start

```bash
# Marketplace 页面
# http://localhost:3000/agent-marketplace

# 已安装 Agent 管理
# http://localhost:3000/agent-marketplace/installations

# Internal Agent Center（Agent 执行）
# http://localhost:3000/agents

# 业务场景
# http://localhost:3000/agents/scenarios
```

**页面边界**：
- `/agents` — **执行中心**（Internal Agent Center）：运行 Agent、执行 Workflow、运行 Scenario
- `/agent-marketplace` — **发现与安装中心**（Agent Marketplace）：浏览、安装、配置、治理 Agent
- 两者通过 `agent_id` 关联，职责完全分离

**后端 API**：
- `GET /agent-marketplace` — 浏览 Marketplace（支持 category/department/status/installed 过滤）
- `GET /agent-marketplace/{id}` — Agent 详情 + 安装状态
- `POST /agent-marketplace/{id}/install` — 安装 Agent（admin/owner）
- `GET /agent-marketplace/installations` — 已安装列表
- `PATCH /agent-marketplace/installations/{id}/config` — 更新安装配置
- `GET /agent-marketplace/analytics/summary` — Marketplace 分析概览（MVP）

**测试**：
```bash
# Marketplace 专项测试（156 tests）
python -m pytest tests/test_agents/test_marketplace_api.py tests/test_agents/test_marketplace_store.py tests/test_agents/test_marketplace_security.py -v

# 全量回归（647 tests）
python -m pytest tests/test_security.py tests/test_agents/ tests/test_rbac/ tests/test_saas/ -v

# 前端检查
cd frontend
npx tsc --noEmit
npx eslint app/agent-marketplace/ components/agents/AgentU* components/agents/Marketplace* types/marketplace.ts services/marketplace.ts --ext .ts,.tsx
```

**文档**：
- [Step 20-D Demo Script](docs/STEP20D_DEMO_SCRIPT.md)
- [Step 21 Marketplace Demo Script](docs/STEP21_MARKETPLACE_DEMO_SCRIPT.md)
- [Roadmap](docs/ROADMAP.md)

**边界说明**：
- Agent Marketplace 当前是企业内部 Agent 分发中心（6 内置 Agent + Developer Agent）
- **不支持**第三方开发者上传 / Agent SDK / 外部审核 / Revenue Share / 真实支付 — 这些是 Step 22 Open Platform 范围
- Usage / Billing / Analytics 为 MVP 级别计量，非真实计费

---

## Open Platform Quick Start

```bash
# Developer Console
# http://localhost:3000/developer

# Developer 注册
# http://localhost:3000/developer/register

# API Key 管理
# http://localhost:3000/developer/api-keys

# Agent Submission 管理
# http://localhost:3000/developer/agents

# 创建新 Submission
# http://localhost:3000/developer/agents/new

# Admin Review 审核队列
# http://localhost:3000/admin/agent-submissions

# Developer Agent 在 Marketplace
# http://localhost:3000/agent-marketplace/{id}
```

**页面路径**：

| 路径 | 职责 |
|------|------|
| `/developer` | Developer Console — 开发者身份与 profile |
| `/developer/register` | Developer 注册 |
| `/developer/api-keys` | API Key 创建与管理 |
| `/developer/agents` | Agent Submission 列表 |
| `/developer/agents/new` | 创建新 Submission（Manifest 编辑） |
| `/developer/agents/{id}` | Submission 详情与状态管理 |
| `/admin/agent-submissions` | 管理员审核队列 |
| `/admin/agent-submissions/{id}` | 审核详情与 Publish |
| `/agent-marketplace/{id}` | Marketplace 详情（含 Developer Agent） |

**核心 API**：

Developer API (`/developers`)：
- `POST /developers/register` — 注册 Developer Account
- `GET /developers/me` — 获取当前开发者信息
- `POST /developers/api-keys` — 创建 API Key（raw_key 仅此一次返回）
- `GET /developers/api-keys` — 列出 API Keys（不暴露 key_hash）
- `DELETE /developers/api-keys/{id}` — 撤销 API Key
- `POST /developers/agents` — 创建 Agent Submission（draft）
- `GET /developers/agents` — 列出自己的 Submissions
- `GET /developers/agents/{id}` — 查看 Submission 详情
- `PATCH /developers/agents/{id}` — 编辑 draft manifest
- `POST /developers/agents/{id}/validate` — 校验 manifest
- `POST /developers/agents/{id}/submit` — 提交审核
- `POST /developers/agents/{id}/withdraw` — 撤回提交

Admin Review API (`/admin/agent-submissions`)：
- `GET /admin/agent-submissions` — 审核队列（按 status/tenant/developer 筛选）
- `GET /admin/agent-submissions/{id}` — Submission 详情（含 developer / validation / review record）
- `GET /admin/agent-submissions/{id}/reviews` — 审核记录
- `POST /admin/agent-submissions/{id}/start-review` — 开始审核
- `POST /admin/agent-submissions/{id}/approve` — 通过审核
- `POST /admin/agent-submissions/{id}/reject` — 拒绝（notes 必填）
- `POST /admin/agent-submissions/{id}/request-changes` — 要求修改（notes 必填）
- `POST /admin/agent-submissions/{id}/publish` — 发布到 Marketplace

**测试**：

```bash
# Open Platform 专项测试
python -m pytest tests/test_open_platform/ -v

# 全量回归（含 security + agents + rbac + saas + open_platform）
python -m pytest tests/test_security.py tests/test_agents/ tests/test_rbac/ tests/test_saas/ tests/test_open_platform/ -q
```

**文档**：
- [Step 20-D Demo Script](docs/STEP20D_DEMO_SCRIPT.md)
- [Step 21 Marketplace Demo Script](docs/STEP21_MARKETPLACE_DEMO_SCRIPT.md)
- [Step 22 Open Platform Demo Script](docs/STEP22_OPEN_PLATFORM_DEMO_SCRIPT.md)
- [Roadmap](docs/ROADMAP.md)

**边界说明**：
- Open Platform 支持 Developer Console / Submission / Admin Review / Publish to Marketplace
- ✅ Manifest-first（MVP 不执行第三方代码）
- ✅ API Key auth 已完成 — X-Cognitive-API-Key header, scope enforcement, admin routes denied
- ❌ 不执行 package_url — 仅存储，不下载/解压/运行
- ❌ 不注册 AgentRuntime — Publish 是纯数据映射
- ❌ 不自动安装 — 需要管理员在 Marketplace 手动安装
- ❌ 不做真实支付 — Usage/Billing MVP 级别计量
- ❌ 不做 Revenue Share — 所有 Agent pricing_model=free

---

## Step 23：Runtime / SDK / Ecosystem Hardening

Step 23 建立 Developer Agent 的安全运行时准入体系 — API Key、Manifest SDK、Package 静态校验、Sandbox Policy、Runtime Binding、Simulation dry-run。**不执行第三方代码。**

**页面路径**：

| 路径 | 职责 |
|------|------|
| `/developer/api-keys` | API Key 创建与管理（scope enforcement） |
| `/developer/agents/new` | Manifest 编辑（runtime_type=manifest_only） |
| `/admin/agent-submissions/[id]` | Package Validation Panel + Review |
| `/admin/runtime` | Runtime Adapters / Bindings / Sandbox Policies / Readiness Guide |
| `/agent-marketplace` | Developer Agent 发现/安装/配置 |

**核心 API**：

Developer：
- `GET /developers/agent-manifest/schema` — Manifest JSON Schema
- `POST /developers/agent-manifest/validate` — 静态校验（不创建 submission）
- `POST /developers/marketplace-agents/{id}/simulate` — Simulation dry-run

Admin：
- `POST /admin/agent-submissions/{id}/validate-package` — Package 静态校验
- `GET /admin/agent-submissions/{id}/package-validation` — 校验结果
- `GET /admin/runtime/adapters` — Runtime Adapter 列表
- `GET /admin/runtime/bindings` — Runtime Binding 列表
- `POST /admin/runtime/bindings` — 创建 Binding
- `POST /admin/runtime/bindings/{id}/enable` — Enable（不执行代码）
- `POST /admin/runtime/bindings/{id}/sandbox-policy` — 绑定 Sandbox Policy
- `GET /admin/runtime/developer-agents/{id}/eligibility` — Runtime Eligibility
- `GET /admin/sandbox-policies` — Sandbox Policy 列表

**non-execution guarantees**：
- ❌ 不下载 package / 不解压 / 不执行
- ❌ 不执行 entrypoint
- ❌ 不联网（所有 validator/adapter 不发起 HTTP 请求）
- ❌ 不调用 AgentRuntime / 不注册 AgentRegistry
- ❌ install ≠ execution / publish ≠ runtime enabled
- ✅ Simulation 是 deterministic dry-run

**测试状态**：

| 套件 | 结果 |
|------|------|
| Step23 Security/Runtime 专项 | 77 passed |
| Open Platform 全量 | 678 passed |
| 后端全量回归 | 1325 passed |

**文档**：
- [Step 23 Demo Script](docs/STEP23_RUNTIME_SDK_DEMO_SCRIPT.md)
- [Step 23-A Architecture Audit](docs/STEP23A_ARCHITECTURE_AUDIT.md)
- [Step 23-I Security Tests](docs/STEP23I_SECURITY_RUNTIME_TESTS.md)
- [Roadmap](docs/ROADMAP.md)

---

## Step 24 Runtime Safety Layer

Step 24 builds developer agent execution safety gates. **All execution entrypoints fail-closed.** No production sandbox yet. No external code execution yet. `/runtime/agents/{id}/execute` is blocked by design.

| Step | Name | Status |
|------|------|--------|
| 24-A | Architecture Audit + Execution Boundary | ✅ |
| 24-B | Package Artifact & Quarantine Store | ✅ |
| 24-C | Checksum / Signature Verification | ✅ |
| 24-D | Runtime Execution Plan Model + Store | ✅ |
| 24-E | Sandbox Worker Interface + Disabled Stub | ✅ |
| 24-F | Policy Enforcement Translator | ✅ |
| 24-G | Local Dev Sandbox Prototype | ✅ |
| 24-H | Runtime Execution API Draft + Admin Gate | ✅ |
| 24-I | Security Escape Guard Tests | ✅ |
| 24-J | Demo + Documentation | ✅ |
| 24-K | Final Regression + Step 25 Gate | ✅ |

**Step 24 Final Gate: PASS. Step 25 Admission: PASS.**
**Core tests**: 1350 passed  **Full regression**: 1997 passed  **Startup**: zero errors

**Docs**: [Final Gate](docs/STEP24K_FINAL_REGRESSION_STEP25_GATE.md) · [Demo](docs/STEP24_RUNTIME_DEMO_SCRIPT.md) · [Q&A](docs/STEP24_SECURITY_QA.md) · [Architecture](docs/STEP24_RUNTIME_ARCHITECTURE_SUMMARY.md) · [Roadmap](docs/ROADMAP.md)

---

## Step 25 Production Sandbox Roadmap

Step 25 is in architecture phase. **No production sandbox implemented. No execution enabled.** `/runtime/agents/{id}/execute` remains blocked.

| Step | Name | Status | Notes |
|------|------|--------|-------|
| 25-A | Architecture Gate + Isolation Strategy | ✅ | 30 threats, 20 hard gates, design only |
| 25-B | Sandbox Execution Store + Audit Model | ✅ | Audit-only records, no queue/execution |
| 25-C | Container/MicroVM Feasibility Spike | ✅ | 10 tech assessed, no runtime started |
| 25-D | Package Download Quarantine | ✅ | Admin-gated metadata-only, no real download |
| 25-E | Archive Extraction Guard | ✅ | Entry metadata validation, no unzip |
| 25-F | Worker Queue Design | ✅ | Metadata-only disabled queue records |
| 25-G | Network/FS/Secrets Enforcement | ✅ | Default-deny proof, no real enforcement |
| 25-H | Limited Trusted Fixture Execution | ✅ | Built-in fixtures, no third-party code |
| 25-I | Red-Team Escape Tests | ✅ | 163 escape guard tests, no critical path found |
| 25-J | Demo + Documentation | ✅ | Demo, Q&A, architecture summary, claim boundary |
| 25-K | Final Regression Gate | ✅ | Step 25 PASS, Step 26 Admission PASS |

**Docs**: [25-A Architecture Gate](docs/STEP25A_PRODUCTION_SANDBOX_RUNTIME_ARCHITECTURE_GATE.md) · [Roadmap](docs/ROADMAP.md)

---

## Step 26-B: Kill Switch + Runtime Incident Store

**Status**: ✅  **Date**: 2026-06-12

Step 26-B builds the safety control plane — kill switch policies, triggers, incident records, and audit events — all metadata/control-plane only. **No runtime kill implementation.** Execute endpoint remains blocked for third-party/package execution.

| Step | Name | Status |
|------|------|--------|
| 26-A | Production Sandbox Implementation Gate | ✅ |
| 26-B | Kill Switch + Runtime Incident Store | ✅ |
| 26-C | Controlled Package Download Worker, Disabled by Default | ✅ |
| 26-D | Read-only Artifact Materialization Spike | ✅ |
| 26-E | Rootless Container Prototype Gate | ✅ |
| 26-F | Trusted Fixture in Isolated Runtime | ✅ |
| 26-G | Network/Filesystem/Secrets Enforcement Runtime Spike | ⏸ |

**Key boundaries**:
- ✅ Trusted fixture in isolated runtime is metadata-only gate; no isolated runtime implementation, no fixture executed in container/microVM, no third-party execution
- ✅ Execute endpoint remains blocked for third-party/package execution
- ❌ No container start, no microVM start, no fixture execution in container

**Tests**: `test_trusted_fixture_isolation.py` 107 passed

**Docs**: [Step 26-B](docs/STEP26B_KILL_SWITCH_RUNTIME_INCIDENT_STORE.md) · [Step 26-C](docs/STEP26C_CONTROLLED_PACKAGE_DOWNLOAD_WORKER_DISABLED_BY_DEFAULT.md) · [Step 26-D](docs/STEP26D_READ_ONLY_ARTIFACT_MATERIALIZATION_SPIKE.md) · [Step 26-E](docs/STEP26E_ROOTLESS_CONTAINER_PROTOTYPE_GATE.md) · [Step 26-F](docs/STEP26F_TRUSTED_FIXTURE_IN_ISOLATED_RUNTIME.md) · [Roadmap](docs/ROADMAP.md)

**Docs**: [Step 26-B](docs/STEP26B_KILL_SWITCH_RUNTIME_INCIDENT_STORE.md) · [Step 26-C](docs/STEP26C_CONTROLLED_PACKAGE_DOWNLOAD_WORKER_DISABLED_BY_DEFAULT.md) · [Step 26-D](docs/STEP26D_READ_ONLY_ARTIFACT_MATERIALIZATION_SPIKE.md) · [Step 26-E](docs/STEP26E_ROOTLESS_CONTAINER_PROTOTYPE_GATE.md) · [Roadmap](docs/ROADMAP.md)
