# Sandbox v2 — Incident Response Guide

**版本**: Step 10  
**最后更新**: 2026-06-13  
**目标受众**: 安全运维 / SRE / 值班工程师

---

## 一、发现异常 Job 怎么处理

### 识别异常

| 异常信号 | 可能含义 |
|----------|----------|
| Job 状态异常频繁变为 `failed` | 策略拒绝、输入格式错误、环境问题 |
| Job 卡在 `processing` 超过预期时间 | Worker 挂起、死锁、资源耗尽 |
| 大量 Job 进入 `dead_letter` | 系统性问题 |
| Job 的 `mode` 不是预期的 `simulation` | 配置错误或攻击 |

### 处理步骤

1. **立即获取信息**
   ```bash
   curl http://localhost:8000/api/runtime/sandbox-v2/jobs/{job_id}
   curl http://localhost:8000/api/runtime/sandbox-v2/execution-records?job_id={job_id}
   ```

2. **检查策略决策**
   - 查看 job 的 `policy_snapshot` 字段
   - 查看 `decision.reason` 了解拒绝原因

3. **决定处理方式**
   - 如果是合法任务被策略拒绝 → 审查策略是否需要调整
   - 如果是策略正确拒绝 → 无需处理
   - 如果是系统故障 → 重启 Worker 或回收 lease

4. **Cancel Job（如需）**
   ```bash
   curl -X POST http://localhost:8000/api/runtime/sandbox-v2/jobs/{job_id}/cancel
   ```

5. **记录事件**
   - 记录 job_id、时间、原因、处理方式
   - 如果有安全疑虑，保留所有日志

---

## 二、发现 Package Quarantine 高风险 怎么处理

### 识别高风险信号

| 信号 | 风险等级 | 说明 |
|------|----------|------|
| `vulnerability_status: findings_critical` | 🔴 严重 | 存在已知严重漏洞 |
| `vulnerability_status: findings_high` | 🟠 高 | 存在高危漏洞 |
| `signature_status: failed` | 🔴 严重 | 签名验证失败 |
| `sha256` 与预期不匹配 | 🔴 严重 | 包被篡改 |
| `source_type: external_url` | 🟡 中 | 来自外部 URL |
| `sbom_status: not_provided` | 🟡 中 | 缺少 SBOM |

### 处理步骤

1. **立即隔离**
   - 高风险包保持在 quarantine 状态，不要 release
   - 标记为 `rejected`

2. **调查**
   ```bash
   # 查看 quarantine 详情
   curl http://localhost:8000/api/runtime/sandbox-v2/packages/quarantine/{quarantine_id}
   
   # 查看关联的 package request
   curl http://localhost:8000/api/runtime/sandbox-v2/packages/requests/{package_request_id}
   
   # 查看 SBOM
   curl http://localhost:8000/api/runtime/sandbox-v2/packages/sbom?package_request_id={package_request_id}
   ```

3. **处理**
   - 高风险包：`review` → `rejected`，**不要删除**（保留证据）
   - 确认安全的包：`review` → `approved_metadata_only`
   - 需要进一步分析：保持 `pending_review`

4. **记录**
   - 记录 quarantine_id、package_name、风险发现、处理决定
   - 如有必要，通知安全团队

---

## 三、发现 Network Egress 拒绝记录 怎么处理

### 识别可疑模式

| 模式 | 风险等级 | 说明 |
|------|----------|------|
| 大量 localhost/127.0.0.1 请求 | 🔴 严重 | SSRF 攻击尝试 |
| metadata.google.internal/169.254.169.254 请求 | 🔴 严重 | 云 metadata 窃取尝试 |
| 内网地址 (10.x/172.16/192.168) 请求 | 🟠 高 | 内网探测 |
| file:/// ftp:// 等危险 scheme | 🟠 高 | 本地文件读取尝试 |
| 非常规端口请求 | 🟡 中 | 端口扫描 |

### 处理步骤

1. **审查拒绝记录**
   ```bash
   # 列出 audit records
   curl http://localhost:8000/api/runtime/sandbox-v2/network/audit-records
   
   # 过滤特定 job
   curl ".../network/audit-records?job_id={job_id}"
   ```

2. **分析模式**
   - 是同源大量请求还是分散的？
   - 是合法业务需求还是攻击尝试？
   - 来自哪个 job/organization/workspace？

3. **处理**
   - 合法业务需求：审查是否应在 `allowed_domains` 白名单中添加
   - 攻击尝试：cancel 相关 job，记录事件
   - 策略正确拒绝：正常行为，无需处理

4. **策略调整（谨慎）**
   - 如需添加域名白名单，需安全审查
   - 不要放宽 `file://`、`ftp://` 等危险 scheme 的限制

---

## 四、发现 Kill Switch 触发 怎么处理

### Kill Switch 触发类型

| 触发方式 | 可能原因 |
|----------|----------|
| 用户手动 kill job | 正常操作（任务超时、bug 修复） |
| Kill execution plan | 正常操作（隔离级别调整） |
| Kill container plan | 正常操作（容器执行取消） |
| 高频 kill request | 异常（攻击、系统不稳定） |

### 处理步骤

1. **查看 kill record**
   ```bash
   curl http://localhost:8000/api/runtime/sandbox-v2/kill/records
   ```

2. **分析 kill record 字段**
   - `action_taken`：实际执行的动作
   - `status_before` / `status_after`：状态变化
   - `provider_result`：provider 执行结果
   - 时间戳：kill 请求的时间

3. **判断是否异常**
   - 单个 job kill → 正常运维
   - 批量 kill → 可能需要调查
   - 无法 kill 的对象 → 策略正确阻止

4. **不要删除 kill record**
   - Kill record 是审计证据
   - 保留所有记录供安全审查

---

## 五、发现 Red-Team 失败 怎么处理

### 严重程度判定

| 级别 | 情况 | 处理 |
|------|------|------|
| 🔴 BLOCKER | Red-team test 失败 | 立即阻止生产部署，修复安全问题 |
| 🟠 HIGH | 多个相关 test 失败 | 需深度调查，可能发现安全漏洞 |
| 🟡 MEDIUM | 1-2 个 test 失败 | 分析是环境问题还是真实漏洞 |

### 处理步骤

1. **复现失败**
   ```bash
   # 运行失败的测试文件
   python -m pytest tests/test_open_platform/red_team/test_sandbox_v2_red_team_{domain}.py -v
   
   # 查看具体失败信息
   python -m pytest tests/test_open_platform/red_team/test_sandbox_v2_red_team_{domain}.py -v --tb=long
   ```

2. **分类失败**
   - 安全策略变宽松 → 严重，立即修复
   - 环境差异 → 调整环境配置
   - 测试 bug → 修复测试（但不放宽安全策略！）

3. **修复与验证**
   - 修复后重新运行全部 red-team tests
   - 确认零回归
   - 如果修复涉及安全策略，需安全团队审查

4. **记录**
   - 记录失败测试、根因、修复、验证结果
   - 更新安全回归记录

---

## 六、日志与证据保留建议

### 必须保留的日志

| 日志类型 | 保留期限 | 理由 |
|----------|----------|------|
| Execution Records | ≥ 90 天 | 审计所有 sandbox 执行 |
| Network Audit Records | ≥ 90 天 | 审计所有网络出站 |
| Kill Records | ≥ 365 天 | 安全事故调查 |
| Package Quarantine Records | ≥ 365 天 | 供应链安全调查 |
| Artifact Metadata | ≥ 90 天 | 执行输出审计 |
| API Access Logs | ≥ 90 天 | 访问审计 |

### 不要删除的证据

1. **Kill Records** — 即使在正常操作中，也保留所有记录
2. **Network Audit Records** — 包括被正确拒绝的请求
3. **Package Quarantine Records** — 即使包被拒绝，保留记录
4. **Artifact Metadata** — 即使 artifact 已过期
5. **Execution Records** — 即使 job 已完成/取消/失败

### 证据保护原则

- **不可变性**: 审计记录一经创建不可修改
- **完整性**: 完整的请求-决策-结果链路
- **可追溯**: 每条记录包含时间戳、操作人、上下文
- **定期备份**: 审计日志定期备份到安全存储

---

## 七、上报流程

### 安全事件上报

1. **识别** → 发现异常后立即记录时间、类型、范围
2. **隔离** → 取消相关 job、关闭容器执行（如启用）
3. **调查** → 收集证据、分析根因
4. **修复** → 修复漏洞、验证修复
5. **复盘** → 写事件报告、更新安全策略

### 上报矩阵

| 严重程度 | 响应时间 | 上报对象 |
|----------|----------|----------|
| 🔴 Critical | 15 分钟内 | CISO + 工程 VP |
| 🟠 High | 1 小时内 | 安全团队 lead |
| 🟡 Medium | 4 小时内 | 安全值班 |
| 🔵 Low | 24 小时内 | 记录到 issue tracker |

---

## 八、紧急回滚流程

如果 Sandbox v2 出现严重安全事件：

### 立即操作

```bash
# 1. 禁用所有危险能力
export SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=false
export SANDBOX_V2_NETWORK_ENABLED=false
export SANDBOX_V2_PACKAGE_DOWNLOAD_ENABLED=false
export SANDBOX_V2_PACKAGE_INSTALLATION_ENABLED=false
export SANDBOX_V2_USER_COMMAND_EXECUTION=false
export SANDBOX_V2_USER_IMAGE_EXECUTION=false
export SANDBOX_V2_AUTO_PULL_IMAGES=false
export SANDBOX_V2_FAIL_CLOSED=true

# 2. 重启服务

# 3. 验证回滚
python scripts/check_sandbox_v2_production_readiness.py
```

### 验证确认

- [ ] Container execution 已关闭
- [ ] Network 已关闭
- [ ] Package download/install 已关闭
- [ ] User command/image 已关闭
- [ ] Readiness check 无 blockers
- [ ] Red-team tests 全部通过
