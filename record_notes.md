# 项目演示视频录制记录

## 启动命令

- 后端：`python main.py`
- 前端：`cd frontend && npm run dev -- --hostname 127.0.0.1 --port 3000`
- 后端健康检查：`GET http://127.0.0.1:8000/health`
- 前端入口：`http://127.0.0.1:3000`

## 录制方式

- 使用 Playwright Chromium 真实打开本地前端页面。
- 使用管理员账号登录后写入浏览器 localStorage，不在视频中展示密码。
- 分辨率：1920x1080。
- 原始录制格式：Playwright WebM。
- 最终视频格式：H.264 MP4，无配音音轨，保留页面底部中文字幕。
- 字幕方式：在浏览器页面底部叠加中文说明条。

## 最终视频时长

- 原始 Playwright 录制约 4 分 11 秒。
- 用户确认 4 分钟左右可以接受，因此最终 MP4 保持原速，没有做提速或时长压缩。
- 视频内容未删减，21 个页面/证据页全部录制成功。

## 安全边界说明

视频中明确说明：当前 Runtime/Sandbox 主要是安全治理控制面、模拟运行、metadata-only、disabled-by-default，不宣称已经完成生产级第三方代码执行沙箱。

## 演示数据补充

- 当前管理员原本未注册 Developer Account。为展示 Open Platform 真实流程，录制前通过项目自身 API 创建了演示开发者、API Key 和 Manifest-only Agent Submission。
- 演示提交名称：`政企政策知识助手`。
- 演示提交安全边界：`runtime_type=manifest_only`，`sandbox_level=no_execution`。

## 成功页面

- 成功：01_dashboard，来源 `/dashboard`，截图 `screenshots\video\01_01_dashboard.png`，展示项目首页、平台入口和 Cognitive OS 总体定位。
- 成功：02_chat，来源 `/chat`，截图 `screenshots\video\02_02_chat.png`，展示智能问答与长期记忆连接的认知工作台。
- 成功：03_memory，来源 `/memory`，截图 `screenshots\video\03_03_memory.png`，展示组织长期记忆、资料沉淀和知识复用能力。
- 成功：04_timeline，来源 `/timeline`，截图 `screenshots\video\04_04_timeline.png`，展示知识沉淀与事件演化时间线。
- 成功：05_graph，来源 `/graph`，截图 `screenshots\video\05_05_graph.png`，展示知识图谱与实体关系可视化。
- 成功：06_reflection，来源 `/reflection`，截图 `screenshots\video\06_06_reflection.png`，展示反思、复盘和洞察沉淀能力。
- 成功：07_agents，来源 `/agents`，截图 `screenshots\video\07_07_agents.png`，展示 Internal Agent Center。
- 成功：08_agent_scenarios，来源 `/agents/scenarios`，截图 `screenshots\video\08_08_agent_scenarios.png`，展示智能体业务场景编排。
- 成功：09_workflows，来源 `/agents/workflows`，截图 `screenshots\video\09_09_workflows.png`，展示 Workflow 与执行记录入口。
- 成功：10_marketplace，来源 `/agent-marketplace`，截图 `screenshots\video\10_10_marketplace.png`，展示 Agent Marketplace。
- 成功：11_installations，来源 `/agent-marketplace/installations`，截图 `screenshots\video\11_11_installations.png`，展示智能体安装、权限和用量管理。
- 成功：12_developer，来源 `/developer`，截图 `screenshots\video\12_12_developer.png`，展示 Developer Console 与 Open Platform。
- 成功：13_api_keys，来源 `/developer/api-keys`，截图 `screenshots\video\13_13_api_keys.png`，展示 API Key 和 Scope 权限控制。
- 成功：14_developer_agents，来源 `/developer/agents`，截图 `screenshots\video\14_14_developer_agents.png`，展示 Agent Submission 提交流程。
- 成功：15_admin_review，来源 `/admin/agent-submissions`，截图 `screenshots\video\15_15_admin_review.png`，展示 Admin Review 管理员审核流程。
- 成功：16_audit，来源 `/admin/audit`，截图 `screenshots\video\16_16_audit.png`，展示 Audit Log 审计能力。
- 成功：17_runtime_admin，来源 `/admin/runtime`，截图 `screenshots\video\17_17_runtime_admin.png`，展示 Runtime Admin 与安全治理控制面。
- 成功：18_governance_code，来源 `generated runtime governance code evidence slide`，截图 `screenshots\video\18_18_governance_code.png`，展示 Runtime/Sandbox 代码与文档证据页。
- 成功：19_analytics，来源 `/analytics`，截图 `screenshots\video\19_19_analytics.png`，展示 Usage、Analytics 和 SaaS 运营指标。
- 成功：20_billing，来源 `/billing`，截图 `screenshots\video\20_20_billing.png`，展示 Billing 与商业化基础。
- 成功：21_end，来源 `/dashboard`，截图 `screenshots\video\21_21_end.png`，展示结尾定位与项目愿景。

## 失败或替代展示

- 无页面失败。
- Runtime Governance Evidence 为根据当前项目代码、文档和运行时治理模块生成的证据展示页，用于补充说明 Runtime/Sandbox 的实现边界和安全控制面进展。

## 输出文件

- 原始录制：`output\video\playwright_raw\page@b7d8cc408ac5519d806a7af8fd3b6e09.webm`
- 最终 MP4：`demo_video.mp4`
- 视频脚本：`video_script.md`
- 关键截图目录：`screenshots\video\`
