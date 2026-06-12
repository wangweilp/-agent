"""Sandbox Worker Registry — worker 注册与默认查找。

Step 24-E: 默认只注册 DisabledSandboxWorker。
不注册 container/local_process/wasm/microVM。
不动态导入 worker。不自动启用真实 worker。
这不是 AgentRegistry — 不 import src.agents.registry。
"""

from __future__ import annotations

from typing import Any

from src.open_platform.sandbox_worker import (
    SandboxWorker, SandboxWorkerRequest, SandboxWorkerResult, SandboxWorkerType,
)
from src.open_platform.sandbox_worker_stub import DisabledSandboxWorker


class SandboxWorkerRegistry:
    """Worker 注册中心 — 管理 SandboxWorker 实例。"""

    def __init__(self) -> None:
        self._workers: dict[str, SandboxWorker] = {}
        # 默认注册 DisabledSandboxWorker
        self._register_disabled()

    def _register_disabled(self) -> None:
        worker = DisabledSandboxWorker()
        self._workers[worker.get_worker_type()] = worker

    def register(self, worker: SandboxWorker) -> None:
        self._workers[worker.get_worker_type()] = worker

    def get(self, worker_type: str) -> SandboxWorker | None:
        return self._workers.get(worker_type)

    def get_default(self) -> SandboxWorker:
        return self._workers.get(SandboxWorkerType.DISABLED_STUB, DisabledSandboxWorker())

    def list_workers(self) -> list[dict[str, Any]]:
        return [{"worker_type": wt, "availability": w.get_availability()}
                for wt, w in self._workers.items()]

    def evaluate_with_default(self, request: SandboxWorkerRequest) -> SandboxWorkerResult:
        worker = self.get_default()
        return worker.evaluate_request(request)


def create_default_sandbox_worker_registry(
    enable_local_dev_dry_run: bool = False,
) -> SandboxWorkerRegistry:
    """创建默认 registry。enable_local_dev_dry_run=False 时只注册 disabled stub。"""
    reg = SandboxWorkerRegistry()
    if enable_local_dev_dry_run:
        from src.open_platform.local_dev_sandbox import LocalDevSandboxConfig
        from src.open_platform.local_dev_sandbox_worker import LocalDevSandboxPrototypeWorker
        cfg = LocalDevSandboxConfig.dry_run_for_tests()
        worker = LocalDevSandboxPrototypeWorker(config=cfg)
        reg.register(worker)
    return reg
