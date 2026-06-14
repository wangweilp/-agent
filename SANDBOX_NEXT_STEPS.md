# SANDBOX NEXT STEPS — 分阶段修复路线

**审查日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)
**当前状态**: metadata-only 安全治理控制面

---

## 路线总览

```
Phase 0        Phase 1        Phase 2        Phase 3        Phase 4        Phase 5        Phase 6
 边界修正    →  前端可视化  →  API/模型   →  任务队列   →  工件/包隔离  →  执行隔离PoC  →  红队测试
 (文档)        (前端)         (后端)        (基础设施)     (数据安全)     (核心安全)     (验证)
  1周           2-3周          3-4周         4-6周          4-6周          8-12周         持续
```

---

## Phase 0：边界修正与审计报告（1 周）

### 目标
统一文案，明确当前不是生产级沙箱。确保所有面向用户的界面和文档都有清晰的边界声明。

### 任务清单

- [ ] **0.1** 审查所有对外文档，确保下列边界声明出现在关键位置：
  - README.md 的 Runtime/Sandbox 章节
  - API 文档（如果存在）
  - 前端 Runtime Admin 页面的 Guide Tab
  - 任何面向合作伙伴/客户的 PPT 或文档

- [ ] **0.2** 在 `frontend/app/admin/runtime/page.tsx` 的 Guide Tab 中，添加详细的"当前能力边界"说明：
  - 当前完成了什么（列出来）
  - 当前尚未完成什么（列出来）
  - 什么条件下会进入下一阶段

- [ ] **0.3** 在 `src/open_platform/` 目录创建 `CAPABILITY_BOUNDARY.md`，作为代码级边界声明：
  - 列出当前所有 `always False` 的方法和位置
  - 列出当前所有 `metadata_only=True` 的位置
  - 说明这些不是 bug，是有意设计

- [ ] **0.4** 确认 `production_sandbox_gate.py` 中的 23 项 requirement 状态与实际代码一致：
  - 检查是否有 any requirement 状态需要更新
  - 确保 Gate 的 `calculate_status()` 逻辑与实际情况一致

### 产出
- 边界声明审查报告
- `CAPABILITY_BOUNDARY.md`

### 不做什么
- 不修改 `always False` 的行为
- 不修改业务逻辑
- 不新增任何功能

---

## Phase 1：Runtime Governance 可视化（2-3 周）

### 目标
补齐 Runtime Admin 前端中目前存在但数据展示不完整的面板。当前 Governance Summary API 返回了大量数据，但前端可能未全部渲染。

### 任务清单

- [ ] **1.1** Kill Switch 面板增强
  - 展示所有 `RuntimeKillSwitchPolicy` 列表
  - 展示 `RuntimeKillSwitchTrigger` 历史（最新 N 条）
  - 展示 trigger 的 `no_process_killed`, `no_runtime_terminated` 等 flags
  - 添加 "Trigger Kill Switch (Metadata Only)" 按钮（仅触发 metadata event）

- [ ] **1.2** Incident Store 面板增强
  - 展示所有 `RuntimeIncidentRecord` 列表（带筛选：按 severity/status/type）
  - 展示 Incident 详情（evidence_refs, blockers, remediation_notes）
  - 添加 Incident 状态变更操作（Open → Triaged → Closed Metadata Only）

- [ ] **1.3** Package Download Worker Gate 面板增强
  - 展示 Package Download Policy 列表
  - 展示 Quarantine 中的 package 列表
  - 展示 Package Download Job 历史（blocked 记录）

- [ ] **1.4** Artifact Materialization Gate 面板增强
  - 展示 Artifact Materialization Policy 列表
  - 展示 blocked materialization 请求记录
  - 展示 extraction guard 决策记录

- [ ] **1.5** Sandbox Execution Record 面板增强
  - 展示所有 `SandboxExecutionRecord` 列表（带筛选）
  - 展示每个 record 的 audit events 时间线
  - 突出显示 `no_execution_performed: true` 标签

- [ ] **1.6** Red-Team Result 面板增强
  - 展示红队测试结果统计
  - 展示最新测试通过的 escape guard 列表
  - 明确标注"控制面测试"与"运行时测试"的区别

- [ ] **1.7** Production Sandbox Gate 面板增强
  - 展示 23 项 requirement 的完整状态表
  - 高亮 MISSING 的 critical 项
  - 展示 roadmap 进度

### 产出
- 完整的前端 Runtime Admin 可视化
- 所有面板的 mock/fallback 数据替换为真实 API 数据

### 不做什么
- 不修改 API 逻辑
- 不新增后端 API
- 不改变任何 store 的行为

---

## Phase 2：API 与数据模型补齐（3-4 周）

### 目标
为 Runtime Governance 增加稳定 API、状态模型、审计记录和测试。当前 API 存在（`runtime_admin_router.py` 等），但可能需要补充分页、排序、筛选、批量操作等能力。

### 任务清单

- [ ] **2.1** Runtime Admin API 补充
  - `GET /admin/runtime/governance/summary` — 分页支持
  - `GET /admin/runtime/incidents` — 完整 CRUD + 筛选
  - `GET /admin/runtime/kill-switch/policies` — 列表 + 详情
  - `GET /admin/runtime/kill-switch/triggers` — 历史查询
  - `POST /admin/runtime/kill-switch/trigger` — metadata trigger
  - `POST /admin/runtime/kill-switch/release` — metadata release

- [ ] **2.2** Sandbox Execution API 补充
  - `GET /admin/runtime/executions` — 分页 + 筛选
  - `GET /admin/runtime/executions/{id}` — 详情 + audit events
  - `GET /admin/runtime/executions/{id}/audit-events` — 审计事件列表

- [ ] **2.3** Production Sandbox Gate API 补充
  - `GET /admin/runtime/production-gate/requests` — 列表
  - `GET /admin/runtime/production-gate/requests/{id}` — 详情 + requirements
  - `POST /admin/runtime/production-gate/requests/{id}/evaluate` — 重新评估

- [ ] **2.4** 数据模型验证
  - 检查所有 `to_dict()` / `from_dict()` 方法的字段完整性
  - 确保所有 `metadata` 字段都有合理的默认值
  - 确保 `created_at` / `updated_at` 正确设置

- [ ] **2.5** API 测试补充
  - 为上述所有新端点编写测试
  - 确保所有测试遵循 fail-closed 原则
  - 确保所有测试不触发真实执行、下载、网络访问

### 产出
- 完整的 Runtime Admin RESTful API
- 完整的 API 测试覆盖

### 不做什么
- 不修改现有的 store 实现（SQLite）
- 不迁移到 PostgreSQL（那是 Phase 5 的事）
- 不打开任何执行路径

---

## Phase 3：任务队列与 Worker 框架（4-6 周）

### 目标
从 disabled-by-default / inline worker 过渡到真实任务队列，但仍不执行不可信代码。此阶段的目标是让任务队列基础设施就绪，但所有 Sandbox Worker 仍保持 `DISABLED_STUB`。

### 任务清单

- [ ] **3.1** 任务队列接入
  - 接入 Redis（用于 Celery/RQ broker）
  - 配置 Celery 或 RQ 应用实例
  - 定义队列：`sandbox_execution`, `package_analysis`, `artifact_processing`, `policy_audit`
  - 将 `TaskQueueAdapter` 从 readiness assessment 升级为真实连接管理

- [ ] **3.2** Worker 生命周期框架
  - 实现 `SandboxWorkerRegistry` 的真实注册逻辑
  - 实现 Worker 健康检查
  - 实现 Worker 优雅关闭
  - 实现 Worker 日志收集
  - 保持 `DisabledSandboxWorker` 为默认注册的 worker

- [ ] **3.3** Job 状态管理
  - 实现 job 状态机：`PENDING → QUEUED → STARTED → (COMPLETED | FAILED | CANCELLED | TIMEOUT)`
  - 实现 retry 逻辑（可配置次数、退避策略）
  - 实现 timeout 机制
  - 实现 dead letter queue（不可恢复的失败 job）

- [ ] **3.4** Queue 级别的安全守卫
  - `SandboxWorkerQueue` 的 `is_enqueue_allowed()` 仍保持 `False`（Phase 5 再打开）
  - 实现 queue-level audit logging
  - 实现 queue metrics（长度、吞吐、延迟）

- [ ] **3.5** 测试
  - 测试 celery/redis 连接
  - 测试 worker 注册/注销
  - 测试 job 状态流转
  - 测试 retry 和 timeout
  - 测试 dead letter queue
  - 确保所有测试不触发真实代码执行

### 产出
- 运行中的 Celery/RQ worker 集群（只执行 trusted 内部任务）
- Worker 生命周期管理工具
- Queue 监控 dashboard 数据

### 不做什么
- 不让 Sandbox Worker 执行任何不可信代码
- 不打开 package download
- 不打开 artifact materialization
- 不修改 DisabledSandboxWorker 的行为

---

## Phase 4：只读工件物化与包下载隔离（4-6 周）

### 目标
完善 artifact、package、download gate、quarantine 和审计。此阶段实现只读的工件物化能力，但仍在严格控制下运作。

### 任务清单

- [ ] **4.1** 只读工件物化
  - 实现 artifact 上传（限制大小、MIME 检查）
  - 实现 artifact 存储（本地文件系统或对象存储）
  - 实现只读 artifact 引用（不执行、不解包、不 mount）
  - 实现 artifact hash 计算（SHA256）
  - 实现 artifact 元数据索引

- [ ] **4.2** 路径穿越与解压炸弹防护
  - 实现 `ArtifactExtractionGuard` 的真实防护逻辑
  - 路径穿越检测（`..`, 绝对路径, symlink）
  - 解压炸弹检测（文件数量限制、总大小限制、压缩比限制）
  - 实现临时目录隔离和清理

- [ ] **4.3** 包下载隔离
  - 实现 `PackageDownloadQuarantine` 的真实隔离逻辑
  - 下载前域名/IP 检查（allowlist/denylist）
  - 下载内容大小限制
  - 下载内容 MIME 类型检查
  - 下载内容病毒扫描（如果接入 ClamAV 等）
  - 所有下载的包存储在 quarantine 区，默认不可执行

- [ ] **4.4** 包验证增强
  - 实现 `SignatureVerifier` 的真实签名验证（minisign/cosign/GPG）
  - 实现包 hash 验证
  - 实现 manifest hash 锁定

- [ ] **4.5** 审计与日志
  - 所有 artifact 操作记录 `ArtifactAuditEvent`
  - 所有 package download 操作记录 `PackageDownloadAuditEvent`
  - 所有 quarantine 操作记录 `QuarantineAuditEvent`

- [ ] **4.6** 测试
  - 路径穿越测试
  - 解压炸弹测试
  - 包下载隔离测试
  - 签名验证测试
  - MIME 绕过测试

### 产出
- 只读工件物化基础设施
- Package quarantine 基础设施
- 包下载隔离
- 签名验证基础设施

### 不做什么
- 不执行任何下载的包
- 不自动物化任何 artifact 到可写位置
- 不打开生产级代码执行

---

## Phase 5：生产级执行隔离 PoC（8-12 周）

### 目标
探索 Rootless Container 或 MicroVM，建立最小安全执行 PoC。这是最关键也最复杂的一个 Phase。

### 前置条件
- PostgreSQL/Redis/Object Storage 已迁移（`production_backends.py` 切换为生产配置）
- 真实任务队列已就绪（Phase 3）
- 工件与包隔离已就绪（Phase 4）
- Kill Switch 和 Incident Store 已接入真实能力

### 任务清单

- [ ] **5.1** 环境准备
  - 准备 Linux 测试环境（服务器或 VM）
  - 安装 Podman/Docker（rootless mode）
  - 安装 containerd/runc
  - 配置 user namespace
  - 验证 kernel 版本支持所需特性

- [ ] **5.2** Rootless Container PoC
  - 创建 rootless container image（最小化 base image，如 `scratch` + 必要 runtime）
  - 配置 seccomp profile（默认 deny，需要时 allow）
  - 配置 read-only rootfs
  - 配置 no-new-privileges
  - 配置 network namespace（默认无网络）
  - 配置 cgroups v2（CPU/Memory/PID limits）
  - 实现容器生命周期管理（create/start/stop/remove）
  - 实现 stdout/stderr 捕获

- [ ] **5.3** 安全集成
  - 将 `RootlessContainerGate` 从 metadata-only 升级为真实 gate
  - 实现 `RootlessContainerPrototypePolicy` 的真实执行
  - 接入 Kill Switch（真实容器停止能力）
  - 接入 Incident Store（容器逃逸尝试记录）
  - 接入 Audit Trail

- [ ] **5.4** `SandboxWorker` 实现
  - 实现 `RootlessContainerSandboxWorker`（继承 `SandboxWorker` protocol）
  - `evaluate_request()` → `execute_request()`（仅在 policy 允许时）
  - 实现 `SandboxWorkerResult` 的真实 stdout/stderr/exit_code/duration_ms
  - `is_successful_execution()` 可返回 `True`（仅在合规执行时）

- [ ] **5.5** 安全开关
  - 所有执行默认关闭（通过 `ProductionSandboxGate` 控制）
  - 需要一个显式的 admin action 才能打开第一个 tenant 的执行
  - 执行能力按 tenant 逐步放开（ramp-up）
  - 任何异常事件触发自动回退到 DISABLED

- [ ] **5.6** 测试
  - 容器启动/停止测试
  - 资源限制测试（CPU/Memory/PID 上限）
  - 网络隔离测试（确保容器无法出站）
  - 文件系统隔离测试（确保容器无法写 host）
  - seccomp profile 测试（确保禁止的系统调用被拦截）
  - 超时测试
  - 并发容器隔离测试

- [ ] **5.7** MicroVM PoC（可选，后续）
  - 探索 Firecracker 或 cloud-hypervisor
  - 对比 Rootless Container vs MicroVM 的安全边界
  - 评估性能开销

### 产出
- 运行中的 rootless container sandbox worker
- 完整的安全配置模板（seccomp, AppArmor, cgroups）
- Execution 监控和日志
- 安全开关控制面

### 不做什么
- 不默认打开生产级执行
- 不跳过任何安全守卫
- 不在没有 Kill Switch 的情况下运行

---

## Phase 6：红队测试与安全验证（持续）

### 目标
增加 escape test、SSRF、路径穿越、资源耗尽、权限绕过等测试。此阶段要求有真实的执行隔离环境（Phase 5 完成）。

### 任务清单

- [ ] **6.1** 真实沙箱逃逸测试
  - 在 rootless container 中尝试执行恶意代码
  - 尝试突破 seccomp profile
  - 尝试突破 namespace 隔离
  - 尝试突破 cgroup 限制
  - 尝试访问 host 文件系统
  - 尝试访问 host 网络
  - 尝试访问其他容器

- [ ] **6.2** 恶意代码执行测试
  - Fork bomb（进程爆炸）
  - Memory bomb（内存耗尽）
  - Disk bomb（磁盘写满）
  - CPU exhaustion（CPU 占满）
  - 系统调用 fuzzing
  - `/proc` / `/sys` 信息泄露

- [ ] **6.3** 网络安全测试
  - SSRF 尝试（访问内网 metadata service）
  - DNS 隧道
  - 反向 shell
  - 端口扫描
  - ARP 欺骗

- [ ] **6.4** 文件系统安全测试
  - 路径穿越（`../../../etc/passwd`）
  - 符号链接攻击
  - 设备文件创建
  - SUID 二进制利用
  - Shared memory 攻击

- [ ] **6.5** 权限与策略绕过测试
  - 尝试以 root 运行
  - 尝试修改 seccomp profile
  - 尝试修改 cgroup 限制
  - 尝试挂载新文件系统
  - 尝试创建新的网络接口

- [ ] **6.6** 回归测试基础设施
  - 将所有红队测试加入 CI/CD pipeline
  - 每次部署前自动运行
  - 任何失败阻止部署

- [ ] **6.7** Bug Bounty / 外部审计
  - 在隔离环境成熟后，考虑外部安全审计
  - 考虑 bug bounty 程序

### 产出
- 完整的红队测试套件
- CI/CD 安全门禁
- 安全审计报告

---

## 关键原则（贯穿所有 Phase）

1. **Default Deny**: 所有新能力默认关闭，需要显式 admin action 才能打开
2. **Fail Closed**: 任何异常或未知状态都要回到最安全的状态
3. **Audit First**: 先有审计能力，再有执行能力
4. **Metadata Before Runtime**: 先在控制面完备建模，再接入真实执行
5. **Boundary Statement**: 在所有面向用户的界面明确当前能力边界
6. **No Silent Enable**: 不允许任何代码路径在未经过 Gate 评估的情况下打开执行

---

## 依赖关系图

```
Phase 0 (边界修正)
  └→ Phase 1 (前端可视化)
       └→ Phase 2 (API/模型)
            └→ Phase 3 (任务队列) ──────┐
                 └→ Phase 4 (工件/包隔离) ─┤
                      └→ Phase 5 (执行隔离 PoC) ← Phase 3, Phase 4
                           └→ Phase 6 (红队测试) ← Phase 5
```

Phase 0-2 可以部分并行执行。Phase 3 和 Phase 4 可以并行执行。Phase 5 必须在 Phase 3 + Phase 4 完成后才能开始。Phase 6 必须在 Phase 5 完成后才能开始。

---

## 时间估算

| Phase | 乐观估计 | 悲观估计 | 前置依赖 |
|-------|----------|----------|----------|
| Phase 0 | 1 周 | 2 周 | 无 |
| Phase 1 | 2 周 | 3 周 | Phase 0 |
| Phase 2 | 3 周 | 4 周 | Phase 1 |
| Phase 3 | 4 周 | 6 周 | Phase 2 |
| Phase 4 | 4 周 | 6 周 | Phase 2 |
| Phase 5 | 8 周 | 12 周 | Phase 3 + Phase 4 |
| Phase 6 | 持续 | 持续 | Phase 5 |
| **总计** | **22 周** | **33+ 周** | |

**注意**: Phase 5 的 8-12 周是最保守估计，实际可能更长，因为涉及 Linux kernel 安全特性、容器运行时、seccomp profile 编写等深层系统编程工作。
