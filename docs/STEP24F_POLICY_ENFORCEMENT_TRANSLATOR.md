# Step 24-F：Policy Enforcement Translator

## 1. 本轮目标

实现 SandboxPolicy → WorkerPolicyConfig 的 fail-closed 翻译层。

**只做 policy → config translation — 不执行、不联网、不读取文件/secrets。**

## 2. Domain Model

`src/open_platform/policy_enforcement.py`

- 7 enums: PolicyEnforcementDecision/Status/CheckType/CheckStatus/Severity + 4 mode enums (NetworkEgressMode, FilesystemMode, SecretAccessMode, DataAccessMode)
- PolicyEnforcementCheck (polchk_<16>) — 22 check types
- 5 Config dataclasses: NetworkPolicyConfig, FilesystemPolicyConfig, SecretPolicyConfig, ResourceLimitPolicyConfig, DataAccessPolicyConfig
- WorkerPolicyConfig (polcfg_<16>) — composite config with enforceable flag
- PolicyTranslationResult (poltr_<16>) — status, decision, checks, safety flags
- build_policy_config_snapshot() — safe snapshot helper

## 3. Translator

`src/open_platform/policy_enforcement_translator.py`

SandboxPolicyEnforcementTranslator with configurable worker support flags (all default False/disabled):
- no_execution/simulation_only → ALLOW_CONFIG (config generatable, not executable)
- restricted → requires worker support for network/filesystem/secrets/data; fail closed if unsupported
- isolated → FAIL_CLOSED (unsupported in Step 24-F)
- domain validation: block private IPs, localhost, metadata IP
- resource validation: timeout 1-300000ms, memory>0, cpu 1-100%, output>0
- raw_env_injection always false
- host_mount always false
- direct DB/file/vector access always false

## 4. Non-Execution Guarantees

- No subprocess/container/network/file access
- No secrets read / no local path access
- ALLOW_CONFIG ≠ execution permission
- No worker creation / dispatch / execute/run methods

## 5. Tests

68 tests: domain (19) + no_exec/sim (8) + restricted (16) + snapshot (5) + safety (11) + integration (9)

```bash
python -m pytest tests/test_open_platform/test_policy_enforcement_translator.py -v
# 68 passed

python -m pytest tests/test_open_platform/ -q
# 1046 passed

python -m pytest tests/test_security.py tests/test_agents/ tests/test_saas/ tests/test_open_platform/ -q
# 1693 passed
```

## 6. Next Step

Step 24-G：Local Development Sandbox Prototype
