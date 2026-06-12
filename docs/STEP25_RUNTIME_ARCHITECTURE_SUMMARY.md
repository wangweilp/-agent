# Step 25 Runtime Architecture Summary

## 1. Executive Summary

Step 25 从 Step 24 的"安全准备态"推进到"生产级沙箱路线图与安全门控体系"。核心成果：8 个 domain model + store + service 组件，1 个可行性评估服务，1 个静态 trusted fixture registry，163 个红队逃逸守卫测试。

**所有执行入口 fail-closed。**

## 2. Architecture Flow

```
Developer Submission → Package Artifact (24-B)
  → Sandbox Execution Record (25-B, audit-only, is_executable=False)
  → Container/MicroVM Feasibility (25-C, 10 technologies, execution_enabled=False)
  → Download Admin Gate (25-D, HTTPS→review, HTTP/private blocked, no download)
  → Quarantine Reservation (25-D, metadata-only, file_materialized=False)
  → Read-only Extraction Guard (25-E, no unzip, no archive read)
  → Disabled Worker Queue Record (25-F, no enqueue/dispatch/worker)
  → Enforcement Proof (25-G, metadata-only, no iptables/mount/secrets)
  → Trusted Fixture Execution (25-H, built-in only, no third-party code)
  → Red-Team Escape Tests (25-I, 163 tests, no critical path)
  → Step 25-K Final Gate
```

## 3. Component Table

| Component | Step | Purpose | What It Does NOT Do |
|-----------|------|---------|---------------------|
| SandboxExecutionRecord | 25-B | Audit-only execution metadata | Execute/dispatch/queue |
| SandboxAdapterFeasibility | 25-C | 10-tech paper assessment | Start container/microVM/docker |
| PackageDownloadRequest | 25-D | Admin-gated download request | HTTP GET / download package |
| PackageDownloadQuarantine | 25-D | Metadata-only quarantine reservation | Write file / materialize |
| ArchiveEntryMetadata | 25-E | String-level path validation | Read archive / extract |
| ReadOnlyExtractionPlan | 25-E | Logical extraction reference | Write file / allow extraction |
| SandboxWorkerQueueRecord | 25-F | Disabled queue metadata record | Enqueue / dispatch / start worker |
| EnforcementProofRequest | 25-G | Metadata-only rule validation proof | Apply iptables / mount / read secret |
| TrustedFixtureRegistry | 25-H | 5 built-in deterministic fixtures | Execute third-party / package code |
| Red-Team Escape Guards | 25-I | 163 tests, 11 guard categories | — |

## 4. Trust Boundaries (15)

1. Execution record ≠ execution
2. Feasibility assessment ≠ container implementation
3. Admin approval ≠ download
4. Quarantine reservation ≠ file materialization
5. Extraction guard ≠ archive extraction
6. Extraction plan ≠ file write
7. Queue record ≠ queue
8. Queue gate ≠ dispatch
9. Enforcement proof ≠ enforcement
10. Secret rule ≠ secret read
11. Trusted fixture ≠ third-party code
12. Trusted fixture success ≠ package success
13. Execute endpoint exists ≠ execution enabled
14. Red-team tests passed ≠ production sandbox complete
15. Step 25 completed ≠ external code execution completed

## 5. Safety Invariants

All `is_*` methods return False:
- is_executable(), is_dispatchable(), is_downloadable(), is_extraction_allowed(), is_enforcement_active(), is_third_party_success(), is_package_success()

All dangerous flags default False on every domain object. No socket/requests/docker/subprocess/AgentRuntime/AgentRegistry imports in any step25 module. Execute endpoint always returns blocked.

## 6. Known Issues

No production sandbox, no real worker queue, no package download, no archive extraction, no crypto signature verify, no dependency scan, no container/microVM implementation, no data/secret/network broker, no kill switch. All intentional Step 26+ deferrals.
