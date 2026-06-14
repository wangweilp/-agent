#!/usr/bin/env python
"""Sandbox v2 MicroVM / Firecracker Preflight Check Script.

Step 11 — MicroVM / Firecracker PoC preflight 检查。

功能:
1. 读取 MicroVM 环境变量配置
2. 检查 Linux / Windows
3. 检查 /dev/kvm
4. 检查 firecracker binary
5. 检查 kernel/rootfs
6. 检查 env var
7. 输出 JSON summary
8. mask 本地敏感路径
9. 不启动 Firecracker
10. 不联网
11. 不下载文件
"""

from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "").strip().lower() in ("true", "1", "yes")


def _mask_path(path: str) -> str:
    """Mask 敏感本地路径：只显示 basename。"""
    if not path:
        return ""
    return f".../{Path(path).name}"


def run_microvm_preflight() -> dict:
    """运行 MicroVM preflight 检查。"""
    is_linux = platform.system() == "Linux"
    is_windows = not is_linux

    # KVM
    has_kvm = False
    kvm_msg = "Not Linux — KVM unavailable."
    if is_linux:
        if os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK):
            has_kvm = True
            kvm_msg = "/dev/kvm available and accessible"
        else:
            kvm_msg = "/dev/kvm not found or not accessible"

    # Firecracker binary
    fb_path = os.getenv("SANDBOX_V2_FIRECRACKER_BIN_PATH", "")
    fb_ok = False
    fb_msg = "firecracker binary not found"
    import shutil
    if fb_path:
        if os.path.isfile(fb_path) and os.access(fb_path, os.X_OK):
            fb_ok = True
            fb_msg = f"Firecracker binary found at {_mask_path(fb_path)}"
        else:
            fb_msg = f"Firecracker binary not found at {_mask_path(fb_path)}"
    elif shutil.which("firecracker"):
        fb_ok = True
        fb_msg = "firecracker found in PATH"

    # Kernel
    ker_path = os.getenv("SANDBOX_V2_FIRECRACKER_KERNEL_PATH", "")
    ker_ok = bool(ker_path and os.path.isfile(ker_path))
    ker_msg = f"Kernel {'found' if ker_ok else 'NOT found'} at {_mask_path(ker_path)}" if ker_path else "Kernel path not configured"

    # Rootfs
    rfs_path = os.getenv("SANDBOX_V2_FIRECRACKER_ROOTFS_PATH", "")
    rfs_ok = bool(rfs_path and os.path.isfile(rfs_path))
    rfs_msg = f"Rootfs {'found' if rfs_ok else 'NOT found'} at {_mask_path(rfs_path)}" if rfs_path else "Rootfs path not configured"

    # Env vars
    exec_enabled = _env_bool("SANDBOX_V2_MICROVM_EXECUTION_ENABLED")
    integ_enabled = _env_bool("SANDBOX_V2_RUN_MICROVM_INTEGRATION")
    net_disabled = not _env_bool("SANDBOX_V2_MICROVM_NETWORK_ENABLED")

    runnable = all([is_linux, has_kvm, fb_ok, ker_ok, rfs_ok, exec_enabled, integ_enabled, net_disabled])

    blockers: list[str] = []
    if not is_linux: blockers.append("Platform is not Linux")
    if not has_kvm: blockers.append("/dev/kvm not available")
    if not fb_ok: blockers.append("Firecracker binary not found")
    if not ker_ok: blockers.append("MicroVM kernel not found")
    if not rfs_ok: blockers.append("MicroVM rootfs not found")
    if not exec_enabled: blockers.append("SANDBOX_V2_MICROVM_EXECUTION_ENABLED not true")
    if not integ_enabled: blockers.append("SANDBOX_V2_RUN_MICROVM_INTEGRATION not true")

    warnings: list[str] = []
    if not net_disabled: warnings.append("MicroVM network is enabled — should be disabled for production")

    return {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "platform": platform.system(),
        "is_linux": is_linux, "is_windows": is_windows,
        "has_kvm": has_kvm, "kvm_message": kvm_msg,
        "firecracker_binary_present": fb_ok, "firecracker_message": fb_msg,
        "kernel_present": ker_ok, "kernel_message": ker_msg,
        "rootfs_present": rfs_ok, "rootfs_message": rfs_msg,
        "execution_enabled": exec_enabled, "integration_enabled": integ_enabled,
        "network_disabled": net_disabled,
        "runnable": runnable,
        "blockers": blockers,
        "warnings": warnings,
        "reason": "; ".join(blockers) if blockers else "All MicroVM preconditions satisfied.",
        "note": "MicroVM is disabled by default. Real Firecracker execution requires Linux+KVM+Firecracker+kernel+rootfs+env vars.",
    }


def main() -> int:
    result = run_microvm_preflight()
    output_json = "--json" in sys.argv

    if output_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("=" * 70)
        print("  Sandbox v2 MicroVM / Firecracker Preflight Check")
        print("=" * 70)
        print(f"  Platform: {result['platform']}")
        print(f"  Linux: {result['is_linux']} | Windows: {result['is_windows']}")
        print()
        status = "[OK]" if result["has_kvm"] else "[FAIL]"
        print(f"  [{status}] KVM: {result['kvm_message']}")
        status = "[OK]" if result["firecracker_binary_present"] else "[FAIL]"
        print(f"  [{status}] Firecracker binary: {result['firecracker_message']}")
        status = "[OK]" if result["kernel_present"] else "[FAIL]"
        print(f"  [{status}] Kernel: {result['kernel_message']}")
        status = "[OK]" if result["rootfs_present"] else "[FAIL]"
        print(f"  [{status}] Rootfs: {result['rootfs_message']}")
        print()
        print(f"  Execution enabled: {result['execution_enabled']}")
        print(f"  Integration enabled: {result['integration_enabled']}")
        print(f"  Network disabled: {result['network_disabled']}")
        print()

        blockers = result["blockers"]
        if blockers:
            print(f"  [BLOCKERS] ({len(blockers)}):")
            for b in blockers: print(f"     - {b}")
        else:
            print("  [OK] No blockers")
        print()

        if result["warnings"]:
            for w in result["warnings"]: print(f"  [WARN] {w}")

        status = "[READY]" if result["runnable"] else "[NOT READY]"
        print(f"  {status} MicroVM runnable: {result['runnable']}")
        print()
        print(f"  {result['note']}")
        print("=" * 70)

    return 1 if result["blockers"] else 0


if __name__ == "__main__":
    sys.exit(main())
