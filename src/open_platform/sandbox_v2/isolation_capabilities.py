"""Sandbox v2 Isolation Capability Probe — 能力探测。

检测当前平台和执行隔离能力，不执行用户代码。
不启动容器、不拉镜像、不访问网络。
Windows 上 Linux namespace/cgroup/seccomp 返回 unavailable。
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
from datetime import datetime, timezone

from src.open_platform.sandbox_v2.models import (
    SandboxIsolationCapability,
    SandboxV2IsolationProvider,
)

logger = logging.getLogger(__name__)


class SandboxIsolationCapabilityProbe:
    """隔离能力探测器 — 只检测，不执行。"""

    def detect_platform(self) -> dict:
        return {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "is_windows": platform.system() == "Windows",
            "is_linux": platform.system() == "Linux",
        }

    def check_docker_available(self) -> tuple[bool, str]:
        try:
            if shutil.which("docker"):
                return True, "docker binary found"
            return False, "docker binary not found"
        except Exception as e:
            return False, f"check failed: {e}"

    def check_podman_available(self) -> tuple[bool, str]:
        try:
            if shutil.which("podman"):
                return True, "podman binary found"
            return False, "podman binary not found"
        except Exception as e:
            return False, f"check failed: {e}"

    def check_firecracker_available(self) -> tuple[bool, str]:
        try:
            if shutil.which("firecracker"):
                return True, "firecracker binary found"
            return False, "firecracker binary not found"
        except Exception as e:
            return False, f"check failed: {e}"

    def check_gvisor_available(self) -> tuple[bool, str]:
        try:
            if shutil.which("runsc"):
                return True, "runsc (gVisor) binary found"
            return False, "runsc (gVisor) binary not found"
        except Exception as e:
            return False, f"check failed: {e}"

    def check_kata_available(self) -> tuple[bool, str]:
        try:
            if shutil.which("kata-runtime"):
                return True, "kata-runtime binary found"
            return False, "kata-runtime binary not found"
        except Exception as e:
            return False, f"check failed: {e}"

    def check_linux_namespaces(self) -> tuple[bool, str]:
        if platform.system() != "Linux":
            return False, "Not Linux — namespaces unavailable on this platform."
        try:
            if os.path.exists("/proc/self/ns/user"):
                return True, "User namespace available"
            return False, "/proc/self/ns/user not found"
        except Exception as e:
            return False, f"Check failed: {e}"

    def check_cgroups(self) -> tuple[bool, str]:
        if platform.system() != "Linux":
            return False, "Not Linux — cgroups unavailable on this platform."
        try:
            if os.path.exists("/sys/fs/cgroup"):
                return True, "cgroup v1/v2 path exists"
            return False, "/sys/fs/cgroup not found"
        except Exception as e:
            return False, f"Check failed: {e}"

    def check_seccomp(self) -> tuple[bool, str]:
        if platform.system() != "Linux":
            return False, "Not Linux — seccomp unavailable on this platform."
        try:
            if os.path.exists("/proc/self/status"):
                with open("/proc/self/status") as f:
                    content = f.read()
                    if "Seccomp:" in content:
                        return True, "Seccomp supported"
            return False, "Seccomp status unknown"
        except Exception as e:
            return False, f"Check failed: {e}"

    def check_lsm(self) -> tuple[bool, bool, str]:
        if platform.system() != "Linux":
            return False, False, "Not Linux — LSM unavailable."
        has_aa = os.path.exists("/sys/kernel/security/apparmor")
        has_se = os.path.exists("/sys/fs/selinux")
        return has_aa, has_se, f"AppArmor={has_aa}, SELinux={has_se}"

    def collect_capabilities(self) -> SandboxIsolationCapability:
        p = self.detect_platform()
        is_win = p["is_windows"]
        is_lin = p["is_linux"]
        now = datetime.now(timezone.utc)

        has_ns = self.check_linux_namespaces()
        has_cg = self.check_cgroups()
        has_sc = self.check_seccomp()
        has_aa, has_se, lsm_msg = self.check_lsm()
        has_docker, docker_msg = self.check_docker_available()
        has_podman, podman_msg = self.check_podman_available()
        has_fire, fire_msg = self.check_firecracker_available()
        has_gv, gv_msg = self.check_gvisor_available()
        has_kata, kata_msg = self.check_kata_available()

        # Determine available providers
        available_providers: list[str] = [SandboxV2IsolationProvider.DISABLED]
        if has_docker:
            available_providers.append(SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE)
        if has_podman:
            available_providers.append(SandboxV2IsolationProvider.PODMAN_ROOTLESS_FUTURE)
        if has_fire:
            available_providers.append(SandboxV2IsolationProvider.FIRECRACKER_FUTURE)
        if has_gv:
            available_providers.append(SandboxV2IsolationProvider.GVISOR_FUTURE)
        if has_kata:
            available_providers.append(SandboxV2IsolationProvider.KATA_FUTURE)

        reasons = []
        if is_win:
            reasons.append("Windows: namespace/cgroup/seccomp unavailable.")
        if not has_docker:
            reasons.append(f"Docker: {docker_msg}")
        if not has_podman:
            reasons.append(f"Podman: {podman_msg}")

        capability = SandboxIsolationCapability(
            provider=",".join(available_providers),
            available=has_ns[0] or has_docker or has_podman,
            enabled=False,  # always disabled by default
            reason="; ".join(reasons) if reasons else "Capability probe completed.",
            platform=p["system"],
            os_name=f"{p['system']} {p['release']}",
            is_windows=is_win,
            is_linux=is_lin,
            has_docker=has_docker,
            has_podman=has_podman,
            has_firecracker=has_fire,
            has_gvisor=has_gv,
            has_kata=has_kata,
            has_user_namespace=has_ns[0],
            has_cgroup=has_cg[0],
            has_seccomp=has_sc[0],
            has_apparmor=has_aa,
            has_selinux=has_se,
            has_network_namespace=has_ns[0],
            has_mount_namespace=has_ns[0],
            checked_at=now,
            metadata={"raw_detection": {
                "docker": docker_msg, "podman": podman_msg,
                "namespace": has_ns[1], "cgroup": has_cg[1],
                "seccomp": has_sc[1], "lsm": lsm_msg,
                "providers_detected": available_providers,
            }},
        )
        return capability

    def get_readiness_summary(self) -> dict:
        cap = self.collect_capabilities()
        return {
            "isolation_capability_probe": True,
            "execution_provider_abstraction": True,
            "trusted_fixture_provider": True,
            "untrusted_code_execution": False,
            "local_process_execution": False,
            "docker_execution": False,
            "podman_execution": False,
            "microvm_execution": False,
            "runtime_network_namespace": cap.has_network_namespace and not cap.is_windows,
            "runtime_filesystem_namespace": cap.has_mount_namespace and not cap.is_windows,
            "seccomp_enforcement": cap.has_seccomp and not cap.is_windows,
            "cgroup_enforcement": cap.has_cgroup and not cap.is_windows,
            "platform": cap.platform,
            "is_windows": cap.is_windows,
            "provider": cap.provider,
            "available_sandbox_runtimes": [
                r for r in ["docker", "podman", "firecracker", "gvisor", "kata"]
                if cap.to_dict().get(f"has_{r}")
            ],
            "current_execution_mode": "simulation_or_trusted_fixture_only",
            "boundary": "No untrusted code execution. Only simulation and trusted fixture are allowed.",
            "capability": cap.to_dict(),
        }

    # ═══════════════════════════════════════════
    # Step 6C — Container Runtime Preflight
    # ═══════════════════════════════════════════

    def detect_wsl2(self) -> tuple[bool, str]:
        """检测是否在 WSL2 环境中运行。"""
        try:
            if os.path.exists("/proc/sys/fs/binfmt_misc/WSLInterop"):
                return True, "WSL2 detected via WSLInterop"
            if os.path.exists("/proc/version"):
                with open("/proc/version") as f:
                    if "microsoft" in f.read().lower() or "wsl" in f.read().lower():
                        return True, "WSL2 detected via /proc/version"
        except Exception:
            pass
        if platform.system() == "Linux":
            return True, "Running on native Linux"
        return False, f"Not Linux/WSL2. Current: {platform.system()}"

    def check_local_image_exists(self, runtime: str, image: str) -> tuple[bool, str]:
        """检查本地镜像是否存在。不 pull。"""
        rt = shutil.which(runtime)
        if not rt:
            return False, f"Runtime '{runtime}' not found."
        try:
            import subprocess
            r = subprocess.run([rt, "image", "inspect", image], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                return True, f"Image '{image}' exists locally."
            return False, f"Image '{image}' not found locally: {r.stderr.strip()[:100]}"
        except Exception as e:
            return False, f"Image check failed: {e}"

    def get_container_runtime_info(self, runtime: str) -> tuple[bool, str]:
        """获取容器运行时 info（非 root）。"""
        rt = shutil.which(runtime)
        if not rt:
            return False, f"Runtime '{runtime}' binary not found."
        try:
            import subprocess
            r = subprocess.run([rt, "info", "--format", "{{.OSType}}"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                return True, f"Runtime '{runtime}' info available: {r.stdout.strip()[:100]}"
            return False, f"Runtime info failed: {r.stderr.strip()[:100]}"
        except Exception as e:
            return False, f"Runtime info check failed: {e}"

    # ═══════════════════════════════════════════
    # Step 11 — MicroVM / KVM Detection
    # ═══════════════════════════════════════════

    def detect_kvm(self) -> tuple[bool, str]:
        """检测 /dev/kvm 是否存在。Windows 直接返回 False。"""
        if platform.system() != "Linux":
            return False, "Not Linux — KVM unavailable on this platform."
        try:
            if os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK):
                return True, "/dev/kvm available and accessible"
            return False, "/dev/kvm not found or not accessible"
        except Exception as e:
            return False, f"KVM check failed: {e}"

    def check_microvm_firecracker_binary(self, bin_path: str = "") -> tuple[bool, str]:
        """检查 Firecracker binary 是否存在。不执行。"""
        if bin_path:
            exists = os.path.isfile(bin_path) and os.access(bin_path, os.X_OK)
            return exists, f"Firecracker binary {'found' if exists else 'not found'} at {bin_path}"
        if shutil.which("firecracker"):
            return True, "firecracker found in PATH"
        return False, "firecracker binary not found"

    def check_microvm_kernel_exists(self, kernel_path: str = "") -> tuple[bool, str]:
        """检查 MicroVM kernel 是否存在。"""
        if kernel_path and os.path.isfile(kernel_path):
            return True, f"Kernel found at {kernel_path}"
        return False, f"Kernel not found at {kernel_path or '(no path configured)'}"

    def check_microvm_rootfs_exists(self, rootfs_path: str = "") -> tuple[bool, str]:
        """检查 MicroVM rootfs 是否存在。"""
        if rootfs_path and os.path.isfile(rootfs_path):
            return True, f"Rootfs found at {rootfs_path}"
        return False, f"Rootfs not found at {rootfs_path or '(no path configured)'}"

    def check_microvm_preconditions(self) -> dict:
        """完整 MicroVM 前置条件检查。不启动 Firecracker。不联网。"""
        p = self.detect_platform()
        is_linux = p["is_linux"]
        has_kvm, kvm_msg = self.detect_kvm()
        bin_path = os.environ.get("SANDBOX_V2_FIRECRACKER_BIN_PATH", "")
        kernel_path = os.environ.get("SANDBOX_V2_FIRECRACKER_KERNEL_PATH", "")
        rootfs_path = os.environ.get("SANDBOX_V2_FIRECRACKER_ROOTFS_PATH", "")
        has_fb, fb_msg = self.check_microvm_firecracker_binary(bin_path)
        has_ker, ker_msg = self.check_microvm_kernel_exists(kernel_path)
        has_rfs, rfs_msg = self.check_microvm_rootfs_exists(rootfs_path)
        exec_enabled = os.environ.get("SANDBOX_V2_MICROVM_EXECUTION_ENABLED", "").lower() in ("true", "1", "yes")
        integ_enabled = os.environ.get("SANDBOX_V2_RUN_MICROVM_INTEGRATION", "").lower() in ("true", "1", "yes")
        net_disabled = os.environ.get("SANDBOX_V2_MICROVM_NETWORK_ENABLED", "").lower() not in ("true", "1", "yes")

        runnable = all([is_linux, has_kvm, has_fb, has_ker, has_rfs, exec_enabled, integ_enabled, net_disabled])

        return {
            "platform": p["system"], "is_linux": is_linux, "is_windows": not is_linux,
            "has_kvm": has_kvm, "kvm_message": kvm_msg,
            "firecracker_binary_present": has_fb, "firecracker_message": fb_msg,
            "kernel_present": has_ker, "kernel_message": ker_msg,
            "rootfs_present": has_rfs, "rootfs_message": rfs_msg,
            "execution_env_enabled": exec_enabled,
            "integration_env_enabled": integ_enabled,
            "network_disabled": net_disabled,
            "runnable": runnable,
            "reason": "All preconditions satisfied." if runnable else "Preconditions not met.",
        }

    def get_microvm_readiness_summary(self) -> dict:
        """返回 MicroVM readiness 摘要。"""
        pc = self.check_microvm_preconditions()
        return {
            "microvm_provider_abstraction": True,
            "firecracker_provider_abstraction": True,
            "microvm_execution_enabled": pc["execution_env_enabled"],
            "microvm_integration_enabled": pc["integration_env_enabled"],
            "microvm_runnable": pc["runnable"],
            "kvm_available": pc["has_kvm"],
            "firecracker_binary_present": pc["firecracker_binary_present"],
            "microvm_kernel_present": pc["kernel_present"],
            "microvm_rootfs_present": pc["rootfs_present"],
            "microvm_network_enabled": not pc["network_disabled"],
            "user_kernel_allowed": False,
            "user_rootfs_allowed": False,
            "host_mounts_allowed": False,
            "real_microvm_execution": False,
            "platform": pc["platform"],
            "boundary": "MicroVM is disabled by default. Trusted fixture only. No user kernel/rootfs/command/network.",
            "blockers": [] if pc["runnable"] else [pc["reason"]],
        }

    def check_container_execution_preconditions(self, runtime: str, image: str) -> dict:
        """完整的容器执行前置条件检查。不 pull、不启动容器。"""
        p = self.detect_platform()
        is_linux = p["is_linux"] or self.detect_wsl2()[0]
        has_docker = shutil.which("docker") is not None
        has_podman = shutil.which("podman") is not None
        rt_available = shutil.which(runtime) is not None
        env_enabled = os.environ.get("SANDBOX_V2_CONTAINER_EXECUTION_ENABLED", "").lower() in ("true", "1", "yes")
        integration_enabled = os.environ.get("SANDBOX_V2_RUN_CONTAINER_INTEGRATION", "").lower() in ("true", "1", "yes")
        image_present, image_msg = (False, "skipped") if not rt_available else self.check_local_image_exists(runtime, image)
        runtime_info_ok, runtime_info_msg = (False, "skipped") if not rt_available else self.get_container_runtime_info(runtime)

        runnable = all([is_linux, rt_available, env_enabled, integration_enabled, image_present])

        reasons = []
        if not is_linux: reasons.append("Platform is not Linux/WSL2.")
        if not rt_available: reasons.append(f"Runtime '{runtime}' not found.")
        if not env_enabled: reasons.append("SANDBOX_V2_CONTAINER_EXECUTION_ENABLED not set to true.")
        if not integration_enabled: reasons.append("SANDBOX_V2_RUN_CONTAINER_INTEGRATION not set to true.")
        if not image_present: reasons.append(f"Image '{image}' not available locally.")

        return {
            "platform": p["system"], "is_linux": is_linux,
            "is_wsl2": self.detect_wsl2()[0],
            "docker_available": has_docker, "podman_available": has_podman,
            "runtime_available": rt_available,
            "runtime_info_available": runtime_info_ok, "runtime_info": runtime_info_msg,
            "image_present": image_present, "image_message": image_msg,
            "env_enabled": env_enabled, "integration_enabled": integration_enabled,
            "runnable": runnable,
            "reason": "; ".join(reasons) if reasons else "All preconditions satisfied.",
            "auto_pull_images": False, "user_command_execution": False,
            "user_image_execution": False, "network_enabled_in_container": False,
        }
