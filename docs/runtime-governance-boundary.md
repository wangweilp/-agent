# Runtime Governance Boundary — 知维 OS 安全控制面边界声明

> **设计哲学：安全控制面先行，执行层虚拟化后置。**
>
> 知维 OS 的 Runtime/Sandbox 子系统当前完成的是**安全治理控制面**（Control Plane）、**模拟运行**（Simulation Runtime）、**元数据校验**（Metadata Validation）、**默认关闭**（Disabled-by-Default）和**审计追踪**（Audit Trail）能力，**不等于**已经完成生产级第三方代码执行沙箱。

---

## 1. 设计哲学

知维 OS 采用**控制面与执行面分离**的架构策略：

```
┌─────────────────────────────────────────────────────────────┐
│                  安全控制面 (Control Plane)                   │
│  ─────────────────────────────────────────────────────────   │
│  ✓ 策略定义与决策     ✓ 元数据校验      ✓ Kill Switch        │
│  ✓ 审计追踪          ✓ Incident Store   ✓ 默认拒绝 (Fail Closed) │
│  ✓ 模拟运行 (Simulation)  ✓ Binding 治理   ✓ Gate Matrix      │
│                                                             │
│  状态：ACTIVE · metadata-only · simulation-driven            │
└─────────────────────────┬───────────────────────────────────┘
                          │ 审计先行 · 策略先行 · 元数据先行
                          ▼
┌─────────────────────────────────────────────────────────────┐
│               执行层 (Execution Plane) — 后置                │
│  ─────────────────────────────────────────────────────────   │
│  ✗ microVM 隔离       ✗ Rootless Container   ✗ 真实进程执行   │
│  ✗ 网络出口 enforcement  ✗ 文件系统隔离       ✗ 密钥访问控制   │
│  ✗ cgroup / namespace / seccomp                             │
│                                                             │
│  状态：DISABLED · 等待 PostgreSQL + 分布式队列基础设施就绪     │
└─────────────────────────────────────────────────────────────┘
```

**核心理由**：

1. **安全审计优先**：在没有建立完整的策略决策、审计追踪、Kill Switch 和 Incident Store 之前，任何形式的真实代码执行都是不可接受的攻击面。
2. **基础设施依赖**：生产级执行环境需要 PostgreSQL（持久化）、Redis（状态缓存）、对象存储（工件物化）、分布式任务队列（异步执行）等基础设施，当前阶段尚未就绪。
3. **渐进式可信**：控制面先行允许我们以元数据形式验证策略语言、Gate Matrix、Binding 工作流和审计链路的完整性，为后续执行层接入提供可信基线。

---

## 2. 当前能力 (Current Capability)

### 2.1 控制面能力（已实现）

| 模块 | 状态 | 说明 |
|---|---|---|
| Runtime Adapter 注册 | `metadata_only` | 仅记录 manifest，不创建真实运行时实例 |
| Runtime Binding 治理 | `simulation` | 绑定关系以元数据形式存在，不触发真实执行 |
| Sandbox Policy 模型 | `deny_by_default` | 策略语言完整定义，但 enforcement 仅在元数据层 |
| Kill Switch | `triggered_metadata_only` | 熔断信号广播为元数据标记，不终止真实进程 |
| Incident Store | `configured_metadata_only` | 拦截记录以模拟数据形式展示 |
| Package Download Worker Gate | `disabled_by_default` | 包下载 worker 未启动，gate 始终返回 blocked |
| Artifact Materialization Gate | `read_only_metadata` | 工件物化仅暴露只读元数据引用 |
| Sandbox Execution Record | `is_executable()=false` | 执行记录存在但可执行性永远为 false |
| Production Sandbox Gate | `disabled` + `fail_closed` | 生产级沙箱 gate 始终返回未满足条件 |

### 2.2 模拟能力（已实现）

- **Simulation Runtime**：`RuntimeAdapterType.SIMULATION` 枚举值，所有 MVP 允许的 adapter 类型限定为 `manifest_only` 和 `simulation`。
- **Mock Incident Telemetry**：`GET /admin/runtime/incidents` 返回 6 条精选模拟拦截记录（文件越权、网络出口违规、密钥访问、子进程 fork、文件系统写入、资源超限）。
- **Control Plane Status**：`GET /admin/runtime/status` 硬编码返回 `mode="simulation"`, `production_sandbox="disabled"`, `default_policy="deny_by_default"`。

### 2.3 审计能力（已实现）

- 所有治理操作（binding enable/disable/suspend、policy assign/test）均记录 usage event。
- Governance Summary 端点聚合 7 个模块面板状态，提供完整审计视图。
- Boundary Statement 在后端 `runtime_governance_summary.py` 中硬编码声明。

---

## 3. 明确的非能力 (Explicit Non-Capability)

以下能力**当前不存在**，任何认为系统已具备这些能力的假设都是错误的：

- ✗ **无** 生产级第三方代码执行沙箱
- ✗ **无** subprocess / container / MicroVM 执行能力
- ✗ **无** 包下载 worker 的网络/文件写权限
- ✗ **无** 工件提取/物化到真实文件系统的能力
- ✗ **无** runtime 级网络/文件系统/密钥/cgroup/namespace/seccomp enforcement
- ✗ **无** 真实进程 kill 能力（Kill Switch 仅标记 metadata）

---

## 4. 边界术语 (Boundary Terminology)

在代码、文档、API 响应和 UI 文案中必须一致使用以下术语：

| 术语 | 含义 | 使用场景 |
|---|---|---|
| `metadata-only` | 仅元数据，无真实执行 | adapter / binding / artifact 状态 |
| `simulation` | 模拟运行，dry-run | runtime mode / status endpoint |
| `disabled-by-default` | 默认关闭 | worker gate / production sandbox |
| `deny_by_default` | 默认拒绝 | policy decision / status endpoint |
| `fail_closed` | 故障关闭 | 未知风险一律拦截 |
| `audit-first` | 审计先行 | 治理流程描述 |
| `triggered_metadata_only` | 仅元数据触发 | kill switch 状态 |
| `configured_metadata_only` | 仅元数据配置 | incident store 状态 |

---

## 5. 生产级沙箱就绪条件 (Production Sandbox Gate)

Production Sandbox Gate 必须**保持 disabled** 直到以下全部条件满足并验证：

### 5.1 基础设施就绪

- [ ] PostgreSQL 集群迁移完成（替换嵌入式 SQLite）
- [ ] Redis 状态缓存层部署
- [ ] 对象存储服务接入（工件物化）
- [ ] 分布式任务队列集群部署（Celery / Dramatiq + Redis broker）

### 5.2 隔离层实现

- [ ] Rootless Container runtime 接入（runc / crun rootless 模式）
- [ ] MicroVM 隔离 spike（Firecracker / Cloud Hypervisor）
- [ ] 只读工件物化（immutable read-only artifact extraction）
- [ ] 网络出口 enforcement（eBPF / iptables 策略）
- [ ] 文件系统隔离（chroot / overlayfs / readonly bind mount）
- [ ] 密钥访问控制（secret store + 策略 gate）

### 5.3 安全验证

- [ ] Red-team escape 测试套件全通过
- [ ] Fail-closed 回归测试套件全通过
- [ ] cgroup / namespace / seccomp profile 验证
- [ ] 审计链路完整性验证（kill → incident → audit → replay）

---

## 6. API 边界声明

### 6.1 已暴露的控制面端点（metadata-only）

| 端点 | 方法 | 说明 |
|---|---|---|
| `/admin/runtime/status` | GET | 控制面全局状态（mode=simulation 硬编码） |
| `/admin/runtime/incidents` | GET | 模拟拦截遥测数据流 |
| `/admin/runtime/governance/summary` | GET | 7 模块治理摘要 |
| `/admin/runtime/adapters` | GET | Runtime adapter 列表 |
| `/admin/runtime/bindings` | GET/POST | Binding 治理 CRUD |
| `/admin/sandbox-policies` | GET/POST/PATCH | 策略模型 CRUD |
| `/api/runtime/sandbox-v2/*` | * | Sandbox v2 核心契约（metadata-only） |

### 6.2 永远 blocked 的执行端点

| 端点 | 方法 | 说明 |
|---|---|---|
| `/runtime/agents/{id}/execute` | POST | 公共执行入口，永远返回 blocked |

### 6.3 未挂载的端点（文件存在但未 include_router）

| 文件 | prefix | 说明 |
|---|---|---|
| `runtime_capability_router.py` | `/api/runtime/capabilities` | 预留，未挂载 |
| `policy_enforcement_router.py` | `/api/runtime/policy-decisions` | 预留，未挂载 |

---

## 7. 下一阶段工程演进路线 (Next Build Steps)

1. **基础设施迁移**：完成 PostgreSQL + Redis + 对象存储 + 分布式任务队列部署。
2. **只读工件物化**：实现 immutable read-only artifact extraction 到临时文件系统。
3. **Rootless Container 接入**：在 disabled gate 后接入 rootless container runtime admission。
4. **MicroVM 隔离 spike**：作为独立受控 spike 验证 Firecracker / Cloud Hypervisor 隔离能力。
5. **网络/文件系统/密钥 enforcement**：实现真实 kernel 级 enforcement（eBPF / seccomp / cgroup）。
6. **Red-team 回归**：每次 runtime 变更后运行 escape 测试和 fail-closed 回归。

---

## 8. Phase 4 安全控制面仪表盘

Phase 4 构建的管理员安全大屏（`/admin/runtime` → "安全控制面" tab）**仅消费 metadata-only 端点**：

- `GET /admin/runtime/status` → 全局状态卡片（Simulation / Fail Closed / Disabled）
- `GET /admin/runtime/incidents` → 拦截遥测数据表（6 条模拟记录）
- `GET /admin/runtime/governance/summary` → 治理面板 7 模块详情
- Kill Switch → 模拟熔断 UI（二次确认弹窗，仅标记 metadata，不终止真实进程）

**仪表盘明确声明**：当前隔离层处于 Metadata 模拟模式。microVM 与容器化底层需要依赖 PostgreSQL 与分布式队列集群，已列入下一阶段工程演进路线。

---

## 变更日志

| 日期 | 变更 |
|---|---|
| 2026-06-26 | Phase 4 扩展：新增 `/admin/runtime/status` 和 `/admin/runtime/incidents` 端点，构建安全控制面仪表盘，补充设计哲学和 API 边界声明 |
| 2026-06-25 | 初始版本：STEP25 边界声明 |
