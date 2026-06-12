# Step 22 Demo Script：Open Platform 开放平台

## 1. 演示目标

**证明 Cognitive OS 已经从"企业内部 Agent Marketplace"升级为"开发者可提交、管理员可审核、审核通过后可发布到 Marketplace 的开放平台"。**

Open Platform 引入三层架构：

| 路径 | 层 | 职责 |
|------|-----|------|
| `/agents` | Internal Agent Center | 执行 Agent、运行 Workflow、运行 Scenario |
| `/agent-marketplace` | Agent Marketplace | 发现、安装、配置、治理 Agent |
| `/developer` | Developer Console | 开发者注册、API Key 管理、Agent Manifest 提交 |
| `/admin/agent-submissions` | Admin Review | 审核与发布 |

**Step 22 是 Open Platform MVP，必须明确边界：**

- ✅ 是 Developer Console + Admin Review + Publish to Marketplace
- ❌ 不是真实支付系统
- ❌ 不是 Revenue Share 系统
- ❌ 不是远程代码执行平台
- ❌ 不是未审核 Agent 自动运行平台
- ❌ 不是 Public Store（无需认证的公开市场）

## 2. 演示核心卖点

| # | 卖点 | 演示中如何体现 |
|---|------|---------------|
| 1 | Developer Account | 注册流程、profile card、status 展示 |
| 2 | API Key 管理 | 创建/列表/撤销，scopes 配置 |
| 3 | raw_key 一次性展示 | 创建后弹窗展示，关闭后不再显示 |
| 4 | Agent Manifest 草稿 | 创建 draft，编辑 manifest JSON |
| 5 | Manifest Validation | 必填字段检查、security_profile 校验、runtime_type 限制 |
| 6 | Agent Submission 状态机 | draft → submitted → in_review → approved → published |
| 7 | Admin Review Queue | 按 status 筛选，查看 submission card |
| 8 | Manifest / Security Profile 审核 | 查看完整 manifest、security_profile、validation panel |
| 9 | Approve / Reject / Request Changes | 三种审核决策，必填 notes |
| 10 | Publish to Marketplace | 从 approved → published，创建 MarketplaceAgent |
| 11 | Developer Agent 出现在 Marketplace | `/agent-marketplace/{id}` 显示 developer badge |
| 12 | Marketplace Developer Publisher 信息 | publisher_type=developer, publisher_name, review_status |
| 13 | Publish 不执行代码 | package_url stored only, not executed |
| 14 | Publish 不创建 installation | MarketplaceAgent 创建但不自动安装 |
| 15 | Tenant / Workspace 隔离 | 跨 tenant 404，developer 只能操作自己的 submission |
| 16 | Security Gate 通过 | 27 安全审计测试 + 893 全量回归全部通过 |

## 3. 演示准备

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

推荐测试命令：

```bash
# Open Platform 专项测试
cd D:\dma\day2
python -m pytest tests/test_open_platform/ -v

# 全量回归（含 security + agents + rbac + saas + open_platform）
python -m pytest tests/test_security.py tests/test_agents/ tests/test_rbac/ tests/test_saas/ tests/test_open_platform/ -q

# 前端检查
cd frontend
npx tsc --noEmit

npx eslint app/developer/ app/admin/agent-submissions/ app/agent-marketplace/[id]/ components/open-platform/ types/open-platform.ts types/marketplace.ts services/developer.ts services/admin-submissions.ts services/marketplace.ts --ext .ts,.tsx
```

> **说明**：
> - `npx next build` 编译成功（✓ Compiled successfully）
> - 全量 lint 仍被历史 lint blocker 阻塞（`graph/page.tsx`、`memory/page.tsx` 等文件），非 Step 22 新增

## 4. 演示路径 A：Developer Console 注册

**路径：** `/developer`

### 步骤

| # | 操作 | 讲解要点 |
|---|------|---------|
| 1 | 打开 `/developer` | "这是 Cognitive OS 的 Developer Console——Open Platform 的开发者入口" |
| 2 | 如果未注册，页面引导进入 `/developer/register` | "首次使用需要注册 Developer Account" |
| 3 | 填写 `display_name` / `organization_name` / `contact_email` | "开发者身份绑定当前登录用户与 workspace" |
| 4 | 点击注册 | "创建成功后自动返回 Developer Console" |
| 5 | 查看 Developer Profile Card | "显示 developer_id、status、verified、注册时间" |
| 6 | 查看 status 标签 | "active / pending / suspended / rejected 四种状态" |

**讲解重点：**

> "开发者身份绑定现有用户与 workspace，不是匿名开发者。每个 user + workspace 组合只能注册一个 Developer Account。这是 Open Platform 的信任基础。"

## 5. 演示路径 B：API Key 管理

**路径：** `/developer/api-keys`

### 步骤

| # | 操作 | 讲解要点 |
|---|------|---------|
| 1 | 打开 API Keys 页面 | "API Key 管理——创建、查看、撤销" |
| 2 | 点击"创建 API Key" | |
| 3 | 填写 `name`（如 "My First Key"） | |
| 4 | 填写 `scopes`（如 `["agent:read", "agent:submit"]`） | "scopes 定义此 Key 的权限范围" |
| 5 | 可选填写 `expires_at` | "ISO 8601 格式，到期自动失效" |
| 6 | 点击创建 | |
| 7 | **弹窗展示 `raw_key`** | "这是唯一一次能看到完整 API Key 的机会！" |
| 8 | 复制 raw_key | "格式：`cos_dev_<prefix>_<secret>`" |
| 9 | 关闭弹窗 | "raw_key 不再显示——关闭后无法找回" |
| 10 | 查看 API Key 列表 | "列表只显示 `key_prefix`，不显示 raw_key，也不显示 key_hash" |
| 11 | 点击"撤销"按钮 | "撤销后 key 立即失效，不可恢复" |
| 12 | 确认撤销 | "撤销是软操作——记录保留但 status 变为 revoked" |

**讲解重点：**

> "API Key 只在创建时显示一次，数据库只存 prefix + hash。用 PBKDF2-HMAC-SHA256 + 260,000 轮迭代 + constant-time comparison 验证。这是安全最佳实践。"

**诚实说明：**

> "当前 API Key auth middleware 尚未实现。API Key 还不能用于绕过 JWT 调用系统 API。这是 Step 22-K 或 Step 23 的工作。"

## 6. 演示路径 C：创建 Agent Submission

**路径：** `/developer/agents/new`

### 步骤

| # | 操作 | 讲解要点 |
|---|------|---------|
| 1 | 打开 New Submission 页面 | "创建 Agent Submission——从 Manifest 开始" |
| 2 | 查看默认 Manifest 模板 | "系统预填了合理的默认值" |
| 3 | 修改 `name`（如 `my-knowledge-agent`） | "技术名，只允许小写字母、数字、短横线、下划线" |
| 4 | 修改 `display_name`（如 "我的知识助手"） | "展示名，用户可见" |
| 5 | 修改 `description` | "简要描述 Agent 功能" |
| 6 | 查看 `required_permissions` | "必须声明 Agent 所需的权限" |
| 7 | 查看 `security_profile` | "sandbox_level 默认为 no_execution" |
| 8 | 填写 `package_url`（可选） | "填写 package URL——但是..." |
| 9 | **强调：package_url stored only, not executed** | "MVP 阶段 package_url 只存储不执行——没有 Runtime sandbox" |
| 10 | 点击"创建草稿" | "创建成功，状态为 draft" |
| 11 | 跳转到 submission detail 页 | "可以继续编辑 manifest" |

**讲解重点：**

> "Step 22 MVP 是 Manifest-first，不执行第三方代码。`runtime_type` 必须是 `manifest_only`，`sandbox_level` 必须是 `no_execution`。任何其他值都会被 Manifest Validation 拒绝。这是安全底线——在 Runtime sandbox 就绪之前，不执行任何外部代码。"

## 7. 演示路径 D：提交审核

**路径：** `/developer/agents/[id]`

### 步骤

| # | 操作 | 讲解要点 |
|---|------|---------|
| 1 | 查看 draft submission 详情 | "显示完整 manifest、status、时间线" |
| 2 | 点击"Validate Manifest" | "运行 manifest 校验——检查必填字段、格式、安全约束" |
| 3 | 如果校验通过，显示 ✓ Valid | "所有必填字段完整、permissions 已声明、security_profile 合规" |
| 4 | 如果校验失败，显示具体 errors + warnings | "errors 阻止提交，warnings 提示潜在风险" |
| 5 | 点击"Submit for Review" | "提交审核——状态从 draft → submitted" |
| 6 | 确认提交 | "提交后 manifest 变为只读——不可编辑" |
| 7 | 查看状态变为 `submitted` | "等待管理员审核" |
| 8 | 点击"Withdraw"（可选） | "可以撤回——状态变回 draft，恢复可编辑" |

**讲解重点：**

> "Developer 只能提交审核，不能直接 publish。审核是 Open Platform 的安全闸门——在管理员 approve 之前，Agent 不会出现在 Marketplace。"

## 8. 演示路径 E：管理员审核队列

**路径：** `/admin/agent-submissions`

### 步骤

| # | 操作 | 讲解要点 |
|---|------|---------|
| 1 | 管理员打开审核队列 | "这是 Admin Review Queue——Open Platform 的安全闸门" |
| 2 | 按 status 筛选 `submitted` | "默认显示所有非 withdrawn 状态" |
| 3 | 按 status 筛选 `in_review` | "正在审核中的 submission" |
| 4 | 按 status 筛选 `approved` | "已通过但尚未发布的 submission" |
| 5 | 查看 submission card | "显示 name、status、developer_id、提交时间" |
| 6 | 查看 `developer_id` | "可以从 developer profile 了解开发者信息" |
| 7 | 查看 `required_permissions` 数量 | "权限需求概览——审核前快速判断风险" |
| 8 | 查看 security flags（如果有） | "安全风险标签——高亮显示" |
| 9 | 点击进入详情页 | "进入完整审核界面" |

**讲解重点：**

> "审核是 Open Platform 的安全闸门。没有自动通过——每个 submission 都必须经过管理员人工审核。Member 和 viewer 无权访问审核队列——需要 admin/owner 或以上角色。"

## 9. 演示路径 F：管理员审核详情

**路径：** `/admin/agent-submissions/[id]`

### 步骤

| # | 操作 | 讲解要点 |
|---|------|---------|
| 1 | 查看 Submission 基本信息 | "submission_id、developer_id、tenant_id、status、时间线" |
| 2 | 查看 Developer Profile | "display_name、organization_name、contact_email、verified 状态" |
| 3 | 查看 Manifest 完整内容 | "name、description、capabilities、supported_workflows" |
| 4 | 查看 Required Permissions | "逐条展示——审核者评估权限是否合理" |
| 5 | 查看 Security Profile | "sandbox_level、requires_network、reads_user_data、writes_user_data、data_access_scope" |
| 6 | 查看 Validation Panel | "自动校验结果：valid/errors/warnings" |
| 7 | 点击"Start Review" | "状态从 submitted → in_review，记录 reviewer_id" |
| 8 | **Approve**：填写 notes（可选），点击通过 | "状态从 in_review → approved，创建 review record" |
| 9 | **Reject**：填写拒绝理由（必填），点击拒绝 | "状态从 in_review → rejected，notes 必填" |
| 10 | **Request Changes**：填写修改建议（必填），点击要求修改 | "状态从 in_review → rejected，notes 说明需要什么改动" |
| 11 | 查看 Review Records | "每次审核决策都有独立记录——可追溯" |

**讲解重点：**

> "审核通过只是 approved，不等于已上架。approved 状态是一个中间状态——意味着 Manifest 通过审核，但还没有发布到 Marketplace。管理员不能审核自己的 submission（self-review 403）。"

## 10. 演示路径 G：Publish to Marketplace

**路径：** `/admin/agent-submissions/[id]`

### 步骤

| # | 操作 | 讲解要点 |
|---|------|---------|
| 1 | 在 approved 状态下，点击"Publish to Marketplace" | "将审核通过的 Agent 发布到 Marketplace" |
| 2 | 查看确认弹窗 | "弹窗明确说明发布行为" |
| 3 | 确认弹窗内容： | |
|   | ✓ create MarketplaceAgent entry | "在 marketplace_agents 表中创建记录" |
|   | ✓ publisher_type = developer | |
|   | ✓ does not execute package_url | "不执行任何代码" |
|   | ✓ does not install for any tenant | "不自动安装——需要管理员手动安装" |
|   | ✓ does not enable payment / revenue share | "不涉及真实支付" |
| 4 | 点击"确认发布" | |
| 5 | 状态变为 `published` | "published 是最终状态" |
| 6 | 显示 `marketplace_agent_id` | "格式：`mkp_dev_<name>_<suffix>`" |
| 7 | 点击跳转到 `/agent-marketplace/{id}` | "在 Marketplace 中查看已发布的 Agent" |

**讲解重点：**

> "Publish 只做一件事：把审核通过的 Manifest 映射成 MarketplaceAgent。不执行代码，不安装到任何 tenant，不注册 Runtime，不做任何运行时操作。Developer Agent 默认 visibility=beta, pricing_model=free。"

## 11. 演示路径 H：Marketplace Developer Agent

**路径：** `/agent-marketplace/{id}`

### 步骤

| # | 操作 | 讲解要点 |
|---|------|---------|
| 1 | 打开 Developer Agent 详情页 | "这就是从 Developer Console 审核发布的 Agent" |
| 2 | 查看 Developer Agent badge | "`publisher_type: developer` 标签——区别于 builtin" |
| 3 | 查看 `publisher_name` | "开发者组织名或 display_name" |
| 4 | 查看 `review_status` | "published——表明已经过审核" |
| 5 | 查看 `runtime_type` | "manifest_only——无运行时" |
| 6 | 查看 `sandbox_level` | "no_execution——无代码执行" |
| 7 | 查看 `no_remote_code_execution` 标注 | "metadata 中明确标注不执行远程代码" |
| 8 | 查看 `verified_publisher` | "显示开发者是否已验证" |
| 9 | 查看 install flow | "安装流程与 builtin Agent 一致——需要管理员操作" |
| 10 | **强调 install ≠ runtime execution** | "安装只是记录 installation 状态，不代表 Agent 可以自动运行" |

**讲解重点：**

> "Developer Agent 进入 Marketplace 后，仍然受 Marketplace 安装、权限和租户隔离管控。它和 builtin Agent 走完全相同的 install → enable → config → usage 流程。Open Platform 只负责'准入'，不负责'执行'。"

## 12. 推荐讲解话术

### 30 秒版本

> "Cognitive OS Open Platform 让外部开发者可以注册、提交 Agent Manifest、经过管理员审核后发布到 Marketplace。整个流程从 Developer Console → Admin Review → Publish → Marketplace，形成完整的开发者生态闭环。"

### 2 分钟版本

> "大家好，这是 Cognitive OS Open Platform。
>
> 在 Step 20 我们实现了 Agent 执行能力，Step 21 实现了企业内部 Agent Marketplace。
> Step 22 把 Marketplace 从封闭变为开放——但不是无限制开放。
>
> 核心流程四步：
> 1. **Developer Console** — 开发者注册、创建 API Key、编写 Agent Manifest、提交审核
> 2. **Admin Review** — 管理员审核 Manifest、Security Profile、Required Permissions，决定 approve/reject/request changes
> 3. **Publish** — 审核通过后发布到 Marketplace，创建 MarketplaceAgent，但不执行代码、不安装、不运行
> 4. **Marketplace** — Developer Agent 出现在 Marketplace，与其他内置 Agent 走相同的安装/配置/治理流程
>
> 安全底线：MVP 阶段不做远程代码执行、不做 Runtime sandbox、不做真实支付、不做 Revenue Share。
> 所有安全约束都通过 Manifest Validation + Admin Review + Publish 边界三重保障。"

### 5 分钟版本

> "各位评委好，我是黔智脑 Cognitive OS 的技术负责人。
> 我今天展示的是 Step 22 Open Platform——从封闭 Agent 平台到开放开发者生态的升级。
>
> 回顾一下演进路径：
> - **Step 20** Enterprise AI Agent Platform — 让 Agent 可运行
> - **Step 21** Agent Marketplace — 让 Agent 可管理
> - **Step 22** Open Platform — 让 Agent 可开放
>
> 核心问题：如果企业想引入外部 AI 能力，怎么办？
> 传统做法是找供应商、签合同、定制开发——周期长、成本高。
> Open Platform 提供了一条标准化路径。
>
> 先看 Developer Console。
> （演示注册 → API Key → Manifest → Submit）
> 开发者用现有用户体系注册——不需要单独账号系统。
> API Key 用 PBKDF2-HMAC-SHA256 存储，创建时一次性展示。
> Agent Manifest 是能力声明——name、capabilities、permissions、security_profile。
> Manifest Validation 确保声明合规——runtime_type 必须是 manifest_only，sandbox_level 必须是 no_execution。
>
> 再看 Admin Review。
> （演示审核队列 → 详情 → approve → publish）
> 管理员看到完整的 Manifest、Security Profile、Validation Panel。
> 三种决策：approve / reject / request changes。
> 不能自审——防止利益冲突。
> approve 只是通过审核，不等于上架。
>
> Publish 是关键一步。
> （演示 Publish → MarketplaceAgent 创建）
> build_marketplace_agent_from_submission() 做映射——Manifest → MarketplaceAgent。
> publisher_type = developer, visibility = beta, pricing_model = free。
> 不执行 package_url、不注册 Runtime、不创建 Installation。
>
> 发布后——Marketplace 详情页。
> Developer badge 让用户知道这是外部开发者提交的 Agent。
> 安装流程与 builtin Agent 完全一致——管理员手动安装。
> 所有权限检查、tenant 隔离、usage 计量照常生效。
>
> 安全方面：
> - Step 22-I 新增 27 个安全审计测试
> - Auth / Permission / Tenant Isolation / Publish Security / API Key Security / Frontend UX 全覆盖
> - 893 个后端全量回归测试全部通过
> - TypeScript typecheck 通过
> - Scoped ESLint: 0 errors, 0 warnings
>
> 诚实说明：
> - API Key auth middleware 尚未实现——目前 API Key 还不能用于绕过 JWT
> - 没有 Runtime sandbox——不能执行外部代码
> - 没有真实支付——不涉及 Revenue Share
> - 没有 SDK CLI——开发者手动编写 Manifest JSON
> - build 被历史 lint blocker 阻塞，不是 Step 22 新增
>
> 下一步 Step 22-K：最终回归与 Step 23 准入审查。
> 再之后 Step 23：Runtime Sandbox / SDK / Ecosystem Hardening。"

## 13. 评委可能追问与回答

### Q1: Open Platform 和 Marketplace 有什么区别？

> "Marketplace 是 Agent 发现与安装中心——用户在这里浏览、安装、配置、治理 Agent。Open Platform 是开发者入口——外部开发者在这里注册、提交 Agent、等审核、发布到 Marketplace。关系是：Open Platform 产生 Agent，Marketplace 分发 Agent。两者通过 Publish 连接。"

### Q2: Developer 能不能直接发布 Agent？

> "不能。Developer 只能提交审核（submit）。只有管理员在审核通过后（approved）才能发布（publish）。这是三层安全模型：Developer → Admin Review → Publish。没有绕过路径。"

### Q3: API Key 是否已经能调用系统 API？

> "不能。API Key auth middleware 尚未实现。当前 API Key 可以创建、管理、撤销——但还不能用于绕过 JWT 调用系统 API。这是已知限制，Step 22-K 或 Step 23 完成。"

### Q4: package_url 会不会被执行？

> "不会。MVP 阶段 package_url 只存储在数据库 agent_submissions 表的 package_url 字段中。Publish 时记录 `package_url_present: true` 到 metadata——仅作为信息标记。没有任何代码路径会下载、解压或执行 package_url。安全审计已覆盖此边界。"

### Q5: 外部 Agent 能不能访问企业数据？

> "不能，原因有三：
> 1. MVP 阶段 manifest_only——没有运行时，Agent 根本没有执行能力
> 2. 即使将来引入 Runtime，也会通过 sandbox_level 和 data_access_scope 控制
> 3. 所有 Agent 执行都经过 RBAC + Tenant + Workspace 三层隔离
> 外部 Agent 不会获得比内置 Agent 更高的权限"

### Q6: Publish 后是否自动安装？

> "不自动安装。Publish 只创建 MarketplaceAgent 记录。安装需要管理员在 Marketplace 中手动操作——和内置 Agent 一样的 install flow。Publish 和 Install 是完全独立的两个操作。"

### Q7: Publish 后是否自动运行？

> "不自动运行。Publish 不做任何运行时操作。不注册 AgentRuntime、不创建 WorkflowExecution、不触发任何 Agent 循环。Publish 是纯数据映射操作。"

### Q8: 是否支持真实支付？

> "不支持。当前 Usage / Billing 是 MVP 级别计量——记录 usage_events，推导 limit/remaining。没有接入任何支付网关。所有页面标注 'MVP only; no real payment charge'。"

### Q9: 是否支持 Revenue Share？

> "不支持。Revenue Share 是开发者与平台之间的收入分成机制——属于商业模型层面。Step 22 MVP 完全不涉及。Marketplace 中所有 Agent 的 pricing_model 在发布时强制设为 free。"

### Q10: 如何防止恶意 Agent？

> "四层防护：
> 1. **Manifest Validation** — name/capabilities/permissions/security_profile 格式和约束检查
> 2. **Admin Review** — 管理员人工审核 Manifest 内容是否合理、权限是否过度
> 3. **Publish 边界** — 不执行代码、不注册 Runtime、不自动安装
> 4. **Marketplace 管控** — 安装后仍受 install → enable → config → permissions 全流程管理
> Step 23 将增加第五层：Runtime Sandbox。"

### Q11: 如何保证 tenant 不串？

> "和 Step 21 一致的三层隔离：
> 1. 所有 API 从 JWT TokenPayload 提取 tenant_id + workspace_id
> 2. Developer Store 按 user_id + tenant_id 唯一索引
> 3. Submission Store 按 tenant_id 过滤
> 4. 跨 tenant 访问返回 404（不暴露存在性）
> 5. super_admin 可跨 tenant 查看所有审核队列
> 安全测试中已验证跨 tenant 隔离。"

### Q12: 为什么不直接做 SDK Runtime？

> "架构分层原则。先确保准入机制（Developer Console + Admin Review + Publish）可靠，再做运行时安全（Runtime Sandbox + SDK）。就像 App Store：先有审核流程，才有开发者 SDK。贸然开放 Runtime 却没有完善的审核和沙箱机制，是安全灾难。"

### Q13: Step 23 会做什么？

> "Step 23 的当前规划方向：
> 1. Runtime Sandbox — 受限代码执行环境
> 2. Agent SDK — 标准化开发接口，降低开发者门槛
> 3. Ecosystem Hardening — 加强安全边界、完善监控和告警
> 具体范围将在 Step 22-K 最终回归后确定。"

## 14. Security Gate 摘要

**Step 22-I 结论：Security Gate Passed**

安全审计覆盖：

| 审计域 | 状态 | 说明 |
|--------|------|------|
| Auth / Permission | ✅ Passed | 所有 Open Platform API require_auth |
| Tenant / Workspace Isolation | ✅ Passed | 跨 tenant 404，developer 只能操作自己的 submission |
| Publish Security | ✅ Passed | 只能从 approved 状态 publish |
| Runtime Non-Execution | ✅ Passed | Publish 不执行 package_url |
| Runtime Registration | ✅ Passed | Publish 不注册 AgentRuntime |
| Installation Boundary | ✅ Passed | Publish 不创建 TenantAgentInstallation |
| API Key Security | ✅ Passed | raw_key 一次性展示，key_hash 不出现在任何 API response |
| Usage Metadata Security | ✅ Passed | usage events 不暴露敏感信息 |
| Frontend Security UX | ✅ Passed | 无 payment / revenue / remote execution 误导 |
| Developer Agent Pipeline | ✅ Passed | Developer Agent 走完整 Marketplace install flow |

测试结果：

- 新增 27 个全链路安全审计测试
- 后端全量回归：893 tests 全绿
- TypeScript typecheck：通过
- Scoped ESLint：0 errors, 0 warnings
- `npx next build`：编译成功

## 15. Known Issues

| # | 问题 | 说明 | 影响 |
|---|------|------|------|
| 1 | API Key auth middleware 未实现 | API Key 不能用于绕过 JWT 调用系统 API | 外部 API 调用暂不可用 |
| 2 | API Key scopes 不做运行时权限控制 | scopes 仅存储在 DB，无 enforcement | 即使 middleware 实现后也需要额外工作 |
| 3 | API Key rate limit 未实现 | 没有调用频率限制 | 可能被滥用 |
| 4 | 无 Agent Runtime sandbox | 不能执行外部代码 | MVP 阶段仅 Manifest-first |
| 5 | Build 被历史 lint blocker 阻塞 | `graph/page.tsx`、`memory/page.tsx` 等历史文件 | 非 Step 22 新增，不影响功能 |
| 6 | Manifest rejected 后无前端 reopen 按钮 | 后端 `reopen_to_draft()` 已实现 | 前端缺少对应 UI |
| 7 | Admin Review 无 dashboard / pagination | 审核队列为简单列表 | 大量 submission 时体验下降 |
| 8 | 发布后不能由 developer 原地更新 | 需要新 submission 流程 | 迭代更新路径较长 |

**以上所有限制在 Step 22-K / Step 23 均可解决。**

## 16. 下一步

**Step 22-K：最终回归与 Step 23 准入审查**

> 完整跑一遍 893 测试、确认所有 Known Issues 明确标注、清理阻塞项、为 Step 23 做好准备。
