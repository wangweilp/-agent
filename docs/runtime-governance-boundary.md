# Runtime Governance Boundary

当前 Runtime/Sandbox 主要完成的是安全治理控制面、模拟运行、元数据校验、默认关闭和审计追踪能力，不等于已经完成生产级第三方代码执行沙箱。生产级执行环境需要后续接入 PostgreSQL/Redis/对象存储、真实任务队列、Rootless Container/MicroVM、只读工件物化和安全隔离验证。

## Current Capability

- Metadata-only runtime governance control plane.
- Simulation runtime and dry-run eligibility checks.
- Sandbox policy models and audit records.
- Runtime binding admin workflow.
- Kill Switch metadata records and Incident Store.
- Package Download Worker Gate that is disabled by default.
- Artifact Materialization Gate that only exposes read-only metadata references.
- Sandbox/Simulation Execution Record where `is_executable()` stays false.
- Production Sandbox Gate that remains disabled and fail-closed.

## Explicit Non-Capability

- No production-grade third-party code execution sandbox.
- No subprocess, container, or MicroVM execution for developer packages.
- No package download worker with network/file-write permission.
- No artifact extraction/materialization onto a live filesystem.
- No runtime-level network, filesystem, secret, cgroup, namespace, or seccomp enforcement.

## Runtime/Sandbox Policy Language

Use the following boundary terms consistently:

- `metadata-only`
- `simulation runtime`
- `disabled-by-default`
- `deny by default`
- `fail closed`
- `audit-first`

## Production Sandbox Gate

The Production Sandbox Gate should show production execution as disabled until
all of the following are implemented and verified:

- PostgreSQL/Redis/object storage migration
- Real task queue
- Rootless Container
- MicroVM
- Read-only artifact materialization
- Security isolation verification

## Next Build Steps

1. Complete production data migration and queue infrastructure.
2. Implement immutable read-only artifact materialization.
3. Add rootless container runtime admission behind disabled gates.
4. Add MicroVM isolation as a separate controlled spike.
5. Run red-team escape tests and fail-closed regression tests after every runtime change.
