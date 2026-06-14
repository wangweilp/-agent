# 黔智脑 Cognitive OS 项目演示视频脚本

用于贵州省 2026 人工智能创业大赛报名材料。

本视频基于当前项目真实代码和本地可运行页面录制，最终 MP4 保持原速，时长约 4 分 11 秒。视频无配音音轨，采用页面底部中文字幕说明，重点呈现“黔智脑 Cognitive OS”作为面向政企组织的 AI 认知操作系统与智能体开放平台的产品形态、组织知识沉淀能力、智能体开放生态、安全治理控制面和商业化基础。

## 一、分段结构

| 段落 | 时间 | 展示重点 | 字幕/旁白主旨 |
|---|---:|---|---|
| 第 1 段：项目定位 | 约 00:00-00:23 | Dashboard 与平台入口 | 黔智脑 Cognitive OS 是面向政企组织的 AI 认知操作系统与智能体开放平台，帮助组织把分散数据转化为可检索、可协同、可审计的知识资产。 |
| 第 2 段：组织知识管理 | 约 00:23-01:10 | Chat、Memory、Timeline、Graph、Reflection | 系统支持文档、会议、项目经验和业务资料沉淀，形成组织长期记忆、语义检索、知识图谱与复盘能力。 |
| 第 3 段：智能体协同 | 约 01:10-01:49 | Agent Center、Scenarios、Workflows | 平台通过 Agent Center 支持面向不同业务场景的智能体管理、任务拆解、流程编排、结果生成和复盘。 |
| 第 4 段：智能体市场与开放平台 | 约 01:49-02:45 | Marketplace、Installations、Developer Console、API Key、Agent Submission | 开发者可提交智能体，管理员审核后进入市场，企业用户按需安装使用，形成受控的智能体生态。 |
| 第 5 段：安全治理与运行时控制面 | 约 02:45-03:37 | Admin Review、Audit Log、Runtime Admin、Runtime Governance Evidence | 平台通过权限、审计、模拟运行、默认拒绝和失败关闭机制提升政企场景下的安全可信能力。当前完成的是安全治理控制面，不等于生产级第三方代码执行沙箱。 |
| 第 6 段：商业化和应用场景 | 约 03:37-04:00 | Analytics、Billing | 项目可应用于企业知识管理、智能招商、政务服务问答和园区企业服务，支持订阅、项目交付、行业知识包和智能体市场分成。 |
| 第 7 段：结尾 | 约 04:00-04:11 | Dashboard 收束画面 | 黔智脑 Cognitive OS，让政企组织拥有可沉淀、可协同、可审计、可进化的 AI 组织大脑。 |

## 二、详细镜头脚本

| 时间 | 页面/画面 | 展示内容 | 字幕文案 |
|---|---|---|---|
| 00:00-00:23 | `/dashboard` | 项目首页、平台总览、能力入口 | 黔智脑 Cognitive OS 是面向政企组织的 AI 认知操作系统与智能体开放平台，把分散数据转化为可检索、可协同、可审计的知识资产。 |
| 00:23-00:31 | `/chat` | 智能问答与认知工作台 | Chat 不是一次性问答，而是连接长期记忆、工具调用、主动反思和上下文组织的认知工作台。 |
| 00:31-00:42 | `/memory` | 组织长期记忆 | 文档、会议、项目经验和业务资料可以沉淀为组织记忆，支持后续检索、复盘和知识复用。 |
| 00:42-00:50 | `/timeline` | 时间线与知识演化 | Timeline 展示知识沉淀的时间脉络，帮助组织看到经验、任务和事件如何持续积累。 |
| 00:50-01:02 | `/graph` | 知识图谱 | Graph 把长期记忆中的实体、主题和关系组织成可视化网络，支撑跨主题发现和语义检索。 |
| 01:02-01:10 | `/reflection` | 反思与复盘 | Reflection 用于沉淀复盘和洞察，让组织知识不仅被保存，还能被重新理解和结构化。 |
| 01:10-01:25 | `/agents` | Internal Agent Center | Agent Center 集中管理企业内部 Agent，支持面向知识、会议、研发、销售、客服等场景的智能体协同。 |
| 01:25-01:40 | `/agents/scenarios` | 业务场景编排 | 平台支持会议到培训、部门知识助手等闭环场景，将任务拆解、工具调用和结果生成纳入可追踪流程。 |
| 01:40-01:49 | `/agents/workflows` | Workflow 与执行记录 | Workflow 页面展示智能体流程编排入口，为人工确认、执行追踪和复盘提供基础。 |
| 01:49-02:03 | `/agent-marketplace` | Agent Marketplace | 企业用户可以浏览、安装和治理 Agent，平台从单一工具扩展为可分发的智能体生态。 |
| 02:03-02:11 | `/agent-marketplace/installations` | 安装与用量管理 | 安装管理、权限和用量统计让 Agent 市场具备企业内部治理和计量基础。 |
| 02:11-02:25 | `/developer` | Developer Console | 开发者通过 Open Platform 创建 API Key、提交 Agent Manifest，并进入受控审核流程。 |
| 02:25-02:34 | `/developer/api-keys` | API Key 与 Scope 权限 | API Key 采用 scope 权限控制，第三方能力接入必须声明可用范围，不能绕过管理边界。 |
| 02:34-02:45 | `/developer/agents` | Agent Submission | 开发者提交 Manifest 后，由平台记录状态、权限、能力和安全声明，再交由管理员审核。 |
| 02:45-02:59 | `/admin/agent-submissions` | Admin Review | 管理员审核 Agent 提交，检查权限、安全声明和企业数据边界；审核通过不等于自动执行代码。 |
| 02:59-03:07 | `/admin/audit` | Audit Log | 审计中心记录关键操作和风险事件，为政企场景提供可追溯、可检查的治理基础。 |
| 03:07-03:23 | `/admin/runtime` | Runtime Admin | 当前 Runtime/Sandbox 主要是安全控制面、模拟运行、metadata-only、disabled-by-default，不宣称生产级第三方代码执行沙箱。 |
| 03:23-03:37 | Runtime Governance Evidence | Runtime、Sandbox、治理相关代码与文档证据页 | 代码与文档已覆盖 Kill Switch、Incident Store、disabled-by-default 和 metadata-only 等控制面设计。 |
| 03:37-03:50 | `/analytics` | Usage 与运营分析 | Analytics 展示 MRR、ARR、转化率、留存率、Memory/LLM/Embedding 调用趋势，支撑 SaaS 化运营。 |
| 03:50-04:00 | `/billing` | Billing 与商业化基础 | 平台可面向订阅、项目交付、行业知识包和 Agent 市场分成建立商业化路径。 |
| 04:00-04:11 | `/dashboard` | 结尾与项目愿景 | 黔智脑 Cognitive OS，让政企组织拥有可沉淀、可协同、可审计、可进化的 AI 组织大脑。 |

## 三、安全表述边界

视频中对 Runtime/Sandbox 的表述限定为“安全治理控制面、模拟运行、metadata-only、disabled-by-default”，不宣称项目已经完成生产级第三方代码执行沙箱。该表述与当前项目页面、代码结构和实现进度保持一致。
