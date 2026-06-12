# Step 25 Security Q&A

## Q1: 你们现在能执行第三方代码了吗？
不能。Step 25 A-I 均为安全门控体系，没有任何真实第三方代码执行路径。execute endpoint 仍 blocked，is_executable() 始终 False。

## Q2: Trusted fixture 是不是第三方代码？
不是。Trusted fixture 是 5 个平台内置静态确定性 fixture。不 eval/exec/import。不读文件/网络/secrets。third_party_code_executed=False。

## Q3: execute endpoint 为什么 blocked？
因为前 20 个 hard gates 未全部满足：package download verified、checksum/signature verified、dependency scanned、sandbox worker available、kill switch operational。Endpoint 暴露为 draft 验证 auth schema，始终返回 blocked。

## Q4: admin approval 为什么不等于 download？
Approval 是状态变更 (ADMIN_APPROVED_FOR_FUTURE_DOWNLOAD)，不是 HTTP GET。is_downloadable() 始终 False。

## Q5: metadata-only quarantine 有什么意义？
保存隔离记录元数据，预留未来真实隔离的文件系统位置。file_materialized=False，extraction_allowed=False。

## Q6: extraction guard 为什么不读 archive？
未 import zipfile/tarfile/shutil。只做 entry metadata 字符串级路径验证，不需要打开文件。

## Q7: queue record 为什么不是 queue？
SandboxWorkerQueueRecord 是数据记录，无 enqueue/dispatch/worker 方法。queue_enabled=False。

## Q8: enforcement proof 为什么不是 enforcement？
Proof 只验证规则完整性，不改 iptables/mount/secrets。is_enforcement_active() 始终 False。

## Q9: container feasibility 为什么不是 container implementation？
paper-tier 评估，不 import docker。container_start_enabled=False。

## Q10: rootless container 为什么只是 candidate？
需要 Seccomp+AppArmor+no privileged+docker socket+host mount+read-only rootfs。Candidate ≠ execution approved。

## Q11: microVM 为什么没有实现？
Firecracker 仅 Linux，Windows 不可行。reserved_for_future_spike。

## Q12: subprocess 为什么被拒绝？
隔离不足，不能作为不可信代码边界。os.system()/ctypes/mmap 可逃逸。永久 REJECTED。

## Q13-Q20: 有没有下载/解压/执行 entrypoint/启动 worker/启动 Docker/读 secrets/联网/读写文件？
全部没有。所有模块验证无 socket/requests/docker/subprocess/open/os.environ。

## Q21: 如何防止 package_url 泄露？
PackageSourceMetadata 只保存 SHA256 hash 和 redacted host。raw URL 不在 to_dict 中出现。

## Q22: 如何防止 stdout/stderr 泄露？
SandboxWorkerResult.stdout/stderr/exit_code 默认 None。所有 to_dict() 不含这些字段。

## Q23: 如何保证 AgentRuntime/AgentRegistry 不被调用？
所有 Step 25 模块不 import AgentRuntime/AgentRegistry。Trusted fixture registry 独立，不继承 AgentRegistry。

## Q24: 163 red-team tests 覆盖了什么？
11 守卫类别：import/call/enum/method/behavior/fixture/metadata/endpoint/service/docs/startup。零逃逸路径。

## Q25: Step 25-K 要做什么？
Final Regression Gate — 全量回归 + 安全门禁 + 文档一致性 + 启动验证。

## Q26: 真正 sandbox 前缺什么 hard gates？
Package download quarantine、checksum/signature crypto verify、dependency scan、container/microVM adapter、worker queue、data/secret/network broker、kill switch。20 gates 中 ~14 未满足。

## Q27: 对企业客户价值？
向前证明安全治理能力：知道能不能执行，为什么不能，何时能。符合 enterprise risk management 和 defense-in-depth 原则。

## Q28-Q35: Known Issues / Next Step
无生产 sandbox。全部故意推迟到 Step 26+。Step 25-K Final Regression Gate 为下一步。
