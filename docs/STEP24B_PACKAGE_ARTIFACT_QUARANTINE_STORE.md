# Step 24-B：Package Artifact & Quarantine Domain Model + Store

## 1. 本轮目标

实现 Package Artifact 与 Quarantine 的领域模型、SQLite Store、状态机、审计事件和测试。

**只做 metadata-only artifact declaration。不下载、不验证、不执行。**

## 2. PackageArtifact Model

`src/open_platform/package_artifact.py`

### 枚举

| Enum | Values |
|------|--------|
| ArtifactSourceType | package_url, repository, inline_metadata, unknown |
| ArtifactStatus | declared, quarantined, metadata_validated, verification_pending, verified, rejected, disabled |
| QuarantineStatus | not_quarantined, quarantined, review_required, released, rejected, expired |
| VerificationStatus | not_verified, metadata_only, checksum_pending, checksum_verified, signature_pending, signature_verified, failed |
| ArtifactRiskLevel | low, medium, high, critical, unknown |
| ArtifactAuditEventType | created, metadata_updated, quarantined, released, rejected, disabled, verification_status_changed, risk_level_changed |

### PackageArtifact (dataclass, 30 fields)

- artifact_id (art_<16>), submission_id, developer_id, tenant_id
- marketplace_agent_id, source_type, package_url, repository_url
- package_name, package_version, checksum_algorithm, checksum_value
- signature_algorithm, signature_value, signing_key_id
- declared_size_bytes, content_type
- artifact_status, verification_status, risk_level, quarantine_status
- package_metadata (dict), validation_id, created_by, updated_by
- metadata (dict)
- to_dict / from_dict
- is_quarantined() — quarantine_status == quarantined
- is_verified_for_execution() — **Step 24-B always returns False**

### PackageQuarantineRecord (dataclass, 19 fields)

- quarantine_id (quar_<16>), artifact_id, tenant_id, submission_id
- status, reason, risk_level
- policy_snapshot (dict), validation_summary (dict)
- created_by, released_by, rejected_by
- created_at, updated_at, released_at, rejected_at, expires_at
- metadata (dict)
- to_dict / from_dict

### PackageArtifactAuditEvent (dataclass, 8 fields)

- event_id (artevt_<16>), artifact_id, tenant_id, event_type
- actor_id, message, metadata (dict), created_at
- to_dict / from_dict

### 错误类

- PackageArtifactError, PackageArtifactNotFoundError
- PackageArtifactAlreadyExistsError, PackageArtifactStateError
- PackageQuarantineNotFoundError

## 3. State Machines

### Artifact Status

```
DECLARED → METADATA_VALIDATED → VERIFICATION_PENDING → VERIFIED
              ↓                                              ↓
         QUARANTINED ←────────────────────────────────── REJECTED
              ↓                                              ↓
         DISABLED                                           DISABLED
```

### Quarantine Status

```
QUARANTINED → REVIEW_REQUIRED → RELEASED / REJECTED
                                      ↓
                                   EXPIRED
```

### Verification Status

```
NOT_VERIFIED / METADATA_ONLY → CHECKSUM_PENDING → CHECKSUM_VERIFIED
                                → SIGNATURE_PENDING → SIGNATURE_VERIFIED
                                → FAILED
```

## 4. SQLite Store

`src/adapters/package_artifact_store.py`

### 3 张表

| Table | Rows |
|-------|------|
| package_artifacts | 29 columns, 8 indexes (UNIQUE submission_id) |
| package_quarantine_records | 18 columns, 4 indexes |
| package_artifact_audit_events | 8 columns, 4 indexes |

### 模式

- `create_sqlite_db(path)` → autocommit / WAL / busy_timeout=30000
- `execute_with_retry(lambda: self._init_schema())` → schema
- `_init_schema()` → split(";") → `_db.execute(s)` → `self._db.conn.commit()`
- `flush()` → safe `self._db.conn.commit()`
- JSON: `json.dumps(ensure_ascii=False)` / `json.loads()`
- Datetime: ISO format strings

### 状态同步

- `create_quarantine_record()` → syncs `artifact.quarantine_status`
- `set_quarantine_status()` → syncs `artifact.quarantine_status`
- All status changes → `_audit()` → audit event

### 实现的方法（22 个）

Artifact: create, get, get_by_submission, list (6 filters), update, set_status, set_verification_status, set_risk_level, count
Quarantine: create, get, get_latest_for_artifact, list (3 filters), set_status
Audit: add_event, list_events

## 5. Artifact Declaration Service

`src/open_platform/package_artifact_service.py`

### PackageArtifactDeclarationService

- `declare_artifact_from_submission(submission_id, actor_id, tenant_id, quarantine=True)`
  1. Read submission → verify tenant match
  2. Extract manifest metadata (package_url, checksum, signature, deps, license...)
  3. Link latest PackageValidationResult
  4. Create PackageArtifact (artifact_status=DECLARED)
  5. Optionally create quarantine record → re-fetch artifact
  6. Record usage
- 不下载 / 不计算 checksum / 不验证 signature

## 6. Usage

新增 3 个 `UsageResource` 枚举值：
- `PACKAGE_ARTIFACT_DECLARE`
- `PACKAGE_ARTIFACT_QUARANTINE`
- `PACKAGE_ARTIFACT_STATUS_CHANGE`

Usage metadata 不包含 raw_key, key_hash, package contents, secrets, full package_url。

## 7. Bootstrap

**未修改 main.py。** Store 保持内部状态，用于 tests 和 future Step 24-C/D。

## 8. Non-Execution Guarantees

- ❌ 不下载 package — package_url 只存字符串
- ❌ 不解压 package
- ❌ 不执行 package_url / entrypoint
- ❌ 不联网 — 无 requests/httpx import
- ❌ 不访问 repository
- ❌ 不计算真实 checksum — checksum_value 只存声明值
- ❌ 不验证真实 signature — signature_value 只存声明值
- ❌ 不做 CVE scan
- ❌ 不调用 AgentRuntime / AgentRegistry
- ❌ 不创建 worker / container / subprocess
- ❌ 不创建 runtime execution API
- ❌ is_verified_for_execution() 始终返回 False

## 9. Tests

**83 tests, 全部通过：**

- Domain Model: 15 tests (PackageArtifact × 9, Quarantine x 4, Audit x 2)
- Store Artifact: 18 tests (CRUD, filters, status transitions, audit events, error handling)
- Store Quarantine: 18 tests (CRUD, sync, release/reject/expire, audit)
- Audit: 6 tests (add, list, sort, tenant_id, safety)
- Service: 11 tests (declare, tenant/rejection, metadata, quarantine toggle, safety)
- Startup Stability: 7 tests (init, repeated, JSON/datetime roundtrip, count, sequential)
- Non-Execution Guards: 8 tests (no requests/subprocess/docker/AgentRuntime/AgentRegistry imports; URL/checksum/signature stored not actioned; no worker)

```bash
python -m pytest tests/test_open_platform/test_package_artifact_store.py -v
# 83 passed

python -m pytest tests/test_open_platform/ -v
# 774 passed

python -m pytest tests/test_security.py tests/test_agents/ tests/test_saas/ tests/test_open_platform/ -q
# 1421 passed
```

## 10. Known Issues

- No real package download yet (Step 24-C+)
- Checkum/signature stored as declared values — not verified
- No dependency scanner
- No package quarantine directory on disk
- No artifact promotion to verified storage
- Service uses mock submission store in tests

## 11. Next Step

**Step 24-C：Checksum / Signature Verification Pipeline**
