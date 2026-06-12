# Step 25-E：Read-only Artifact Extraction Guard

## 1. 本轮目标

只实现 read-only extraction guard — entry metadata 字符串级路径验证。**不 import zipfile/tarfile/shutil。不读取 archive 文件。不写文件。不解压。**

## 2. Why This Is Not Real Extraction

- No zipfile/tarfile/shutil imports
- No archive file read (no open/read on archives)
- No file write (no extraction to disk)
- No file materialization
- Entry metadata is validated by string inspection only (pathlib.PurePosixPath, heuristics)
- is_extraction_allowed/is_execution_allowed always False
- ReadOnlyExtractionPlan is metadata-only logical reference

## 3. Domain Model

`src/open_platform/artifact_extraction_guard.py`

- ArchiveEntryMetadata: 24 flag fields per entry — raw name hash/redacted only, blocked flags for path traversal/absolute/Windows drive/UNC/NUL/symlink/device/fifo/socket/script/exec-mode
- ArtifactExtractionGuardRequest: 42 fields, entries list, all safety flags True
- ExtractionGuardCheck + ArtifactExtractionGuardResult: guard evaluation with per-entry checks
- ReadOnlyExtractionPlan: logical_extraction_ref only, extraction_allowed=False

## 4. SQLite Store

`src/adapters/artifact_extraction_guard_store.py`

4 tables (requests + results + plans + audit_events), 15 indexes. All operations metadata-only.

## 5. Service

`src/open_platform/artifact_extraction_guard_service.py`

create_guard_request → evaluate_guard (per-entry path checks) → reserve_read_only_plan (logical ref only). No file writes, no archive access.

## 6. Tests

78 tests: entry builder (22) + domain (20) + store (30) + service (6)
1706 Open Platform / 2353 regression passed.

## 7. Next Step

Step 25-F：Worker Queue Design, Disabled by Default
