# SANDBOX V2 STEP 3 REPORT — Artifact 文件系统隔离与只读物化

**实施日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)
**步骤**: Sandbox v2 Step 3 — Artifact 文件系统隔离与只读物化

---

## 一、本次新增文件

| # | 文件 | 用途 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/artifact_policy.py` | Artifact 安全策略引擎（10 条安全规则：fail closed、路径穿越、危险扩展名、MIME 白名单、大小限制等） |
| 2 | `src/open_platform/sandbox_v2/artifacts.py` | LocalSandboxArtifactStore — 安全本地文件存储（路径隔离、sha256、只读权限、分目录） |
| 3 | `tests/test_open_platform/test_sandbox_v2_artifact_policy.py` | Artifact 策略测试（28 项） |
| 4 | `tests/test_open_platform/test_sandbox_v2_artifact_store.py` | Artifact 存储测试（11 项） |
| 5 | `tests/test_open_platform/test_sandbox_v2_artifact_service.py` | Artifact 服务测试（7 项） |
| 6 | `tests/test_open_platform/test_sandbox_v2_artifact_api.py` | Artifact API 测试（14 项） |

**共新增 6 个文件。**

---

## 二、本次修改文件

| # | 文件 | 变更内容 |
|---|------|----------|
| 1 | `src/open_platform/sandbox_v2/models.py` | 新增 4 个数据类 + 2 个枚举 + 3 个常量（~260 行）：SandboxArtifact, SandboxArtifactManifest, SandboxArtifactMaterializationRequest, SandboxArtifactPolicyDecision; SandboxV2ArtifactStatus, SandboxV2ArtifactType; BLOCKED_FILE_EXTENSIONS, ALLOWED_ARTIFACT_MIME_TYPES |
| 2 | `src/open_platform/sandbox_v2/store.py` | 新增 10 个 artifact store protocol 方法 |
| 3 | `src/adapters/sqlite_sandbox_v2_store.py` | 新增 2 个表（sandbox_v2_artifacts, sandbox_v2_artifact_manifests）+ 10 个 CRUD 方法 + 2 个 row mapper |
| 4 | `src/open_platform/sandbox_v2/service.py` | 构造函数接受 artifact_store；新增 9 个 artifact 方法 |
| 5 | `src/open_platform/sandbox_v2/worker.py` | process_queue_item 在 simulation 完成后生成 log artifact + artifact_refs |
| 6 | `src/api/sandbox_v2.py` | 新增 8 个 Artifact API 端点；更新 readiness schema（+9 个 artifact 字段）；Pydantic 模型外提 |
| 7 | `main.py` | 初始化 LocalSandboxArtifactStore + 注入 service |
| 8 | `frontend/services/runtime-admin.ts` | 新增 8 个 Artifact API client 方法 + 类型导入 |
| 9 | `frontend/types/runtime-admin.ts` | 新增 7 个 TypeScript 接口 |

**共修改 9 个文件。**

---

## 三、新增 API 列表

| 方法 | 路径 | 功能 | 新增于 |
|------|------|------|--------|
| `POST` | `/api/runtime/sandbox-v2/artifacts` | 创建/物化 artifact（经过 policy） | Step 3 |
| `GET` | `/api/runtime/sandbox-v2/artifacts` | 列出 artifacts（支持多维度过滤） | Step 3 |
| `GET` | `/api/runtime/sandbox-v2/artifacts/{artifact_id}` | 查看 artifact metadata | Step 3 |
| `GET` | `/api/runtime/sandbox-v2/artifacts/{artifact_id}/content` | 读取 artifact 内容文本 | Step 3 |
| `POST` | `/api/runtime/sandbox-v2/artifacts/{artifact_id}/expire` | 标记过期 | Step 3 |
| `DELETE` | `/api/runtime/sandbox-v2/artifacts/{artifact_id}` | 删除 artifact（文件 + metadata） | Step 3 |
| `POST` | `/api/runtime/sandbox-v2/artifact-manifests` | 创建 manifest | Step 3 |
| `GET` | `/api/runtime/sandbox-v2/artifact-manifests/{manifest_id}` | 查看 manifest | Step 3 |

Step 1/2 的 11 个原始端点不变，全部向后兼容。

---

## 四、Artifact 当前完成能力

### 4.1 安全策略 ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| 默认 fail closed | ✅ | 任何异常 → 拒绝 |
| 路径穿越防护 | ✅ | `../`, `..\`, 绝对路径, 盘符路径, UNC 路径全部拦截 |
| 危险扩展名拦截 | ✅ | .exe/.dll/.bat/.cmd/.ps1/.sh/.so/.jar 等 16 种 |
| 文件名 sanitize | ✅ | 移除 NULL 字节、不可打印字符、首尾点号 |
| MIME 类型白名单 | ✅ | 10 种安全类型，允许 text/plain 到 application/octet-stream |
| 大小限制 | ✅ | 单文件默认 1 MiB，job 总大小默认 10 MiB |
| 强制只读 | ✅ | 所有 artifact 默认 read_only=true |
| 未知类型拒绝 | ✅ | 非标准 artifact_type → fail closed |

### 4.2 本地存储 ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| 路径隔离 | ✅ | 所有路径 resolve 验证在 artifact root 内 |
| 分目录存储 | ✅ | {org}/{ws}/{job_id}/{artifact_id}/file |
| SHA256 hash | ✅ | 写入后自动计算 |
| 只读权限 | ✅ | 写入后 chmod 0444 |
| 安全读取 | ✅ | 只允许读 root 内文件 |
| 安全删除 | ✅ | 只允许删除 root 内文件 |
| 文本截断 | ✅ | 大文件返回截断内容 + 大小提示 |
| Manifest 生成 | ✅ | 汇总 job/record 所有 artifact |

### 4.3 Worker 集成 ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| 模拟日志 artifact | ✅ | Worker 完成后生成 simulation log |
| artifact_refs 关联 | ✅ | execution_record 包含 artifact_id 列表 |

---

## 五、Artifact 当前限制（诚实声明）

| 能力 | 状态 | 原因 |
|------|------|------|
| 压缩包处理 | ❌ | 不解压 zip/tar/gz — 安全性考虑 |
| 二进制文件存储 | ⚠️ | API 层仅支持文本；store 支持 bytes |
| 对象存储后端 | ❌ | 仅本地文件系统；Protocol 设计允许后续替换 |
| Artifact 共享/分发 | ❌ | 不支持跨 tenant |
| 大文件流式读写 | ❌ | 仅支持全量读写 |
| ClamAV 病毒扫描 | ❌ | 未集成 |

---

## 六、为什么这一步仍然不等于生产级沙箱

1. **无执行隔离** — 文件存储在本地，无人容器/namespace 保护。
2. **无运行时文件系统隔离** — artifact root 不在 chroot/mount namespace 中。
3. **无压缩包处理** — 不解压，不解包，防止 zip bomb。
4. **无包下载** — 不下载外部依赖。
5. **无运行时强制** — 文件系统策略只在 policy layer 检查，无 OS 级别强制。

---

## 七、测试结果

### 新增测试
```
test_sandbox_v2_artifact_policy.py   28 passed (sanitize/extension/path/size/mime/fail_closed)
test_sandbox_v2_artifact_store.py    11 passed (create/read/delete/sha256/manifest/isolation)
test_sandbox_v2_artifact_service.py   7 passed (materialize/list/content/delete/manifest/worker)
test_sandbox_v2_artifact_api.py      14 passed (CRUD/readiness/compatibility/no-500)
```

### 全部 sandbox v2 测试
```
159 passed in 5.59s
```

### 全部 test_open_platform 测试
```
3725 passed in 81.89s
```

零回归。Step 1/2/3 所有测试通过。

---

## 八、测试覆盖清单

1. ✅ 正常 text artifact 可以物化
2. ✅ JSON artifact 可以物化
3. ✅ 物化后文件为 read_only
4. ✅ 文件名会被 sanitize
5. ✅ ../ 路径穿越被拒绝
6. ✅ Windows drive path 被拒绝
7. ✅ absolute path 被拒绝
8. ✅ 危险扩展名 .exe / .bat / .ps1 / .sh 被拒绝
9. ✅ 超过大小限制被拒绝
10. ✅ 不允许 MIME 类型被拒绝
11. ✅ artifact 写入后 sha256 正确
12. ✅ artifact metadata 存入 SQLite
13. ✅ list_artifacts 可按 job_id 过滤
14. ✅ get content 只允许读 artifact root 内文件
15. ✅ delete artifact 只能删除 artifact root 内文件
16. ✅ manifest 可以生成并包含 artifact_ids
17. ✅ worker run_once 会生成 simulation log artifact
18. ✅ readiness 正确显示 artifact_store=true
19. ✅ 旧 Step 1 / Step 2 测试仍通过（159 total）

---

## 九、下一步建议

**建议进入 Step 4：Package 下载隔离、签名验证、SBOM、漏洞扫描接口**

参考 SANDBOX_NEXT_STEPS.md Phase 4，具体任务：

1. Package Download Quarantine 隔离
2. 包签名验证（minisign/cosign 接口）
3. SBOM 生成接口
4. 漏洞扫描集成接口（不执行扫描，只做接口框架）
5. 包 Allowlist/Denylist 管理
6. 下载前域名/IP 检查
7. 所有下载默认 blocked

---

## 十、命令速查

```bash
# 运行全部 artifact 测试
python -m pytest tests/test_open_platform/test_sandbox_v2_artifact_*.py -q -v

# 运行全部 sandbox v2 测试（Step 1+2+3）
python -m pytest tests/test_open_platform/test_sandbox_v2_*.py -q -v

# 运行完整 test_open_platform
python -m pytest tests/test_open_platform -q
```
