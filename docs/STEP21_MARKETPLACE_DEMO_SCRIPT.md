# Step 21 Demo Script：Agent Marketplace 企业内部智能体市场

## 1. 演示目标

**证明 Cognitive OS 已经从"能运行 Agent"升级为"能发现、安装、配置、治理和计量 Agent"。**

Agent Marketplace 是 Cognitive OS 的**企业内部 Agent 能力分发中心**，补全了 Step 20 Enterprise AI Agent Platform 缺失的发现、安装、配置和治理闭环。

核心边界：
- `/agents` — 执行中心（Internal Agent Center）：运行 Agent、执行 Workflow、运行 Scenario
- `/agent-marketplace` — 发现与安装中心（Agent Marketplace）：浏览、安装、配置、治理 Agent
- **这不是 Step 22 Open Platform** — 当前仅支持内置 Agent，不支持第三方开发者上传

## 2. 演示核心卖点

| 卖点 | 演示中如何体现 |
|------|---------------|
| Agent 可发现 | 按 category / department 筛选、搜索、卡片浏览 |
| Agent 可安装 | 一键安装，自动记录 UsageEvent |
| Agent 可配置 | Config Dialog 编辑 JSON 配置、权限、用量限制、版本锁定 |
| Agent 可启停 | Enable / Disable 开关，即时生效 |
| Agent 可卸载 | 软删除，不影响其他 workspace |
| Agent 权限可展示 | required / granted / missing 三栏权限面板 |
| Agent 用量可计量 | Usage Summary：总调用、30天调用、安装次数、最后使用、限额、剩余 |
| Plan Limit 管控 | Free(1) / Personal(1) / Professional(5) / Team(20) / Enterprise(无限) |
| Tenant/Workspace 隔离 | 跨 tenant 返回 404，跨 workspace 数据不泄露 |
| 安全权限模型 | Member/Viewer 可浏览不可管理，Admin/Owner/SuperAdmin 可管理 |
| Analytics MVP | installed_agents, enabled_installations, top_categories, top_agents |
| 不越界 Step 22 | 无 publish/upload/developer/review/revenue/share 入口 |

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

验证：
```bash
cd D:\dma\day2

# Marketplace 专项测试（89 + 67 = 156 tests）
python -m pytest tests/test_agents/test_marketplace_api.py tests/test_agents/test_marketplace_store.py tests/test_agents/test_marketplace_security.py -v

# 全量回归
python -m pytest tests/test_security.py tests/test_agents/ tests/test_rbac/ tests/test_saas/ -v
# → 647 passed, 0 failed

# 前端检查
cd frontend
npx tsc --noEmit
npx eslint app/agent-marketplace/ components/agents/AgentU* components/agents/Marketplace* types/marketplace.ts services/marketplace.ts --ext .ts,.tsx
```

> **注意**: `npx next build` 编译成功（✓ Compiled successfully），但全量 lint 仍有历史 blocker：
> `graph/page.tsx`（vis-network `any` 类型）、`memory/page.tsx`（prefer-const）等。非 Step 21 新增。

## 4. 演示路径 A：Marketplace 首页 — Agent 发现

**路径：** `http://localhost:3000/agent-marketplace`

### 步骤

| # | 操作 | 讲解要点 |
|---|------|---------|
| 1 | 打开 `/agent-marketplace` | "这是 Cognitive OS 的 Agent Marketplace——企业内部 Agent 发现与安装中心" |
| 2 | 指向 Hero 区域 | "四个状态标签：Internal Marketplace、Auth/RBAC Protected、Tenant Installed、Usage Metered" |
| 3 | 指向文案说明 | "`/agents` 用于执行 Agent，`/agent-marketplace` 用于发现与安装 Agent——两个页面职责清晰" |
| 4 | 展示 Analytics Summary 卡片 | "Agent 总数、已安装、已启用、已停用、安装事件、Agent 执行——一条线看全景" |
| 5 | 指向 Agent 卡片列表 | "6 个内置 Agent 以卡片展示，含分类、部门、计费模型、能力标签、安装次数、评分" |
| 6 | 使用 category 筛选下拉选择 `automation` | "按分类筛选——automation / assistant / knowledge / training / sales / support / engineering / hr / analytics" |
| 7 | 使用 department 筛选下拉选择 `销售部` | "按部门筛选——每个部门 Agent 只服务于本部门" |
| 8 | 点击 Installed filter 切换到 "已安装" | "目前没有任何已安装 Agent" |
| 9 | 切换回 "全部" | "也可以通过搜索框按名称/描述/能力搜索" |
| 10 | 选择一个 Agent，点击 **"安装"** 按钮 | "一键安装——安装成功后状态立即变为'已安装'" |
| 11 | 切换到 "已安装" 筛选 | "现在该 Agent 出现在已安装列表" |
| 12 | 点击卡片上的 **"详情"** | 进入 Agent 详情页（演示路径 B） |

**讲解重点：**

> "这不是 Agent 执行页面，而是企业内部 Agent 的发现和安装中心。
> 就像企业内部应用商店——管理员可以看到所有可用 Agent，了解能力和权限，然后决定安装哪些。"

## 5. 演示路径 B：Agent 详情页 — 深度了解与决策

**路径：** `http://localhost:3000/agent-marketplace/mkp_knowledge`

### 步骤

| # | 操作 | 讲解要点 |
|---|------|---------|
| 1 | 打开详情页 | "这里展示 Agent 的完整信息：display_name、long_description、category、department、pricing_model、version" |
| 2 | 展示 Capabilities 区域 | "Agent 支持的具体能力——以标签形式展示" |
| 3 | 展示 Supported Workflows | "该 Agent 参与的工作流——如 meeting-to-knowledge-to-training" |
| 4 | 展示 Permissions Panel | "三栏权限：required 需要哪些权限、granted 已授权哪些、missing 还缺哪些" |
| 5 | 指向 Pricing Badge | "免费 / 按次计费 / 按人计费 / 订阅——一目了然" |
| 6 | 展示安装状态区域（未安装时） | "如果未安装，显示 Install 按钮" |
| 7 | 点击 **"安装 Agent"** | "安装成功后，状态区域切换为已安装视图" |
| 8 | 展示 Installation ID、Status、Enabled | "每个安装有唯一 ID，可追溯" |
| 9 | 展示 Usage Summary | "总调用、30天调用、安装次数、最后使用时间、限额、剩余——完整用量画像" |
| 10 | 指向 billing_note | "明确标注：MVP usage only; no real payment charge." |
| 11 | 点击 **"启用/停用"** 按钮 | "可以随时启停 Agent——停用不影响安装数据，只是暂时不接收调用" |
| 12 | 点击 **"配置"** 按钮 | 打开 Config Dialog（演示路径 C） |

**讲解重点：**

> "管理员在安装 Agent 之前可以完整了解：这个 Agent 做什么、需要什么权限、怎么计费。
> 安装后，Usage Summary 告诉你实际用量——虽然当前是 MVP 计量，但数据模型已经为真实 billing 做好准备。"

## 6. 演示路径 C：安装管理页 — 配置与治理闭环

**路径：** `http://localhost:3000/agent-marketplace/installations`

### 步骤

| # | 操作 | 讲解要点 |
|---|------|---------|
| 1 | 打开 `/agent-marketplace/installations` | "当前 workspace 所有已安装 Agent——一个管理面板" |
| 2 | 展示列表 | "每个安装显示 agent_id、installation_id、安装时间、状态（运行中/已停用/异常）、version_pinned" |
| 3 | 点击 **"详情"** 跳转到 Agent 详情页 | "快速导航到 Agent 完整信息" |
| 4 | 返回 installations 页 | |
| 5 | 点击某个 Agent 的 **"启用/停用"** | "即时切换——成功返回后列表自动更新" |
| 6 | 点击 **"配置"** 按钮 | "打开 Config Dialog" |
| 7 | 在 Config Dialog 中编辑 config JSON | `{"mode": "full", "timeout": 30}` |
| 8 | 编辑 permissions_granted JSON 数组 | `["agent:execute", "memory:read", "memory:write"]` |
| 9 | 编辑 usage_limit_override JSON | `{"max_calls": 100}` |
| 10 | 编辑 version_pinned | `"2.0.0"` — 锁定版本，留空跟随最新 |
| 11 | 点击 **"保存"** | "保存成功后弹窗关闭，列表实时更新——JSON 格式错误会在提交前校验" |
| 12 | 点击 **"卸载"** | "两步确认——防止误操作" |
| 13 | 点击 **"确认"** | "安装记录从列表中移除（软删除），但数据仍然可查" |
| 14 | 返回首页 `/agent-marketplace` | "该 Agent 的 Installed 状态已变为'未安装'" |

**讲解重点：**

> "Marketplace 不只是展示页——而是安装、配置、治理的完整闭环。
> 从发现到安装到配置到启用/停用到卸载，每一步都有权限检查、tenant 隔离、usage 记录。
> 这不是'演示级'功能——是经过 156 个专项测试和 647 个全量回归的生产级代码。"

## 7. 演示路径 D：Plan Limit 与安全边界

### 步骤

| # | 操作 | 讲解要点 |
|---|------|---------|
| 1 | 打开浏览器 DevTools Network 面板 | "我们先验证跨 tenant 隔离" |
| 2 | 在 Swagger (`/docs`) 中尝试用 viewer token 调用 POST install | "返回 403 — viewer 只能浏览不能安装" |
| 3 | 尝试用 member token 调用 PATCH config | "返回 403 — member 不能管理" |
| 4 | 尝试用其他 tenant 的 installation_id 调用 GET detail | "返回 404 — 不暴露跨 tenant 资源存在性" |
| 5 | 切换到 Plan Limit 说明 | "每个 SaaS 套餐有对应的 Agent 安装数量上限" |

**Plan Limit 规则表：**

| Plan Tier | max_marketplace_agents | 说明 |
|-----------|----------------------|------|
| Free | 1 | 试用限制 |
| Personal | 1 | 个人限制 |
| Professional | 5 | 小团队够用 |
| Team | 20 | 中大型团队 |
| Enterprise | 999999 | 无限制 |

**讲解重点：**

> "Plan Limit 确保 Agent 安装数量与套餐匹配——不是阻碍，而是让企业理性选择。
> disabled 的安装仍然占用配额，但 uninstalled 不占用——
> 这意味着你可以在不增加成本的情况下来回测试 Agent。"

## 8. 推荐讲解话术

### 30 秒电梯演讲

> "Cognitive OS 不只是能运行 Agent——它能让你像管理企业应用一样管理 Agent。
> 你可以浏览、安装、配置、启用/停用、卸载 Agent，
> 查看每个 Agent 的用量和权限，按套餐控制安装数量。
> 从'能运行'到'可管理'——这就是 Agent Marketplace。"

### 2 分钟路演版

> "大家好，这是 Cognitive OS Agent Marketplace——企业内部 Agent 分发中心。
>
> 我们先看 Step 20 的核心能力：12 个内置 Agent 可以执行任务、运行 Workflow、完成业务场景。
> 但问题来了：如果企业有 100 个员工、20 个部门、10 种使用场景——
> 怎么知道哪些 Agent 可用？谁能安装？装了多少？用了多少次？
>
> Agent Marketplace 解决了这个问题。
> 你可以在 Marketplace 首页按分类和部门浏览所有可用 Agent。
> 点击安装——权限自动校验、usage event 自动记录。
> 安装后，你可以编辑配置、管理权限、设置用量上限、锁定版本。
> 启动/停用——即时生效。卸载——软删除，数据不丢。
>
> 这不是演示——是 156 个专项测试和 647 个全量回归测试覆盖的生产级代码。
> 所有操作受 tenant/workspace 隔离保护，member 和 viewer 只能浏览不能管理。"

### 5 分钟答辩版

> "各位评委好，我是黔智脑 Cognitive OS 的技术负责人。
> 我今天展示的是 Step 21 Agent Marketplace——从 Agent Runtime 到 Agent Governance 的升级。
>
> 先回顾一下背景：Step 20 我们实现了 Enterprise AI Agent Platform——
> 12 个内置 Agent、WorkflowEngine 9 种节点、ScenarioEngine 业务场景编排。
> 但 Step 20 回答的问题是"Agent 能不能运行"。
> Step 21 回答的是"Agent 能不能被有效地分发、管理、控制和计量"。
>
> 演示第一部分：Marketplace 首页。
> （打开页面，展示筛选和安装交互）
> 6 个内置 Agent 以卡片方式展示。按分类筛选、按部门筛选、按安装状态筛选。
> 一键安装——usage event 自动记录。安装后立即显示已安装状态。
> Analytics Summary 让你一眼看到全貌：哪些 Agent 被装了多少、启用了多少、执行了多少次。
>
> 演示第二部分：Agent 详情页。
> （打开 detail 页面，展示能力和权限）
> 管理员可以完整了解：这个 Agent 做什么、需要什么权限、如何计费。
> 权限三栏面板：required vs granted vs missing——边界清晰。
> Usage Summary 告诉实际用量：总调用、30天调用、限额、剩余。
> 明确标注 "MVP usage only; no real payment charge"——诚实、不做假。
>
> 演示第三部分：安装管理页。
> （打开 installations 页面，展示配置和卸载）
> 启用/停用、编辑配置、管理权限——完整的治理闭环。
> JSON 格式校验在提交前完成，避免无效 API 调用。
> 卸载是两步确认——防止误操作。
>
> 演示第四部分：安全边界和 Plan Limit。
> （展示 403/404/plan_limit）
> 跨 tenant 访问返回 404——不暴露存在性。
> Member/Viewer 只能浏览不能管理——403。
> Plan Limit 确保安装数量与套餐匹配——Free(1), Professional(5), Enterprise(无限)。
>
> 技术架构上：
> - 六边形架构：MarketplaceAgent / TenantAgentInstallation 纯领域模型
> - SQLiteMarketplaceStore：完整协议实现，30 个单元测试
> - 13 个 API 端点：全部 require_auth，层次分明的权限模型
> - Tenant/workspace 隔离：跨 tenant 404，数据不泄露
> - Usage/Billing/Analytics MVP：真实写入 usage_events，可扩展
> - 647 个后端测试全部通过，零回归
>
> 需要诚实说明的是：
> - 当前不是外部开放市场——不支持第三方开发者上传
> - 不接入真实支付——Usage 是 MVP 计量
> - 这为 Step 22 Open Platform 做好了完整的数据模型和权限基础
>
> 总结：Agent Marketplace 让 Cognitive OS 从'能运行 Agent'升级为'能管理 Agent 生态'。
> 这不是一个页面——是一套经过测试、经过安全审计、经过隔离验证的企业级 Agent 治理体系。"

## 9. 评委可能追问与回答

### Q1: 这和 /agents 页面有什么区别？

> "`/agents` 是执行中心：运行 Agent、执行 Workflow、查看执行历史。关注的是'运行'。
> `/agent-marketplace` 是发现与安装中心：浏览、安装、配置、启停、卸载。关注的是'生命周期管理'。
> 两者通过 agent_id 关联，但不是同一个页面——职责分离。"

### Q2: 为什么需要 Marketplace？Agent 直接运行不就行了？

> "当企业有 6 个 Agent，管理员可以说'把所有都装了'。
> 当有 60 个 Agent、20 个部门、10 种使用场景时——
> 你需要知道哪些 Agent 存在、每个需要什么权限、哪些部门安装了哪些、用了多少次。
> Marketplace 解决的就是 Agent 的'可发现性'和'可治理性'问题。"

### Q3: 如何防止普通员工随便安装 Agent？

> "安装 Agent 需要 admin/owner 角色。Member 和 viewer 只能浏览，不能安装、配置、卸载。
> Super admin 可以管理所有。403 错误会明确提示'需要 admin 或以上角色'。
> 这是通过 `_require_admin` 依赖注入实现的——不是前端隐藏按钮，是后端强制检查。"

### Q4: 如何保证不同企业数据不串？

> "每个 API 调用都从 JWT TokenPayload 中提取 tenant_id 和 workspace_id。
> Store 层的所有安装查询都按 tenant_id + workspace_id 过滤。
> 跨 tenant 访问返回 404——不是 403，避免暴露资源存在性。
> 数据库层面有 UNIQUE INDEX `(tenant_id, workspace_id, marketplace_agent_id) WHERE status != 'uninstalled'`。"

### Q5: Agent 安装数量如何和套餐绑定？

> "PlanLimit 有一个 `max_marketplace_agents` 字段。
> 安装 Agent 时，`_check_plan_agent_limit()` 查询当前 subscription 的 plan limit，
> 统计当前 tenant 的非 uninstalled 安装数，超出限制返回 403。
> 卸载后释放配额。停用（disabled）不释放——因为你还在用。
> Super admin 可以绕过这个限制。"

### Q6: 是否已经接入真实支付？

> "没有。当前 Usage/Billing/Analytics 是 MVP 级别。
> Usage events 真实写入 usage_events 表——数据模型正确。
> 但 limit 来自 `usage_limit_override` 或 `plan_limit` 推导，不是真实支付扣费。
> 所有页面上明确标注 'MVP usage only; no real payment charge.'
> 这为 Step 22 接入真实支付提供了完整的计量基础。"

### Q7: 是否支持第三方开发者上传 Agent？

> "当前不支持。内置 Marketplace Catalog 只有 6 个 Agent。
> 这是 Step 22 Open Platform 的范围——将支持：
> - 第三方开发者注册
> - Agent SDK
> - 上传和审核流程
> - Revenue Share
> - Developer Console
> 当前 API 和前端经过审计确认——没有越界暴露任何 Step 22 能力。"

### Q8: Step 22 会做什么？

> "Step 22 Open Platform 将把 Marketplace 从封闭变为开放：
> 1. 第三方开发者注册和认证
> 2. Agent SDK — 标准化 Agent 开发接口
> 3. Agent 上传、审核、发布流程
> 4. Public / Private Marketplace 切换
> 5. Revenue Share — 平台与开发者收入分成
> 6. Developer Console — 开发者管理面板
> 7. API Key Management — 外部调用鉴权
> Step 21 已为该层打下完整的数据模型和权限基础。"

### Q9: 当前 Marketplace 的已知限制是什么？

> "诚实列出：
> 1. 不支持第三方 Agent 上传（Step 22）
> 2. 不支持 Agent SDK（Step 22）
> 3. 不支持 Revenue Share（Step 22）
> 4. 不接入真实支付（Step 22+）
> 5. Usage 是 MVP 计量，非真实 billing
> 6. Config 编辑器是 textarea，未来可升级 schema editor
> 7. next build 全量 lint 仍有历史 blocker（非 Step 21 新增文件）
> 8. 30 天 period 硬编码，可参数化
> 9. Agent runs 统计依赖 Metrics Store 注入 usage_store"

### Q10: 为什么不直接做 Open Platform？

> "架构分层原则：先确保核心 Agent 治理体系稳定可靠，再开放给外部。
> 就像 App Store 的演进——Apple 先有 iPhone，再有 App Store。
> Step 20 让 Agent 可运行。
> Step 21 让 Agent 可管理。
> Step 22 才让 Agent 可开放。"

## 10. 已知限制

| 限制 | 说明 | 影响 |
|------|------|------|
| 非外部开放市场 | 不支持第三方 Agent 上传 | 当前只展示内置 Catalog |
| 无 Agent SDK | 未提供标准化 Agent 开发接口 | 外部开发者无法创建 Agent |
| 无 Revenue Share | 未实现收入分成 | 不涉及真实商业模型 |
| 无真实支付 | Usage / Billing 是 MVP 级计量 | limit/remaining 来自配置推导，非真实扣费 |
| Config textarea | 配置编辑使用 JSON textarea | 升级路径：CodeMirror / Monaco schema editor |
| Build lint blocker | next build 编译成功，但全量 lint 被历史文件阻塞 | graph/page.tsx、memory/page.tsx、debug/page.tsx 等 |
| Agent runs 依赖注入 | Agent run usage 统计依赖 Metrics Store → UsageStore 注入链 | 如果 main.py 变更注入方式，需确保保持 |
| 30 days hardcoded | Usage period 固定 30 天 | 可参数化为 API query param |

**以上所有限制在 Step 22 及之后均可解决。当前不影响 Step 21 Marketplace 的完整闭环效果。**

## 11. 下一步

**Step 21-I：最终回归与 Step 22 准入审查** — 已完成。

**Step 22 Open Platform** — 已完成（2026-06-10）。Open Platform 将 Marketplace 从封闭变为开放：外部开发者可注册、提交 Agent Manifest、经过管理员审核后发布到 Marketplace。详见 [Step 22 Open Platform Demo Script](STEP22_OPEN_PLATFORM_DEMO_SCRIPT.md)。

## Related Demo

- **Step 20 Enterprise AI Agent Demo**: [STEP20D_DEMO_SCRIPT.md](STEP20D_DEMO_SCRIPT.md)
  - Step 20 展示 Agent 如何**执行** — 从会议到知识到培训的全自动闭环
  - Step 21 展示 Agent 如何被**发现、安装、配置、治理和计量** — 企业内部的 Agent 能力分发中心
- **Step 22 Open Platform Demo**: [STEP22_OPEN_PLATFORM_DEMO_SCRIPT.md](STEP22_OPEN_PLATFORM_DEMO_SCRIPT.md)
  - Step 22 展示外部开发者如何**提交 Agent**、管理员如何**审核**、审核通过后如何**发布到 Marketplace**

> **Step 21 / Step 22 边界**：Step 21 展示 Agent 如何被发现、安装、配置、治理和计量；Step 22 展示外部开发者如何提交 Agent、管理员如何审核、审核通过后如何发布到 Marketplace。Step 21 是"企业内部 Agent 分发中心"，Step 22 是"开放平台准入层"。两者通过 Publish 机制连接——Step 22 审核通过的 Agent 以 `publisher_type=developer` 进入 Step 21 的 Marketplace。
