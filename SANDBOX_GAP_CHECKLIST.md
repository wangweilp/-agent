# SANDBOX GAP CHECKLIST — Runtime / Sandbox 差距清单

**审查日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)

---

## 差距总览

| # | 模块 | 当前状态 | 证据文件 | 是否完成 | 风险等级 | 缺口说明 | 建议下一步 |
|---|------|----------|----------|----------|----------|----------|------------|
| 1 | **Runtime Governance 控制面** | metadata-only 安全治理控制面已完整实现 | `runtime.py`, `sandbox_policy.py`, `runtime_execution_gate.py`, `runtime_governance_summary.py` | ✅ 控制面完成 | 🟢 Low | 控制面设计完整，策略模型、状态机、审计链路齐备 | 继续维护，保持文档与代码一致 |
| 2 | **Simulation Runtime** | 9-step 安全仿真链路完成 | `simulation_runtime.py`, `simulation.py` | ✅ 完成 | 🟢 Low | 模拟链路不执行代码、不联网、返回 deterministic mock | 保持当前设计 |
| 3 | **Production Sandbox Gate** | readiness assessment 完成，23 项需求矩阵 | `production_sandbox_gate.py` | ✅ 控制面完成 | 🟡 Medium | 标记 14 项为 MISSING，执行始终 blocked | 接入 Phase 5 隔离层 PoC 后再评估 |
| 4 | **Rootless Container / MicroVM 执行隔离** | 缺失 — 22 项 capability 中 11 项运行时能力为 MISSING | `rootless_container_gate.py` | ❌ 未完成 | 🔴 Critical | 无 user namespace, seccomp, AppArmor, cgroup, 网络隔离, 只读 rootfs 等任何运行时隔离 | Phase 5: Rootless Container PoC |
| 5 | **真实任务队列** | metadata-only readiness assessment | `task_queue_adapter.py` | ❌ 未完成 | 🔴 Critical | 无 Celery/RQ/Redis Queue, `queue_active=False`, 所有 enqueue/dispatch 被 block | Phase 3: 接入真实任务队列 |
| 6 | **Worker 生命周期管理** | 仅 disabled stub worker 实现 | `sandbox_worker_stub.py`, `sandbox_worker.py` | ❌ 未完成 | 🔴 Critical | 无 worker 启动/停止/重启/健康检查/优雅关闭 | Phase 3: 构建 Worker 框架 |
| 7 | **Artifact Materialization Gate** | metadata-only gate, 无真实物化 | `artifact_materialization.py`, `artifact_materialization_service.py` | ❌ 未完成 | 🔴 Critical | `is_materialized()` 始终 `False`, 无文件大小限制、MIME 检查、路径穿越防护 | Phase 4: 只读工件物化 |
| 8 | **Package Download Gate** | metadata-only gate, 无真实下载 | `package_download_worker.py`, `package_download_quarantine.py` | ❌ 未完成 | 🔴 Critical | `is_downloadable()` 始终 `False`, 无真实签名验证、供应链扫描、SBOM | Phase 4: 包下载隔离 |
| 9 | **Network Egress Control** | 控制面 policy 存在，运行时强制缺失 | `sandbox_policy.py` (allow_network 字段), `rootless_container_gate.py` (标记为 MISSING) | ❌ 未完成 | 🔴 Critical | 无 iptables/nftables/network namespace 运行时强制，无 SSRF 防护 | Phase 5: 网络隔离 |
| 10 | **文件系统隔离** | 控制面 policy 存在，运行时强制缺失 | `sandbox_policy.py` (allow_filesystem 字段), `rootless_container_gate.py` (标记为 MISSING) | ❌ 未完成 | 🔴 Critical | 无 read-only mount, no host mount, no temp dir isolation | Phase 5: 文件系统隔离 |
| 11 | **Resource Limits** | 控制面字段存在 (max_timeout_ms 等) | `sandbox_policy.py`, `rootless_container_gate.py` (CPU/Memory/PID limit 标记为 MISSING) | ❌ 未完成 | 🔴 Critical | 无 cgroup CPU/memory/PID 限制, 无 OOM killer, 无磁盘配额 | Phase 5: 资源限制 |
| 12 | **API Key / Scope 权限** | 已完成 | `api_auth.py`, `developer_api_auth.py`, `rbac_service.py` | ✅ 完成 | 🟢 Low | API Key 创建、Scope 分配、验证链路完整 | 保持 |
| 13 | **Audit Log** | 已完成 | `core/audit.py`, `api/audit_router.py` | ✅ 完成 | 🟢 Low | AuditLog, AuditSummary, AuditStore protocol | 接入 Sandbox 级别审计事件 |
| 14 | **Incident Store** | metadata-only 完成 | `runtime_kill_switch.py` (RuntimeIncidentRecord) | ⚠️ 部分完成 | 🟡 Medium | 16 种 incident 类型, 状态机完整, 但只在控制面层记录 | Phase 1: 前端可视化 |
| 15 | **Kill Switch** | metadata-only 完成, 无真实 kill | `runtime_kill_switch.py` (RuntimeKillSwitchPolicy/Trigger) | ⚠️ 部分完成 | 🔴 Critical | 所有 `*_kill_implemented` 字段 = `False`, 不能杀进程/容器 | Phase 3: 接入真实 kill 能力 |
| 16 | **Red-Team Tests** | 控制面测试完成 (163 项) | `test_step24_security_escape_guards.py`, `test_step25_red_team_escape_guards.py` | ⚠️ 部分完成 | 🟡 Medium | 当前测试验证"是否正确拒绝"，非"沙箱是否防逃逸" | Phase 6: 真实沙箱逃逸测试 |
| 17 | **Runtime Admin 前端可视化** | 已完成 | `frontend/app/admin/runtime/page.tsx`, `frontend/services/runtime-admin.ts` | ✅ 完成 | 🟢 Low | 5 Tab 管理界面, Governance 摘要, Adapter/Binding/Policy CRUD | Phase 1: 补齐缺失模块前端 |
| 18 | **Production Readiness 文档** | 边界声明完整, 但缺少运维 runbook | `runtime_governance_summary.py` (BOUNDARY_STATEMENT), 前后端均有边界提示 | ⚠️ 部分完成 | 🟡 Medium | 边界声明清晰, 但缺运维 runbook、紧急禁用流程、回滚方案 | Phase 0: 运维文档 |

---

## 按方向汇总

### A. 执行隔离层 — 🔴 全部缺失

| 子项 | 状态 |
|------|------|
| Rootless Container | ❌ |
| Firecracker/MicroVM | ❌ |
| gVisor/Kata | ❌ |
| seccomp | ❌ |
| AppArmor/SELinux | ❌ |
| Linux namespaces | ❌ |
| cgroups | ❌ |
| 网络隔离 (container-level) | ❌ |
| 文件系统只读挂载 | ❌ |
| CPU/内存/时间限制 | ❌ |
| 非 root 用户 | ⚠️ 设计满足，无运行时验证 |
| 临时目录清理 | ❌ |

### B. 任务队列 — 🔴 全部缺失

| 子项 | 状态 |
|------|------|
| Celery/RQ/Dramatiq | ❌ |
| Redis Queue | ❌ |
| Worker 进程 | ❌ DisabledStub |
| Job Status | ❌ |
| Retry | ❌ |
| Timeout | ❌ |
| Cancellation | ❌ |
| Dead Letter Queue | ❌ |

### C. 工件与文件系统安全 — 🔴 全部缺失

| 子项 | 状态 |
|------|------|
| Artifact Storage | ⚠️ 域模型存在 |
| 只读工件物化 | ❌ |
| 文件大小限制 | ❌ |
| MIME 类型检查 | ❌ |
| 路径穿越防护 | ❌ |
| 解压炸弹防护 | ❌ |
| 临时目录隔离 | ❌ |
| 输出文件审计 | ⚠️ audit model 存在 |
| Artifact Hash | ❌ |
| Artifact Retention Policy | ❌ |

### D. 包下载与依赖安全 — 🔴 大部分缺失

| 子项 | 状态 |
|------|------|
| Package Quarantine | ⚠️ 域模型存在 |
| Package Allowlist/Denylist | ⚠️ 域模型存在 |
| Hash Verification | ⚠️ 域模型存在 |
| Signature Verification | ❌ |
| SBOM | ❌ |
| Vulnerability Scanning | ❌ |
| Offline Install | ❌ |
| Download Disabled by Default | ✅ |
| Dependency Provenance | ❌ |

### E. 网络访问控制 — 🔴 运行时全部缺失

| 子项 | 状态 |
|------|------|
| 默认禁止外网 | ✅ 控制面 |
| 域名 Allowlist | ⚠️ 域模型存在 |
| IP Denylist | ❌ |
| Metadata Service Block | ❌ |
| DNS 控制 | ❌ |
| Egress Proxy | ❌ |
| 请求审计 | ⚠️ 部分 |
| SSRF 防护 | ❌ |

### F. 权限与多租户隔离 — 🟢 应用层接近完成

| 子项 | 状态 |
|------|------|
| Organization Isolation | ✅ |
| Workspace Isolation | ✅ |
| RBAC | ✅ |
| Scope 权限 | ✅ |
| Per-agent Permission | ⚠️ |
| Per-tool Permission | ❌ |
| Tenant Data Boundary | ⚠️ 应用层 |
| Audit Subject/Actor/Org | ⚠️ 部分 |

### G. 审计与可观测性 — 🟡 应用层部分完成

| 子项 | 状态 |
|------|------|
| Sandbox Execution Record | ✅ audit-only |
| Audit Log | ✅ |
| Incident Store | ✅ metadata-only |
| Run Trace | ❌ |
| Input/Output Capture | ❌ |
| Policy Decision Log | ⚠️ |
| Risk Score | ⚠️ 域模型存在 |
| Metrics | ❌ |
| Alerting | ❌ |
| Dashboard | ✅ |

### H. 安全测试 — 🟡 控制面测试完成

| 子项 | 状态 |
|------|------|
| Red-Team Escape (控制面) | ✅ 163 项 |
| Malicious Package | ⚠️ 间接覆盖 |
| Path Traversal | ❌ |
| SSRF | ❌ |
| Privilege Escalation | ❌ |
| Timeout | ❌ |
| Resource Exhaustion | ❌ |
| Artifact Abuse | ❌ |
| Network Isolation Test | ❌ |
| Policy Fail-Closed | ✅ |
| Red-Team Escape (运行时) | ❌ |

---

## 风险等级图例

| 等级 | 含义 |
|------|------|
| 🟢 Low | 已完成或接近完成 |
| 🟡 Medium | 部分完成，需要补充 |
| 🔴 Critical | 缺失 — 生产级执行必须解决 |

---

## 统计

- **总模块数**: 18
- ✅ 已完成: 6 (33%)
- ⚠️ 部分完成: 5 (28%)
- ❌ 未完成: 7 (39%)
- 🔴 Critical: 8
- 🟡 Medium: 4
- 🟢 Low: 6
