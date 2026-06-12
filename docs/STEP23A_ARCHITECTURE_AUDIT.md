# Step 23-A：Runtime Sandbox / SDK / Ecosystem Hardening 架构审计报告

## 1. 本轮目标

本轮只做架构审计与设计，不写代码。产出一份完整的 Step 23 设计蓝图，覆盖威胁模型、Runtime 边界、API Key 中间件、Runtime Adapter Registry、Sandbox Policy、SDK Manifest Schema、Package Validation Pipeline、API/Frontend 提案、分阶段实施计划与风险评估。

---

## 2. Current State Audit

### 2.1 Step 22 当前已具备能力

**Developer 体系**：
- DeveloperAccount — 绑定 user_id + tenant_id，UNIQUE INDEX
- DeveloperApiKey — PBKDF2-HMAC-SHA256 存储，prefix + hash，raw_key 一次性展示
- key_prefix 索引查找，verify_and_lookup 完整闭环（revoke/expire 检查）
- `to_dict()` 不含 key_hash

**Manifest / Submission 体系**：
- AgentManifest — name/display_name/description/capabilities/required_permissions/security_profile/runtime_type/entrypoint/config_schema/usage_limits
- SecurityProfile — sandbox_level/requires_network/reads_user_data/writes_user_data/data_access_scope
- `validate()` — 强制 manifest_only + no_execution，拒绝任何其他 runtime_type 或 sandbox_level
- AgentSubmission 状态机 — draft→submitted→in_review→approved→published/rejected→draft(reopen)
- AgentReviewRecord — reviewer_id/decision/notes/checklist 持久化
- submit 前 manifest validation，approve 前 re-validate（reject if invalid/warnings）
- publish 前 re-validate

**Admin Review 体系**：
- _require_admin 门禁（admin/owner/org_admin/super_admin）
- 自审禁止（_check_not_self_review → 403）
- 三种决策：approve / reject（notes 必填）/ request_changes（notes 必填）
- review_record 持久化
- tenant scoped listing（super_admin 可跨 tenant）

**Publish 集成**：
- `build_marketplace_agent_from_submission()` — Manifest → MarketplaceAgent
- publisher_type=developer, visibility/status=beta, pricing_model=free
- 不执行 package_url（仅存储为 metadata `package_url_present`）
- 不注册 AgentRuntime
- 不创建 TenantAgentInstallation
- submission.marketplace_agent_id 写回

**安全验证（246 + 893 tests）**：
- Auth: 所有 Open Platform API require_auth
- Tenant isolation: admin 只看到当前 tenant，super_admin 可跨 tenant
- Developer isolation: 只能操作自己的 key/submission
- API Key: raw_key 不泄露, key_hash 不暴露
- Publish: 不执行/不注册/不安装
- No traceback leak

**前端**：
- Developer Console: /developer, /register, /api-keys, /agents, /agents/new, /agents/[id]
- Admin Review: /admin/agent-submissions, /admin/agent-submissions/[id]
- Marketplace Detail: /agent-marketplace/[id] 显示 developer badge

### 2.2 Developer Agent 当前在 Marketplace 中的状态

- MarketplaceAgent 记录存在于 marketplace_agents 表
- publisher_type="developer"，publisher_name 来自 DeveloperAccount
- visibility="beta"，status="beta"
- pricing_model="free"
- metadata 包含：developer_id, submission_id, runtime_type="manifest_only", sandbox_level="no_execution", no_remote_code_execution=true, verified_publisher
- 可以像 builtin Agent 一样 install / enable / config / uninstall
- **关键边界**：install 不意味着 execution — AgentRuntime 根本没有注册这个 agent

### 2.3 当前 AgentRuntime / AgentRegistry 能力

**AgentRuntime**（`src/agents/runtime.py`）：
- PEOR 循环（Plan→Execute→Observe→Reflect）
- AgentContext：含 tenant_id, user_id, workspace_id, user_roles, permission_checker
- PermissionChecker Protocol：check(user_id, tenant_id, resource, action) → bool
- AgentTask：含 title, description, input_data, priority, deadline
- AgentResult：含 trace (ExecutionTraceStep), memory_refs, kg_refs, timeout
- Tool Calling / Memory Calling / Knowledge Graph Calling 协议
- 所有 Agent 执行有 tenant_id/user_id（不空）

**AgentRegistry**（`src/agents/registry.py`）：
- 管理 AgentRegistration：agent_id, name, enabled, version, config, tags, usage_count, success_rate, avg_duration_ms
- register / unregister / enable / disable / upgrade / get / list
- 当前注册的 Agent：6 builtin (knowledge, meeting, research, sales, support, training) + 6 department (rd, product, operations, sales_dept, hr, customer_service)
- **没有任何 developer_ 前缀的 agent**

### 2.4 当前没有 Developer Runtime 的边界

| 维度 | 当前状态 |
|------|---------|
| Developer Agent 在 AgentRegistry | ❌ 未注册 |
| Developer Agent 可被 execute() | ❌ 不可 |
| manifest_only 含义 | 只存在 Manifest，不进 Runtime |
| no_execution 含义 | SecurityProfile 禁止任何代码执行 |
| runtime_type 校验 | 非 manifest_only 直接 rejection |
| Publish 后自动 runtime | ❌ 不注册 |
| Marketplace install 后 auto-execution | ❌ 必须走 install flow，但不能 execute |

### 2.5 当前 API Key 能力与缺口

| 能力 | 状态 | 代码位置 |
|------|------|---------|
| 生成（PBKDF2） | ✅ | `developer.py:156-168` |
| 存储（prefix + hash） | ✅ | `developer_store.py:157-176` |
| 列表（不含 hash） | ✅ | `developer.py:124-137` |
| revoke | ✅ | `developer_store.py:194-202` |
| expire（is_usable） | ✅ | `developer.py:116-119` |
| verify raw_key → key 查找 | ✅ | `developer_store.py:210-235` |
| **API Key auth middleware** | ❌ **缺失** | |
| **Scopes runtime enforcement** | ❌ **缺失** — scopes 只存不查 |
| **Rate limit** | ❌ **缺失** | |
| **API Key 调用 Developer API** | ❌ **缺失** — 只能用 JWT | |

### 2.6 当前 SecurityProfile / Manifest 可复用字段

| 字段 | 可复用于 Step 23 |
|------|-----------------|
| `sandbox_level` | 映射到 SandboxPolicy.sandbox_level |
| `requires_network` | 映射到 policy.allow_network |
| `reads_user_data` | 映射到 policy 数据访问控制 |
| `writes_user_data` | 同上 |
| `data_access_scope` | 直接映射到 policy.data_access_scope |
| `allowed_domains` | 直接映射到 policy.allowed_domains |
| `risk_notes` | Admin review checklist 输入 |
| `runtime_type` | 映射到 RuntimeAdapterType |
| `required_permissions` | 映射到 install 的 permissions_granted |

### 2.7 当前 Marketplace install flow 可复用点

- TenantAgentInstallation: tenant_id + workspace_id + marketplace_agent_id 隔离
- install → enable/disable → config → uninstall 完整闭环
- permissions_granted 持久化
- usage_limit_override 持久化
- version_pinned 持久化
- PlanLimit 管控（max_marketplace_agents）
- tenant/workspace 隔离— 跨 tenant 404

### 2.8 当前 usage / metrics 可复用点

- UsageEvent: tenant_id, user_id, workspace_id, resource, quantity, unit, metadata
- UsageResource 枚举已有: AGENT_RUN, WORKFLOW_RUN, DEVELOPER_REGISTER, AGENT_SUBMISSION_CREATE 等
- AgentMetricsStore 协议：record_event, get_agent_stats, get_department_distribution
- InMemoryAgentMetricsStore（可对接 UsageStoreAdapter）
- PlanLimit 体系已就位

### 2.9 当前 Known Issues（Step 22-K 分级）

**Non-blocking**：
- Build 被历史 lint blocker 阻塞（graph/page.tsx, memory/page.tsx 等）
- Manifest rejected 后无前端 reopen 按钮

**Step 23 Inputs**：
- API Key auth middleware 未实现
- API Key scopes 无 runtime enforcement
- API Key rate limit 未实现
- 无 Runtime sandbox
- Admin Review 无 dashboard / pagination
- 发布后不能由 developer 原地更新

### 2.10 Step 23 最小安全推进路径

1. **先 API Key auth middleware** → 让 API Key 从"只存不用"变成"可用于受控调用"
2. **再 Simulation Runtime** → 不执行代码但验证 Manifest / permissions / scopes / metrics 链路
3. **再 Sandbox Policy 定义** → admin 可配置安全策略
4. **再 Runtime Adapter Registry** → admin 可启用/停用 developer agent runtime
5. **最后 SDK / Package Validation** → 降低开发者提交门槛

**绝对不做**：在 Sandbox Policy 就位前执行任何第三方代码。

---

## 3. Step 23 Goal Definition

### 3.1 产品目标

把 Step 22 的 "Developer Agent 可提交、可审核、可发布到 Marketplace" 继续推进到：

1. **API Key 可用** — API Key 可用于受控 developer API 调用，scopes 做运行时授权
2. **Agent 可被安全识别** — Developer Agent 在 Runtime 体系中有受控绑定
3. **Simulation 可验证链路** — 不执行外部代码但验证 manifest→install→permission→runtime→metric 闭环
4. **Sandbox 可声明和验证** — Admin 定义 sandbox policy，developer 只能声明需求
5. **Package / Manifest 可安全校验** — 不做代码执行，但做安全检查
6. **SDK 可辅助标准化提交** — 轻量 Manifest SDK（非完整 CLI）
7. **Admin 有结构化审核 checklist** — 审核不仅看 Manifest，还看 runtime eligibility
8. **Marketplace 有 runtime 状态区分** — install ≠ execution_available

### 3.2 安全目标

1. **不允许无沙箱执行第三方代码** — 必须 sandbox policy 就位 + admin 显式 enable runtime
2. **不允许 package_url 被直接执行** — 只做 validation/scanning/metadata extraction
3. **不允许 developer agent 绕过 tenant/workspace 权限** — Runtime 必须注入 AgentContext tenant/user
4. **不允许 API Key 绕过 JWT 权限体系** — API Key scopes 独立体系，不能冒充 user JWT
5. **不允许 API Key scopes 只做展示不做 enforcement** — 每个 API endpoint 必须检查 required scope
6. **不允许 Runtime Adapter 隐式联网** — simulation adapter 不联网；sandbox adapter 需显式 allow_network
7. **不允许外部 Agent 默认读写企业数据** — reads_user_data/writes_user_data 必须在 policy 中声明 + admin 授权
8. **不允许 Marketplace install 自动等于 execution permission** — 需要独立的 runtime enable 步骤
9. **不允许未审核版本进入 Runtime** — runtime binding 应关联特定 approved submission
10. **不允许真实支付 / Revenue Share 混入** — Step 23 不做任何支付相关能力

### 3.3 与 Step 22 的关系

- Step 22 建立 Open Platform 的"准入层"（Developer → Review → Publish）
- Step 23 建立 Open Platform 的"运行时安全层"（API Key Auth → Runtime Adapter → Sandbox Policy → Simulation）
- Step 22 的 publish 不变 — 仍然是映射 Manifest → MarketplaceAgent，不注册 runtime
- Step 23 的 runtime enable 是 publish 后的独立操作

### 3.4 与 Step 24+ 的关系

- Step 23 完成 simulation runtime（不执行外部代码）
- Step 24+ 完成 sandboxed execution（容器/子进程/worker 隔离）
- Step 23 不做真实支付/Revenue Share（留给后续商业模型版本）

### 3.5 本阶段不做什么

- ❌ 不实现 Runtime Sandbox 执行引擎
- ❌ 不实现 API Key middleware 代码
- ❌ 不开发 SDK CLI
- ❌ 不开发 Package Validator 代码
- ❌ 不修改 AgentRuntime
- ❌ 不修改 AgentRegistry
- ❌ 不修改 Marketplace Publish 逻辑
- ❌ 不修改 Open Platform API
- ❌ 不修改前端
- ❌ 不接入真实支付
- ❌ 不实现 Revenue Share
- ❌ 不执行 package_url
- ❌ 不远程拉取代码
- ❌ 不运行第三方代码

---

## 4. Runtime Threat Model

### 威胁总览

| # | Threat | Impact | Priority | Existing Protections (Step 22) | Missing Protections | Step 23 Mitigation |
|---|--------|--------|----------|-------------------------------|---------------------|-------------------|
| 1 | **Remote Code Execution** — package_url 包含恶意代码，执行后控制服务器 | Critical — 完整服务器 compromise | **P0** | package_url 仅存储不执行；manifest_only + no_execution 校验；publish 不下载/不解压 | 没有沙箱；没有执行隔离；package 扫描缺失 | Simulation adapter 不执行代码；Sandbox Policy 执行前检查；容器/子进程隔离（Step 24） |
| 2 | **Malicious package_url** — URL 指向恶意载荷（不直接执行但 social-engineering admin 执行） | High — 社工绕过 | **P0** | package_url 仅 metadata | URL 无白名单/格式校验 | Package Validation Pipeline：HTTPS only + domain allowlist/denylist + checksum 校验 |
| 3 | **Manifest 欺骗** — developer 声明低风险 Manifest 但实际包能力远超声明 | High — 审核绕过 | **P0** | Manifest Validation + Admin Review | manifest 与 package 内容无一致性交叉校验 | Package metadata extraction（MVP mock）；manifest-package diff report；review checklist template |
| 4 | **Permission escalation** — API Key scopes 写得大但调用时不做 enforcement | Critical — 越权访问 | **P0** | scopes 以 JSON 存 DB | 运行时不做 scopes enforcement | API Key middleware 在 endpoint 层面检查 required scopes；scopes 白名单体系 |
| 5 | **Tenant data exfiltration** — developer agent 通过 runtime adapter 读取 tenant A 数据发送给 tenant B 的 developer | Critical — 数据泄露 | **P0** | AgentContext.tenant_id 注入；tenant isolation 404 | 无 runtime execution — 尚无此攻击面 | Runtime binding 绑定 tenant_id；sandbox policy 限制 data_access_scope；network egress policy；audit log |
| 6 | **Workspace boundary bypass** — API Key 跨 workspace 调用 | High — 跨 workspace 访问 | **P0** | workspace_id 在 JWT payload 中 | API Key 无 workspace binding | DeveloperApiPrincipal 包含 tenant_id/workspace_id；middleware 注入 workspace context |
| 7 | **API Key leakage** — raw_key 泄露给第三方或被日志记录 | High — 身份冒用 | **P1** | raw_key 仅 create response 返回一次；不写日志 | rate limit 缺失 → brute force 可能 | log sanitizer 过滤 `cos_dev_` pattern；rate limit per key；key rotation API |
| 8 | **API Key replay** — 拦截 raw_key 后重放 | High — 未授权调用 | **P1** | 无 replay protection | 无 nonce/timestamp/signature | HTTP header 级：要求 HTTPS（已有）；可选的 HMAC signature（Step 23 later） |
| 9 | **API Key over-scoped access** — developer 申请 scopes 远超合理范围 | Medium — 权限过大 | **P1** | scopes 存储在 DB | scopes 不与 manifest required_permissions 交叉校验 | Admin Review 检查 scopes vs required_permissions 一致性；scopes 推荐/max 值 |
| 10 | **Agent prompt injection** — manifest description/capabilities 含注入内容，影响审核者判断或未来 LLM agent | Medium — 审核干扰 | **P1** | Admin 人工审核 | manifest 字段无内容安全检查 | Manifest Validation 增加 description/capabilities 敏感词检查（MVP 简单 keyword filter） |
| 11 | **Network egress abuse** — sandbox adapter 联网拉取恶意载荷或 exfiltrate data | High — 网络滥用 | **P1** | 无 runtime → 无网络调用 | sandbox adapter 无 network policy | SandboxPolicy.allow_network + allowed_domains；simulation adapter 完全无网 |
| 12 | **File system access abuse** — sandbox agent 写临时文件、覆盖配置、读取密钥 | High — 本地提权 | **P1** | 无 runtime → 无文件访问 | 无 file system policy | SandboxPolicy.allow_filesystem_read/write + allowed_paths；readonly root |
| 13 | **Secret leakage** — sandbox agent 通过环境变量或配置文件读取 DB password/API keys | Critical — 基础设施泄露 | **P0** | 无 runtime → 无 access | 无 secret isolation | SandboxPolicy.allow_secrets + allowed_secret_names；secret injection via controlled env vars |
| 14 | **Infinite loop / resource exhaustion** — agent 死循环耗尽 CPU/内存/DB 连接 | High — DoS | **P1** | 无 runtime | 无 timeout/内存限制 | SandboxPolicy.max_timeout_ms + max_memory_mb + max_cpu_percent；kill_switch |
| 15 | **SSRF** — agent 诱导 sandbox adapter 内网调用 admin API 或其他内部服务 | High — 内网渗透 | **P1** | 无 runtime | 无网络 egress 限制 | allowed_domains 白名单；禁止内网 IP 段（127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16） |
| 16 | **Data poisoning** — developer agent 写入虚假或恶意数据到 Memory/KG | Medium — 数据污染 | **P2** | 无 runtime write | 无 data access 限制 | SandboxPolicy.writes_user_data + data_access_scope；permission checker 在 runtime context |
| 17 | **Review bypass** — developer 通过 API Key 自审或绕过 admin review | High — 审核失效 | **P0** | 自审禁止（403）；developer 不能访问 admin API | developer 无法 publish → 已有保护；API Key 不能调用 admin API | API Key scopes 禁止包含 admin:review / admin:publish |
| 18 | **Published agent version swap** — 已发布 agent 绑定的 Manifest 被替换为新恶意版本 | High — 供应链攻击 | **P1** | published 状态不可编辑；publish 创建新 MarketplaceAgent | runtime binding 不锁定到 submission/manifest version | Runtime binding 关联 submission_id + manifest_version；update = new submission + re-review |
| 19 | **Runtime adapter spoofing** — malicious adapter 伪装成合法 adapter 类型 | Medium — 信任边界破解 | **P2** | 无 adapter registry | 无 adapter identity/status 检查 | RuntimeAdapter.status + adapter_type 在白名单；admin 显式 enable；audit log |
| 20 | **Marketplace install 被误认为 execution permission** | Medium — 用户误解 | **P1** | 产品边界文档明确 | UI 无 runtime 状态区分 | Marketplace UI 增加：runtime_supported badge、simulation available badge、execution not enabled notice |

**P0: 7 threats** — Remote Code Execution, Malicious package_url, Manifest spoofing, Permission escalation, Tenant data exfiltration, Secret leakage, Review bypass
**P1: 10 threats** — API Key leakage, API Key replay, over-scoped access, prompt injection, network egress, file system access, resource exhaustion, SSRF, version swap, install vs execution confusion
**P2: 3 threats** — Data poisoning, adapter spoofing, (future)

---

## 5. Runtime Execution Boundary

### 5.1 Layer 1: Manifest-only（Step 22 当前状态）

**现状**：
- Developer Agent 只是 Manifest + MarketplaceAgent entry
- runtime_type="manifest_only", sandbox_level="no_execution"
- 不执行 package_url，不注册 runtime，不支持 external execution
- Manifest Validation 拒绝任何非 manifest_only 的 runtime_type
- **这是安全基线** — 在没有 Sandbox Policy 时，这是唯一允许的状态

### 5.2 Layer 2: Simulation Runtime（Step 23 MVP）

**目标**：让 Developer Agent 可以"假装执行"来验证整个链路，但不执行任何外部代码。

**能力**：
- Simulation Runtime Adapter — 注册到 RuntimeAdapterRegistry
- 接受 AgentTask + AgentContext → 返回 AgentResult
- **不执行外部代码** — adapter 内部是确定性 mock logic
- 验证链路：
  1. installation 存在 + status=active
  2. permissions_granted 匹配 agent.required_permissions
  3. API Key scopes 匹配调用所需的 scope
  4. usage event 记录（UsageResource.AGENT_RUN + metadata 含 simulation=true）
  5. metrics 更新（AgentMetricsStore）
  6. AgentResult 返回 simulation metadata（不返回真实业务结果）
- 不联网
- 不读取真实企业数据（除非显式 mock 数据注入）
- 返回结构化 mock response："{agent_name} simulation completed. Permissions: [list]. Scope: [scope]. Tenant: {tenant_id}."

**与真实执行的区别**：agent_result.metadata 包含 `{"simulation": true, "adapter_type": "simulation"}`

### 5.3 Layer 3: Sandboxed Runtime（Step 24+）

**目标**：在 Sandbox Policy 就位后，允许受限代码执行。

**隔离层**（候选方案，Step 23 只设计不实现）：
- 容器隔离（Docker/Podman）
- 子进程 + seccomp（Python subprocess + resource limits）
- Worker 进程池（pre-fork, per-agent worker）
- CPU/memory/timeout 硬限制
- 网络 egress policy（白名单 + 禁止内网）
- 文件系统只读或临时 overlay（tmpfs）
- secret injection policy（白名单 env vars）
- permission-bound data access（AgentContext.permission_checker）
- audit log（every call, every resource access）
- kill switch（admin 一键 kill per agent or global）
- package scanning（静态分析 / signature verification）

**Step 23-A 明确声明**：
- ✅ 先做 Simulation Runtime（Step 23-D）— 零代码执行，验证全链路
- ⏸ Sandboxed Execution 延后到 Step 24+ — 需要容器化 infrastructure
- ❌ **绝对禁止**：在 Sandbox Policy 就位前、仿真验证未完成前、安全测试未覆盖前，真执行任何第三方代码

### 5.4 绝对禁止项

| # | 禁止项 | 原因 |
|---|--------|------|
| 1 | 不通过 sandbox policy 执行任何第三方代码 | 无沙箱 = 无安全 |
| 2 | 不在 Simulation 阶段引入网络调用 | 仿真不联网 |
| 3 | 不让 developer 自行选择 sandbox/adapter | admin 决定 |
| 4 | 不让 API Key 绕过 JWT 权限调用 admin API | 权限分离 |
| 5 | 不让 install 自动等于 execution permission | 需要独立 enable |
| 6 | 不让未审核 manifest 版本进入 Runtime | association 必须带审核 |
| 7 | 不让 source_type="manifest" 的 agent 进入 sandbox 级执行 | manifest_only agent 不应有运行时 |

---

## 6. API Key Auth Middleware Design

### 6.1 Header 设计

**方案比较**：

| 方案 | Header | 优点 | 缺点 |
|------|--------|------|------|
| A | `X-Cognitive-API-Key: cos_dev_...` | 语义清晰；不与 JWT Bearer 冲突 | 非标准 header |
| B | `Authorization: Bearer cos_dev_...` | 标准 header；现有基础设施可复用 | 与 JWT Bearer 格式冲突；需要区分 token type |

**推荐：方案 A** — `X-Cognitive-API-Key: cos_dev_xxx`

原因：
1. 不与现有 `Authorization: Bearer <jwt>` 冲突
2. 语义明确——这是 API Key 不是 JWT
3. 可以同时传 JWT（浏览器场景）或只传 API Key（CLI/SDK 场景）
4. FastAPI 解析简单

### 6.2 认证流程

```
Request with X-Cognitive-API-Key
  │
  ├─ 1. Extract raw_key from header
  │     └─ if missing → continue to JWT auth (fallback)
  │
  ├─ 2. Lookup DeveloperApiKey by key_prefix
  │     └─ if not found → 401
  │
  ├─ 3. verify_api_key(raw_key, stored_hash)
  │     └─ constant-time comparison
  │     └─ if mismatch → 401
  │
  ├─ 4. Check key.status == 'active'
  │     └─ if revoked → 401 "API Key has been revoked"
  │     └─ if expired → 401 "API Key has expired"
  │
  ├─ 5. Check key.expires_at (is_usable)
  │     └─ if expired → 401 "API Key has expired"
  │
  ├─ 6. Lookup DeveloperAccount by developer_id
  │     └─ if not found → 401
  │     └─ if status != active → 403 "Developer account suspended"
  │
  ├─ 7. Build DeveloperApiPrincipal
  │     ├─ developer_id
  │     ├─ user_id (from DeveloperAccount)
  │     ├─ tenant_id (from DeveloperAccount)
  │     ├─ api_key_id
  │     ├─ key_prefix
  │     ├─ scopes
  │     └─ auth_type = "developer_api_key"
  │
  ├─ 8. Update last_used_at (async, non-blocking)
  │
  ├─ 9. Record usage event (DEVELOPER_API_KEY_USED)
  │
  └─ 10. Do NOT log raw_key in any form
```

### 6.3 Principal 模型

```python
@dataclass
class DeveloperApiPrincipal:
    """API Key 认证后的 principal — 不是 User，不继承 JWT 权限。"""
    developer_id: str
    user_id: str           # 关联的用户
    tenant_id: str
    workspace_id: str = ""  # 从 request body/query 或 developer default 获取
    api_key_id: str
    key_prefix: str
    scopes: list[str]
    auth_type: str = "developer_api_key"  # 区别于 "jwt" / "user"
```

**与 JWT TokenPayload 的关键区别**：
| 属性 | JWT TokenPayload | DeveloperApiPrincipal |
|------|-----------------|----------------------|
| 来源 | Bearer token | X-Cognitive-API-Key |
| role | owner/admin/member/viewer | **无 role** |
| is_super_admin | True/False | **永远 False** |
| email | 有 | 无（仅 developer 关联的 user） |
| auth_type | jwt | developer_api_key |
| 可调用 admin API | ✅ (if role>=admin) | ❌ **永远禁止** |
| 可 publish | ✅ (if admin) | ❌ **永远禁止** |

### 6.4 Scopes 定义

**允许 scopes**：

| Scope | 含义 | 对应端点 |
|-------|------|---------|
| `developer:read` | 读取自己的 developer profile | GET /developers/me |
| `developer:write` | 更新自己的 developer profile | PATCH /developers/me |
| `api_keys:read` | 列出自己的 API Keys | GET /developers/api-keys |
| `api_keys:write` | 创建/撤销自己的 API Keys | POST/DELETE /developers/api-keys |
| `submissions:read` | 读取自己的 submissions | GET /developers/agents |
| `submissions:write` | 创建/编辑 draft submission | POST/PATCH /developers/agents |
| `submissions:submit` | 提交审核 | POST /developers/agents/{id}/submit |
| `marketplace:read` | 浏览 Marketplace（read-only） | GET /agent-marketplace/* |
| `agent:simulate` | 触发 simulation runtime | POST /developer-api/agents/{id}/simulate |
| `agent:execute:simulation` | 同 agent:simulate（细粒度） | |
| `agent:execute:sandbox` | 触发 sandbox runtime | Step 24+ |
| `usage:read` | 查看自己的 usage | GET /developer-api/usage |

**禁止 scopes**（中间件强制拒绝）：

| Scope | 原因 |
|-------|------|
| `admin:review` | API Key 不能审核 |
| `admin:publish` | API Key 不能发布 |
| `tenant:admin` | API Key 不能管理 tenant |
| `billing:write` | API Key 不能操作账单 |
| `revenue:write` | API Key 不能操作收入 |
| `system:super_admin` | API Key 不能成为超管 |
| `workspace:admin` | API Key 不能管理工作区 |
| `org:admin` | API Key 不能管理组织 |

**强制检查**：
1. API Key 创建时 scopes 白名单校验 — 含禁止 scope → 422
2. API endpoint 检查 required_scope — 不匹配 → 403
3. Admin API 直接拒绝 `auth_type == "developer_api_key"` — 403

### 6.5 权限边界

```
┌──────────────────────────────────────────────┐
│                  API Layer                     │
│                                                │
│  require_auth          → JWT ✅  │  API Key ❌ │
│  require_admin         → JWT ✅  │  API Key ❌ │
│  require_dev_api_key   → JWT ❌  │  API Key ✅ │
│  require_scope(s)      → 两者都可用            │
│                                                │
│  Developer API (/developers)                   │
│    └─ JWT: 对自己 developer 的操作            │
│    └─ API Key: require_scope check             │
│                                                │
│  Admin API (/admin/agent-submissions)          │
│    └─ JWT: admin/owner/super_admin            │
│    └─ API Key: ❌ 403 always                   │
│                                                │
│  Marketplace API (/agent-marketplace)          │
│    └─ Browse: JWT ✅ / API Key with "marketplace:read" ✅ │
│    └─ Install: JWT admin ✅ / API Key ❌       │
│    └─ Config: JWT admin ✅ / API Key ❌        │
│                                                │
│  Developer API Key API (/developer-api)        │
│    └─ JWT: ❌ (专用 API Key 端点)              │
│    └─ API Key: ✅ with appropriate scopes      │
└──────────────────────────────────────────────┘
```

### 6.6 需要新增测试

- `test_api_key_auth_middleware.py`：
  - test_missing_header_returns_401
  - test_invalid_key_returns_401
  - test_revoked_key_returns_401
  - test_expired_key_returns_401
  - test_suspended_developer_returns_403
  - test_valid_key_returns_principal
  - test_key_cannot_access_admin_api
  - test_key_cannot_publish
  - test_scope_missing_returns_403
  - test_scope_sufficient_returns_200
  - test_ban_scopes_rejected
  - test_last_used_updated
  - test_usage_event_recorded
  - test_raw_key_not_in_usage_metadata
  - test_rate_limit_per_key

---

## 7. Runtime Adapter Registry Design

### 7.1 Adapter 类型

```python
class RuntimeAdapterType(StrEnum):
    MANIFEST_ONLY = "manifest_only"     # Step 22: 不执行
    SIMULATION = "simulation"           # Step 23 MVP: 仿真
    HTTP_WEBHOOK = "http_webhook"       # Step 24+: HTTP 回调
    SANDBOXED_PROCESS = "sandboxed_process"  # Step 24+: 子进程沙箱
    CONTAINER = "container"             # Step 24+: 容器沙箱
    BUILTIN_BRIDGE = "builtin_bridge"   # Step 24+: 内置 Agent 桥接
```

**Step 23 MVP 只允许**：
- `manifest_only` — 已有
- `simulation` — 新增

**Step 23 暂不允许**：
- `http_webhook`
- `sandboxed_process`
- `container`
- `builtin_bridge`（developer agent 不能伪装成 builtin）

### 7.2 RuntimeAdapter 模型

```python
@dataclass
class RuntimeAdapter:
    adapter_id: str          # f"rad_{uuid4().hex[:12]}"
    adapter_type: str         # RuntimeAdapterType
    name: str
    description: str
    supports_network: bool = False
    supports_user_data_read: bool = False
    supports_user_data_write: bool = False
    sandbox_required: bool = True  # 是否要求 SandboxPolicy
    max_timeout_ms: int = 30_000
    max_memory_mb: int = 128
    status: str = "active"    # active | deprecated | disabled
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

**MVP 预注册 adapter**：
```python
SIMULATION_ADAPTER = RuntimeAdapter(
    adapter_id="rad_simulation",
    adapter_type="simulation",
    name="Simulation Runtime Adapter",
    description="Non-executing simulation adapter. Validates manifest/permissions/usage/metrics chain without executing external code.",
    supports_network=False,
    supports_user_data_read=False,
    supports_user_data_write=False,
    sandbox_required=False,  # 仿真不需要沙箱
    max_timeout_ms=10_000,
    max_memory_mb=64,
)
```

### 7.3 DeveloperAgentRuntimeBinding 模型

```python
@dataclass
class DeveloperAgentRuntimeBinding:
    binding_id: str                     # f"rb_{uuid4().hex[:12]}"
    marketplace_agent_id: str           # 关联 MarketplaceAgent
    submission_id: str                  # 关联 approved submission
    developer_id: str                   # 开发者
    tenant_id: str                      # 所属 tenant
    adapter_type: str                   # 当前启用的 adapter 类型
    runtime_status: str = "disabled"    # disabled | simulation_active | sandbox_active
    sandbox_policy_id: str | None = None  # 关联 SandboxPolicy
    enabled_by: str | None = None       # admin user_id
    enabled_at: datetime | None = None
    last_executed_at: datetime | None = None
    execution_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

### 7.4 Execution 前置检查

所有 developer agent 执行前必须通过五层检查：

```
Execution Request
  │
  ├─ Layer 1: Installation Check
  │   ├─ TenantAgentInstallation exists? → 404
  │   ├─ status = active? → 403 "Installation not active"
  │   └─ enabled = True? → 403 "Agent is disabled"
  │
  ├─ Layer 2: Runtime Binding Check
  │   ├─ RuntimeBinding exists? → 403 "Runtime not enabled"
  │   ├─ runtime_status != disabled? → 403 "Runtime is disabled"
  │   └─ adapter_type matches request? → 400 "Adapter mismatch"
  │
  ├─ Layer 3: Sandbox Policy Check (skip if simulation)
  │   ├─ sandbox_policy_id set?
  │   ├─ policy active?
  │   └─ sandbox_level != no_execution? (for non-simulation)
  │
  ├─ Layer 4: Permission Check
  │   ├─ AgentContext.permission_checker
  │   ├─ tenant_id / workspace_id match
  │   └─ required_permissions ⊆ permissions_granted
  │
  ├─ Layer 5: API Key Scope Check (如果 auth 方式是 API Key)
  │   └─ required_scope ∈ scopes
  │
  └─ ✅ Execute via adapter
      └─ Audit log every execution
```

**无 Runtime Binding 时的错误响应**：
```json
{
  "detail": "Runtime not enabled for this developer agent. Admin must enable runtime before execution.",
  "error_code": "RUNTIME_NOT_ENABLED",
  "binding_status": "not_found"
}
```

---

## 8. Sandbox Policy Design

### 8.1 SandboxPolicy 数据模型

```python
@dataclass
class SandboxPolicy:
    policy_id: str                    # f"sp_{uuid4().hex[:12]}"
    name: str                         # "Simulation Only Policy" / "Restricted Sandbox"
    sandbox_level: str = "no_execution"  # no_execution | restricted | isolated
    allow_network: bool = False
    allowed_domains: list[str] = field(default_factory=list)  # 白名单
    allow_filesystem_read: bool = False
    allow_filesystem_write: bool = False
    allowed_paths: list[str] = field(default_factory=list)     # 允许的路径前缀
    allow_secrets: bool = False
    allowed_secret_names: list[str] = field(default_factory=list)  # 允许注入的 env var 名
    max_timeout_ms: int = 30_000
    max_memory_mb: int = 128
    max_cpu_percent: int = 50
    max_output_bytes: int = 1_048_576    # 1MB
    max_requests_per_minute: int = 60
    data_access_scope: list[str] = field(default_factory=list)  # 允许访问的数据范围
    audit_enabled: bool = True
    kill_switch_enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    created_by: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

### 8.2 MVP Policies

```python
NO_EXECUTION_POLICY = SandboxPolicy(
    policy_id="sp_no_execution",
    name="No Execution Policy",
    sandbox_level="no_execution",
    # 所有 access 均为 False
    allow_network=False,
    allow_filesystem_read=False,
    allow_filesystem_write=False,
    allow_secrets=False,
    audit_enabled=True,
    kill_switch_enabled=True,
)

SIMULATION_ONLY_POLICY = SandboxPolicy(
    policy_id="sp_simulation",
    name="Simulation Only Policy",
    sandbox_level="no_execution",  # 仍然是 no_execution — 不执行代码
    allow_network=False,
    allow_filesystem_read=False,
    allow_filesystem_write=False,
    allow_secrets=False,
    max_timeout_ms=10_000,
    audit_enabled=True,
    kill_switch_enabled=False,  # 仿真不需要 kill switch
)

RESTRICTED_NETWORK_OFF_POLICY = SandboxPolicy(
    policy_id="sp_restricted_no_net",
    name="Restricted Sandbox — Network Off",
    sandbox_level="restricted",
    allow_network=False,     # ❌ 禁网
    allowed_domains=[],
    allow_filesystem_read=True,
    allowed_paths=["/tmp/sandbox/"],  # 仅临时目录
    allow_filesystem_write=True,
    allowed_paths=["/tmp/sandbox/"],
    allow_secrets=False,     # ❌ 不注入 secrets
    max_timeout_ms=30_000,
    max_memory_mb=128,
    max_cpu_percent=50,
    audit_enabled=True,
    kill_switch_enabled=True,
)
# RESTRICTED_NETWORK_OFF_POLICY 是 Step 24+ 使用，Step 23 不激活
```

### 8.3 Developer 声明 vs Admin 授权

| 角色 | 能做什么 | 不能做什么 |
|------|---------|-----------|
| Developer | 在 Manifest/security_profile 中声明 `requires_network`, `reads_user_data`, `writes_user_data`, `data_access_scope` | 不决定最终 sandbox policy |
| Reviewer/Admin | 审核 developer 声明是否合理 | — |
| Admin | 选择 sandbox policy；enable runtime binding | 不自动 enable（需要人工确认） |
| System | 执行前读取 binding.sandbox_policy_id → 加载 SandboxPolicy → 应用限制 | 不跳过 policy |

### 8.4 Policy Enforcement 点

1. **Runtime Adapter 入口** — 加载 policy，检查 adapter_type 是否允许
2. **Network 调用前** — 检查 allow_network + allowed_domains
3. **File system 操作前** — 检查 allow_filesystem_read/write + allowed_paths
4. **Secret 注入前** — 检查 allow_secrets + allowed_secret_names
5. **Execution timeout** — timer + kill
6. **Memory limit** — resource.setrlimit (Unix) 或 job object (Windows)
7. **Output size limit** — 超过 max_output_bytes 截断 + error
8. **Rate limit** — per-binding counter
9. **Policy violation** — 返回安全错误（不泄露 policy 内部细节）

### 8.5 Audit / Kill Switch

- **Audit**：每个 execution 记录 binding_id + policy_id + adapter_type + tenant_id + user_id + result + duration + resources_used
- **Kill Switch**：Admin 可 per-policy 或 per-binding 一键停止所有 pending/running execution

---

## 9. SDK / Manifest SDK Design

### 9.1 SDK MVP 范围

**不做完整 CLI**。轻量 Manifest SDK — 帮助开发者规范提交。

**MVP 能力**：
1. **Manifest JSON Schema** — `cognitive-agent.schema.json`
2. **Validation library** — Python 函数，复用现有 `AgentManifest.validate()` 逻辑
3. **SecurityProfile builder** — 结构化 security_profile 创建辅助
4. **Docs + examples** — 3-5 个完整 Manifest 示例（knowledge/automation/training/sales/support）
5. **Dry-run validator** — `python -m cognitive_sdk validate manifest.json`

**Step 23 不做**：
- ❌ 完整 CLI（`cognitive init`, `cognitive deploy`, `cognitive publish`）
- ❌ 远程代码上传执行
- ❌ SDK-based agent registration
- ❌ SDK-based API key management（用 curl 或 API docs）
- ❌ TypeScript SDK（先 Python, step 23 later）
- ❌ NPM/PyPI publish

### 9.2 Manifest Schema（摘录）

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://cognitive-os.dev/schemas/agent-manifest.json",
  "title": "Cognitive OS Agent Manifest",
  "type": "object",
  "required": ["name", "display_name", "description", "version", "capabilities", "required_permissions", "security_profile"],
  "properties": {
    "name": {
      "type": "string",
      "pattern": "^[a-z0-9_-]+$",
      "description": "Technical name (lowercase, dashes, underscores only)"
    },
    "display_name": { "type": "string", "minLength": 1 },
    "description": { "type": "string", "minLength": 1 },
    "version": { "type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+" },
    "capabilities": { "type": "array", "minItems": 1, "items": { "type": "string" } },
    "required_permissions": { "type": "array", "minItems": 1, "items": { "type": "string" } },
    "runtime_type": { "enum": ["manifest_only"] },
    "security_profile": {
      "type": "object",
      "required": ["sandbox_level"],
      "properties": {
        "sandbox_level": { "enum": ["no_execution"] },
        "requires_network": { "type": "boolean" },
        "reads_user_data": { "type": "boolean" },
        "writes_user_data": { "type": "boolean" },
        "allowed_domains": { "type": "array", "items": { "type": "string" } },
        "data_access_scope": { "type": "array", "items": { "type": "string" } },
        "risk_notes": { "type": "string" }
      }
    },
    "entrypoint": { "type": ["string", "null"] },
    "config_schema": { "type": "object" },
    "usage_limits": { "type": "object" },
    "metadata": { "type": "object" }
  }
}
```

### 9.3 Developer Workflow（SDK 辅助）

```
1. 开发者阅读 docs/examples
2. 编写 manifest.json（参考 schema + examples）
3. 本地校验：cognitive-sdk validate manifest.json
4. 修复 errors / warnings
5. 复制 manifest 到 Developer Console → /developer/agents/new
6. 提交审核
```

### 9.4 后续 SDK Roadmap（Step 24+）

- TypeScript SDK
- `cognitive-sdk submit` — API 提交
- `cognitive-sdk status` — 查询 submission 状态
- Manifest version diff tool
- Package bundler（打包 manifest + package）
- IDE plugin（VS Code）

---

## 10. Package Validation Pipeline Design

### 10.1 Pipeline Steps

```
package_url / repository
  │
  ├─ Step 1: URL Format Validation
  │   └─ Must be HTTPS scheme
  │   └─ Well-formed URL
  │
  ├─ Step 2: Domain Check
  │   └─ Allowed domain list (admin-configurable)
  │   └─ Denied domain list (block known malicious)
  │   └─ MVP: allow GitHub/GitLab/PyPI, deny raw IP
  │
  ├─ Step 3: URL Reachability Check (MVP: optional/skip)
  │   └─ HTTP HEAD → 200?
  │   └─ Not in Step 23 MVP — head requests can be SSRF vectors
  │
  ├─ Step 4: Checksum / Signature Field
  │   └─ manifest.metadata.package_checksum (sha256)
  │   └─ manifest.metadata.package_signature (optional, Step 24)
  │
  ├─ Step 5: Package Metadata Extraction (MVP: mock)
  │   └─ manifest.metadata.package_name, package_version, package_license
  │   └─ Cross-reference with manifest name/version
  │   └─ MVP: developer self-declares, system validates consistency
  │
  ├─ Step 6: Manifest-Package Consistency Check
  │   └─ manifest.name == package.name?
  │   └─ manifest.version == package.version?
  │   └─ manifest.capabilities ⊇ package.claimed_capabilities?
  │   └─ MVP: manual review checklist
  │
  ├─ Step 7: Dependency Declaration Scan (MVP: manual)
  │   └─ developer declares dependencies in metadata.dependencies
  │   └─ System checks known vulnerability DB (Step 24+)
  │
  ├─ Step 8: License Check
  │   └─ manifest.metadata.license
  │   └─ Validate against allowed license list (MIT/Apache2/BSD OK, GPL flag)
  │
  ├─ Step 9: Security Warnings
  │   └─ If security_profile.requires_network=True → WARNING
  │   └─ If security_profile.reads_user_data=True → WARNING
  │   └─ If dependencies contain known CVE → ERROR (Step 24+)
  │
  └─ Step 10: Review Checklist Update
      └─ Auto-populate review checklist based on pipeline results
      └─ Admin can override
```

### 10.2 MVP 可做 vs 延后

| Step | Step 23 MVP | 说明 |
|------|------------|------|
| URL Format | ✅ | 简单正则 |
| Domain Check | ✅ | Admin 配置白名单/黑名单 |
| Reachability | ❌ | 避免 SSRF |
| Checksum | ✅ | 开发者声明 sha256 |
| Package Metadata | ✅ (mock) | 开发者自声明，系统交叉校验 consistency |
| Manifest-Package Consistency | ✅ (manual) | Admin review checklist |
| Dependency Scan | ❌ | Step 24+ |
| License Check | ✅ | 简单列表校验 |
| Security Warnings | ✅ | 基于 security_profile 字段 |
| Review Checklist | ✅ | Auto-populate |

### 10.3 安全边界

- **绝对不执行 package** — 不下载，不解压，不 import，不 subprocess
- **不直连外部 URL** — 不做 HTTP fetch（MVP）
- **checksum 由 developer 提供** — 不回源验证（MVP）
- **domain check 是静态字符串匹配** — 不做 DNS 解析

---

## 11. API / Frontend Proposal

### 11.1 API Key Middleware API

| Method | Path | Scope Required | MVP/Later | 说明 |
|--------|------|---------------|-----------|------|
| `GET` | `/developer-api/me` | `developer:read` | Step 23-B | 用 API Key 获取 developer profile |
| `GET` | `/developer-api/submissions` | `submissions:read` | Step 23-B | 用 API Key 列出自己的 submissions |
| `POST` | `/developer-api/submissions` | `submissions:write` | Step 23-B | 用 API Key 创建 draft |
| `POST` | `/developer-api/submissions/{id}/submit` | `submissions:submit` | Step 23-B | 用 API Key 提交审核 |
| `POST` | `/developer-api/agents/{id}/simulate` | `agent:simulate` | Step 23-D | 用 API Key 触发仿真 |

### 11.2 Runtime Admin API

| Method | Path | MVP/Later | 说明 |
|--------|------|-----------|------|
| `GET` | `/admin/runtime-adapters` | Step 23-C | 列出所有 RuntimeAdapter |
| `GET` | `/admin/runtime-adapters/{id}` | Step 23-C | Adapter 详情 |
| `POST` | `/admin/developer-agents/{mkp_id}/runtime/enable` | Step 23-C | 启用 developer agent runtime binding |
| `POST` | `/admin/developer-agents/{mkp_id}/runtime/disable` | Step 23-C | 停用 runtime binding |
| `GET` | `/admin/developer-agents/{mkp_id}/runtime` | Step 23-C | 查看 runtime binding 状态 |

### 11.3 Sandbox Policy API

| Method | Path | MVP/Later | 说明 |
|--------|------|-----------|------|
| `GET` | `/admin/sandbox-policies` | Step 23-E | 列出所有 SandboxPolicy |
| `GET` | `/admin/sandbox-policies/{id}` | Step 23-E | Policy 详情 |
| `POST` | `/admin/sandbox-policies` | Step 23-E | 创建自定义 policy |
| `PATCH` | `/admin/sandbox-policies/{id}` | Step 23-E | 更新 policy |
| `POST` | `/admin/sandbox-policies/{id}/test` | Step 23-E | 测试 policy 约束（dry-run） |

### 11.4 Package Validation API

| Method | Path | MVP/Later | 说明 |
|--------|------|-----------|------|
| `POST` | `/admin/agent-submissions/{id}/validate-package` | Step 23-F | 运行 package validation pipeline |
| `GET` | `/admin/agent-submissions/{id}/package-validation` | Step 23-F | 查看验证结果 |

### 11.5 Frontend 提案

**Developer Console 新增**（Step 23-B/D）：
- API Key 卡片显示 `last_used_at` + usage count
- Manifest Schema Guide 面板（schema 字段说明 + 示例）
- Simulation Result Panel（显示仿真结果——权限/scope/usage 链路状态）

**Admin Review 新增**（Step 23-E/F/G）：
- Package Validation Panel（显示 pipeline 结果 + warnings）
- Runtime Eligibility Panel（显示：该 agent 是否满足 runtime 条件）
- Sandbox Policy Selector（admin 选择/创建 policy）
- Runtime Enable/Disable Toggle
- Review Checklist Template（auto-populate from manifest/pipeline/policy）

**Marketplace Detail 新增**（Step 23-G）：
- `runtime_supported` badge（是否有 enabled runtime binding）
- `simulation_available` badge（是否支持仿真）
- `execution_not_enabled` notice（无 runtime → 提示需要 admin enable）
- `sandbox_level` badge（no_execution / restricted / isolated）

**MVP/Later 分类**：

| 页面 | MVP (Step 23-B..G) | Later (Step 24+) |
|------|-------------------|-------------------|
| Developer Console | last_used_at + schema guide | simulation result panel |
| Admin Review | runtime eligibility + checklist template | package validation panel interactive |
| Admin Review | sandbox policy selector | runtime enable/disable toggle (API-driven) |
| Marketplace Detail | runtime_supported badge + execution_not_enabled notice | sandbox_level badge |

---

## 12. Step 23 Implementation Plan

| 子阶段 | 目标 | 修改范围 | 不做什么 | 验收标准 | 测试重点 |
|--------|------|---------|---------|---------|---------|
| **23-A** Architecture Audit + Threat Model | 完整设计蓝图 | docs/STEP23A_ARCHITECTURE_AUDIT.md | 不写代码 | Threat model ≥15 威胁；Runtime boundary 三层定义；API Key middleware 设计；Sandbox policy 设计；SDK scope 定义；Implementation plan 完整 | 无需测试 |
| **23-B** API Key Auth Middleware + Scope Enforcement | API Key 可用于受控调用 | src/api/middleware.py (新增 require_dev_api_key), src/core/auth.py (DeveloperApiPrincipal), src/open_platform/developer.py (scope 白名单校验) | 不修改 JWT auth; 不做 rate limit; 不修改 admin API | API Key 可调用 Developer API; scopes 白名单校验; 禁止 scopes 在创建时拒绝; admin API 拒绝 API Key; 15+ 中间件测试 | test_api_key_auth_middleware.py: 15-20 tests; 不破坏现有 893 tests |
| **23-C** Runtime Adapter Domain Model + Store | RuntimeAdapter + RuntimeBinding 数据模型 | src/open_platform/runtime_adapter.py (新 domain model), src/adapters/runtime_adapter_store.py (新 SQLite store), src/api/admin_runtime_router.py (新 admin API) | 不实现 adapter 执行逻辑; 不修改 AgentRuntime; 不修改 publish; 不做 simulation | RuntimeAdapter CRUD; RuntimeBinding CRUD; admin API 5 endpoints; adapter 白名单; 20+ store tests; 10+ API tests | test_runtime_adapter_store.py; test_runtime_admin_api.py |
| **23-D** Simulation Runtime Adapter | 不执行代码的仿真 adapter | src/agents/runtime_adapters/simulation.py (新), main.py (注册 simulation adapter) | 不执行 package_url; 不联网; 不读写真实数据; 不修改 AgentRegistry | Simulation adapter accepts AgentTask + AgentContext → returns AgentResult with simulation=true; execution 前置检查（5 layers）; usage event recorded; 20+ tests | test_simulation_adapter.py; test_execution_precheck.py |
| **23-E** Sandbox Policy Model + Admin API | Admin 可定义/应用 sandbox policy | src/open_platform/sandbox_policy.py (新 domain model), src/adapters/sandbox_policy_store.py (新 store), src/api/sandbox_policy_router.py (新 admin API) | 不做 policy enforcement engine; 不修改 AgentRuntime; 不实现容器隔离 | SandboxPolicy CRUD; 3 MVP policies 预置; policy 可关联 runtime binding; 15+ store tests; 10+ API tests | test_sandbox_policy_store.py; test_sandbox_policy_api.py |
| **23-F** Package Validation Pipeline | Manifest/package 安全校验 pipeline | src/open_platform/package_validator.py (新), src/api/admin_submission_router.py (新增 validate-package endpoint) | 不执行 package; 不下载远程内容; 不做 dependency CVE scan; 不做 HTTP reachability check | URL format validation; domain allowlist/denylist; checksum format check; license check; auto-populate review checklist; 15+ tests | test_package_validator.py |
| **23-G** Runtime Admin Frontend | Admin 可管理 runtime/sandbox | frontend/app/admin/runtime/ (新页面), frontend/app/admin/sandbox-policies/ (新页面), frontend/services/runtime.ts | 不修改 Developer Console; 不修改 Marketplace Publish 页面; 不做 sandbox 执行 UI | Runtime Adapter 列表页; Sandbox Policy 列表/创建/编辑页; Runtime Binding enable/disable UI; Scoped ESLint 0; TypeScript 通过 | 前端 typecheck + scoped lint |
| **23-H** Developer SDK / Manifest Schema | 轻量 Manifest SDK + schema + docs | sdk/python/cognitive_sdk/ (新目录), docs/agent-manifest.schema.json, docs/examples/ | 不做 CLI; 不做 npm publish; 不做远程执行; 不做 TypeScript SDK | `cognitive-agent.schema.json`; Python validation library; 3-5 manifest examples; docs | SDK unit tests |
| **23-I** Security + Runtime Tests | 全链路安全测试 | tests/test_runtime/ (新目录), tests/test_sandbox/ (新目录) | 不修改现有测试逻辑; 不降低安全断言 | API Key auth 安全测试; simulation adapter 安全测试; sandbox policy 边界测试; execution precheck 测试; 不执行代码确认; 全量回归零失败 | test_api_key_security.py; test_simulation_security.py; test_sandbox_boundary.py |
| **23-J** Demo + Documentation | Step 23 演示脚本 + 文档更新 | docs/STEP23_RUNTIME_DEMO_SCRIPT.md; README.md; ROADMAP.md | 不开发新功能 | Demo script 完整; README runtime quick start; ROADMAP Step 23; 文档安全边界 | 文档链接 + 虚假能力检查 |
| **23-K** Final Regression + Step 24 Gate | 最终回归 + 准入审查 | 全量测试 + build + lint 检查 | 不开发 Step 24 | 全量回归通过; Security Gate 通过; Documentation Gate 通过; Step 23 capability gate 闭环 | 全量测试 + 专项测试 |

---

## 13. Risk Assessment

| # | Risk | Severity | Trigger Condition | Mitigation | Target Step |
|---|------|----------|-------------------|------------|-------------|
| 1 | **无沙箱执行第三方代码** | Critical | adapter_type=sandbox 但 sandbox_policy 未就位 | Execution 前置检查 Layer 3 — policy 必须存在且 sandbox_level≠no_execution；MVP 只允许 simulation | 23-A/D |
| 2 | **API Key 权限扩大** | High | scopes 设计过宽或 enforcement 缺失 | Scope 白名单校验 at creation time + endpoint-level enforcement；禁止 scopes 硬编码拒绝 | 23-B |
| 3 | **scopes 设计过宽** | Medium | 粗粒度 scope 如 `agent:execute` 包含过多权限 | MVP 细粒度 scopes（agent:simulate / agent:execute:simulation / agent:execute:sandbox 分开）；最小权限原则 | 23-B |
| 4 | **Tenant 数据泄露** | Critical | Runtime adapter 缺乏 tenant_id 注入 | AgentContext 强制 tenant_id/user_id/workspace_id；permission_checker 每次执行前调用 | 23-D |
| 5 | **SSRF** | High | Simulation adapter 意外引入网络调用 | Simulation adapter 不导入任何网络库；policy 白名单；内网 IP 黑名单 | 23-D/E |
| 6 | **package_url 恶意载荷** | High | Checksum 缺失或可伪造 | Developer 必须提供 sha256；validation pipeline 校验格式；不做 HTTP 回源 | 23-F |
| 7 | **Dependency confusion** | Medium | 恶意 package 同名同版本覆盖合法依赖 | MVP: developer 声明依赖；审核 checklist 交叉校验；Step 24+ CVE scan | 23-F/24+ |
| 8 | **Secret leakage** | Critical | Sandbox 环境变量泄露 DB keys | SandboxPolicy.allow_secrets 默认 False；白名单机制 | 23-E |
| 9 | **Long-running execution 耗尽资源** | High | 无 timeout 的 agent loop | SandboxPolicy.max_timeout_ms + max_memory_mb；kill_switch | 23-E/D |
| 10 | **Runaway cost** | Medium | Simulation 被滥用导致 usage_events 爆炸 | Rate limit per API Key + per runtime binding；usage alert | 23-B/D |
| 11 | **Runtime adapter spoofing** | Medium | 恶意代码伪装成合法 adapter | Admin 显式 enable adapter；adapter_id 白名单；audit log | 23-C |
| 12 | **Review checklist 流于形式** | Medium | Auto-populate 内容 admin 不审 | 强制 checklist 审核；admin notes 必填；手动确认每一 warning | 23-F/G |
| 13 | **Simulation 被误认为真实执行** | Low | UI 标志不清晰 | AgentResult.metadata.simulation=true；Marketplace UI badge "Simulation Only" | 23-D/G |
| 14 | **Payment/Revenue 过早混入** | Medium | 压力导致过早产品化 | 文档明确边界；代码无支付相关路径；Milestone gate 拒绝 | 23-A |
| 15 | **Public store 过早开放** | High | 未经安全审计开放外部访问 | 所有 Marketplace API 保持 require_auth；无 public 端点 | 23-A（持续） |
| 16 | **Historical lint debt 拖累 Step 23** | Low | Build 被历史错误阻塞 | Step 22 scoped lint 0 errors；Cleanup PR in early Step 23 | 23-B（early） |
| 17 | **Developer agent versioning 混乱** | Medium | 同一 Agent 多次发布但 runtime binding 指向旧版本 | Runtime binding 关联 submission_id + marketplace_agent_id；update = new submission + re-review；旧 binding 失效 | 23-C |

---

## 14. Recommended Next Step

**Step 23-B：API Key Auth Middleware + Scope Enforcement**

按照本设计文档第 6 章实现：
- `X-Cognitive-API-Key` header auth middleware
- DeveloperApiPrincipal 模型
- Scopes 白名单 + 禁止 scopes
- Scope enforcement at endpoint level
- `require_dev_api_key` dependency
- 15-20 中间件安全测试
- 不破坏现有 893 测试

---

**Step 23-A 完成。本文件为架构审计报告，不包含任何代码实现。所有设计内容待 Step 23-B 起逐步实现。**
