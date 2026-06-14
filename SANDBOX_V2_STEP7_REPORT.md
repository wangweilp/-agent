# SANDBOX V2 STEP 7 REPORT — Kill Switch、任务取消、超时终止与 Provider Cancel 能力

**实施日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)
**步骤**: Sandbox v2 Step 7 — Kill Switch 统一控制服务

---

## 一、本次新增文件

| # | 文件 | 用途 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/kill_policy.py` | Kill Policy Engine（9 条安全规则：默认 deny、不允许 PID kill、terminal→no_active、queued→cancel queue、active→mark canceled、container kill 仅 Linux+enabled+recorded） |
| 2 | `src/open_platform/sandbox_v2/kill_switch.py` | SandboxKillSwitchService（统一 kill 请求→policy→apply decision→audit record 全链路） |
| 3 | `tests/test_open_platform/test_sandbox_v2_kill_policy.py` | Kill Policy 测试（11 项） |
| 4 | `tests/test_open_platform/test_sandbox_v2_kill_switch.py` | Kill Switch Service 测试（8 项） |
| 5 | `tests/test_open_platform/test_sandbox_v2_kill_api.py` | Kill API 集成测试（12 项） |
| 6 | `tests/test_open_platform/test_sandbox_v2_worker_cancel.py` | Worker Cancel 检查点测试（4 项） |

**共新增 6 个文件。**

---

## 二、本次修改文件

| # | 文件 | 变更内容 |
|---|------|----------|
| 1 | `src/open_platform/sandbox_v2/models.py` | +3 枚举（KillRequestStatus, KillTargetType, KillAction, ActiveExecutionStatus）+ 4 数据类（~120 行） |
| 2 | `src/open_platform/sandbox_v2/store.py` | +14 个 Protocol 方法 |
| 3 | `src/adapters/sqlite_sandbox_v2_store.py` | +3 个 SQL 表 + 14 个 CRUD 方法 + 3 个 row mapper |
| 4 | `src/open_platform/sandbox_v2/service.py` | 构造函数 +kill_switch 参数；+10 个 kill 方法；cancel_job 升级走 kill_switch |
| 5 | `src/open_platform/sandbox_v2/worker.py` | +3 个 cancel 检查点（入队检查、handle 注册、handle cancel_requested 检查）；超时 handle 清理 |
| 6 | `src/open_platform/sandbox_v2/container_provider.py` | +build_kill_command；cancel_execution 完善（Linux+enabled+container_id 验证） |
| 7 | `src/api/sandbox_v2.py` | +8 个 kill endpoints + readiness +14 字段 |
| 8 | `main.py` | SandboxKillSwitchService 初始化注入 service |
| 9 | `frontend/types/runtime-admin.ts` | +5 个 TS 接口 |
| 10 | `frontend/services/runtime-admin.ts` | +8 个 API client 方法 |

**共修改 10 个文件。**

---

## 三、新增 API 列表

| 方法 | 路径 | 功能 | 新增于 |
|------|------|------|--------|
| `POST` | `/api/runtime/sandbox-v2/kill/job/{job_id}` | 请求取消/kill job | Step 7 |
| `POST` | `/api/runtime/sandbox-v2/kill/execution-plan/{id}` | 请求取消 execution plan | Step 7 |
| `POST` | `/api/runtime/sandbox-v2/kill/container-plan/{id}` | 请求取消 container plan | Step 7 |
| `GET` | `/api/runtime/sandbox-v2/kill/requests` | 列出 kill requests | Step 7 |
| `GET` | `/api/runtime/sandbox-v2/kill/records` | 列出 kill records（审计） | Step 7 |
| `GET` | `/api/runtime/sandbox-v2/kill/active-handles` | 列出 active execution handles | Step 7 |
| `POST` | `/api/runtime/sandbox-v2/kill/handles/{id}/cancel-request` | 标记 handle cancel_requested | Step 7 |
| `GET` | `/api/runtime/sandbox-v2/kill/readiness` | Kill Switch 能力状态 | Step 7 |

Step 1—6B 的 44 个端点全部向后兼容。`POST /jobs/{id}/cancel` 也升级为走 kill_switch 内部链路。

---

## 四、Kill Switch 当前完成能力

### 4.1 Kill Policy Engine ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| 默认 deny | ✅ | 空 target/unknown target → reject |
| fail closed | ✅ | 异常 → deny |
| 只 kill sandbox 管理对象 | ✅ | target_owned_by_sandbox 必为 True |
| 不允许任意 PID | ✅ | pid: 前缀 target_id 拒绝 |
| terminal → no_active_execution | ✅ | completed/rejected/failed/dead_letter |
| queued → cancel_queue_item | ✅ | 调用 queue.cancel |
| active → mark_canceled | ✅ | leased/processing/running_simulation |
| container kill 三条件 | ✅ | Linux + enabled + container_id recorded |
| Windows container kill → unsupported | ✅ | 拒绝并说明原因 |

### 4.2 Kill Switch Service ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| request_kill 统一入口 | ✅ | 经过 kill_policy → apply_decision → kill_record |
| job cancel 整合 | ✅ | cancel_job 内部走 kill_switch |
| queue_item cancel | ✅ | 调用 queue.cancel |
| provider cancel | ✅ | 调用 ExecutionProvider.cancel_execution |
| kill record 自动创建 | ✅ | 每次 kill 请求写 SandboxKillRecord |
| ActiveExecutionHandle 注册 | ✅ | Worker 在处理任务前注册 handle |
| Handle cancel_requested | ✅ | 标记后 Worker 检查并停止 |
| Handle lifecycle | ✅ | register → active → cancel_requested → completed/expired |
| expire stale handles | ✅ | 超时 handle → expired |

### 4.3 Worker Cancel Checkpoints ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| checkpoint 1: 入队取消 | ✅ | 检查队列状态 |
| handle 注册 | ✅ | 处理前注册 ActiveExecutionHandle |
| checkpoint 2: handle cancel_requested | ✅ | 检查并停止 simulation |
| handle 清理 | ✅ | 完成后 mark_completed |
| timeout 处理 | ✅ | handle 标记 timeout |

### 4.4 Container Kill ✅（接口+命令构建，默认不执行）

| 能力 | 状态 | 说明 |
|------|------|------|
| CommandBuilder.build_kill_command | ✅ | docker/podman kill 命令数组，不使用 shell=True |
| Provider cancel_execution | ✅ | Linux+enabled+valid_container_id 调用 |
| 默认 disabled | ✅ | 未设置环境变量 → 返回 disabled |
| Windows → unavailable | ✅ | 拒绝真实 kill |

---

## 五、Kill Switch 当前限制（诚实声明）

| 能力 | 状态 | 原因 |
|------|------|------|
| 真实进程 kill | ❌ | simulation/trusted_fixture 均无真实进程 |
| 任意 PID kill | ❌ | 安全策略拒绝 |
| 跨 sandbox kill | ❌ | 只 kill sandbox 管理对象 |
| Windows 容器 kill | ❌ | Windows 不支持 Linux container |
| 实时容器 kill | ⚠️ | 需 Linux + `SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=true` + recorded container_id |
| kill 自动触发 | ❌ | 未集成监控/告警自动触发 |

---

## 六、测试结果

### 新增测试
```
test_sandbox_v2_kill_policy.py    11 passed
test_sandbox_v2_kill_switch.py     8 passed
test_sandbox_v2_kill_api.py       12 passed
test_sandbox_v2_worker_cancel.py   4 passed
```

### 全部 sandbox v2 测试 (Step 1-7)
```
407 passed in 18.45s
```

### 全部 test_open_platform
```
3973 passed in 95.57s
```

零回归。

---

## 七、下一步建议

**建议进入 Step 8：Red-Team / Escape Test Suite**

具体任务：

1. 将现有 163 项红队逃逸守卫测试从 control-plane 测试升级到包含 Kill Switch 测试
2. 覆盖 Kill Switch 绕过尝试、kill 权限边界测试
3. 超时/死锁场景测试
4. 资源耗尽场景测试
5. 日志注入和审计完整性测试
6. 或进入 Step 6C：在 Linux/WSL2 rootless Docker/Podman 环境中做真实容器 fixture + kill 验证

---

## 八、命令速查

```bash
# 运行 Kill Switch 测试
python -m pytest tests/test_open_platform/test_sandbox_v2_kill_*.py tests/test_open_platform/test_sandbox_v2_worker_cancel.py -q -v

# 运行全部 sandbox v2 测试
python -m pytest tests/test_open_platform/test_sandbox_v2_*.py -q 2>&1 || python -m pytest tests/test_open_platform/test_sandbox_v2_models.py ... -q

# 运行完整 test_open_platform
python -m pytest tests/test_open_platform -q
```
