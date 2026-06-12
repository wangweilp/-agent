# Step 25-F：Worker Queue Design, Disabled by Default

## 1. 本轮目标

只实现 disabled-by-default worker queue domain model + metadata-only records。**不创建真实 queue。不 enqueue。不 dispatch。不启动 worker。**

## 2. Domain Model

`src/open_platform/sandbox_worker_queue.py`

- SandboxWorkerQueueStatus: NO QUEUED/ENQUEUED/DISPATCHED/RUNNING/COMPLETED
- SandboxWorkerQueueRecord: 62 fields, 10 snapshots, 7 enable flags (all False), 12 no_* flags (all True)
- is_queue_enabled/is_enqueue_allowed/is_dispatch_allowed/is_worker_start_allowed/is_execution_allowed = all False
- SandboxWorkerQueueGateResult: is_passed_for_queue/is_dispatch_allowed = False

## 3. Tests

64 tests: domain (25) + store (27) + service (12)
1770 Open Platform / 2417 regression passed.

## 4. Next Step

Step 25-G：Network/Filesystem/Secrets Enforcement Proof
