# Step 23 Demo Script：Runtime Sandbox / SDK / Ecosystem Hardening

## 1. Demo 目标

**证明 Cognitive OS 已经从 "Open Platform 可提交、可审核、可发布 Developer Agent" 升级为 "具备 API Key 认证、Manifest SDK、Package 静态校验、Sandbox Policy 策略模型、Runtime Binding readiness 管理和 Simulation dry-run 的安全运行时准入体系"**

核心信息：
- ✅ Step 23 是安全准入链路，不执行第三方代码
- ✅ Simulation 是 deterministic dry-run，不下载/不解压/不执行 package
- ✅ Sandbox Policy 是策略模型，不是容器沙箱
- ✅ Runtime Binding enable 只改状态，不启动 worker
- ❌ 不做 container sandbox execution
- ❌ 不下载 package
- ❌ 不联网调用外部服务
- ❌ 不做真实 CVE scan / signature verification

## 2. Demo 前置条件

```bash
# 终端 1：启动后端
cd D:\dma\day2
python main.py
# → http://127.0.0.1:8000  (Swagger: http://127.0.0.1:8000/docs)

# 终端 2：启动前端
cd D:\dma\day2\frontend
npm run dev
# → http://localhost:3000
```

**账号要求**：需要 JWT 登录（管理员角色）。参考 `python main.py create-admin` 创建管理员账号。

## 3. Demo 路线总览（8 步）

| # | 场景 | 页面/API | 演示价值 |
|---|------|---------|---------|
| 1 | Developer API Key | `/developer/api-keys` | raw_key only once, scope enforcement |
| 2 | Manifest Schema & Validate | API + Developer Console | Static validation, no submission created |
| 3 | Developer Submission | `/developer/agents/new` | Manifest-first, no execution |
| 4 | Package Validation | `/admin/agent-submissions/[id]` | Static metadata check, no download |
| 5 | Admin Review | `/admin/agent-submissions/[id]` | Approve does not equal execution |
| 6 | Publish to Marketplace | `/admin/agent-submissions/[id]` | Publish does not create runtime binding |
| 7 | Runtime Admin | `/admin/runtime` | Binding, policy, eligibility management |
| 8 | Simulation Runtime | API or test | Deterministic dry-run, 9-step validation |

## 4. 30 秒讲解词

> "Cognitive OS Step 23 建立了一套安全的 Developer Agent 运行时准入体系。
> 开发者提交 Manifest → 管理员审核并做 Package 静态校验 → 通过后发布到 Marketplace。
> 要真正"运行"Agent？不是执行代码——而是进入 Simulation dry-run：
> 系统验证 install、permissions、runtime binding、sandbox policy、API Key scope 全链路，
> 返回确定性 mock 结果。全程不下载、不联网、不执行任何外部代码。
> 这是为 Step 24 真正的 sandbox execution 铺好的安全地基。"

## 5. 2 分钟讲解词

> "大家好，我今天展示 Step 23——从 Open Platform 到安全运行时准入的完整升级。
>
> 回顾一下：Step 22 让外部开发者可以注册、提交 Agent Manifest、经过管理员审核后发布到 Marketplace。
> 但 Step 22 的 Agent 发布后只是 Marketplace 中的一个条目——不能运行，不能模拟，没有任何运行时能力。
>
> Step 23 补齐了什么呢？八层能力：
>
> **第一，API Key**。开发者创建 API Key 时，scope 必须经过白名单校验。
> `admin:review`、`admin:publish` 等 scope 在创建时就被硬拒绝。
> 所有 Admin Review / Runtime Admin / Sandbox Policy API 不接受 API Key。
>
> **第二，Manifest Schema & SDK**。我们提供了标准 JSON Schema 和 Python SDK 校验器。
> 开发者本地 `validate` 就能发现 runtime_type=container、requires_network=true 等不合规声明。
>
> **第三，Package Validation**。管理员在审核时点击 validate-package，
> 系统静态检查 URL 必须是 HTTPS、不能是 localhost/内网 IP、checksum/signature 算法是否声明合规。
> 全程不下载 package——只做 metadata check。
>
> **第四，Sandbox Policy**。3 个 system policies：no_execution、simulation_only、restricted_network_off。
> 都是策略模型，不是容器沙箱。`is_execution_allowed()` 对 no_execution 和 simulation_only 永远返回 False。
>
> **第五，Runtime Binding**。管理员在 Runtime Admin 中为 Developer Agent 创建 binding，
> 绑定 simulation adapter 和 sandbox policy。enable binding 只改状态——不启动 worker，不执行代码。
>
> **第六，Eligibility 评估**。系统自动检查：binding 是否存在？是否 enabled？
> adapter 是否 active？是否 MVP allowed？sandbox policy 是否 assigned？
> 每一步都有明确的 code 和 required_action。
>
> **第七，Simulation Runtime**。9 步验证链路：
> marketplace_agent → developer_publisher → runtime_metadata → installation → permissions → runtime_binding → adapter → scope → simulated_response。
> 任何一步 blocked 即终止。返回 deterministic mock 结果，metadata 强制标记 `no_remote_code_execution=true`。
>
> **第八，安全测试**。77 个 Step23 专项安全测试覆盖 API Key boundary、tenant isolation、runtime binding 状态机、
> simulation safety、sandbox policy 保护、package validation no-download、manifest SDK no-execution、
> 日志/类型/前端 UX 不泄露敏感信息。全量 1325 后端测试全部通过。
>
> 这一切的核心：让准入链路完整、可验证、可审计，但不越界执行。"

## 6. 5 分钟完整演示词

### Scene 1 — Developer Console

**页面**：`/developer` → `/developer/api-keys` → `/developer/agents/new`

> "首先看 Developer Console。开发者注册后，在 API Keys 页面创建一个 Key。
> （操作）选择 scopes：`submissions:read`、`submissions:write`、`submissions:submit`、`agent:simulate`。
> （点击创建）raw_key 弹出——这是唯一一次能看到完整 Key 的机会。关闭后再也无法找回。
> 数据库中只存 PBKDF2-HMAC-SHA256 hash 和 8 字符 prefix。
>
> 然后看 Manifest Schema。
> （调用 API 或展示 SDK）`GET /developers/agent-manifest/schema` 返回标准 JSON Schema。
> `POST /developers/agent-manifest/validate` 做静态校验——不创建 submission。
> 如果 runtime_type 写成 container、requires_network 写成 true，strict mode 直接 blocker。
>
> 开发者用 SDK 本地校验通过后，在 `/developer/agents/new` 粘贴 Manifest JSON，创建 submission。"

### Scene 2 — Admin Review + Package Validation

**页面**：`/admin/agent-submissions` → `/admin/agent-submissions/[id]`

> "管理员在 Review Queue 中看到新 submission。进入详情页。
> （展示）Manifest、SecurityProfile、Validation Panel——和 Step 22 一样的审核界面。
> 但多了两个东西。
>
> 第一：Package Validation Panel。
> （点击 Validate Package）系统运行 19 个静态检查。
> - URL 必须是 HTTPS
> - 不能是 localhost/127.0.0.1/内网 IP
> - checksum algorithm 只允许 sha256/sha384/sha512
> - signature algorithm 只允许 minisign/cosign/gpg
> - license/security_contact/dependencies 声明检查
> - `package_not_downloaded` 和 `package_not_executed` 两个 check 永远 passed
>
> （展示结果）有 blocker → blocked。有 error → failed。有 warning → passed_with_warnings。
> review_recommendation 会自动生成建议文案。
>
> 注意：validate-package 不修改 submission status，不创建 review record，不 approve，不 publish。只是辅助审核。"

### Scene 3 — Marketplace

**页面**：`/agent-marketplace`

> "审核通过后，管理员 Publish 到 Marketplace。Developer Agent 以 `publisher_type=developer` 出现在 Marketplace 中。
> 管理员可以 install、配置 permissions_granted。
> 但 install 不意味着可以 execution。这是关键边界——Marketplace install 和 Runtime enable 是两个独立步骤。"

### Scene 4 — Runtime Admin

**页面**：`/admin/runtime`

> "进入 Sidebar 新菜单：Runtime Admin。
>
> （切换到 Runtime Adapters tab）
> 5 个 adapter 类型：manifest_only（active）、simulation（beta）、http_webhook/sandboxed_process/container（disabled）。
> 每个 adapter 展示 supports_network、supports_user_data_read/write、sandbox_required、max_timeout_ms、max_memory_mb。
> MVP 只允许 manifest_only 和 simulation。
>
> （切换到 Runtime Bindings tab）
> 点击 Create Binding——填写 marketplace_agent_id、选择 simulation adapter、可选绑定 sandbox policy。
> 创建后 binding 状态为 pending。
> 提示文案：'Creating a binding does NOT execute code, install the agent, or grant data access.'
>
> 点击 Enable。系统检查：adapter 是否 active？是否 MVP allowed？
> simulation adapter 不需要 sandbox policy。Enable 成功后状态变为 enabled。
> 提示文案：'Binding enabled. Does NOT execute code.'
>
> （切换到 Sandbox Policies tab）
> 3 个 system policies：no_execution、simulation_only、restricted_network_off。
> 全部 system_managed=true——不可删除，不可由普通 admin 修改关键字段。
> 点击 Test Policy——请求 network=true → 返回 deny。
>
> （切换到 Readiness Guide tab）
> 7 步 checklist，让管理员清楚知道 Developer Agent 是否 simulation-ready。"

### Scene 5 — Simulation Runtime

**API**：`POST /developers/marketplace-agents/{id}/simulate`

> "最后，我们看 Simulation 的实际效果。
>
> （使用 curl 或 Swagger，带 API Key header 或 JWT）
> （发送 POST simulate 请求）
>
> 系统执行 9 步验证链路：
> 1. validate_marketplace_agent → agent 存在 ✓
> 2. validate_developer_publisher → publisher_type=developer ✓
> 3. validate_runtime_metadata → package_url not executed ✓
> 4. validate_installation → installation active + enabled ✓
> 5. validate_permissions → agent:execute granted ✓
> 6. validate_runtime_binding → binding exists + eligible ✓
> 7. validate_adapter → simulation adapter active ✓
> 8. validate_scope → agent:simulate scope present ✓
> 9. generate_simulated_response → deterministic mock
>
> （展示响应）
> ```json
> {
>   "status": "success",
>   "simulated_output": {
>     "mode": "simulation",
>     "agent_name": "Test Sim Agent",
>     "message": "Simulation completed without executing external code. No package_url was downloaded or executed. No network calls were made. No real enterprise data was accessed. This is a deterministic mock response."
>   },
>   "metadata": {
>     "no_remote_code_execution": true,
>     "simulation_only": true,
>     "no_network": true
>   }
> }
> ```
>
> 如果缺少 installation——blocked: INSTALLATION_REQUIRED。
> 如果缺少 runtime binding——blocked: RUNTIME_BINDING_REQUIRED。
> 如果 API Key 没有 agent:simulate scope——403。
>
> 全过程：不下载 package、不执行 entrypoint、不调用 AgentRuntime、不注册 AgentRegistry。"

## 7. 页面操作步骤

| 页面 | 操作 | 关键展示点 | 安全边界一句话 |
|------|------|-----------|-------------|
| `/developer` | 查看 Developer Profile | status, developer_id, stats | 开发者身份绑定 JWT user + workspace |
| `/developer/api-keys` | 创建 Key → 展示 raw_key → 关闭弹窗 → 撤销 | raw_key only once, key_prefix only in list | 数据库只存 prefix + hash, not raw |
| `/developer/agents/new` | 默认模板 → 修改 → 创建 draft | Manifest JSON textarea | runtime_type=manifest_only only |
| `/admin/agent-submissions` | 筛选 submitted → 点击详情 | submission card, status badge | Admin only, tenant scoped |
| `/admin/agent-submissions/[id]` | Start Review → Approve → Publish | Manifest/SecurityProfile/Validation/Review | Approve ≠ publish; publish ≠ runtime |
| `/agent-marketplace` | 浏览 → 点击 Developer Agent | publisher_type=developer badge | Install ≠ execution |
| `/admin/runtime` | Adapters/Bindings/Policies/Guide 4 tabs | Create Binding, Enable, Assign Policy, Test | Enable ≠ code execution; Policy ≠ container |

## 8. API 演示步骤

```bash
# 1. 获取 Manifest Schema
curl http://127.0.0.1:8000/developers/agent-manifest/schema \
  -H "Authorization: Bearer <JWT_TOKEN>"

# 2. 校验 Manifest
curl -X POST http://127.0.0.1:8000/developers/agent-manifest/validate \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"manifest": {...}, "strict": true}'

# 3. Package Validation (Admin)
curl -X POST http://127.0.0.1:8000/admin/agent-submissions/<SUBMISSION_ID>/validate-package \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"validation_options": {}}'

# 4. 获取 Package Validation 结果
curl http://127.0.0.1:8000/admin/agent-submissions/<SUBMISSION_ID>/package-validation \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>"

# 5. 创建 Runtime Binding (Admin)
curl -X POST http://127.0.0.1:8000/admin/runtime/bindings \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"marketplace_agent_id": "<MKP_ID>", "adapter_id": "rtadp_simulation"}'

# 6. Enable Binding (Admin)
curl -X POST http://127.0.0.1:8000/admin/runtime/bindings/<BINDING_ID>/enable \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>"

# 7. Simulation (Developer API Key)
curl -X POST http://127.0.0.1:8000/developers/marketplace-agents/<MKP_ID>/simulate \
  -H "X-Cognitive-API-Key: <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"input_text": "hello"}'

# 8. Runtime Eligibility
curl http://127.0.0.1:8000/admin/runtime/developer-agents/<MKP_ID>/eligibility \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>"

# 9. List Adapters
curl http://127.0.0.1:8000/admin/runtime/adapters \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>"

# 10. List Sandbox Policies
curl http://127.0.0.1:8000/admin/sandbox-policies \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>"
```

## 9. 安全边界页

| 能力 | 当前状态 | 是否真实执行 | 说明 |
|------|---------|------------|------|
| Manifest Schema | ✅ 完成 | 否 | 静态 JSON Schema + 后端 validator |
| SDK Validator | ✅ 完成 | 否 | 本地 CLI, 不联网, 不调 API |
| Package Validation | ✅ 完成 | 否 | 静态 metadata check, 不下载 |
| Sandbox Policy | ✅ 完成 | 否 | 策略模型, is_execution_allowed=False |
| Runtime Binding | ✅ 完成 | 否 | Readiness 状态管理, enable ≠ execute |
| Runtime Eligibility | ✅ 完成 | 否 | 状态检查, 不调 AgentRuntime |
| Simulation Runtime | ✅ 完成 | 否 | Deterministic dry-run, mock output |
| API Key Auth | ✅ 完成 | — | Scope enforcement, admin routes denied |
| Container Sandbox | ❌ 未实现 | — | Step 24+ |
| External Code Execution | ❌ 未实现 | — | Step 24+ |
| Real CVE Scan | ❌ 未实现 | — | Step 24+ |
| Signature Verification | ❌ 未实现 | — | Step 24+ |
| Real Payment | ❌ 未实现 | — | Not planned in Step 24 |

## 10. 评委 Q&A（15 题）

### Q1: 你们是否执行第三方代码？

> "不执行。Step 23 所有能力——Manifest SDK、Package Validation、Sandbox Policy、Runtime Binding、Simulation Runtime——都不执行任何第三方代码。Simulation 返回的是 deterministic mock 结果。真正的外部代码执行需要 Step 24+ 的容器/子进程 sandbox 基础设施。"

### Q2: package_url 会不会被下载？

> "不会被下载。Package Validation Pipeline 只做静态 URL 格式校验——检查 scheme 是否为 HTTPS、hostname 是否在 blocklist 中、是否为内网 IP。不做 DNS 解析，不发 HTTP HEAD/GET，不下载任何内容。PackageValidationResult 强制设置 `no_download_performed=true`。"

### Q3: Sandbox Policy 是不是容器沙箱？

> "不是。SandboxPolicy 是策略模型——定义 developer agent 允许的资源边界（network、filesystem、secrets、timeout、memory）。它不包含任何执行引擎。`is_execution_allowed()` 对 no_execution 和 simulation_only 永远返回 False。真正的容器沙箱需要 Step 24+。"

### Q4: Simulation 是不是实际运行？

> "不是。Simulation Runtime Adapter 不执行 package_url、不执行 entrypoint、不联网、不读取真实企业数据。它只验证 install → permissions → binding → adapter → scope 链路是否通畅，然后返回 deterministic mock 结果。AgentResult.metadata 强制标记 `simulation=true`。"

### Q5: API Key 能不能绕过管理员审核？

> "不能。API Key 的 scope 在创建时经过白名单校验——`admin:review`、`admin:publish` 在 FORBIDDEN 列表中直接被拒绝。所有 Admin Review / Runtime Admin / Sandbox Policy API 使用 `require_auth`（JWT only），不接受 API Key。API Key 只能访问 Developer API 的特定端点。"

### Q6: Developer 能不能自己 publish？

> "不能。publish 在 Admin Review router 中，需要 `_require_admin`（JWT admin/owner/super_admin）。Developer 只能提交审核（submit），不能 publish。API Key 同样不能——publish endpoint 不接受 API Key。"

### Q7: Install 之后是不是自动可以运行？

> "不是。Marketplace install 和 Runtime enable 是两个独立步骤。install 创建 TenantAgentInstallation 记录，赋予 permissions_granted。但要进入 Simulation Runtime，还需要：admin 创建 Runtime Binding、enable binding、bind sandbox policy（如果需要）。缺少任何一步，Simulation 都会 blocked。"

### Q8: Package Validation 是不是 CVE 扫描？

> "不是。Package Validation Pipeline 只做静态 metadata 检查——URL 合规、checksum/signature 算法声明、dependencies 是否为 list、license 是否声明。不做 CVE scan，不做 dependency 版本分析，不做 package binary 扫描。所有 check codes 中 `package_not_downloaded` 和 `package_not_executed` 永远 passed。"

### Q9: Signature 是否真实验证？

> "不做真实验证。Package Validation 只检查 `package_signature_algorithm` 是否在允许列表（minisign/cosign/gpg）中。不下载 package，不验证签名。这是已知限制，Step 24+ 将集成真实签名验证。"

### Q10: Tenant isolation 怎么保证？

> "所有 Runtime Admin API 要求 admin JWT。tenant_id 从 JWT payload 提取。list_bindings 按当前 tenant 过滤；其他 tenant 的 binding 返回 404（不暴露存在性）。super_admin 可跨 tenant。API Key 的 tenant_id 来自 DeveloperAccount，不接受 request body 覆盖。安全测试中已验证跨 tenant denial。"

### Q11: raw_key/key_hash 是否泄露？

> "不泄露。API Key 创建时 raw_key 只在 response 中返回一次。后续 API 响应只含 key_prefix（8 字符），不含 raw_key 和 key_hash。`DeveloperApiPrincipal.to_dict()` 不含 hash。所有 usage metadata 不含 raw_key/key_hash。前端 TypeScript 类型中 DeveloperApiKey 没有 key_hash 字段。77 个安全测试已验证这些边界。"

### Q12: 如果开发者提交恶意 URL 怎么办？

> "Package Validation 在 URL 层面有三层防护：
> 1. 仅允许 HTTPS——http/ftp/file 被拒绝。
> 2. 内网 IP block——10.0.0.0/8、172.16.0.0/12、192.168.0.0/16、127.0.0.1、localhost、metadata.google.internal、169.254.169.254 全部被阻止。
> 3. Domain allowlist/denylist——管理员可配置。
> 但最重要的是：**系统不下载 package**。URL 只是 metadata。即使 URL 指向恶意载荷，也不会被下载或执行。"

### Q13: Runtime Binding enable 代表什么？

> "Enable binding 只是一个状态变更——将 `runtime_status` 从 `pending` 改为 `enabled`。它不启动 worker、不调用 AgentRuntime、不注册 AgentRegistry、不创建 installation、不修改 submission。它只表示：该 Developer Agent 的 runtime readiness 已就绪，可以进行 Simulation。真正的代码执行需要 Step 24+。"

### Q14: Step 24 要做什么？

> "Step 24 的规划方向：
> 1. Container/isolated worker sandbox — 真正隔离的执行环境
> 2. Policy-enforced execution — SandboxPolicy 在运行时被 enforcement engine 读取并应用
> 3. Package download in sandbox — 在隔离环境中下载并校验 package
> 4. Signature verification — 真实签名验证
> 5. CVE scanner integration — 依赖漏洞扫描
> 6. Runtime logs / kill switch — 运行时日志和紧急停止
> 7. 具体范围将在 Step 23-K 最终回归后确定。"

### Q15: 当前限制是什么？

> "诚实列出：
> 1. 不执行任何外部代码——Simulation 只是 dry-run
> 2. 没有容器/子进程 sandbox
> 3. 不做真实 CVE scan / signature verification
> 4. SDK 未发布 pip/npm 包
> 5. Policy create/edit UI 未做
> 6. Marketplace Detail runtime status 未集成
> 7. Developer Console schema/validate UI 未集成
> 8. Build 可能仍受历史 lint blocker 影响
> 9. 无 payment / revenue share
> 10. 无 public unauthenticated app store"

## 11. 测试证明

| 测试套件 | 数量 | 结果 |
|----------|------|------|
| Step23 Security/Runtime 专项 | 77 | ✅ passed |
| Open Platform 全量 | 678 | ✅ passed |
| 后端全量回归 | 1325 | ✅ passed |
| TypeScript | — | 通过 |
| Scoped ESLint | — | 0 errors, 0 warnings |

> **Build note**：`npx next build` 编译成功但被历史 lint blocker（`graph/page.tsx`、`memory/page.tsx` 等预存文件）阻塞，非 Step 23 新增。

## 12. Known Issues

| # | 问题 | 影响 | 计划 |
|---|------|------|------|
| 1 | Policy create/edit UI 未做 | Admin 需通过 API 管理 tenant policy | Step 24 |
| 2 | Marketplace Detail runtime status 未集成 | Developer Agent 页面不展示 runtime readiness | Step 24 |
| 3 | Developer Console schema/validate UI 未集成 | 开发者需用 SDK CLI 或 API 校验 manifest | Step 24 |
| 4 | SDK 未发布 pip/npm | 开发者需手动复制 SDK 代码或使用 API | Step 24 |
| 5 | Package validation 不做真实 CVE scan | 依赖安全需人工审核 | Step 24 |
| 6 | Signature 不做真实验证 | 供应链安全依赖人工验证 | Step 24 |
| 7 | 无 container sandbox | 外部代码无法执行 | Step 24+ |
| 8 | 无 external code execution | Simulation 仅为 dry-run | Step 24+ |
| 9 | Build 被历史 lint blocker 阻塞 | 不影响功能 | Cleanup PR |

## 13. Step 24 Preview

Step 24 候选方向（规划，非承诺）：
- Container / isolated worker sandbox design
- Policy-enforced execution engine
- Package download in sandbox
- Signature verification
- CVE scanner integration
- Runtime logs / kill switch
- SDK pip/npm publish
- Frontend UX completion (policy editor, runtime status in marketplace detail, manifest schema UI)
- Historical lint blocker cleanup

> 具体范围将在 Step 23-K 最终回归后确定。
