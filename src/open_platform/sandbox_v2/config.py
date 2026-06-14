"""Sandbox v2 Production Configuration — 从环境变量读取。

设计原则：
1. 所有默认值遵循 fail-closed 安全原则。
2. 危险能力默认关闭，需要显式环境变量开启。
3. 轻量级，不依赖 pydantic_settings 避免引入重依赖。
4. 独立于项目全局 Settings，不破坏现有代码。
5. 可被 service / readiness / check script 逐步接入。

Step 10 — Production Configuration Layer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool) -> bool:
    """读取布尔型环境变量。true/1/yes → True, false/0/no/空 → False。"""
    val = os.getenv(name, "").strip().lower()
    if val in ("true", "1", "yes"):
        return True
    if val in ("false", "0", "no"):
        return False
    return default


def _env_int(name: str, default: int) -> int:
    """读取整型环境变量。"""
    val = os.getenv(name, "").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_list(name: str, default: list[str] | None = None) -> list[str]:
    """读取逗号分隔的列表环境变量。"""
    val = os.getenv(name, "").strip()
    if not val:
        return default if default is not None else []
    return [item.strip() for item in val.split(",") if item.strip()]


def _env_str(name: str, default: str) -> str:
    """读取字符串环境变量。"""
    val = os.getenv(name, "").strip()
    return val if val else default


@dataclass
class SandboxV2Settings:
    """Sandbox v2 生产化配置。

    所有字段默认值严格遵循 fail-closed 安全原则。
    危险能力必须显式设置环境变量为 "true" 才能开启。
    """

    # ── Core ──
    enabled: bool = True
    mode: str = "simulation"             # simulation | trusted_fixture | metadata_only
    default_action: str = "deny"         # deny | allow
    fail_closed: bool = True

    # ── Artifact ──
    artifact_root: str = ".sandbox_v2_artifacts"
    max_artifact_bytes: int = 1_048_576          # 1 MB
    max_job_artifact_bytes: int = 10_485_760     # 10 MB
    read_only_artifacts: bool = True

    # ── Package ──
    package_quarantine_root: str = ".sandbox_v2_package_quarantine"
    package_download_enabled: bool = False
    public_registry_enabled: bool = False
    package_installation_enabled: bool = False
    require_package_hash: bool = True
    require_package_signature: bool = True
    require_sbom: bool = True

    # ── Network ──
    network_enabled: bool = False
    network_preflight_only: bool = True
    block_private_networks: bool = True
    block_metadata_service: bool = True
    allowed_domains: list[str] = field(default_factory=list)
    denied_domains: list[str] = field(default_factory=lambda: [
        "localhost", "127.0.0.1", "169.254.169.254"
    ])

    # ── Container ──
    container_execution_enabled: bool = False
    run_container_integration: bool = False
    allowed_images: list[str] = field(default_factory=lambda: [
        "python:3.11-alpine", "busybox:latest"
    ])
    auto_pull_images: bool = False
    user_command_execution: bool = False
    user_image_execution: bool = False

    # ── Kill Switch ──
    kill_switch_enabled: bool = True
    arbitrary_pid_kill: bool = False
    container_kill_enabled: bool = False

    # ── Queue / Worker ──
    queue_backend: str = "sqlite"            # sqlite | redis | celery
    worker_enabled: bool = True
    worker_max_attempts: int = 3
    worker_lease_seconds: int = 60

    # ── MicroVM / Firecracker (Step 11) ──
    microvm_execution_enabled: bool = False
    run_microvm_integration: bool = False
    firecracker_bin_path: str = ""
    firecracker_kernel_path: str = ""
    firecracker_rootfs_path: str = ""
    firecracker_jailer_enabled: bool = False
    microvm_network_enabled: bool = False
    microvm_max_memory_mb: int = 128
    microvm_vcpu_count: int = 1
    microvm_timeout_seconds: int = 10
    microvm_allow_user_kernel: bool = False
    microvm_allow_user_rootfs: bool = False
    microvm_allow_host_mounts: bool = False

    # ── Future Production Backends ──
    run_backend_integration: bool = False     # Step 13 — 真实集成测试开关
    database_backend: str = "sqlite"         # sqlite | postgres
    postgres_dsn: str = ""                   # postgresql://user:pass@host:5432/db
    redis_url: str = ""
    object_storage_backend: str = "local"    # local | s3 | minio
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "sandbox-v2-artifacts"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "sandbox-v2-artifacts"
    s3_region: str = "us-east-1"
    storage_prefix: str = ""                 # object key prefix (e.g. "sandbox-v2/prod")

    # ── Observability (Step 18) ──
    observability_enabled: bool = False
    prometheus_export_enabled: bool = True
    prometheus_scrape_path: str = "/api/runtime/sandbox-v2/monitoring/metrics/prometheus"
    grafana_dashboard_enabled: bool = False
    otel_enabled: bool = False
    otel_exporter: str = "disabled"
    otel_endpoint: str = ""
    otel_service_name: str = "sandbox-v2"
    otel_traces_enabled: bool = False
    otel_metrics_enabled: bool = False
    otel_logs_enabled: bool = False
    otel_export_interval_seconds: int = 60
    otel_include_sensitive_attributes: bool = False
    observability_safe_mode: bool = True
    run_observability_integration: bool = False

    # ── IAM / SSO (Step 17) ──
    iam_enabled: bool = False
    sso_enabled: bool = False
    iam_provider: str = "disabled"
    oidc_enabled: bool = False
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_jwks_uri: str = ""
    oidc_discovery_enabled: bool = False
    saml_enabled: bool = False
    saml_entity_id: str = ""
    saml_metadata_path: str = ""
    saml_metadata_url: str = ""
    saml_metadata_download_enabled: bool = False
    iam_jit_provisioning: bool = False
    iam_default_role: str = "viewer"
    iam_allowed_domains: list[str] = field(default_factory=list)
    iam_require_verified_email: bool = True
    iam_external_group_mapping_enabled: bool = False
    run_iam_integration: bool = False

    # ── Load Testing / SLO (Step 19) ──
    load_testing_enabled: bool = False
    run_staging_load_test: bool = False
    staging_base_url: str = ""
    staging_auth_mode: str = "none"
    staging_api_token: str = ""
    load_test_profile: str = "smoke"
    load_test_max_users: int = 5
    load_test_max_rps: int = 5
    load_test_duration_seconds: int = 30
    load_test_timeout_seconds: int = 5
    load_test_targets: list[str] = field(default_factory=lambda: ["readiness", "metrics", "network_preflight"])
    load_test_output_dir: str = ".sandbox_v2_load_reports"
    load_test_allow_production: bool = False
    load_test_require_confirmation: bool = True
    slo_p95_ms: int = 500
    slo_p99_ms: int = 1500
    slo_error_rate_percent: float = 1.0
    slo_availability_percent: float = 99.0

    # ── Performance / Capacity (Step 16) ──
    perf_tests_enabled: bool = False
    run_performance_benchmarks: bool = False
    perf_profile: str = "small"
    perf_max_jobs: int = 100
    perf_max_queue_items: int = 100
    perf_max_artifacts: int = 50
    perf_max_concurrency: int = 4
    perf_timeout_seconds: int = 60
    perf_cleanup_after_run: bool = True
    perf_output_dir: str = ".sandbox_v2_perf_reports"

    def is_safe_default(self) -> bool:
        """验证当前配置是否处于安全默认状态。"""
        return (
            self.fail_closed
            and not self.network_enabled
            and not self.package_download_enabled
            and not self.package_installation_enabled
            and not self.container_execution_enabled
            and not self.user_command_execution
            and not self.user_image_execution
            and not self.arbitrary_pid_kill
            and not self.auto_pull_images
            and not self.public_registry_enabled
            and not self.microvm_execution_enabled
            and not self.microvm_network_enabled
            and not self.microvm_allow_user_kernel
            and not self.microvm_allow_user_rootfs
            and not self.microvm_allow_host_mounts
            and not self.run_performance_benchmarks
            and not self.iam_enabled
            and not self.sso_enabled
            and not self.oidc_discovery_enabled
            and not self.saml_metadata_download_enabled
            and not self.run_iam_integration
            and not self.run_observability_integration
            and not self.otel_enabled
            and not self.run_staging_load_test
            and not self.load_testing_enabled
        )

    def production_blockers(self) -> list[str]:
        """返回当前配置中的生产阻塞项。"""
        blockers: list[str] = []
        if not self.fail_closed:
            blockers.append("fail_closed is false — must be true for production")
        if self.network_enabled:
            blockers.append("network_enabled is true — must be false unless audited and approved")
        if not self.network_preflight_only:
            blockers.append("network_preflight_only is false — production must be preflight-only")
        if self.package_download_enabled:
            blockers.append("package_download_enabled is true — must be false unless audited and approved")
        if self.package_installation_enabled:
            blockers.append("package_installation_enabled is true — must be false unless audited and approved")
        if self.public_registry_enabled:
            blockers.append("public_registry_enabled is true — must be false for production")
        if self.container_execution_enabled:
            blockers.append(
                "container_execution_enabled is true — requires Linux + red-team pass + "
                "rootless verification + security audit"
            )
        if self.user_command_execution:
            blockers.append("user_command_execution is true — MUST be false for production")
        if self.user_image_execution:
            blockers.append("user_image_execution is true — MUST be false for production")
        if self.arbitrary_pid_kill:
            blockers.append("arbitrary_pid_kill is true — MUST be false for production")
        if self.auto_pull_images:
            blockers.append("auto_pull_images is true — must be false; images must be pre-pulled and audited")
        if not self.read_only_artifacts:
            blockers.append("read_only_artifacts is false — must be true for production")
        if self.microvm_execution_enabled:
            blockers.append(
                "microvm_execution_enabled is true — requires Linux+KVM+Firecracker+kernel+rootfs + "
                "security audit. Must be false by default."
            )
        if self.microvm_network_enabled:
            blockers.append("microvm_network_enabled is true — must be false for production")
        if self.microvm_allow_user_kernel:
            blockers.append("microvm_allow_user_kernel is true — MUST be false for production")
        if self.microvm_allow_user_rootfs:
            blockers.append("microvm_allow_user_rootfs is true — MUST be false for production")
        if self.microvm_allow_host_mounts:
            blockers.append("microvm_allow_host_mounts is true — MUST be false for production")
        if self.run_performance_benchmarks and self.perf_profile == "large":
            blockers.append(
                "run_performance_benchmarks with large profile is enabled - "
                "only use after explicit capacity-plan approval"
            )
        if self.iam_provider not in ("disabled", "mock", "oidc", "saml"):
            blockers.append(f"iam_provider={self.iam_provider} is invalid — must be disabled|mock|oidc|saml")
        if self.run_iam_integration and not self.iam_enabled:
            blockers.append("run_iam_integration=true but iam_enabled=false — must enable IAM first")
        if self.sso_enabled and not self.iam_enabled:
            blockers.append("sso_enabled=true but iam_enabled=false — must enable IAM first")
        if self.oidc_enabled and self.iam_provider != "oidc":
            blockers.append("oidc_enabled=true but iam_provider is not 'oidc'")
        if self.saml_enabled and self.iam_provider != "saml":
            blockers.append("saml_enabled=true but iam_provider is not 'saml'")
        if self.oidc_discovery_enabled:
            blockers.append("oidc_discovery_enabled=true — must be false; no external network calls allowed")
        if self.saml_metadata_download_enabled:
            blockers.append("saml_metadata_download_enabled=true — must be false; no external network calls allowed")
        if self.otel_enabled and self.otel_exporter not in ("disabled", "mock", "otlp_http"):
            blockers.append(f"otel_exporter={self.otel_exporter} is invalid — must be disabled|mock|otlp_http")
        if self.otel_enabled and self.otel_include_sensitive_attributes:
            blockers.append("otel_include_sensitive_attributes=true — must be false for production")
        if self.run_observability_integration and not self.observability_enabled:
            blockers.append("run_observability_integration=true but observability_enabled=false")
        if self.run_staging_load_test and self.load_test_allow_production:
            blockers.append("run_staging_load_test=true AND load_test_allow_production=true — must NOT target production")
        if self.run_staging_load_test and not self.staging_base_url:
            blockers.append("run_staging_load_test=true but staging_base_url is empty")
        if self.load_test_max_users > 10:
            blockers.append(f"load_test_max_users={self.load_test_max_users} exceeds safe limit (10)")
        if self.load_test_max_rps > 10:
            blockers.append(f"load_test_max_rps={self.load_test_max_rps} exceeds safe limit (10)")
        if self.load_test_duration_seconds > 120:
            blockers.append(f"load_test_duration_seconds={self.load_test_duration_seconds} exceeds safe limit (120)")
        return blockers

    def backend_blockers(self) -> list[str]:
        """返回当前配置中的后端阻塞项。

        如果用户显式选择了 postgres/redis/minio 但缺配置，则为 blocker。
        如果默认 SQLite/local，则无 blocker。
        """
        blockers: list[str] = []
        if self.database_backend == "postgres" and not self.postgres_dsn:
            blockers.append(
                "database_backend=postgres but SANDBOX_V2_POSTGRES_DSN is empty — "
                "must provide connection string"
            )
        if self.queue_backend == "redis" and not self.redis_url:
            blockers.append(
                "queue_backend=redis but SANDBOX_V2_REDIS_URL is empty — "
                "must provide Redis connection URL"
            )
        if self.object_storage_backend in ("minio", "s3"):
            if self.object_storage_backend == "minio":
                endpoint = self.minio_endpoint
                access_key = self.minio_access_key
                secret_key = self.minio_secret_key
                bucket = self.minio_bucket
                if not endpoint:
                    blockers.append(
                        "object_storage_backend=minio but SANDBOX_V2_MINIO_ENDPOINT is empty"
                    )
            else:
                endpoint = ""  # S3 uses AWS default endpoint
                access_key = self.s3_access_key
                secret_key = self.s3_secret_key
                bucket = self.s3_bucket

            missing = []
            if not access_key:
                key_env = "SANDBOX_V2_MINIO_ACCESS_KEY" if self.object_storage_backend == "minio" else "SANDBOX_V2_S3_ACCESS_KEY"
                missing.append(f"access key ({key_env})")
            if not secret_key:
                key_env = "SANDBOX_V2_MINIO_SECRET_KEY" if self.object_storage_backend == "minio" else "SANDBOX_V2_S3_SECRET_KEY"
                missing.append(f"secret key ({key_env})")
            if not bucket:
                key_env = "SANDBOX_V2_MINIO_BUCKET" if self.object_storage_backend == "minio" else "SANDBOX_V2_S3_BUCKET"
                missing.append(f"bucket ({key_env})")
            if missing:
                blockers.append(
                    f"object_storage_backend={self.object_storage_backend} but missing: {', '.join(missing)}"
                )
        return blockers

    def backend_warnings(self) -> list[str]:
        """返回当前配置中的后端警告项。"""
        warns: list[str] = []
        if self.database_backend == "sqlite":
            warns.append("Database backend is sqlite — consider PostgreSQL for production")
        if self.queue_backend == "sqlite":
            warns.append("Queue backend is sqlite (single-node) — consider Redis for distributed workers")
        if self.object_storage_backend == "local":
            warns.append("Object storage backend is local — consider MinIO/S3 for production")
        return warns

    def warnings(self) -> list[str]:
        """返回当前配置中的警告项。"""
        warns: list[str] = []
        warns.extend(self.backend_warnings())
        if not self.redis_url:
            warns.append("SANDBOX_V2_REDIS_URL not configured — needed for production queue backend")
        if not self.require_package_hash:
            warns.append("require_package_hash is false — should be true")
        if not self.require_package_signature:
            warns.append("require_package_signature is false — should be true")
        if not self.require_sbom:
            warns.append("require_sbom is false — should be true")
        if not self.perf_tests_enabled:
            warns.append("Sandbox v2 performance tests are disabled by default")
        if self.perf_profile not in {"smoke", "small", "medium", "large", "custom"}:
            warns.append("SANDBOX_V2_PERF_PROFILE is invalid - expected smoke/small/medium/large/custom")
        if self.iam_enabled and self.iam_default_role not in ("viewer", "auditor", "developer", "operator"):
            warns.append(f"IAM default_role={self.iam_default_role} is elevated — should be 'viewer' or 'auditor'")
        if self.iam_enabled and not self.iam_require_verified_email:
            warns.append("iam_require_verified_email=false — should be true for production")
        if self.iam_enabled and self.iam_jit_provisioning:
            warns.append("iam_jit_provisioning=true — JIT provisioning is not yet production-hardened")
        if self.iam_enabled and not self.iam_allowed_domains:
            warns.append("iam_allowed_domains is empty — all email domains will be denied when IAM enabled")
        if self.observability_enabled and not self.prometheus_export_enabled:
            warns.append("observability_enabled=true but prometheus_export_enabled=false")
        if self.otel_enabled:
            warns.append("otel_enabled=true — real external telemetry export not yet implemented (Step 18)")
        if self.run_staging_load_test:
            warns.append("run_staging_load_test=true — staging load test will make HTTP requests to configured staging URL")
        if self.load_test_duration_seconds > 30:
            warns.append("load_test_duration_seconds > 30 — consider shorter smoke tests first")
        return warns

    def recommended_next_steps(self) -> list[str]:
        """根据当前配置状态推荐下一步。"""
        steps: list[str] = []
        if self.database_backend == "sqlite":
            steps.append("Set up PostgreSQL and migrate database (Step 12)")
        if self.queue_backend == "sqlite":
            steps.append("Set up Redis and migrate queue backend (Step 12)")
        if self.object_storage_backend == "local":
            steps.append("Set up MinIO/S3 for artifact storage (Step 12)")
        if not self.container_execution_enabled:
            steps.append(
                "Complete Linux/WSL2 rootless container verification "
                "before enabling container_execution_enabled"
            )
        steps.append("Run red-team tests on target deployment environment")
        steps.append("Run production readiness script: python scripts/check_sandbox_v2_production_readiness.py")
        return steps


def load_sandbox_v2_settings() -> SandboxV2Settings:
    """从环境变量加载 Sandbox v2 配置。

    所有危险能力默认关闭。必须显式设置环境变量为 "true" 才能开启。
    """
    return SandboxV2Settings(
        # Core
        enabled=_env_bool("SANDBOX_V2_ENABLED", True),
        mode=_env_str("SANDBOX_V2_MODE", "simulation"),
        default_action=_env_str("SANDBOX_V2_DEFAULT_ACTION", "deny"),
        fail_closed=_env_bool("SANDBOX_V2_FAIL_CLOSED", True),

        # Artifact
        artifact_root=_env_str("SANDBOX_V2_ARTIFACT_ROOT", ".sandbox_v2_artifacts"),
        max_artifact_bytes=_env_int("SANDBOX_V2_MAX_ARTIFACT_BYTES", 1_048_576),
        max_job_artifact_bytes=_env_int("SANDBOX_V2_MAX_JOB_ARTIFACT_BYTES", 10_485_760),
        read_only_artifacts=_env_bool("SANDBOX_V2_READ_ONLY_ARTIFACTS", True),

        # Package
        package_quarantine_root=_env_str("SANDBOX_V2_PACKAGE_QUARANTINE_ROOT", ".sandbox_v2_package_quarantine"),
        package_download_enabled=_env_bool("SANDBOX_V2_PACKAGE_DOWNLOAD_ENABLED", False),
        public_registry_enabled=_env_bool("SANDBOX_V2_PUBLIC_REGISTRY_ENABLED", False),
        package_installation_enabled=_env_bool("SANDBOX_V2_PACKAGE_INSTALLATION_ENABLED", False),
        require_package_hash=_env_bool("SANDBOX_V2_REQUIRE_PACKAGE_HASH", True),
        require_package_signature=_env_bool("SANDBOX_V2_REQUIRE_PACKAGE_SIGNATURE", True),
        require_sbom=_env_bool("SANDBOX_V2_REQUIRE_SBOM", True),

        # Network
        network_enabled=_env_bool("SANDBOX_V2_NETWORK_ENABLED", False),
        network_preflight_only=_env_bool("SANDBOX_V2_NETWORK_PREFLIGHT_ONLY", True),
        block_private_networks=_env_bool("SANDBOX_V2_BLOCK_PRIVATE_NETWORKS", True),
        block_metadata_service=_env_bool("SANDBOX_V2_BLOCK_METADATA_SERVICE", True),
        allowed_domains=_env_list("SANDBOX_V2_ALLOWED_DOMAINS", []),
        denied_domains=_env_list("SANDBOX_V2_DENIED_DOMAINS", ["localhost", "127.0.0.1", "169.254.169.254"]),

        # Container
        container_execution_enabled=_env_bool("SANDBOX_V2_CONTAINER_EXECUTION_ENABLED", False),
        run_container_integration=_env_bool("SANDBOX_V2_RUN_CONTAINER_INTEGRATION", False),
        allowed_images=_env_list("SANDBOX_V2_ALLOWED_IMAGES", ["python:3.11-alpine", "busybox:latest"]),
        auto_pull_images=_env_bool("SANDBOX_V2_AUTO_PULL_IMAGES", False),
        user_command_execution=_env_bool("SANDBOX_V2_USER_COMMAND_EXECUTION", False),
        user_image_execution=_env_bool("SANDBOX_V2_USER_IMAGE_EXECUTION", False),

        # MicroVM / Firecracker
        microvm_execution_enabled=_env_bool("SANDBOX_V2_MICROVM_EXECUTION_ENABLED", False),
        run_microvm_integration=_env_bool("SANDBOX_V2_RUN_MICROVM_INTEGRATION", False),
        firecracker_bin_path=_env_str("SANDBOX_V2_FIRECRACKER_BIN_PATH", ""),
        firecracker_kernel_path=_env_str("SANDBOX_V2_FIRECRACKER_KERNEL_PATH", ""),
        firecracker_rootfs_path=_env_str("SANDBOX_V2_FIRECRACKER_ROOTFS_PATH", ""),
        firecracker_jailer_enabled=_env_bool("SANDBOX_V2_FIRECRACKER_JAILER_ENABLED", False),
        microvm_network_enabled=_env_bool("SANDBOX_V2_MICROVM_NETWORK_ENABLED", False),
        microvm_max_memory_mb=_env_int("SANDBOX_V2_MICROVM_MAX_MEMORY_MB", 128),
        microvm_vcpu_count=_env_int("SANDBOX_V2_MICROVM_VCPU_COUNT", 1),
        microvm_timeout_seconds=_env_int("SANDBOX_V2_MICROVM_TIMEOUT_SECONDS", 10),
        microvm_allow_user_kernel=_env_bool("SANDBOX_V2_MICROVM_ALLOW_USER_KERNEL", False),
        microvm_allow_user_rootfs=_env_bool("SANDBOX_V2_MICROVM_ALLOW_USER_ROOTFS", False),
        microvm_allow_host_mounts=_env_bool("SANDBOX_V2_MICROVM_ALLOW_HOST_MOUNTS", False),

        # Kill Switch
        kill_switch_enabled=_env_bool("SANDBOX_V2_KILL_SWITCH_ENABLED", True),
        arbitrary_pid_kill=_env_bool("SANDBOX_V2_ARBITRARY_PID_KILL", False),
        container_kill_enabled=_env_bool("SANDBOX_V2_CONTAINER_KILL_ENABLED", False),

        # Queue / Worker
        queue_backend=_env_str("SANDBOX_V2_QUEUE_BACKEND", "sqlite"),
        worker_enabled=_env_bool("SANDBOX_V2_WORKER_ENABLED", True),
        worker_max_attempts=_env_int("SANDBOX_V2_WORKER_MAX_ATTEMPTS", 3),
        worker_lease_seconds=_env_int("SANDBOX_V2_WORKER_LEASE_SECONDS", 60),

        # Future Production Backends
        run_backend_integration=_env_bool("SANDBOX_V2_RUN_BACKEND_INTEGRATION", False),
        database_backend=_env_str("SANDBOX_V2_DATABASE_BACKEND", "sqlite"),
        postgres_dsn=_env_str("SANDBOX_V2_POSTGRES_DSN", ""),
        redis_url=_env_str("SANDBOX_V2_REDIS_URL", ""),
        object_storage_backend=_env_str("SANDBOX_V2_OBJECT_STORAGE_BACKEND", "local"),
        minio_endpoint=_env_str("SANDBOX_V2_MINIO_ENDPOINT", ""),
        minio_access_key=_env_str("SANDBOX_V2_MINIO_ACCESS_KEY", ""),
        minio_secret_key=_env_str("SANDBOX_V2_MINIO_SECRET_KEY", ""),
        minio_bucket=_env_str("SANDBOX_V2_MINIO_BUCKET", "sandbox-v2-artifacts"),
        s3_access_key=_env_str("SANDBOX_V2_S3_ACCESS_KEY", ""),
        s3_secret_key=_env_str("SANDBOX_V2_S3_SECRET_KEY", ""),
        s3_bucket=_env_str("SANDBOX_V2_S3_BUCKET", "sandbox-v2-artifacts"),
        s3_region=_env_str("SANDBOX_V2_S3_REGION", "us-east-1"),
        storage_prefix=_env_str("SANDBOX_V2_STORAGE_PREFIX", ""),

        # Performance / Capacity
        perf_tests_enabled=_env_bool("SANDBOX_V2_PERF_TESTS_ENABLED", False),
        run_performance_benchmarks=_env_bool("SANDBOX_V2_RUN_PERFORMANCE_BENCHMARKS", False),
        perf_profile=_env_str("SANDBOX_V2_PERF_PROFILE", "small"),
        perf_max_jobs=_env_int("SANDBOX_V2_PERF_MAX_JOBS", 100),
        perf_max_queue_items=_env_int("SANDBOX_V2_PERF_MAX_QUEUE_ITEMS", 100),
        perf_max_artifacts=_env_int("SANDBOX_V2_PERF_MAX_ARTIFACTS", 50),
        perf_max_concurrency=_env_int("SANDBOX_V2_PERF_MAX_CONCURRENCY", 4),
        perf_timeout_seconds=_env_int("SANDBOX_V2_PERF_TIMEOUT_SECONDS", 60),
        perf_cleanup_after_run=_env_bool("SANDBOX_V2_PERF_CLEANUP_AFTER_RUN", True),
        perf_output_dir=_env_str("SANDBOX_V2_PERF_OUTPUT_DIR", ".sandbox_v2_perf_reports"),

        # IAM / SSO (Step 17)
        iam_enabled=_env_bool("SANDBOX_V2_IAM_ENABLED", False),
        sso_enabled=_env_bool("SANDBOX_V2_SSO_ENABLED", False),
        iam_provider=_env_str("SANDBOX_V2_IAM_PROVIDER", "disabled"),
        oidc_enabled=_env_bool("SANDBOX_V2_OIDC_ENABLED", False),
        oidc_issuer=_env_str("SANDBOX_V2_OIDC_ISSUER", ""),
        oidc_client_id=_env_str("SANDBOX_V2_OIDC_CLIENT_ID", ""),
        oidc_client_secret=_env_str("SANDBOX_V2_OIDC_CLIENT_SECRET", ""),
        oidc_jwks_uri=_env_str("SANDBOX_V2_OIDC_JWKS_URI", ""),
        oidc_discovery_enabled=_env_bool("SANDBOX_V2_OIDC_DISCOVERY_ENABLED", False),
        saml_enabled=_env_bool("SANDBOX_V2_SAML_ENABLED", False),
        saml_entity_id=_env_str("SANDBOX_V2_SAML_ENTITY_ID", ""),
        saml_metadata_path=_env_str("SANDBOX_V2_SAML_METADATA_PATH", ""),
        saml_metadata_url=_env_str("SANDBOX_V2_SAML_METADATA_URL", ""),
        saml_metadata_download_enabled=_env_bool("SANDBOX_V2_SAML_METADATA_DOWNLOAD_ENABLED", False),
        iam_jit_provisioning=_env_bool("SANDBOX_V2_IAM_JIT_PROVISIONING", False),
        iam_default_role=_env_str("SANDBOX_V2_IAM_DEFAULT_ROLE", "viewer"),
        iam_allowed_domains=_env_list("SANDBOX_V2_IAM_ALLOWED_DOMAINS", []),
        iam_require_verified_email=_env_bool("SANDBOX_V2_IAM_REQUIRE_VERIFIED_EMAIL", True),
        iam_external_group_mapping_enabled=_env_bool("SANDBOX_V2_IAM_EXTERNAL_GROUP_MAPPING_ENABLED", False),
        run_iam_integration=_env_bool("SANDBOX_V2_RUN_IAM_INTEGRATION", False),

        # Observability (Step 18)
        observability_enabled=_env_bool("SANDBOX_V2_OBSERVABILITY_ENABLED", False),
        prometheus_export_enabled=_env_bool("SANDBOX_V2_PROMETHEUS_EXPORT_ENABLED", True),
        prometheus_scrape_path=_env_str("SANDBOX_V2_PROMETHEUS_SCRAPE_PATH", "/api/runtime/sandbox-v2/monitoring/metrics/prometheus"),
        grafana_dashboard_enabled=_env_bool("SANDBOX_V2_GRAFANA_DASHBOARD_ENABLED", False),
        otel_enabled=_env_bool("SANDBOX_V2_OTEL_ENABLED", False),
        otel_exporter=_env_str("SANDBOX_V2_OTEL_EXPORTER", "disabled"),
        otel_endpoint=_env_str("SANDBOX_V2_OTEL_ENDPOINT", ""),
        otel_service_name=_env_str("SANDBOX_V2_OTEL_SERVICE_NAME", "sandbox-v2"),
        otel_traces_enabled=_env_bool("SANDBOX_V2_OTEL_TRACES_ENABLED", False),
        otel_metrics_enabled=_env_bool("SANDBOX_V2_OTEL_METRICS_ENABLED", False),
        otel_logs_enabled=_env_bool("SANDBOX_V2_OTEL_LOGS_ENABLED", False),
        otel_export_interval_seconds=_env_int("SANDBOX_V2_OTEL_EXPORT_INTERVAL_SECONDS", 60),
        otel_include_sensitive_attributes=_env_bool("SANDBOX_V2_OTEL_INCLUDE_SENSITIVE_ATTRIBUTES", False),
        observability_safe_mode=_env_bool("SANDBOX_V2_OBSERVABILITY_SAFE_MODE", True),
        run_observability_integration=_env_bool("SANDBOX_V2_RUN_OBSERVABILITY_INTEGRATION", False),

        # Load Testing / SLO (Step 19)
        load_testing_enabled=_env_bool("SANDBOX_V2_LOAD_TESTING_ENABLED", False),
        run_staging_load_test=_env_bool("SANDBOX_V2_RUN_STAGING_LOAD_TEST", False),
        staging_base_url=_env_str("SANDBOX_V2_STAGING_BASE_URL", ""),
        staging_auth_mode=_env_str("SANDBOX_V2_STAGING_AUTH_MODE", "none"),
        staging_api_token=_env_str("SANDBOX_V2_STAGING_API_TOKEN", ""),
        load_test_profile=_env_str("SANDBOX_V2_LOAD_TEST_PROFILE", "smoke"),
        load_test_max_users=_env_int("SANDBOX_V2_LOAD_TEST_MAX_USERS", 5),
        load_test_max_rps=_env_int("SANDBOX_V2_LOAD_TEST_MAX_RPS", 5),
        load_test_duration_seconds=_env_int("SANDBOX_V2_LOAD_TEST_DURATION_SECONDS", 30),
        load_test_timeout_seconds=_env_int("SANDBOX_V2_LOAD_TEST_TIMEOUT_SECONDS", 5),
        load_test_targets=_env_list("SANDBOX_V2_LOAD_TEST_TARGETS", ["readiness", "metrics", "network_preflight"]),
        load_test_output_dir=_env_str("SANDBOX_V2_LOAD_TEST_OUTPUT_DIR", ".sandbox_v2_load_reports"),
        load_test_allow_production=_env_bool("SANDBOX_V2_LOAD_TEST_ALLOW_PRODUCTION", False),
        load_test_require_confirmation=_env_bool("SANDBOX_V2_LOAD_TEST_REQUIRE_CONFIRMATION", True),
        slo_p95_ms=int(float(_env_str("SANDBOX_V2_SLO_P95_MS", "500"))),
        slo_p99_ms=int(float(_env_str("SANDBOX_V2_SLO_P99_MS", "1500"))),
        slo_error_rate_percent=float(_env_str("SANDBOX_V2_SLO_ERROR_RATE_PERCENT", "1.0")),
        slo_availability_percent=float(_env_str("SANDBOX_V2_SLO_AVAILABILITY_PERCENT", "99.0")),
    )
