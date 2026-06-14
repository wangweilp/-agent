# SANDBOX V2 STEP 4 REPORT — Package 下载隔离、签名、SBOM、漏洞扫描接口

**实施日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)
**步骤**: Sandbox v2 Step 4 — Package 下载隔离与供应链安全控制面

---

## 一、本次新增文件

| # | 文件 | 用途 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/package_policy.py` | Package Policy Engine（默认 deny、external_url/public_registry 拒绝、路径穿越防护、quarantine_required） |
| 2 | `src/open_platform/sandbox_v2/packages.py` | LocalSandboxPackageQuarantineStore（隔离存储、sha256 校验、路径隔离、只读权限） |
| 3 | `src/open_platform/sandbox_v2/supply_chain.py` | SignatureVerifier + SBOMValidator + VulnerabilityScanner（trusted fixture 实现，不联网） |
| 4 | `tests/test_open_platform/test_sandbox_v2_package_policy.py` | Package 策略测试（16 项） |
| 5 | `tests/test_open_platform/test_sandbox_v2_package_quarantine.py` | 隔离存储测试（9 项） |
| 6 | `tests/test_open_platform/test_sandbox_v2_supply_chain.py` | 供应链测试（13 项） |
| 7 | `tests/test_open_platform/test_sandbox_v2_package_service.py` | Package 服务测试（8 项） |
| 8 | `tests/test_open_platform/test_sandbox_v2_package_api.py` | Package API 测试（13 项） |

**共新增 8 个文件。**

---

## 二、本次修改文件

| # | 文件 | 变更内容 |
|---|------|----------|
| 1 | `src/open_platform/sandbox_v2/models.py` | +7 枚举 + 5 数据类 + 4 常量（~260 行）：SandboxPackageRequest, PackagePolicyDecision, QuarantineRecord, SBOM, VulnerabilityScanResult |
| 2 | `src/open_platform/sandbox_v2/store.py` | +15 个 protocol 方法（package request / quarantine / SBOM / scan） |
| 3 | `src/adapters/sqlite_sandbox_v2_store.py` | +4 个 SQL 表 + 15 个 CRUD 方法 + 4 个 row mapper |
| 4 | `src/open_platform/sandbox_v2/service.py` | 构造函数 +package_store；+13 个 package/supply chain 方法 |
| 5 | `src/api/sandbox_v2.py` | +4 个 Pydantic schema + 12 个端点 + readiness +11 字段 |
| 6 | `main.py` | LocalSandboxPackageQuarantineStore 初始化注入 |
| 7 | `frontend/types/runtime-admin.ts` | +9 个 TypeScript 接口 |
| 8 | `frontend/services/runtime-admin.ts` | +12 个 API client 方法 + 类型导入 |

**共修改 8 个文件。**

---

## 三、新增 API 列表

| 方法 | 路径 | 功能 | 新增于 |
|------|------|------|--------|
| `POST` | `/api/runtime/sandbox-v2/packages/requests` | 创建 package request | Step 4 |
| `GET` | `/api/runtime/sandbox-v2/packages/requests` | 列出 package requests | Step 4 |
| `GET` | `/api/runtime/sandbox-v2/packages/requests/{id}` | 查看 package request | Step 4 |
| `POST` | `/api/runtime/sandbox-v2/packages/requests/{id}/quarantine` | 离线内容放入 quarantine | Step 4 |
| `GET` | `/api/runtime/sandbox-v2/packages/quarantine` | 列出 quarantine records | Step 4 |
| `GET` | `/api/runtime/sandbox-v2/packages/quarantine/{id}` | 查看 quarantine metadata | Step 4 |
| `POST` | `/api/runtime/sandbox-v2/packages/quarantine/{id}/review` | 审查（approved/rejected） | Step 4 |
| `DELETE` | `/api/runtime/sandbox-v2/packages/quarantine/{id}` | 删除 quarantine | Step 4 |
| `POST` | `/api/runtime/sandbox-v2/packages/sbom` | 提交并校验 SBOM | Step 4 |
| `GET` | `/api/runtime/sandbox-v2/packages/sbom` | 列出 SBOMs | Step 4 |
| `POST` | `/api/runtime/sandbox-v2/packages/scans` | 运行漏洞扫描（fixture） | Step 4 |
| `GET` | `/api/runtime/sandbox-v2/packages/scans` | 列出扫描结果 | Step 4 |

Step 1/2/3 的 19 个端点全部向后兼容。

---

## 四、Package / Supply Chain 当前完成能力

### 4.1 Package Policy ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| external_url 默认拒绝 | ✅ | 任何外部 URL 直接被 policy 拒绝 |
| public_registry 默认拒绝 | ✅ | 任何公共仓库直接被拒绝 |
| offline_upload 可入 quarantine | ✅ | 离线包可进入隔离区 |
| internal_registry 可入 quarantine | ✅ | 内部仓库包可进入隔离区 |
| unknown package_manager 拒绝 | ✅ | 非标准包管理器直接拒绝 |
| unknown source_type 拒绝 | ✅ | 未知来源类型直接拒绝 |
| 包名 sanitize | ✅ | 路径穿越、盘符、绝对路径被拦截 |
| source_url file:// 拦截 | ✅ | 本地文件 URL 被拒绝 |
| metadata service URL 拦截 | ✅ | AWS/GCP/Alibaba Cloud metadata 被拒绝 |
| 默认 quarantine_required | ✅ | 所有包默认进入隔离区 |
| fail closed | ✅ | 任何异常导致 deny |

### 4.2 Package Quarantine ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| 路径隔离在 quarantine root | ✅ | resolve 验证，禁止路径穿越 |
| SHA256 hash 计算和校验 | ✅ | expected_sha256 不匹配被拒绝 |
| 大小限制 | ✅ | 默认 10 MiB，超出被拒绝 |
| 只读权限 | ✅ | chmod 0444 |
| 不解压 zip/tar | ✅ | 不做任何解压 |
| 不执行包 | ✅ | 不做任何安装 |
| review approved ≠ executable | ✅ | review 仅 metadata 审批 |
| 安全删除 | ✅ | 只删除 quarantine root 内文件 |

### 4.3 Supply Chain ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| SignatureVerifier (fixture) | ✅ | 支持 trusted-fixture-signature 和 fixture- 前缀 |
| SignatureVerifier missing → not_provided | ✅ | 缺签名明确标记 |
| SBOMValidator cyclonedx-json | ✅ | 解析 + 基本字段校验 |
| SBOMValidator spdx-json | ✅ | 解析 + 基本字段校验 |
| SBOMValidator auto-detect | ✅ | 自动识别格式 |
| VulerabilityScanner (fixture) | ✅ | fixture-based，不联网 |
| 不调用外部扫描器 | ✅ | 标记为 scanner_unavailable |
| 扫描结果记录 | ✅ | 含 severity/count/findings |

---

## 五、Package / Supply Chain 当前限制

| 能力 | 状态 | 原因 |
|------|------|------|
| 联网下载包 | ❌ | 所有 external/public 被拒绝 |
| 运行 pip/npm install | ❌ | 不安装包 |
| 执行包中代码 | ❌ | 不解压，不执行 |
| release 包到可执行路径 | ❌ | 只允许 metadata_only |
| 真实签名验证（GPG/cosign） | ❌ | 仅 fixture 实现 |
| 真实 CVE 数据库扫描 | ❌ | 仅 fixture scanner |
| SBOM VEX/CSA 支持 | ❌ | 仅基础 cyclonedx/spdx |
| 供应链图谱/溯源 | ❌ | 未实现 |

---

## 六、为什么这一步仍然不等于生产级供应链安全

1. **不联网下载** — 无法验证远程包的供应链安全属性。
2. **签名仅 fixture** — 不是真实 GPG/Sigstore/cosign 验证。
3. **漏洞扫描不联网** — 不调 CVE 数据库，仅 fixture 返回。
4. **不安装/不执行** — 无法做动态分析。
5. **不解压** — 不做 zip bomb、tar slip 等攻击防护验证。

这一步建立了供应链安全**控制面基础**——policy、quarantine、SBOM、签名接口、漏洞扫描接口。真实运行时验证需要在后续阶段配合网络、容器隔离逐步完成。

---

## 七、测试结果

### 新增测试
```
test_sandbox_v2_package_policy.py    16 passed
test_sandbox_v2_package_quarantine.py  9 passed
test_sandbox_v2_supply_chain.py      13 passed
test_sandbox_v2_package_service.py     8 passed
test_sandbox_v2_package_api.py       13 passed
```

### 全部 sandbox v2 测试
```
218 passed in 8.47s
```

### 全部 test_open_platform 测试
```
3784 passed in 84.27s
```

零回归。

---

## 八、测试覆盖清单

1. ✅ external_url 默认拒绝
2. ✅ public_registry 默认拒绝
3. ✅ offline_upload 可以进入 quarantine
4. ✅ unknown package_manager 拒绝
5. ✅ unknown source_type 拒绝
6. ✅ 缺 sha256 → can_release 返回 false
7. ✅ 缺签名 → can_release 返回 false
8. ✅ 缺 SBOM → can_release 返回 false
9. ✅ path traversal package name 被拒绝
10. ✅ Windows drive path 被拒绝
11. ✅ file:// 任意路径被拒绝
12. ✅ metadata service URL 被拒绝
13. ✅ quarantine 写入后 sha256 正确
14. ✅ expected_sha256 不匹配时拒绝
15. ✅ quarantine 文件只读
16. ✅ SignatureVerifier trusted fixture verified
17. ✅ SignatureVerifier 缺失签名 → not_provided
18. ✅ SBOMValidator 可解析 cyclonedx-json
19. ✅ SBOMValidator 可解析 spdx-json
20. ✅ VulnerabilityScanner 不联网（无 urllib/requests 导入）
21. ✅ 扫描结果正常记录
22. ✅ review approved_metadata_only ≠ executable
23. ✅ API 创建 package request 不返回 500
24. ✅ readiness 显示 external_package_download=false
25. ✅ readiness 显示 package_execution=false
26. ✅ 旧 Step 1/2/3 测试仍通过（218 total）

---

## 九、下一步建议

**建议进入 Step 5：Network Egress 网络访问控制**

参考 SANDBOX_NEXT_STEPS.md Phase 4-5，具体任务：

1. Sandbox V2 Network Policy 运行时模型
2. 出站访问 Allowlist/Denylist
3. DNS 解析控制
4. SSRF 防护
5. Metadata Service Endpoint 拦截
6. Egress Proxy 接口
7. 模拟网络测试

---

## 十、命令速查

```bash
# 运行 package 测试
python -m pytest tests/test_open_platform/test_sandbox_v2_package_*.py tests/test_open_platform/test_sandbox_v2_supply_chain.py -q -v

# 运行全部 sandbox v2 测试
python -m pytest tests/test_open_platform/test_sandbox_v2_*.py -q 2>&1 || python -m pytest tests/test_open_platform/test_sandbox_v2_models.py tests/test_open_platform/test_sandbox_v2_policy_engine.py tests/test_open_platform/test_sandbox_v2_service.py tests/test_open_platform/test_sandbox_v2_api.py tests/test_open_platform/test_sandbox_v2_queue.py tests/test_open_platform/test_sandbox_v2_worker.py tests/test_open_platform/test_sandbox_v2_queue_api.py tests/test_open_platform/test_sandbox_v2_artifact_policy.py tests/test_open_platform/test_sandbox_v2_artifact_store.py tests/test_open_platform/test_sandbox_v2_artifact_service.py tests/test_open_platform/test_sandbox_v2_artifact_api.py tests/test_open_platform/test_sandbox_v2_package_policy.py tests/test_open_platform/test_sandbox_v2_package_quarantine.py tests/test_open_platform/test_sandbox_v2_supply_chain.py tests/test_open_platform/test_sandbox_v2_package_service.py tests/test_open_platform/test_sandbox_v2_package_api.py -q

# 运行完整 test_open_platform
python -m pytest tests/test_open_platform -q
```
