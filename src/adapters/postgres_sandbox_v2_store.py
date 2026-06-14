"""PostgreSQL Sandbox v2 Store Adapter — SandboxV2Store Protocol 的 PostgreSQL 实现。

Step 12 — Production Backend Migration.

设计原则:
1. 实现 SandboxV2Store Protocol 所需接口。
2. 使用 psycopg2 (或 psycopg3) 连接 PostgreSQL。
3. 缺依赖或未连接时返回清晰的错误，不做静默回退。
4. 所有方法签名与 SQLite adapter 保持一致。
5. 测试不依赖真实 PostgreSQL — 通过 connect=False 跳过连接。

安全约束:
- 使用参数化查询防止 SQL 注入。
- 不存储 artifact 文件内容，只存 metadata。
- 不使用 ORM，直接用 SQL。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Module-level connection check
# ═══════════════════════════════════════════════════════════════════════════

_PSYCOPG_AVAILABLE = False
_PSYCOPG_MODULE = None

try:
    import psycopg2
    import psycopg2.extras
    _PSYCOPG_AVAILABLE = True
    _PSYCOPG_MODULE = psycopg2
except ImportError:
    try:
        import psycopg  # psycopg 3
        _PSYCOPG_AVAILABLE = True
        _PSYCOPG_MODULE = psycopg
    except ImportError:
        pass

_PSYCOPG_UNAVAILABLE_MSG = (
    "psycopg2 or psycopg is not installed. "
    "Install with: pip install psycopg2-binary"
)


def _require_psycopg():
    """检查 psycopg 是否可用，不可用则抛出 ImportError。"""
    if not _PSYCOPG_AVAILABLE:
        raise ImportError(_PSYCOPG_UNAVAILABLE_MSG)


# ═══════════════════════════════════════════════════════════════════════════
# PostgresSandboxV2Store
# ═══════════════════════════════════════════════════════════════════════════

class PostgresSandboxV2Store:
    """PostgreSQL SandboxV2Store 实现。

    方法签名与 SQLiteSandboxV2Store 一致，便于替换。
    使用原始 SQL + 参数化查询，不做 ORM 抽象。

    参数:
        dsn: PostgreSQL connection string (e.g. postgresql://user:pass@host/db)
        connect: 是否立即连接 (测试中使用 False)
    """

    def __init__(self, dsn: str = "", connect: bool = False):
        self._dsn = dsn or os.getenv("SANDBOX_V2_POSTGRES_DSN", "")
        self._conn: Any = None
        if connect and self._dsn:
            self._connect()

    def _connect(self) -> None:
        """建立数据库连接。"""
        _require_psycopg()
        if not self._dsn:
            raise ValueError("PostgreSQL DSN is empty. Set SANDBOX_V2_POSTGRES_DSN.")
        try:
            if _PSYCOPG_MODULE.__name__ == "psycopg2":
                self._conn = _PSYCOPG_MODULE.connect(self._dsn)
                self._conn.autocommit = True
            else:
                self._conn = _PSYCOPG_MODULE.connect(self._dsn)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to PostgreSQL: {e}") from e

    def _ensure_connected(self) -> Any:
        """确保已连接，返回连接对象。"""
        if self._conn is None:
            self._connect()
        return self._conn

    def _execute(self, sql: str, params: tuple | None = None) -> Any:
        """执行 SQL，返回 cursor。"""
        conn = self._ensure_connected()
        cur = conn.cursor()
        cur.execute(sql, params or ())
        return cur

    def _fetchone(self, sql: str, params: tuple | None = None) -> dict[str, Any] | None:
        """执行查询并返回一行。"""
        cur = self._execute(sql, params)
        try:
            row = cur.fetchone()
            if row is None:
                return None
            cols = [desc[0] for desc in cur.description or []]
            return dict(zip(cols, row))
        finally:
            cur.close()

    def _fetchall(self, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """执行查询并返回所有行。"""
        cur = self._execute(sql, params)
        try:
            rows = cur.fetchall()
            if not rows:
                return []
            cols = [desc[0] for desc in cur.description or []]
            return [dict(zip(cols, row)) for row in rows]
        finally:
            cur.close()

    @property
    def is_available(self) -> bool:
        """检查依赖是否可用。"""
        return _PSYCOPG_AVAILABLE

    @property
    def availability_message(self) -> str:
        """返回可用性描述。"""
        if _PSYCOPG_AVAILABLE:
            module_name = _PSYCOPG_MODULE.__name__ if _PSYCOPG_MODULE else "unknown"
            has_dsn = bool(self._dsn)
            return (
                f"psycopg available ({module_name}). "
                + ("DSN configured." if has_dsn else "DSN not configured.")
            )
        return _PSYCOPG_UNAVAILABLE_MSG

    def health_check(self) -> dict[str, Any]:
        """测试 PostgreSQL 连接健康状态。不执行 schema。"""
        if not _PSYCOPG_AVAILABLE:
            return {"ok": False, "reason": _PSYCOPG_UNAVAILABLE_MSG}
        if not self._dsn:
            return {"ok": False, "reason": "PostgreSQL DSN not configured"}
        try:
            conn = self._ensure_connected()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            return {"ok": True, "reason": "PostgreSQL connection healthy"}
        except Exception as e:
            return {"ok": False, "reason": f"PostgreSQL connection failed: {e}"}

    def initialize_schema(self, sql_path: str | None = None) -> dict[str, Any]:
        """应用 PostgreSQL schema。只在显式调用时执行。不 drop 数据。"""
        if not sql_path:
            p = self.get_schema_sql_path()
            if p is None:
                return {"ok": False, "reason": "Schema SQL file not found"}
            sql_path = str(p)
        if not os.path.isfile(sql_path):
            return {"ok": False, "reason": f"Schema file not found: {sql_path}"}
        try:
            conn = self._ensure_connected()
            cur = conn.cursor()
            content = Path(sql_path).read_text(encoding="utf-8")
            cur.execute(content)
            conn.commit()
            cur.close()
            return {"ok": True, "reason": f"Schema applied from {sql_path}"}
        except Exception as e:
            return {"ok": False, "reason": f"Schema init failed: {e}"}

    def get_schema_sql_path(self) -> Path | None:
        """返回 schema SQL 文件路径。"""
        candidates = [
            Path("docs/sql/sandbox_v2_postgres_schema.sql"),
            Path("src/adapters/sql/sandbox_v2_postgres_schema.sql"),
        ]
        for p in candidates:
            if p.is_file():
                return p.resolve()
        # 尝试从项目根目录查找
        for root in [Path.cwd(), Path(__file__).resolve().parent.parent.parent]:
            for p in candidates:
                fp = root / p
                if fp.is_file():
                    return fp.resolve()
        return None

    # ────────────────────────────────────────────────────────────────────
    # Job
    # ────────────────────────────────────────────────────────────────────

    def create_job(self, job: Any) -> Any:
        _require_psycopg()
        from src.open_platform.sandbox_v2.models import SandboxJob
        sql = """
            INSERT INTO sandbox_v2_jobs (job_id, organization_id, workspace_id, agent_id,
                requested_by, mode, status, requested_action, input_ref,
                policy_snapshot_json, risk_level, metadata_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """
        self._execute(sql, (
            job.job_id, job.organization_id, job.workspace_id, job.agent_id,
            job.requested_by, job.mode, job.status, job.requested_action, job.input_ref,
            json.dumps(job.policy_snapshot), job.risk_level, json.dumps(job.metadata),
        ))
        return job

    def get_job(self, job_id: str) -> Any | None:
        _require_psycopg()
        from src.open_platform.sandbox_v2.models import SandboxJob
        row = self._fetchone("SELECT * FROM sandbox_v2_jobs WHERE job_id = %s", (job_id,))
        if row is None:
            return None
        return self._row_to_job(row)

    def list_jobs(self, organization_id: str | None = None, workspace_id: str | None = None, limit: int = 50) -> list[Any]:
        _require_psycopg()
        sql = "SELECT * FROM sandbox_v2_jobs WHERE 1=1"
        params: list[Any] = []
        if organization_id:
            sql += " AND organization_id = %s"
            params.append(organization_id)
        if workspace_id:
            sql += " AND workspace_id = %s"
            params.append(workspace_id)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        rows = self._fetchall(sql, tuple(params))
        return [self._row_to_job(r) for r in rows]

    def update_job_status(self, job_id: str, status: str) -> Any | None:
        _require_psycopg()
        sql = """UPDATE sandbox_v2_jobs SET status = %s, updated_at = NOW()
                 WHERE job_id = %s RETURNING *"""
        row = self._fetchone(sql, (status, job_id))
        if row is None:
            return None
        return self._row_to_job(row)

    # ────────────────────────────────────────────────────────────────────
    # Execution Record
    # ────────────────────────────────────────────────────────────────────

    def create_execution_record(self, record: Any) -> Any:
        _require_psycopg()
        sql = """INSERT INTO sandbox_v2_execution_records (record_id, job_id, status,
            mode, duration_ms, decision, reason, no_real_execution, metadata_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        self._execute(sql, (
            record.record_id, record.job_id, record.status, record.mode,
            record.duration_ms, record.decision, record.reason,
            record.no_real_execution, json.dumps(record.metadata),
        ))
        return record

    def get_execution_record(self, record_id: str) -> Any | None:
        _require_psycopg()
        row = self._fetchone("SELECT * FROM sandbox_v2_execution_records WHERE record_id = %s", (record_id,))
        if row is None:
            return None
        return self._row_to_execution_record(row)

    def list_execution_records(self, job_id: str | None = None, limit: int = 50) -> list[Any]:
        _require_psycopg()
        if job_id:
            rows = self._fetchall(
                "SELECT * FROM sandbox_v2_execution_records WHERE job_id = %s ORDER BY created_at DESC LIMIT %s",
                (job_id, limit),
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM sandbox_v2_execution_records ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
        return [self._row_to_execution_record(r) for r in rows]

    # ── Artifact ──

    def create_artifact(self, artifact: Any) -> Any:
        _require_psycopg()
        sql = """INSERT INTO sandbox_v2_artifacts (artifact_id, job_id, organization_id,
            workspace_id, record_id, artifact_type, name, original_filename, safe_filename,
            storage_key, storage_backend, size_bytes, mime_type, sha256, read_only, status, risk_level)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        self._execute(sql, (
            artifact.artifact_id, artifact.job_id, artifact.organization_id,
            artifact.workspace_id, artifact.record_id, artifact.artifact_type,
            artifact.name, artifact.original_filename, artifact.safe_filename,
            artifact.storage_key, artifact.storage_backend, artifact.size_bytes,
            artifact.mime_type, artifact.sha256, artifact.read_only,
            artifact.status, artifact.risk_level,
        ))
        return artifact

    def get_artifact(self, artifact_id: str) -> Any | None:
        _require_psycopg()
        row = self._fetchone("SELECT * FROM sandbox_v2_artifacts WHERE artifact_id = %s", (artifact_id,))
        return self._row_to_artifact(row) if row else None

    def list_artifacts(self, job_id: str | None = None, record_id: str | None = None,
                       organization_id: str | None = None, workspace_id: str | None = None,
                       limit: int = 50) -> list[Any]:
        _require_psycopg()
        sql = "SELECT * FROM sandbox_v2_artifacts WHERE 1=1"
        params: list[Any] = []
        if job_id:
            sql += " AND job_id = %s"; params.append(job_id)
        if record_id:
            sql += " AND record_id = %s"; params.append(record_id)
        if organization_id:
            sql += " AND organization_id = %s"; params.append(organization_id)
        if workspace_id:
            sql += " AND workspace_id = %s"; params.append(workspace_id)
        sql += " ORDER BY created_at DESC LIMIT %s"; params.append(limit)
        return [self._row_to_artifact(r) for r in self._fetchall(sql, tuple(params))]

    def update_artifact_status(self, artifact_id: str, status: str) -> Any | None:
        _require_psycopg()
        row = self._fetchone(
            "UPDATE sandbox_v2_artifacts SET status = %s WHERE artifact_id = %s RETURNING *",
            (status, artifact_id),
        )
        return self._row_to_artifact(row) if row else None

    def create_artifact_manifest(self, manifest: Any) -> Any:
        _require_psycopg()
        sql = """INSERT INTO sandbox_v2_artifact_manifests
            (manifest_id, job_id, record_id, artifact_ids_json, total_size_bytes, artifact_count, sealed, sha256)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"""
        self._execute(sql, (
            manifest.manifest_id, manifest.job_id, manifest.record_id,
            json.dumps(manifest.artifact_ids), manifest.total_size_bytes,
            manifest.artifact_count, manifest.sealed, manifest.sha256,
        ))
        return manifest

    def get_artifact_manifest(self, manifest_id: str) -> Any | None:
        _require_psycopg()
        row = self._fetchone("SELECT * FROM sandbox_v2_artifact_manifests WHERE manifest_id = %s", (manifest_id,))
        return self._row_to_manifest(row) if row else None

    def list_artifact_manifests(self, job_id: str | None = None, record_id: str | None = None,
                                 limit: int = 50) -> list[Any]:
        _require_psycopg()
        if job_id:
            rows = self._fetchall(
                "SELECT * FROM sandbox_v2_artifact_manifests WHERE job_id = %s ORDER BY created_at DESC LIMIT %s",
                (job_id, limit),
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM sandbox_v2_artifact_manifests ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
        return [self._row_to_manifest(r) for r in rows]

    def mark_artifact_expired(self, artifact_id: str) -> Any | None:
        return self.update_artifact_status(artifact_id, "expired")

    def delete_artifact_metadata(self, artifact_id: str) -> bool:
        _require_psycopg()
        cur = self._execute("DELETE FROM sandbox_v2_artifacts WHERE artifact_id = %s", (artifact_id,))
        return cur.rowcount > 0

    # ── Package / Supply Chain ──

    def create_package_request(self, request: Any) -> Any:
        _require_psycopg()
        sql = """INSERT INTO sandbox_v2_package_requests
            (package_request_id, job_id, organization_id, workspace_id, requested_by,
             package_name, package_version, package_manager, source_url, source_type,
             requested_action, expected_sha256, expected_signature, sbom_ref, status, risk_level, reason, metadata_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        self._execute(sql, (
            request.package_request_id, request.job_id, request.organization_id,
            request.workspace_id, request.requested_by, request.package_name,
            request.package_version, request.package_manager, request.source_url,
            request.source_type, request.requested_action, request.expected_sha256,
            request.expected_signature, request.sbom_ref, request.status,
            request.risk_level, request.reason, json.dumps(request.metadata),
        ))
        return request

    def get_package_request(self, package_request_id: str) -> Any | None:
        _require_psycopg()
        row = self._fetchone("SELECT * FROM sandbox_v2_package_requests WHERE package_request_id = %s", (package_request_id,))
        return self._row_to_package_request(row) if row else None

    def list_package_requests(self, job_id: str | None = None, organization_id: str | None = None,
                               workspace_id: str | None = None, status: str | None = None,
                               limit: int = 50) -> list[Any]:
        _require_psycopg()
        sql = "SELECT * FROM sandbox_v2_package_requests WHERE 1=1"
        params: list[Any] = []
        if job_id:
            sql += " AND job_id = %s"; params.append(job_id)
        if organization_id:
            sql += " AND organization_id = %s"; params.append(organization_id)
        if workspace_id:
            sql += " AND workspace_id = %s"; params.append(workspace_id)
        if status:
            sql += " AND status = %s"; params.append(status)
        sql += " ORDER BY created_at DESC LIMIT %s"; params.append(limit)
        return [self._row_to_package_request(r) for r in self._fetchall(sql, tuple(params))]

    def update_package_request_status(self, package_request_id: str, status: str, reason: str = "") -> Any | None:
        _require_psycopg()
        row = self._fetchone(
            "UPDATE sandbox_v2_package_requests SET status = %s, reason = %s WHERE package_request_id = %s RETURNING *",
            (status, reason, package_request_id),
        )
        return self._row_to_package_request(row) if row else None

    def create_quarantine_record(self, record: Any) -> Any:
        _require_psycopg()
        sql = """INSERT INTO sandbox_v2_package_quarantine
            (quarantine_id, package_request_id, job_id, organization_id, workspace_id,
             package_name, package_version, package_manager, storage_key, size_bytes, sha256,
             signature_status, sbom_status, vulnerability_status, status, reason, metadata_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        self._execute(sql, (
            record.quarantine_id, record.package_request_id, record.job_id,
            record.organization_id, record.workspace_id, record.package_name,
            record.package_version, record.package_manager, record.storage_key,
            record.size_bytes, record.sha256, record.signature_status,
            record.sbom_status, record.vulnerability_status, record.status,
            record.reason, json.dumps(record.metadata),
        ))
        return record

    def get_quarantine_record(self, quarantine_id: str) -> Any | None:
        _require_psycopg()
        row = self._fetchone("SELECT * FROM sandbox_v2_package_quarantine WHERE quarantine_id = %s", (quarantine_id,))
        return self._row_to_quarantine(row) if row else None

    def list_quarantine_records(self, package_request_id: str | None = None, status: str | None = None,
                                 limit: int = 50) -> list[Any]:
        _require_psycopg()
        sql = "SELECT * FROM sandbox_v2_package_quarantine WHERE 1=1"
        params: list[Any] = []
        if package_request_id:
            sql += " AND package_request_id = %s"; params.append(package_request_id)
        if status:
            sql += " AND status = %s"; params.append(status)
        sql += " ORDER BY created_at DESC LIMIT %s"; params.append(limit)
        return [self._row_to_quarantine(r) for r in self._fetchall(sql, tuple(params))]

    def update_quarantine_status(self, quarantine_id: str, status: str, reason: str = "") -> Any | None:
        _require_psycopg()
        row = self._fetchone(
            "UPDATE sandbox_v2_package_quarantine SET status = %s, reason = %s WHERE quarantine_id = %s RETURNING *",
            (status, reason, quarantine_id),
        )
        return self._row_to_quarantine(row) if row else None

    # ── SBOM / Scan (stub) ──

    def create_package_sbom(self, sbom: Any) -> Any: return sbom
    def get_package_sbom(self, sbom_id: str) -> Any | None: return None
    def list_package_sboms(self, package_request_id: str | None = None, limit: int = 50) -> list[Any]: return []
    def create_vulnerability_scan_result(self, result: Any) -> Any: return result
    def get_vulnerability_scan_result(self, scan_id: str) -> Any | None: return None
    def list_vulnerability_scan_results(self, package_request_id: str | None = None, limit: int = 50) -> list[Any]: return []

    # ── Network Egress ──

    def create_network_egress_request(self, request: Any) -> Any:
        _require_psycopg()
        sql = """INSERT INTO sandbox_v2_network_egress_requests
            (egress_request_id, job_id, organization_id, workspace_id, requested_by,
             url, scheme, hostname, port, resolved_ips_json, method, purpose, status, risk_level, reason, metadata_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        self._execute(sql, (
            request.egress_request_id, request.job_id, request.organization_id,
            request.workspace_id, request.requested_by, request.url, request.scheme,
            request.hostname, request.port, json.dumps(request.resolved_ips),
            request.method, request.purpose, request.status, request.risk_level,
            request.reason, json.dumps(request.metadata),
        ))
        return request

    def get_network_egress_request(self, egress_request_id: str) -> Any | None:
        _require_psycopg()
        row = self._fetchone("SELECT * FROM sandbox_v2_network_egress_requests WHERE egress_request_id = %s", (egress_request_id,))
        return self._row_to_egress_request(row) if row else None

    def list_network_egress_requests(self, job_id: str | None = None, organization_id: str | None = None,
                                      workspace_id: str | None = None, status: str | None = None,
                                      limit: int = 50) -> list[Any]:
        _require_psycopg()
        sql = "SELECT * FROM sandbox_v2_network_egress_requests WHERE 1=1"
        params: list[Any] = []
        if job_id:
            sql += " AND job_id = %s"; params.append(job_id)
        if organization_id:
            sql += " AND organization_id = %s"; params.append(organization_id)
        if workspace_id:
            sql += " AND workspace_id = %s"; params.append(workspace_id)
        if status:
            sql += " AND status = %s"; params.append(status)
        sql += " ORDER BY requested_at DESC LIMIT %s"; params.append(limit)
        return [self._row_to_egress_request(r) for r in self._fetchall(sql, tuple(params))]

    def update_network_egress_request_status(self, egress_request_id: str, status: str, reason: str = "") -> Any | None:
        _require_psycopg()
        row = self._fetchone(
            "UPDATE sandbox_v2_network_egress_requests SET status = %s, reason = %s WHERE egress_request_id = %s RETURNING *",
            (status, reason, egress_request_id),
        )
        return self._row_to_egress_request(row) if row else None

    def create_network_egress_audit_record(self, record: Any) -> Any:
        _require_psycopg()
        sql = """INSERT INTO sandbox_v2_network_egress_audit
            (audit_id, egress_request_id, job_id, organization_id, workspace_id,
             url, hostname, resolved_ips_json, decision, reason, risk_level, metadata_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        self._execute(sql, (
            record.audit_id, record.egress_request_id, record.job_id,
            record.organization_id, record.workspace_id, record.url, record.hostname,
            json.dumps(record.resolved_ips), record.decision, record.reason,
            record.risk_level, json.dumps(record.metadata),
        ))
        return record

    def get_network_egress_audit_record(self, audit_id: str) -> Any | None:
        _require_psycopg()
        row = self._fetchone("SELECT * FROM sandbox_v2_network_egress_audit WHERE audit_id = %s", (audit_id,))
        return self._row_to_audit(row) if row else None

    def list_network_egress_audit_records(self, egress_request_id: str | None = None,
                                           job_id: str | None = None, limit: int = 50) -> list[Any]:
        _require_psycopg()
        sql = "SELECT * FROM sandbox_v2_network_egress_audit WHERE 1=1"
        params: list[Any] = []
        if egress_request_id:
            sql += " AND egress_request_id = %s"; params.append(egress_request_id)
        if job_id:
            sql += " AND job_id = %s"; params.append(job_id)
        sql += " ORDER BY created_at DESC LIMIT %s"; params.append(limit)
        return [self._row_to_audit(r) for r in self._fetchall(sql, tuple(params))]

    # ── Isolation / Execution ──

    def create_isolation_capability(self, capability: Any) -> Any: return capability
    def get_latest_isolation_capability(self, provider: str | None = None) -> Any | None: return None
    def list_isolation_capabilities(self, provider: str | None = None, limit: int = 50) -> list[Any]: return []
    def create_execution_plan(self, plan: Any) -> Any: return plan
    def get_execution_plan(self, execution_plan_id: str) -> Any | None: return None
    def list_execution_plans(self, job_id: str | None = None, organization_id: str | None = None,
                              workspace_id: str | None = None, status: str | None = None,
                              limit: int = 50) -> list[Any]: return []
    def update_execution_plan_status(self, execution_plan_id: str, status: str, reason: str = "") -> Any | None: return None

    # ── Container Execution ──

    def create_container_execution_plan(self, plan: Any) -> Any: return plan
    def get_container_execution_plan(self, container_plan_id: str) -> Any | None: return None
    def list_container_execution_plans(self, job_id: str | None = None, status: str | None = None, limit: int = 50) -> list[Any]: return []
    def update_container_execution_plan_status(self, container_plan_id: str, status: str, reason: str = "") -> Any | None: return None
    def create_container_execution_result(self, result: Any) -> Any: return result
    def get_container_execution_result(self, container_result_id: str) -> Any | None: return None
    def list_container_execution_results(self, job_id: str | None = None, container_plan_id: str | None = None, limit: int = 50) -> list[Any]: return []

    # ── Kill Switch ──

    def create_kill_request(self, request: Any) -> Any: return request
    def get_kill_request(self, kill_request_id: str) -> Any | None: return None
    def list_kill_requests(self, job_id: str | None = None, status: str | None = None, limit: int = 50) -> list[Any]: return []
    def update_kill_request_status(self, kill_request_id: str, status: str, reason: str = "") -> Any | None: return None
    def create_kill_record(self, record: Any) -> Any: return record
    def get_kill_record(self, kill_record_id: str) -> Any | None: return None
    def list_kill_records(self, job_id: str | None = None, kill_request_id: str | None = None, limit: int = 50) -> list[Any]: return []
    def create_active_execution_handle(self, handle: Any) -> Any: return handle
    def get_active_execution_handle(self, handle_id: str) -> Any | None: return None
    def get_active_execution_handle_for_job(self, job_id: str) -> Any | None: return None
    def list_active_execution_handles(self, status: str | None = None, limit: int = 50) -> list[Any]: return []
    def update_active_execution_handle_status(self, handle_id: str, status: str, reason: str = "") -> Any | None: return None
    def mark_active_execution_cancel_requested(self, handle_id: str, reason: str) -> Any | None: return None

    # ────────────────────────────────────────────────────────────────────
    # Row mappers (内部使用)
    # ────────────────────────────────────────────────────────────────────

    def _row_to_job(self, row: dict[str, Any]) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxJob
        return SandboxJob(
            job_id=row.get("job_id", ""),
            organization_id=row.get("organization_id", ""),
            workspace_id=row.get("workspace_id", ""),
            agent_id=row.get("agent_id", ""),
            requested_by=row.get("requested_by", ""),
            mode=row.get("mode", "simulation"),
            status=row.get("status", "created"),
            requested_action=row.get("requested_action", ""),
            input_ref=row.get("input_ref", ""),
            policy_snapshot=_json_loads(row.get("policy_snapshot_json", "{}")),
            risk_level=row.get("risk_level", "unknown"),
            metadata=_json_loads(row.get("metadata_json", "{}")),
        )

    def _row_to_execution_record(self, row: dict[str, Any]) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxV2ExecutionRecord
        return SandboxV2ExecutionRecord(
            record_id=row.get("record_id", ""),
            job_id=row.get("job_id", ""),
            status=row.get("status", "created"),
            mode=row.get("mode", "simulation"),
            duration_ms=row.get("duration_ms", 0),
            decision=row.get("decision", "deny"),
            reason=row.get("reason", ""),
            no_real_execution=row.get("no_real_execution", True),
            metadata=_json_loads(row.get("metadata_json", "{}")),
        )

    def _row_to_artifact(self, row: dict[str, Any]) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxArtifact
        return SandboxArtifact(
            artifact_id=row.get("artifact_id", ""),
            job_id=row.get("job_id", ""),
            organization_id=row.get("organization_id", ""),
            workspace_id=row.get("workspace_id", ""),
            record_id=row.get("record_id", ""),
            artifact_type=row.get("artifact_type", "unknown"),
            name=row.get("name", ""),
            original_filename=row.get("original_filename", ""),
            safe_filename=row.get("safe_filename", ""),
            storage_key=row.get("storage_key", ""),
            storage_backend=row.get("storage_backend", "local"),
            size_bytes=row.get("size_bytes", 0),
            mime_type=row.get("mime_type", ""),
            sha256=row.get("sha256", ""),
            read_only=row.get("read_only", True),
            status=row.get("status", "pending"),
            risk_level=row.get("risk_level", "unknown"),
        )

    def _row_to_manifest(self, row: dict[str, Any]) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxArtifactManifest
        return SandboxArtifactManifest(
            manifest_id=row.get("manifest_id", ""),
            job_id=row.get("job_id", ""),
            record_id=row.get("record_id", ""),
            artifact_ids=_json_loads(row.get("artifact_ids_json", "[]")),
            total_size_bytes=row.get("total_size_bytes", 0),
            artifact_count=row.get("artifact_count", 0),
            sealed=row.get("sealed", False),
            sha256=row.get("sha256", ""),
        )

    def _row_to_package_request(self, row: dict[str, Any]) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxPackageRequest
        return SandboxPackageRequest(
            package_request_id=row.get("package_request_id", ""),
            job_id=row.get("job_id", ""),
            organization_id=row.get("organization_id", ""),
            workspace_id=row.get("workspace_id", ""),
            requested_by=row.get("requested_by", ""),
            package_name=row.get("package_name", ""),
            package_version=row.get("package_version", ""),
            package_manager=row.get("package_manager", "unknown"),
            source_url=row.get("source_url", ""),
            source_type=row.get("source_type", "unknown"),
            requested_action=row.get("requested_action", ""),
            expected_sha256=row.get("expected_sha256", ""),
            expected_signature=row.get("expected_signature", ""),
            sbom_ref=row.get("sbom_ref", ""),
            status=row.get("status", "requested"),
            risk_level=row.get("risk_level", "unknown"),
            reason=row.get("reason", ""),
            metadata=_json_loads(row.get("metadata_json", "{}")),
        )

    def _row_to_quarantine(self, row: dict[str, Any]) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxPackageQuarantineRecord
        return SandboxPackageQuarantineRecord(
            quarantine_id=row.get("quarantine_id", ""),
            package_request_id=row.get("package_request_id", ""),
            job_id=row.get("job_id", ""),
            organization_id=row.get("organization_id", ""),
            workspace_id=row.get("workspace_id", ""),
            package_name=row.get("package_name", ""),
            package_version=row.get("package_version", ""),
            package_manager=row.get("package_manager", "unknown"),
            storage_key=row.get("storage_key", ""),
            size_bytes=row.get("size_bytes", 0),
            sha256=row.get("sha256", ""),
            signature_status=row.get("signature_status", "not_provided"),
            sbom_status=row.get("sbom_status", "not_provided"),
            vulnerability_status=row.get("vulnerability_status", "not_scanned"),
            status=row.get("status", "quarantined"),
            reason=row.get("reason", ""),
            metadata=_json_loads(row.get("metadata_json", "{}")),
        )

    def _row_to_egress_request(self, row: dict[str, Any]) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxNetworkEgressRequest
        return SandboxNetworkEgressRequest(
            egress_request_id=row.get("egress_request_id", ""),
            job_id=row.get("job_id", ""),
            organization_id=row.get("organization_id", ""),
            workspace_id=row.get("workspace_id", ""),
            requested_by=row.get("requested_by", ""),
            url=row.get("url", ""),
            scheme=row.get("scheme", ""),
            hostname=row.get("hostname", ""),
            port=row.get("port", 443),
            resolved_ips=_json_loads(row.get("resolved_ips_json", "[]")),
            method=row.get("method", "GET"),
            purpose=row.get("purpose", ""),
            status=row.get("status", "pending"),
            risk_level=row.get("risk_level", "unknown"),
            reason=row.get("reason", ""),
            metadata=_json_loads(row.get("metadata_json", "{}")),
        )

    def _row_to_audit(self, row: dict[str, Any]) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxNetworkEgressAuditRecord
        return SandboxNetworkEgressAuditRecord(
            audit_id=row.get("audit_id", ""),
            egress_request_id=row.get("egress_request_id", ""),
            job_id=row.get("job_id", ""),
            organization_id=row.get("organization_id", ""),
            workspace_id=row.get("workspace_id", ""),
            url=row.get("url", ""),
            hostname=row.get("hostname", ""),
            resolved_ips=_json_loads(row.get("resolved_ips_json", "[]")),
            decision=row.get("decision", ""),
            reason=row.get("reason", ""),
            risk_level=row.get("risk_level", ""),
            metadata=_json_loads(row.get("metadata_json", "{}")),
        )


def _json_loads(val: Any) -> Any:
    """安全 json.loads，对 str 执行，其他类型直接返回。"""
    if isinstance(val, str) and val:
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    if isinstance(val, (list, dict)):
        return val
    return {} if val is None else val
