# Step 25-D：Package Download Quarantine Prototype with Explicit Admin Gate

## 1. 本轮目标

只实现 download request + admin gate + metadata-only quarantine reservation。**不真实下载，不联网，不执行。**

## 2. Why This Is Not Real Download

- No HTTP client (no requests/httpx/urllib.request)
- No DNS lookup (no socket)
- No network access to package_url
- No file write
- No package extraction
- All source URLs parsed as strings only (urllib.parse safe subset)
- HTTP/file/git/SSH/localhost/private IP/metadata IP all blocked
- HTTPS-only sources go to admin review, then are "approved for future download" which does NOT trigger download

## 3. Domain Model

`src/open_platform/package_download_quarantine.py`

- PackageSourceMetadata: URL parsing (safe), scheme/host extraction, SHA256 hash, redacted URL. Blocked: HTTP, file, git, localhost, private IP, metadata IP
- PackageDownloadRequest: is_downloadable/is_network_allowed/is_execution_allowed → all False
- PackageDownloadQuarantineRecord: file_materialized/extraction_allowed/execution_allowed → all False
- PackageDownloadAuditEvent: 12 event types, metadata excludes secrets/package_url/path

## 4. SQLite Store

`src/adapters/package_download_quarantine_store.py`

3 tables (requests + quarantine_records + audit_events), 16 indexes. Admin approve → ADMIN_APPROVED_RESERVED but still not downloadable.

## 5. Service

`src/open_platform/package_download_quarantine_service.py`

Source validation → HTTPS → admin review. Blocked sources → DOWNLOAD_DISABLED. Admin approval → future download reserved only. Quarantine → metadata-only reservation (no file).

## 6. Tests

106 tests: source metadata (18) + domain (20) + store (41) + service (15) + safety (22)
1628 Open Platform / 2275 regression passed.

## 7. Next Step

Step 25-E：Read-only Artifact Extraction Guard
