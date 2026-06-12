# Step 23-H：Developer SDK / Manifest Schema

## 1. 概述

提供 Agent Manifest JSON Schema、Python SDK 轻量校验器、Manifest Examples、Developer API schema/validate endpoints。

**不下载/不解压/不执行 package。不联网。不做真实 CVE scan。**

## 2. JSON Schema

**位置:** `schemas/cognitive-agent.schema.json`

- draft-2020-12 schema
- Required: name, display_name, description, version, capabilities, required_permissions, runtime_type, security_profile
- runtime_type: manifest_only (MVP enum)
- security_profile.sandbox_level: no_execution / simulation_only
- metadata: package_url, checksum, signature, license, dependencies, etc.

## 3. Python SDK

**位置:** `sdk/python/cognitive_agent_sdk/`

- `validator.py` — validate_manifest_dict, validate_manifest_file, load_manifest_file
- `examples.py` — build_minimal_manifest, build_package_metadata_manifest, build_invalid_network_manifest
- `cli.py` — CLI: validate file, example, schema

## 4. Developer API

- `GET /developers/agent-manifest/schema` — return JSON Schema + non-execution guarantees
- `POST /developers/agent-manifest/validate` — static validation, no submission created

## 5. Non-Execution Guarantees

- ❌ 不下载 package / 不解压 / 不执行
- ❌ 不联网 / 不做真实 CVE scan
- ❌ 不调用 AgentRuntime / AgentRegistry
- ❌ 不创建 submission / 不 approve / 不 publish

## 6. 文件清单

| 文件 | 操作 |
|------|------|
| `schemas/cognitive-agent.schema.json` | 新增 |
| `examples/developer-agents/*.json` | 新增 (3 files) |
| `sdk/python/cognitive_agent_sdk/` | 新增 (4 files) |
| `src/open_platform/manifest_validator.py` | 新增 |
| `src/api/developer_router.py` | 修改 (+schema +validate) |
| `src/core/usage.py` | 修改 (+2 UsageResources) |
| `tests/test_open_platform/test_manifest_sdk_schema.py` | 新增 (66 tests) |
| `docs/ROADMAP.md` | 修改 (23-H ✅) |

## 7. 测试

- Schema tests: 7
- Backend validator: 29
- SDK: 12
- API endpoints: 10
- Examples: 6
- Open Platform 全量: 601 passed (535 + 66)
- 后端全量回归: 1248 passed (1182 + 66)

## 8. Next Step

Step 23-I：Security + Runtime Tests
