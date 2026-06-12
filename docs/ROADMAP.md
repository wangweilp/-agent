# Roadmap: 记忆进化型个人知识助手

## 版本策略
- 每个版本独立可交付，有明确验收标准
- 优先级分为三级：P0（必须）、P1（重要）、P2（高级）
- 任何架构变更必须先写 ADR
- **防回归约束**：升级到新版时，旧版的全部测试必须仍然通过

---

## P0 — 第一优先级（当前必须）

### v0.1 — 真 Agent（真 Tool Calling + 真 Embedding + Context Builder）

**目标**：一个真正的 Agent，不是伪 Agent。

**验收**：
- [ ] 使用 OpenAI Tool Calling API（非 JSON 字符串解析）
- [ ] 本地 bge-small-zh-v1.5 embedding
- [ ] ChromaDB + SQLite 双写
- [ ] Context Builder（动态组装，非全量历史）
- [ ] recall 语义搜索（非 LIKE）
- [ ] 终端 CLI 交互
- [ ] 流式输出

**提交清单**：
```
[ ] feat(core): define rich Memory model (importance, memory_type, etc.)
[ ] feat(core): define MemoryStore, VectorStore, LLMProvider protocols
[ ] feat(core): implement Tool Calling agent loop
[ ] feat(core): implement Context Builder
[ ] feat(core): add System Prompt with safety guardrails
[ ] feat(adapters): implement DeepSeek adapter with tool calling support
[ ] feat(adapters): implement local embedding (bge-small-zh-v1.5)
[ ] feat(adapters): implement ChromaDB vector store
[ ] feat(adapters): implement SQLite store (rich schema)
[ ] feat(tools): implement remember tool (with importance scoring)
[ ] feat(tools): implement recall tool (semantic search + RRF)
[ ] feat(tools): implement tool registry with permission layer
[ ] feat(api): implement /chat endpoint with SSE streaming
[ ] feat(tools): implement CLI interface
[ ] test: all core and adapter tests
```

**不包含**：Web UI、周报、知识图谱、Memory Consolidation

---

## P1 — 第二优先级（下一步）

### v0.2 — Memory Consolidation + Reflection

**目标**：Agent 能自我反思和重组知识。

**验收**：
- [ ] reflect 工具可用，Agent 能自我检查矛盾
- [ ] Memory Consolidation 每日检查，发现认知模式
- [ ] 自动提示：「你正在形成『XX』认知模型」
- [ ] 记忆衰减（旧记忆 importance 自动降低）

**提交清单**：
```
[ ] feat(core): implement consolidation.py
[ ] feat(core): implement importance decay logic
[ ] feat(tools): implement reflect tool
[ ] feat(tools): implement consolidate trigger
[ ] test: consolidation and reflection tests
[ ] docs: ADR for consolidation algorithm
```

---

### v0.3 — 知识图谱 + 实体关系

**目标**：提取实体关系，构建知识图谱。

**验收**：
- [ ] 存储记忆时自动提取实体（DeepSeek few-shot）
- [ ] 实体→记忆可追溯
- [ ] Agent 能主动指出跨领域联系
- [ ] SQLite 三表模拟图谱结构

---

### v0.4 — 认知周报

**目标**：每周生成认知分析报告。

**验收**：
- [ ] 5 板块周报（概览/聚焦/联系/盲点/建议）
- [ ] 自动触发（Windows 任务计划）
- [ ] Markdown 输出

---

### v0.5 — Web 前端

**目标**：可用 Web 界面。

**验收**：
- [ ] 单页对话 + 流式显示
- [ ] 记忆侧边栏
- [ ] 周报浏览
- [ ] 零框架依赖

---

## P2 — 第三优先级（高级）

### v1.0 — 稳定版
- 测试覆盖率 ≥ 85%
- 完整 API 文档
- 数据迁移方案

### v2.0 — 认知操作系统
- [ ] Procedural Memory（用户习惯/偏好）
- [ ] Multi-Agent（反思 Agent 独立运行）
- [ ] 知识导出（Markdown 知识库）
- [ ] 飞书/微信 Webhook
- [ ] 本地 LLM 完全离线

---

## 版本切换规则

1. 开发在 `feature/vX.Y` 分支
2. 完成 checklist → 合并到 develop
3. develop 稳定 → tag → 合并 master
4. tag 命名：`v0.1.0`, `v0.2.0`...


---
## Step 20-D: Enterprise AI Agent (Demo Ready)

当前状态（2026-06-09）:
- Cognitive OS: AI Coach / KG / Memory Search / Import / Sync Hub
- Team Brain / Enterprise Brain / SaaS / Growth Analytics
- **Enterprise AI Agent Platform**: 12 内置 Agent + 6 部门 Agent
- WorkflowEngine: 9 种节点类型, WorkflowExecutionStep 完整追溯
- 业务场景: Meeting-to-Training + Department Assistant
- [演示文档](STEP20D_DEMO_SCRIPT.md)
- 演示数据: `python scripts/seed_agent_demo.py --apply`
- 测试: 530 passed (agent 235 + security 49 + rbac/saas 246)

Next: Step 21 Agent Marketplace

---
## Step 21: Agent Marketplace (Completed / Demo Ready)

当前状态（2026-06-09）:

**Step 21 分阶段**:
| 子阶段 | 内容 | 状态 |
|--------|------|------|
| 21-A | Marketplace Architecture Audit | ✅ |
| 21-B | Domain Model + Store (MarketplaceAgent, TenantAgentInstallation, SQLiteMarketplaceStore, Built-in Catalog) | ✅ |
| 21-C | Marketplace API (13 endpoints, 46 API tests) | ✅ |
| 21-D | Marketplace Frontend (3 pages, 4 components, Sidebar navigation) | ✅ |
| 21-E | Install / Enable / Config 闭环联调 (ConfigDialog, installed sync) | ✅ |
| 21-F | Usage / Billing / Analytics MVP (PlanLimit, usage events, analytics summary) | ✅ |
| 21-G | Security + Tenant Isolation + Tests (67 security tests, 647 regression) | ✅ |
| 21-H | Demo & Documentation | ✅ |

**已完成能力**:
- Built-in Marketplace Catalog（6 个内置 Agent）
- `MarketplaceAgent` / `TenantAgentInstallation` 领域模型
- `SQLiteMarketplaceStore`（30 个 store 单元测试）
- `/agent-marketplace` API（13 端点，require_auth + role 检查）
- `/agent-marketplace` 前端（3 页面 + 4 复用组件）
- install / enable / disable / config / uninstall 完整闭环
- Usage Summary（MVP）— 真实记录 usage_events
- Analytics Summary（MVP）— installed_agents, top_categories, top_agents
- Plan Limit — `max_marketplace_agents` 按套餐层级管控
- tenant / workspace 隔离 — 跨 tenant 404，跨 workspace 数据不泄露
- AgentUsageSummary 组件 — 6 指标展示
- AgentPermissionPanel 组件 — required/granted/missing 三栏
- AgentPricingBadge 组件 — free/per_use/per_seat/subscription 可视化
- AgentConfigDialog 组件 — JSON 编辑弹窗含校验
- 156 个 Marketplace 专项测试（89 API + 67 security）
- 647 个后端全量回归测试全部通过
- TypeScript typecheck 通过
- Scoped ESLint: 0 errors, 0 warnings

**不包含**（留给 Step 22 Open Platform）:
- 第三方开发者注册与上传
- Agent SDK
- Developer Console
- 外部审核流程
- Revenue Share
- 真实支付接入
- Public Marketplace (无需 auth 的公共浏览)

**当前边界**:
- Marketplace 是企业内部 Agent 分发中心
- 内置 Catalog 通过 `seed_builtin_marketplace_agents` 自动初始化
- 所有 API 和前端都禁用 Step 22 路径
- 所有 Usage/Billing 标注 "MVP only; no real payment charge"

**下一步**:
Step 21-I: 最终回归与 Step 22 准入审查（已完成）

再之后:
Step 22: Open Platform（已完成，见下文）

---
## Step 22: Open Platform (Security Gate Passed / Demo Ready)

当前状态（2026-06-10）:

**Step 22 分阶段**:
| 子阶段 | 内容 | 状态 |
|--------|------|------|
| 22-A | Open Platform 架构审计与边界定义 | ✅ |
| 22-B | Developer Account + API Key Domain Model | ✅ |
| 22-C | Agent Manifest + Submission Store | ✅ |
| 22-D | Developer API | ✅ |
| 22-E | Admin Review API | ✅ |
| 22-F | Developer Console Frontend | ✅ |
| 22-G | Admin Review Frontend | ✅ |
| 22-H | Marketplace Publish Integration | ✅ |
| 22-I | Security + Tests | ✅ |
| 22-J | Demo & Documentation | ✅ |

**已完成能力**:
- `DeveloperAccount` / `DeveloperApiKey` 领域模型
- API Key 安全存储（PBKDF2-HMAC-SHA256 hash / revoke / expire / key_prefix 索引）
- `AgentManifest` / `SecurityProfile` 领域模型
- `AgentSubmission` / `AgentReviewRecord` 状态机（draft → submitted → in_review → approved → published）
- `SQLiteDeveloperStore` + `SQLiteSubmissionStore`
- Developer API（16 个端点：register, me, api-keys CRUD, agents CRUD + submit/validate/withdraw）
- Admin Review API（8 个端点：list, detail, start-review, approve, reject, request-changes, publish, reviews）
- Developer Console Frontend（6 个页面：/developer, /register, /api-keys, /agents, /agents/new, /agents/[id]）
- Admin Review Frontend（2 个页面：审核队列 + 审核详情）
- Publish to Marketplace（`build_marketplace_agent_from_submission()` → `PublisherType.DEVELOPER`）
- Marketplace Developer Agent Display（publisher_name, review_status, no_remote_code_execution）
- Security Gate Passed（27 个安全审计测试）
- 893 tests passed（Open Platform + 全量回归）
- TypeScript typecheck 通过
- Scoped ESLint: 0 errors, 0 warnings

**不包含**（留给 Step 22-K / Step 23）:
- API Key auth middleware（API Key 暂不能用于绕过 JWT 调用系统 API）
- API Key runtime scopes enforcement
- Runtime sandbox（无法执行第三方代码）
- Remote code execution（MVP 仅 Manifest-first）
- SDK CLI（开发者手动编写 Manifest JSON）
- Real payment（未接入支付网关）
- Revenue Share（所有 Agent pricing_model=free）
- Public unauthenticated marketplace
- Auto install（Publish 不自动安装）
- Auto execute（Publish 不自动运行）
- Developer Agent 原地更新（需要新 submission 流程）
- Admin Review dashboard / pagination

**当前边界**:
- Open Platform 是 Manifest-first MVP
- 不执行任何第三方代码（`runtime_type=manifest_only`, `sandbox_level=no_execution`）
- Publish 是纯数据映射操作（Manifest → MarketplaceAgent）
- Developer Agent 发布后走完整 Marketplace install flow
- 所有 API require_auth + tenant/workspace 隔离
- 所有 Billing 标注 "MVP only; no real payment charge"

**下一步**:
Step 22-K：最终回归与 Step 23 准入审查（已完成 — 准入通过）

再之后:
Step 23：Runtime Sandbox / SDK / Ecosystem Hardening（进行中）

---
## Step 23: Runtime Sandbox / SDK / Ecosystem Hardening (Completed / Step 24 Admission Passed)

当前状态（2026-06-10）:

**Step 23 分阶段**:
| 子阶段 | 内容 | 状态 |
|--------|------|------|
| 23-A | Architecture Audit + Threat Model | ✅ |
| 23-B | API Key Auth Middleware + Scope Enforcement | ✅ |
| 23-C | Runtime Adapter Domain Model + Store | ✅ |
| 23-D | Simulation Runtime Adapter | ✅ |
| 23-E | Sandbox Policy Model + Admin API | ✅ |
| 23-F | Package Validation Pipeline | ✅ |
| 23-G | Runtime Admin Frontend | ✅ |
| 23-H | Developer SDK / Manifest Schema | ✅ |
| 23-I | Security + Runtime Tests | ✅ |
| 23-J | Demo + Documentation | ✅ |
| 23-K | Final Regression + Step 24 Gate | ✅ |

**23-A 产出**:
- [Step 23-A Architecture Audit Report](STEP23A_ARCHITECTURE_AUDIT.md)
- 20-threat threat model (P0×7, P1×10, P2×3)
- Runtime Execution Boundary 三层设计（Manifest-only / Simulation / Sandboxed）
- API Key Auth Middleware 设计（X-Cognitive-API-Key header, DeveloperApiPrincipal, 12 scopes + 8 禁止 scopes）
- Runtime Adapter Registry 设计（5 types, RuntimeAdapter + RuntimeBinding 模型）
- Sandbox Policy 设计（13 字段, 3 MVP policies）
- SDK / Manifest SDK 设计（JSON Schema + Python validation library）
- Package Validation Pipeline 设计（10-step, 无代码执行）
- API / Frontend Proposal（15+ 新端点 + 5 前端页面）
- 17-risk assessment with severity + trigger + mitigation

**23-J 产出**:
- [Step 23 Demo Script](STEP23_RUNTIME_SDK_DEMO_SCRIPT.md) — 8-scene demo, 15 Q&A, security boundary table, known issues
- README.md Step 23 Quick Start 章节

**Step 23 整体测试**（截至 23-I）:
- Step23 Security/Runtime 专项: 77 passed
- Open Platform 全量: 678 passed
- 后端全量回归: 1325 passed

**Step 23 不包含**（留给 Step 24+）:
- 容器/子进程 sandbox execution
- Real payment / Revenue Share
- Public unauthenticated marketplace
- 未审核 Agent 自动运行
- 无沙箱远程代码执行
- 自动安装到 tenant
- SDK CLI (cognitive init/deploy/publish)
- TypeScript SDK / NPM publish

**Step 23-K Final Gate 结果** (2026-06-10):
- Capability Gate: ✅ PASS
- Security Gate: ✅ PASS (24 checks)
- Documentation Gate: ✅ PASS (10 docs)
- Startup Gate: ✅ PASS
- Backend Regression: 1325 passed, 0 failed
- Frontend: TypeScript ✅, ESLint 0/0 ✅, next build compiled ✅ (lint blocker: historical only)
- Step 24 Admission: ✅ **PASS**

**下一步**:
Step 24-A：Real Sandbox Runtime Architecture Audit + Execution Boundary Design (已完成，见下文)

---
## Step 24：Real Sandbox Runtime (In Progress — Design Phase)

当前状态（2026-06-10）:

**Step 24 分阶段**:
| 子阶段 | 内容 | 状态 |
|--------|------|------|
| 24-A | Architecture Audit + Execution Boundary Design | ✅ |
| 24-B | Package Artifact & Quarantine Domain Model + Store | ✅ |
| 24-C | Checksum / Signature Verification Pipeline | ✅ |
| 24-D | Runtime Execution Plan Model + Store | ✅ |
| 24-E | Sandbox Worker Interface + Disabled-by-default Stub | ✅ |
| 24-F | Policy Enforcement Translator | ✅ |
| 24-G | Local Development Sandbox Prototype | ✅ |
| 24-H | Runtime Execution API Draft + Admin Gate | ✅ |
| 24-I | Security Tests + Escape Guard Tests | ✅ |
| 24-J | Demo + Documentation | ✅ |
| 24-K | Final Regression + Step 25 Gate | ✅ |

**24-B 产出**:
- [Step 24-B Architecture](STEP24B_PACKAGE_ARTIFACT_QUARANTINE_STORE.md)
- `src/open_platform/package_artifact.py` — PackageArtifact + Quarantine + Audit domain model
- `src/adapters/package_artifact_store.py` — SQLitePackageArtifactStore (3 tables, 22 methods)
- `src/open_platform/package_artifact_service.py` — PackageArtifactDeclarationService
- 3 UsageResource enums: PACKAGE_ARTIFACT_DECLARE / QUARANTINE / STATUS_CHANGE
- 83 tests (domain + store + quarantine + audit + service + startup + non-execution guards)
- 1421 regression tests passed

**24-A 产出**:
- [Step 24-A Architecture Audit](STEP24A_REAL_SANDBOX_RUNTIME_ARCHITECTURE_AUDIT.md)
- 34-threat threat model (P0×15, P1×14, P2×5)
- 20 execution boundary hard principles
- 7 sandbox technology options compared (no-exec → container → WASM → microVM)
- 15-component recommended target architecture
- 17-step data flow from submission to execution result
- 5 draft data models (PackageArtifact, ExecutionRequest/Result, AuditEvent, KillSwitch)
- API design drafts (artifact, execution, kill switch)
- Policy enforcement translator design
- Data/Network/Secret/Filesystem enforcement design
- 11-phase implementation roadmap (24-B to 24-K)

**24-K 产出**:
- [24-K Final Gate](STEP24K_FINAL_REGRESSION_STEP25_GATE.md) — Step 24 Final Gate: PASS, Step 25 Admission: PASS

**关键边界（当前）**:
- Step 24 A-K completed (16 source files, 14 docs, 1997 tests)
- Execute endpoint still blocked, DisabledSandboxWorker still default
- 不下载/不解压/不执行 package
- 不联网 / 不创建 worker / 不启动 container
- 不调用 AgentRuntime / 不注册 AgentRegistry
- production sandbox not completed

---

## Step 24 Final Status

- **Step 24 Completed**: ✅
- **Final Regression**: 1997 passed, 0 failed
- **Security Gate**: ✅ PASS (18 checks)
- **Documentation Gate**: ✅ PASS (10 checks)
- **Startup Gate**: ✅ PASS (zero errors)
- **Step 25 Admission**: ✅ PASS

---

## Step 25：Production Sandbox Runtime (In Progress — Architecture)

| Step | Name | Status |
|------|------|--------|
| 25-A | Production Sandbox Runtime Architecture Gate + Isolation Strategy | ✅ |
| 25-B | Sandbox Execution Store + Audit Model | ✅ |
| 25-C | Container/MicroVM Adapter Feasibility Spike | ✅ |
| 25-D | Package Download Quarantine Prototype with Explicit Admin Gate | ✅ |
| 25-E | Read-only Artifact Extraction Guard | ✅ |
| 25-F | Worker Queue Design, Disabled by Default | ✅ |
| 25-G | Network/Filesystem/Secrets Enforcement Proof | ✅ |
| 25-H | Limited Trusted Fixture Execution, Not Third-party Code | ✅ |
| 25-I | Red-Team Escape Tests | ✅ |
| 25-J | Demo + Documentation | ✅ |
| 25-K | Final Regression Gate | ✅ |

**25-A 产出**:
- [25-A Architecture Gate](STEP25A_PRODUCTION_SANDBOX_RUNTIME_ARCHITECTURE_GATE.md) — 30 new threats, 10 isolation options, 20 hard gates, 20-component architecture

**Step 25 is in architecture phase only. No production sandbox implemented. No execution enabled.**
**Step 24 execution endpoint remains blocked.**

**下一步**:
Step 25-B：Sandbox Execution Store + Audit Model

**25-K 产出**:
- [25-K Final Release Gate](STEP25K_FINAL_REGRESSION_GATE.md) — Final regression + Step 26 admission
- [Step 25 Release Checklist](STEP25_RELEASE_CHECKLIST.md)
- 2774 cross-suite regression tests passed

---

## Step 25 Final Status

- **Step 25 Completed**: ✅
- **Final Regression**: All 724+ key tests + 2774 cross-suite passed
- **Red-Team Gate**: ✅ PASS (163 tests, 11 guard categories)
- **Documentation Gate**: ✅ PASS (13 STEP25*.md, no false claims)
- **Startup Gate**: ✅ PASS (zero errors, no worker/queue/downloader started)
- **Step 26 Admission**: ✅ PASS

---

## Step 26：Production Sandbox Implementation (Not Started)

| Step | Name | Status |
|------|------|--------|
| 26-A | Production Sandbox Implementation Gate | ✅ |
| 26-B | Kill Switch + Runtime Incident Store | ✅ |
| 26-C | Controlled Package Download Worker, Disabled by Default | ✅ |
| 26-D | Read-only Artifact Materialization Spike | ✅ |
| 26-E | Rootless Container Prototype Gate | ✅ |
| 26-F | Trusted Fixture in Isolated Runtime | ✅ |
| 26-G | Network/Filesystem/Secrets Enforcement Runtime Spike | ⏸ |
| 26-H | Third-party Code Execution Admission Review | ⏸ |
| 26-I | Red-Team Runtime Escape Tests | ⏸ |
| 26-J | Demo + Documentation | ⏸ |
| 26-K | Final Regression Gate | ⏸ |

**Step 26-F completed: trusted fixture in isolated runtime gate, metadata-only, 18/22 requirements satisfied, no isolated runtime implemented. Step 26-G is the next phase — Network/Filesystem/Secrets Enforcement Runtime Spike. Step 26-H is the earliest possible review point for third-party code execution, not approval by default. Step 26 must not jump directly to arbitrary code execution. Execute endpoint remains blocked after Step 26-F.**

**下一步**:
Step 26-G：Network/Filesystem/Secrets Enforcement Runtime Spike
