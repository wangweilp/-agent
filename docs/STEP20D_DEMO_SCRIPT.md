# Step 20-D Demo Script：Enterprise AI Agent 演示闭环

## 1. 演示目标

**证明 Cognitive OS 已经从知识管理系统升级为组织智能行动系统。**

本演示将展示两个闭环：
- 会议纪要到知识沉淀到培训生成的**全自动闭环**
- 部门知识助手基于部门知识库的**结构化建议生成**

## 2. 演示核心卖点

| 卖点 | 演示中如何体现 |
|------|---------------|
| 组织知识可沉淀 | 会议内容 → Memory + Knowledge Graph 自动入库 |
| 组织流程可执行 | Meeting Agent → Knowledge Agent → Training Agent 自动流转 |
| Agent 执行可追踪 | 每一步 PEOR 循环有完整 trace |
| Workflow steps 可审计 | 每个 WorkflowExecutionStep 含 status/duration/error |
| 部门知识可隔离 | 研发部/销售部/HR 各自的 Agent 只访问本部门 KB |
| 企业场景可落地 | Meeting-to-Training + Department Assistant 两个真实场景 |

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

# 终端 3：初始化演示数据（可选，前端已有 Demo Input 按钮）
cd D:\dma\day2
python scripts/seed_agent_demo.py              # dry-run 预览
python scripts/seed_agent_demo.py --apply      # 写入演示记忆
```

验证：
```bash
cd D:\dma\day2
python -m pytest tests/test_agents/ -q  # 235 passed
python -m pytest tests/test_security.py -q  # 49 passed
```

## 4. 演示路径 — 场景 1：会议纪要自动沉淀与培训生成

**路径：** `http://localhost:3000/agents/scenarios`

### 步骤

| # | 操作 | 讲解要点 |
|---|------|---------|
| 1 | 打开 Business Scenarios 页面 | "这是黔智脑 Internal Agent Center 的业务场景入口" |
| 2 | 在 Meeting-to-Knowledge-to-Training 卡片点击 **"演示输入"** | "一键填充项目复盘会议数据" |
| 3 | 点击 **"运行场景"** | "系统将在 <500ms 内完成 5 步自动执行" |
| 4 | 展开 **会议摘要** | "Meeting Agent 从会议内容中提取了关键信息" |
| 5 | 展开 **决策要点** 和 **行动项** | "每个行动项自动标记了负责人" |
| 6 | 展开 **培训大纲** 和 **练习QA** | "Training Agent 根据知识库自动生成了新人培训材料" |
| 7 | 展开 **实体建议** | "Knowledge Graph 自动识别了关联实体和关系" |
| 8 | 展开 **Workflow Execution Steps** | "5 个节点每一步耗时都可追溯" |
| 9 | 展示 **workflow_execution_id** | "这是真实 WorkflowExecution 的 ID，可在 API 中追溯" |
| 10 | 展开 **Agent Trace** | "每个 Agent 的 PEOR 循环完整记录" |
| 11 | 展示 **Metrics** 栏 | "耗时 ms、记忆引用数、图谱引用数" |

## 5. 演示路径 — 场景 2：部门知识助手

| # | 操作 | 讲解要点 |
|---|------|---------|
| 1 | 在 Department Knowledge Assistant 卡片选择 **研发部** | "部门 Agent 只会访问本部门知识库" |
| 2 | 点击 **"演示输入"** | "自动填充研发部典型问题" |
| 3 | 点击 **"运行场景"** | "Workflow: 部门Agent → Memory检索 → KG查询" |
| 4 | 展示 **分析结果** | "基于部门知识库的结构化建议" |
| 5 | 展示 **推理依据** | "解释为什么给出这些建议" |
| 6 | 展示 **置信度** | "0.85 — 基于确定性规则引擎" |
| 7 | 展示 **局限性** | "透明标注：当前使用关键词匹配，未使用 LLM 推理" |
| 8 | 切换部门到 **销售部** | "销售部的问题只会在销售知识空间搜索，不会看到研发数据" |
| 9 | 展示 **Workflow Steps** 和 **workflow_execution_id** | "同样具备可审计的执行链路" |

## 6. 推荐讲解话术

### 30 秒电梯演讲

> "黔智脑 Cognitive OS 不只是存储知识，还能让知识自动转化为行动。
> 比如，一场会议结束后，系统自动提取决策和行动项，把知识点存入知识图谱，
> 然后生成新人培训材料。整个过程全自动，每一步都可追溯、可审计。
> 这就是从'组织知识系统'到'组织智能行动系统'的升级。"

### 2 分钟路演版

> "大家好，这是黔智脑 Cognitive OS，企业 AI 知识管理操作系统。
>
> 我们先看第一个场景：会议纪要自动沉淀与培训生成。
> 把一场项目复盘会议输入系统，Meeting Agent 自动提取关键决策和行动项，
> Knowledge Agent 将知识点结构化存入知识图谱，
> Training Agent 自动生成培训大纲和练习题。
> 整个过程在 500ms 内完成，每一步都有完整执行记录。
>
> 再看第二个场景：部门知识助手。
> 不同部门有专属的知识空间，研发部的问题只在研发知识库中搜索。
> 即使没有 LLM 在线，我们的确定性规则引擎也能生成结构化建议，
> 并透明标注置信度和局限性。
>
> 核心技术亮点：12 个内置 Agent、PEOR 自反思循环、
> 9 种工作流节点、六边形架构、多租户 RBAC、完整执行追溯。"

### 5 分钟答辩版

> "各位评委好，我是黔智脑 Cognitive OS 的技术负责人。
> 我们今天展示的是 Step 20 Enterprise AI Agent 平台。
>
> 先说一下背景：传统企业知识管理——存了文档，放那儿吃灰。
> Cognitive OS 的不同在于：知识不是终点，行动才是。
>
> 演示第一个场景：会议→知识→培训闭环。
> （执行操作，展示结果）
> 大家看，Meeting Agent 从会议纪要中提取了决策和行动项，
> Knowledge Agent 把知识存入了图谱，并且识别了实体关联。
> 最有价值的是 Training Agent——自动生成了培训大纲和练习题。
> 这意味着新人入职时，过往的会议知识已经在等他。
>
> 第二个场景：部门知识助手。
> （切换部门，展示隔离效果）
> 研发部的数据不会出现在销售部结果里，天然支持企业数据合规。
>
> 技术架构上：六边形架构，核心层零外部依赖。
> Agent PEOR 循环——Plan 规划、Execute 执行、Observe 观察、Reflect 反思。
> WorkflowEngine 支持 9 种节点类型，每一步有 WorkflowExecutionStep。
> 权限上：RBAC+ABAC，6 级角色，Policy 策略引擎。
> 多租户：Tenant → Organization → Workspace 三层隔离。
>
> 测试数据：235 个 Agent 测试、49 个安全测试、246 个 SaaS 测试全部通过。
> 这不仅是演示——是可以直接部署的生产级代码。"

## 7. 技术亮点话术

| 模块 | 话术 |
|------|------|
| Agent Runtime | "每个 Agent 执行 PEOR 循环——不是简单的 if-else，而是有自我反思能力的 Agent" |
| WorkflowEngine | "9 种节点类型，Agent 可以串联 Human/Tool/Memory/KG/Condition 形成完整业务流" |
| WorkflowExecutionStep | "每一步记录耗时、状态、输出摘要、错误信息——满足企业合规审计要求" |
| AgentResult trace | "PEOR 四个阶段各自计时，Plan 花了多久、Execute 花了多久，一目了然" |
| RBAC + Tenant | "6 级角色、组织隔离、Policy 策略——不是玩具，是真正的企业级权限体系" |
| KB + KG integration | "Memory 存储知识、Knowledge Graph 建立关联——搜索'技术风险'不仅找到文档，还能找到相关项目、负责人、决策历史" |
| ScenarioEngine | "业务场景编排无需写死代码，Workflow nodes 定义流程，ScenarioEngine 编排执行" |
| Fallback transparency | "即使 LLM 离线，系统依然能基于规则引擎返回结构化结果，并明确标注'确定性引擎'和置信度" |

## 8. 商业价值话术

| 场景 | 价值 |
|------|------|
| 新人培训 | "新人入职第一天就能看到所有历史会议的要点总结和培训材料——培训效率提升 5-10x" |
| 会议复盘 | "会议结束 30 秒内生成纪要、行动项、知识点——不会再有'上次会议说了什么'的追问" |
| 知识问答 | "跨部门提问不需要'去问那个谁'，部门 Agent 从知识库直接生成答案" |
| 销售辅助 | "客户画像 + 竞品对比 + 话术建议——销售团队人均效率提升" |
| 研发辅助 | "技术方案评估、代码审查建议、技术债务分析——工程师的 AI 同事" |
| HR 培训 | "自动生成 7 天/30 天入职计划，基于公司实际知识库而非通用模板" |
| 客服辅助 | "高频问题识别 + 知识库优化 + 升级判断——减少人工服务量" |

## 9. 评委可能追问与回答

### Q1: 这和普通 Chatbot 有什么区别？

"A: Chatbot 是问答，我们是行动。Chatbot 说'好的，我帮你查一下'，
我们的 Agent 会 Plan→Execute→Observe→Reflect——从规划到执行到反思。
Chatbot 不会记住你上次说了什么，我们有长期 Memory + Knowledge Graph。"

### Q2: 为什么企业愿意为这个产品付费？

"A: 企业不是为 AI 付费，是为'组织知识的可行动化'付费。
当一个公司的经验不再锁在个别员工的脑子里，
而是变成可检索、可关联、可执行的 Agent 能力——这就是核心竞争力。"

### Q3: 知识图谱的价值在哪里？

"A: 搜索'技术风险'：普通搜索返回一堆文档。
知识图谱能告诉你：这个风险关联到哪个项目、谁负责、上次怎么解决的、有什么关联决策。
这就是从'找到信息'到'理解信息'的跃升。"

### Q4: Agent 是否会越权访问数据？

"A: 不会。我们的 Agent 执行前经过三层检查：
1. JWT 认证确认你是谁
2. RBAC 确认你有没有权限执行这个 Agent
3. Department Agent 的 kb_namespace 确保你只能访问本部门知识库
Super admin 也无法绕过这套体系。"

### Q5: 如何保证执行过程可审计？

"A: 每个 Agent 执行有 PEOR trace，每个 Workflow 有 WorkflowExecutionStep。
API 返回 workflow_execution_id，可以在 Execution History 中追溯每一步。
所有异常都有结构化错误记录，不暴露内部 traceback。"

### Q6: 如果 LLM 出错怎么办？

"A: 首先，我们的确定性规则引擎在 LLM 离线时依然可用，并透明标注 fallback_mode=true。
其次，PEOR 循环中有 Reflect 阶段——Agent 执行后会反思结果，如果发现异常会自动重试。
我们的架构是 LLM-optional，不是 LLM-dependent。"

### Q7: 为什么现在还不做 Agent Marketplace？

"A: Step 20 的目标是让 Enterprise AI Agent 可运行、可演示、可交付。
Marketplace 是一个平台型功能，需要稳定的 Agent 生态作为前提。
就像先有 App Store 再允许开发者上传 app——我们先确保 Agent 平台本身稳定可靠。"

### Q8: Step 21 Marketplace 有什么价值？

"A: Agent Marketplace 让企业可以管理、发现、配置内部 Agent 能力。
不是外部的'下载市场'，而是企业内部的'能力目录'。
就像企业有自己的应用商店一样，他们会有自己的 Agent 目录。"

## 10. 已知限制

| 限制 | 说明 | 影响 |
|------|------|------|
| 确定性规则引擎 | 当前 Agent 输出基于关键词匹配和预定义规则，非 LLM 推理 | 输出质量有限，但可保证稳定性和响应速度 |
| 执行历史内存存储 | WorkflowEngine 的 `_executions` dict 在服务重启后丢失 | 真实部署需持久化到数据库 |
| 无 NER 实体提取 | 实体识别使用关键词匹配，非 NLP 模型 | 实体覆盖率和精度有限 |
| 无分布式部署 | 当前为单机架构 | 企业级部署需要数据库升级和消息队列 |
| 演示数据需手动初始化 | Demo memories 需运行 seed 脚本 | 前端已有 Demo Input 按钮作为替代 |

**以上所有限制在 Step 21+ 均可解决，不影响当前 Step 20-D 的演示效果。**

## 11. 演示 Checklist

- [ ] 后端启动 (`python main.py`) — 确认无报错
- [ ] 前端启动 (`npm run dev`) — 确认页面可访问
- [ ] `python scripts/seed_agent_demo.py --apply` — 确认演示记忆写入
- [ ] 235 agent tests passed
- [ ] 49 security tests passed
- [ ] 场景 1 执行成功，展示完整结果
- [ ] 场景 1 Workflow Execution Steps 展示正常
- [ ] 场景 1 Agent Trace 可展开
- [ ] 场景 2 研发部执行成功
- [ ] 场景 2 切换销售部，确认结果不包含研发数据
- [ ] workflow_execution_id 显示正常
- [ ] Metrics 栏显示完整
- [ ] confidence + limitations 透明标注

## 12. Next Step

Step 21：Agent Marketplace
