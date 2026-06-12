# Step 24-C：Checksum / Signature Verification Pipeline

## 1. 本轮目标

实现 Package Artifact 的 checksum/signature verification pipeline。

**只做 verification domain/store/checksum/signature verifier + service。不下载、不联网、不执行。**

## 2. Verification Domain Model

`src/open_platform/package_verification.py`

### Enums
| Enum | Values |
|------|--------|
| VerificationRunStatus | pending, running, passed, passed_with_warnings, failed, blocked, skipped |
| VerificationCheckType | checksum_format, checksum_match, signature_format, signature_metadata, signature_trust_policy, artifact_input_available, local_path_allowed, no_network_used, no_execution_used |
| VerificationCheckStatus | passed, warning, failed, blocked, skipped |
| VerificationSeverity | info, warning, error, blocker |
| SignatureVerificationMode | metadata_only, local_detached_signature, external_tool_reserved |

### VerificationCheck
check_id (verchk_<16>), check_type, status, severity, message, expected, actual, metadata

### PackageVerificationRun
verification_id (pkgver_<16>), artifact_id, submission_id, tenant_id, developer_id, checksum_algorithm, expected_checksum, actual_checksum, signature_algorithm, signature_value_present, signature_verified, signature_mode, checks list, counts, safety flags. add_check(), calculate_status() with _recount(), is_passed(), is_blocked()

## 3. SQLite Verification Store

`src/adapters/package_verification_store.py`

1 table (package_verification_runs), 23 columns, 5 indexes. CRUD, latest_by_artifact, filters, counts.

## 4. Checksum Verifier

`src/open_platform/checksum_verifier.py`

- 支持: sha256, sha384, sha512
- 拒绝: md5, sha1, crc32 (BLOCKED)
- Input: content_bytes or local_path (with allowed_root safety checks)
- 安全检查: no symlinks, no directories, 50MB max, path traversal blocked, no network/subprocess
- `verify_checksum(request) -> ChecksumVerificationResult`

## 5. Signature Verifier

`src/open_platform/signature_verifier.py`

- METADATA_ONLY mode: metadata/trust-policy 层验证
- 支持算法: cosign, minisign, gpg (format check only)
- trusted_key_ids: key trust policy check
- signature_verified: **Step 24-C 始终返回 False** (no crypto)
- EXTERNAL_TOOL_RESERVED: BLOCKED — 不调用外部工具
- 不调用 cosign/gpg/minisign / 不 subprocess / 不联网

## 6. Artifact Verification Service

`src/open_platform/package_verification_service.py`

`PackageVerificationService.verify_artifact()`:
1. Get artifact → verify tenant → check status (rejected/disabled → BLOCKED)
2. Checksum verifier: algo+value+bytes/path → match/mismatch/blocked
3. Signature verifier: metadata-only → format+warnings+trust policy
4. Recalculate status → save run → update artifact.verification_status
5. Write audit event → record usage

## 7. Usage

3 new UsageResource: PACKAGE_VERIFICATION_RUN, PACKAGE_CHECKSUM_VERIFY, PACKAGE_SIGNATURE_VERIFY
Metadata excludes: raw_key, key_hash, package contents, full package_url, secrets

## 8. Bootstrap

**main.py 未修改。** Verification store/service 内部使用。

## 9. Non-Execution Guarantees

- ❌ 不下载 package / 不 HTTP GET/HEAD
- ❌ 不解压 / 不执行 package_url / entrypoint
- ❌ 不访问 repository_url / 不联网
- ❌ 不调用 cosign/gpg/minisign 外部命令
- ❌ 不启动 subprocess / container
- ❌ 不做 CVE scan / dependency scan
- ❌ 不调用 AgentRuntime / 不注册 AgentRegistry
- ❌ signature_verified 始终 False (metadata-only)
- ❌ 不创建 worker / runtime execution API

## 10. Tests

```bash
python -m pytest tests/test_open_platform/test_package_verification.py -v
# 79 passed

python -m pytest tests/test_open_platform/ -q
# 853 passed

python -m pytest tests/test_security.py tests/test_agents/ tests/test_saas/ tests/test_open_platform/ -q
# 1500 passed
```

## 11. Known Issues

- checksum verification only for sha256/sha384/sha512
- signature verification is metadata-only (no real cryptographic verification)
- EXTERNAL_TOOL_RESERVED mode blocked (cosign/gpg/minisign not called)
- No artifact promotion to verified storage (future Step 24-D+)
- Local path security uses os.path.realpath (adequate for trusted admin but not for multi-user mount scenarios)

## 12. Next Step

**Step 24-D：Runtime Execution Plan Model + Store**
