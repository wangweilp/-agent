"""SandboxPolicy → WorkerPolicyConfig 翻译器。

Step 24-F: fail-closed policy enforcement translator.
- no_execution/simulation_only: config生成但不执行
- restricted: 需要 worker support，否则fail closed
- isolated: fail closed (unsupported)
- 不执行 / 不联网 / 不读文件 / 不读 secrets
"""

from __future__ import annotations

import ipaddress, logging
from datetime import datetime, timezone
from typing import Any

from src.open_platform.sandbox_policy import SandboxLevel
from src.open_platform.policy_enforcement import (
    DataAccessMode, DataAccessPolicyConfig, FilesystemMode, FilesystemPolicyConfig,
    NetworkEgressMode, NetworkPolicyConfig, PolicyEnforcementCheck,
    PolicyEnforcementCheckStatus, PolicyEnforcementCheckType, PolicyEnforcementDecision,
    PolicyEnforcementSeverity, PolicyEnforcementStatus, PolicyTranslationResult,
    ResourceLimitPolicyConfig, SecretAccessMode, SecretPolicyConfig,
    WorkerPolicyConfig, build_policy_config_snapshot,
)

logger = logging.getLogger(__name__)

_PRIVATE_NETS = ["10.0.0.0/8","172.16.0.0/12","192.168.0.0/16","169.254.0.0/16","127.0.0.0/8","::1/128","0.0.0.0/0"]
_BLOCKED_DOMAINS = {"localhost","127.0.0.1","0.0.0.0","::1","metadata.google.internal","169.254.169.254"}
_MAX_TIMEOUT_MS = 300_000


class SandboxPolicyEnforcementTranslator:
    def __init__(self, *, supported_sandbox_levels=None,
                 worker_supports_network_enforcement=False,
                 worker_supports_filesystem_enforcement=False,
                 worker_supports_secret_broker=False,
                 worker_supports_data_broker=False,
                 worker_supports_resource_limits=True,
                 worker_supports_kill_switch=False):
        self._supported_levels = supported_sandbox_levels or {SandboxLevel.NO_EXECUTION, SandboxLevel.SIMULATION_ONLY, SandboxLevel.RESTRICTED}
        self._ws_network = worker_supports_network_enforcement
        self._ws_filesystem = worker_supports_filesystem_enforcement
        self._ws_secrets = worker_supports_secret_broker
        self._ws_data = worker_supports_data_broker
        self._ws_resources = worker_supports_resource_limits
        self._ws_killswitch = worker_supports_kill_switch

    def translate_policy(self, policy: Any) -> PolicyTranslationResult:
        result = PolicyTranslationResult(policy_id=getattr(policy, "policy_id", ""),
                                          tenant_id=getattr(policy, "tenant_id", None))
        level = getattr(policy, "sandbox_level", "")
        policy_status = getattr(policy, "status", "")

        # 1. POLICY_EXISTS + ACTIVE
        result.add_check(_chk(PolicyEnforcementCheckType.POLICY_EXISTS, PolicyEnforcementCheckStatus.PASSED,
                              PolicyEnforcementSeverity.INFO, f"Policy found: {result.policy_id}"))
        if policy_status not in ("active",):
            result.add_check(_chk(PolicyEnforcementCheckType.POLICY_ACTIVE, PolicyEnforcementCheckStatus.BLOCKED,
                                  PolicyEnforcementSeverity.BLOCKER, f"Policy status='{policy_status}', not active."))
            result.calculate_status(); result.config = None; return result
        result.add_check(_chk(PolicyEnforcementCheckType.POLICY_ACTIVE, PolicyEnforcementCheckStatus.PASSED,
                              PolicyEnforcementSeverity.INFO, "Policy is active."))

        # 2. SANDBOX_LEVEL_SUPPORTED
        if level not in self._supported_levels:
            unsupported = []
            if level == SandboxLevel.ISOLATED:
                unsupported = ["isolated"]
                result.add_check(_chk(PolicyEnforcementCheckType.SANDBOX_LEVEL_SUPPORTED, PolicyEnforcementCheckStatus.BLOCKED,
                                      PolicyEnforcementSeverity.BLOCKER, f"Sandbox level '{level}' not supported in Step 24-F."))
            else:
                result.add_check(_chk(PolicyEnforcementCheckType.SANDBOX_LEVEL_SUPPORTED, PolicyEnforcementCheckStatus.BLOCKED,
                                      PolicyEnforcementSeverity.BLOCKER, f"Unknown sandbox level '{level}'."))
            cfg = self._fail_closed_config(policy, unsupported)
            result.config = cfg; result.calculate_status(); return result
        result.add_check(_chk(PolicyEnforcementCheckType.SANDBOX_LEVEL_SUPPORTED, PolicyEnforcementCheckStatus.PASSED,
                              PolicyEnforcementSeverity.INFO, f"Sandbox level '{level}' supported for config generation."))

        unsupported: list[str] = []
        warnings: list[str] = []

        # 3. Translate network
        nw = self._translate_network(policy, result, unsupported, warnings)
        # 4. Translate filesystem
        fs = self._translate_filesystem(policy, result, unsupported, warnings)
        # 5. Translate secrets
        sc = self._translate_secrets(policy, result, unsupported, warnings)
        # 6. Translate resources
        rc = self._translate_resources(policy, result, unsupported, warnings)
        # 7. Translate data
        da = self._translate_data(policy, result, unsupported, warnings)
        # 8. Audit
        audit_enabled = bool(getattr(policy, "audit_enabled", True))
        if audit_enabled:
            result.add_check(_chk(PolicyEnforcementCheckType.AUDIT_ENABLED, PolicyEnforcementCheckStatus.PASSED,
                                  PolicyEnforcementSeverity.INFO, "Audit enabled."))
        else:
            warnings.append("audit_disabled")
            result.add_check(_chk(PolicyEnforcementCheckType.AUDIT_ENABLED, PolicyEnforcementCheckStatus.WARNING,
                                  PolicyEnforcementSeverity.WARNING, "Policy has audit_enabled=False."))
        # 9. Kill switch reserved
        if not self._ws_killswitch:
            warnings.append("kill_switch_not_implemented")
            result.add_check(_chk(PolicyEnforcementCheckType.KILL_SWITCH_SUPPORTED_RESERVED, PolicyEnforcementCheckStatus.WARNING,
                                  PolicyEnforcementSeverity.WARNING, "Kill switch not yet implemented (reserved)."))
        else:
            result.add_check(_chk(PolicyEnforcementCheckType.KILL_SWITCH_SUPPORTED_RESERVED, PolicyEnforcementCheckStatus.PASSED,
                                  PolicyEnforcementSeverity.INFO, "Kill switch supported."))
        # 10. Worker can enforce
        result.add_check(_chk(PolicyEnforcementCheckType.WORKER_CAN_ENFORCE_RESERVED, PolicyEnforcementCheckStatus.WARNING,
                              PolicyEnforcementSeverity.WARNING, "Worker enforcement reserved; no real worker in Step 24-F."))

        # 11. Fail closed on unsupported
        if unsupported:
            result.add_check(_chk(PolicyEnforcementCheckType.FAIL_CLOSED_ON_UNSUPPORTED, PolicyEnforcementCheckStatus.BLOCKED,
                                  PolicyEnforcementSeverity.BLOCKER if level not in (SandboxLevel.NO_EXECUTION, SandboxLevel.SIMULATION_ONLY) else PolicyEnforcementSeverity.WARNING,
                                  f"Unsupported features: {unsupported}"))

        # Build config
        enforceable = len(unsupported) == 0 and level in self._supported_levels
        if level in (SandboxLevel.NO_EXECUTION, SandboxLevel.SIMULATION_ONLY):
            enforceable = True  # config is always generatable for no-exec/sim

        cfg = WorkerPolicyConfig(
            policy_id=result.policy_id, tenant_id=result.tenant_id,
            sandbox_level=level, enforceable=enforceable,
            network=nw, filesystem=fs, secrets=sc, resources=rc, data_access=da,
            audit_enabled=audit_enabled, kill_switch_required=not self._ws_killswitch,
            unsupported_features=list(unsupported), warnings=list(warnings),
        )
        result.config = cfg
        result.calculate_status()
        return result

    def _translate_network(self, policy, result, unsupported, warnings):
        allow_net = bool(getattr(policy, "allow_network", False))
        domains = list(getattr(policy, "allowed_domains", []) or [])

        if not allow_net:
            result.add_check(_chk(PolicyEnforcementCheckType.NETWORK_DEFAULT_DENY, PolicyEnforcementCheckStatus.PASSED,
                                  PolicyEnforcementSeverity.INFO, "Network: DENY_ALL (default)."))
            return NetworkPolicyConfig(mode=NetworkEgressMode.DENY_ALL, allow_network=False)

        if not self._ws_network:
            unsupported.append("network_enforcement")
            result.add_check(_chk(PolicyEnforcementCheckType.NETWORK_DEFAULT_DENY, PolicyEnforcementCheckStatus.BLOCKED,
                                  PolicyEnforcementSeverity.BLOCKER, "Network enforcement not supported by worker; fail closed."))
            return NetworkPolicyConfig(mode=NetworkEgressMode.DISABLED_UNSUPPORTED, allow_network=False)

        # Validate domains
        bad = [d for d in domains if d.lower() in _BLOCKED_DOMAINS or _is_private_ip(d)]
        if bad:
            result.add_check(_chk(PolicyEnforcementCheckType.NETWORK_PRIVATE_IP_BLOCKED, PolicyEnforcementCheckStatus.BLOCKED,
                                  PolicyEnforcementSeverity.BLOCKER, f"Blocked domains in allowlist: {bad}"))
            warnings.append(f"blocked_domains: {bad}")
        else:
            result.add_check(_chk(PolicyEnforcementCheckType.NETWORK_PRIVATE_IP_BLOCKED, PolicyEnforcementCheckStatus.PASSED,
                                  PolicyEnforcementSeverity.INFO, "No private/localhost IPs in domain allowlist."))

        result.add_check(_chk(PolicyEnforcementCheckType.NETWORK_METADATA_IP_BLOCKED, PolicyEnforcementCheckStatus.PASSED,
                              PolicyEnforcementSeverity.INFO, "Metadata IP (169.254.169.254) blocked."))
        result.add_check(_chk(PolicyEnforcementCheckType.NETWORK_DOMAIN_ALLOWLIST_VALID, PolicyEnforcementCheckStatus.PASSED,
                              PolicyEnforcementSeverity.INFO, f"Domain allowlist: {domains}"))

        return NetworkPolicyConfig(mode=NetworkEgressMode.ALLOWLIST_ONLY, allow_network=True,
                                   allowed_domains=list(domains), dns_control_required=True)

    def _translate_filesystem(self, policy, result, unsupported, warnings):
        allow_read = bool(getattr(policy, "allow_filesystem_read", False))
        allow_write = bool(getattr(policy, "allow_filesystem_write", False))
        read_paths = list(getattr(policy, "allowed_paths", []) or [])
        write_paths = list(getattr(policy, "allowed_paths", []) or [])

        if not allow_read and not allow_write:
            result.add_check(_chk(PolicyEnforcementCheckType.FILESYSTEM_DEFAULT_DENY, PolicyEnforcementCheckStatus.PASSED,
                                  PolicyEnforcementSeverity.INFO, "Filesystem: DENY_ALL (default)."))
            result.add_check(_chk(PolicyEnforcementCheckType.FILESYSTEM_NO_HOST_MOUNT, PolicyEnforcementCheckStatus.PASSED,
                                  PolicyEnforcementSeverity.INFO, "No host mount."))
            return FilesystemPolicyConfig(mode=FilesystemMode.DENY_ALL, host_mount_allowed=False)

        if not self._ws_filesystem:
            unsupported.append("filesystem_enforcement")
            result.add_check(_chk(PolicyEnforcementCheckType.FILESYSTEM_DEFAULT_DENY, PolicyEnforcementCheckStatus.BLOCKED,
                                  PolicyEnforcementSeverity.BLOCKER, "Filesystem enforcement not supported; fail closed."))
            return FilesystemPolicyConfig(mode=FilesystemMode.DISABLED_UNSUPPORTED, host_mount_allowed=False)

        result.add_check(_chk(PolicyEnforcementCheckType.FILESYSTEM_NO_HOST_MOUNT, PolicyEnforcementCheckStatus.PASSED,
                              PolicyEnforcementSeverity.INFO, "Host mount forbidden."))
        result.add_check(_chk(PolicyEnforcementCheckType.FILESYSTEM_READ_PATHS_VALID, PolicyEnforcementCheckStatus.PASSED
                              if read_paths else PolicyEnforcementCheckStatus.WARNING,
                              PolicyEnforcementSeverity.INFO if read_paths else PolicyEnforcementSeverity.WARNING,
                              f"Read paths: {read_paths or 'none'}" if read_paths else "No read paths specified."))
        result.add_check(_chk(PolicyEnforcementCheckType.FILESYSTEM_WRITE_PATHS_VALID, PolicyEnforcementCheckStatus.PASSED
                              if write_paths else PolicyEnforcementCheckStatus.WARNING,
                              PolicyEnforcementSeverity.INFO if write_paths else PolicyEnforcementSeverity.WARNING,
                              f"Write paths: {write_paths or 'none'}" if write_paths else "No write paths specified."))

        return FilesystemPolicyConfig(mode=FilesystemMode.EPHEMERAL_ONLY, allow_read=allow_read, allow_write=allow_write,
                                      allowed_read_paths=list(read_paths), allowed_write_paths=list(write_paths),
                                      host_mount_allowed=False)

    def _translate_secrets(self, policy, result, unsupported, warnings):
        allow_sec = bool(getattr(policy, "allow_secrets", False))
        names = list(getattr(policy, "allowed_secret_names", []) or [])

        if not allow_sec:
            result.add_check(_chk(PolicyEnforcementCheckType.SECRETS_DEFAULT_DENY, PolicyEnforcementCheckStatus.PASSED,
                                  PolicyEnforcementSeverity.INFO, "Secrets: DENY_ALL (default)."))
            return SecretPolicyConfig(mode=SecretAccessMode.DENY_ALL, raw_env_injection_allowed=False)

        if not self._ws_secrets:
            unsupported.append("secret_broker")
            result.add_check(_chk(PolicyEnforcementCheckType.SECRETS_DEFAULT_DENY, PolicyEnforcementCheckStatus.BLOCKED,
                                  PolicyEnforcementSeverity.BLOCKER, "Secret broker not supported; fail closed."))
            return SecretPolicyConfig(mode=SecretAccessMode.DISABLED_UNSUPPORTED, raw_env_injection_allowed=False)

        result.add_check(_chk(PolicyEnforcementCheckType.SECRET_NAMES_SCOPED, PolicyEnforcementCheckStatus.PASSED
                              if names else PolicyEnforcementCheckStatus.WARNING,
                              PolicyEnforcementSeverity.INFO if names else PolicyEnforcementSeverity.WARNING,
                              f"Secret names: {names or 'none (all secrets blocked)'}"))
        return SecretPolicyConfig(mode=SecretAccessMode.SCOPED_BROKER_RESERVED, allow_secrets=True,
                                  allowed_secret_names=list(names), broker_required=True,
                                  raw_env_injection_allowed=False)

    def _translate_resources(self, policy, result, unsupported, warnings):
        timeout = int(getattr(policy, "max_timeout_ms", 0) or 0)
        mem = getattr(policy, "max_memory_mb", 0) or 0
        cpu = getattr(policy, "max_cpu_percent", 0) or 0
        out_bytes = getattr(policy, "max_output_bytes", 0) or 0
        rate = getattr(policy, "max_requests_per_minute", 0) or 0

        if timeout <= 0 or timeout > _MAX_TIMEOUT_MS:
            result.add_check(_chk(PolicyEnforcementCheckType.RESOURCE_TIMEOUT_LIMIT_VALID, PolicyEnforcementCheckStatus.FAILED,
                                  PolicyEnforcementSeverity.ERROR, f"Invalid timeout: {timeout}ms (must be 1-{_MAX_TIMEOUT_MS})."))
        else:
            result.add_check(_chk(PolicyEnforcementCheckType.RESOURCE_TIMEOUT_LIMIT_VALID, PolicyEnforcementCheckStatus.PASSED,
                                  PolicyEnforcementSeverity.INFO, f"Timeout: {timeout}ms."))

        mem_ok = mem is None or (isinstance(mem, (int, float)) and mem > 0)
        if mem and not mem_ok:
            result.add_check(_chk(PolicyEnforcementCheckType.RESOURCE_MEMORY_LIMIT_VALID, PolicyEnforcementCheckStatus.FAILED,
                                  PolicyEnforcementSeverity.ERROR, f"Invalid memory limit: {mem}."))
        else:
            result.add_check(_chk(PolicyEnforcementCheckType.RESOURCE_MEMORY_LIMIT_VALID, PolicyEnforcementCheckStatus.PASSED,
                                  PolicyEnforcementSeverity.INFO, f"Memory: {mem}MB."))

        cpu_ok = cpu is None or (isinstance(cpu, int) and 1 <= cpu <= 100)
        if cpu and not cpu_ok:
            result.add_check(_chk(PolicyEnforcementCheckType.RESOURCE_CPU_LIMIT_VALID, PolicyEnforcementCheckStatus.FAILED,
                                  PolicyEnforcementSeverity.ERROR, f"Invalid CPU percent: {cpu}."))
        else:
            result.add_check(_chk(PolicyEnforcementCheckType.RESOURCE_CPU_LIMIT_VALID, PolicyEnforcementCheckStatus.PASSED,
                                  PolicyEnforcementSeverity.INFO, f"CPU: {cpu}%."))

        out_ok = out_bytes is None or out_bytes > 0
        if out_bytes and not out_ok:
            result.add_check(_chk(PolicyEnforcementCheckType.OUTPUT_LIMIT_VALID, PolicyEnforcementCheckStatus.FAILED,
                                  PolicyEnforcementSeverity.ERROR, f"Invalid output limit: {out_bytes}."))
        else:
            result.add_check(_chk(PolicyEnforcementCheckType.OUTPUT_LIMIT_VALID, PolicyEnforcementCheckStatus.PASSED,
                                  PolicyEnforcementSeverity.INFO, f"Output limit: {out_bytes or 'unlimited'} bytes."))

        return ResourceLimitPolicyConfig(timeout_ms=timeout,
            memory_mb=int(mem) if mem else None,
            cpu_percent=int(cpu) if cpu else None,
            max_output_bytes=int(out_bytes) if out_bytes else None,
            max_requests_per_minute=int(rate) if rate else None,
            kill_on_timeout=True)

    def _translate_data(self, policy, result, unsupported, warnings):
        scope = list(getattr(policy, "data_access_scope", []) or [])
        if not scope:
            result.add_check(_chk(PolicyEnforcementCheckType.DATA_ACCESS_SCOPE_VALID, PolicyEnforcementCheckStatus.PASSED,
                                  PolicyEnforcementSeverity.INFO, "Data access: DENY_ALL (no scope)."))
            return DataAccessPolicyConfig(mode=DataAccessMode.DENY_ALL)

        if not self._ws_data:
            unsupported.append("data_broker")
            result.add_check(_chk(PolicyEnforcementCheckType.DATA_ACCESS_SCOPE_VALID, PolicyEnforcementCheckStatus.BLOCKED,
                                  PolicyEnforcementSeverity.BLOCKER, "Data broker not supported; fail closed."))
            return DataAccessPolicyConfig(mode=DataAccessMode.DISABLED_UNSUPPORTED)

        result.add_check(_chk(PolicyEnforcementCheckType.DATA_ACCESS_SCOPE_VALID, PolicyEnforcementCheckStatus.PASSED,
                              PolicyEnforcementSeverity.INFO, f"Data access scope: {scope}."))
        return DataAccessPolicyConfig(mode=DataAccessMode.BROKER_ONLY_RESERVED, data_access_scope=list(scope),
                                      broker_required=True, direct_db_access_allowed=False,
                                      direct_file_access_allowed=False, direct_vector_access_allowed=False)

    def _fail_closed_config(self, policy, unsupported):
        return WorkerPolicyConfig(policy_id=getattr(policy, "policy_id", ""),
                                  tenant_id=getattr(policy, "tenant_id", None),
                                  sandbox_level=getattr(policy, "sandbox_level", ""),
                                  enforceable=False, decision=PolicyEnforcementDecision.FAIL_CLOSED,
                                  unsupported_features=list(unsupported))


def _chk(ct, status=PolicyEnforcementCheckStatus.PASSED, sev=PolicyEnforcementSeverity.INFO, msg="", **kw):
    return PolicyEnforcementCheck(check_type=ct, status=status, severity=sev, message=msg, metadata=kw)

def _is_private_ip(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_unspecified
    except ValueError: return False
