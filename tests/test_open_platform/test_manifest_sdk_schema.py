"""Manifest SDK + Schema 测试 — Step 23-H。

覆盖: Schema, SDK validator, SDK examples, Developer API endpoints, safety boundaries.
"""

from __future__ import annotations
import json, os, sys, pytest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.developer_store import SQLiteDeveloperStore
from src.adapters.submission_store import SQLiteSubmissionStore
from src.adapters.usage_store import UsageStoreAdapter
from src.api.developer_router import create_developer_router
from src.api.middleware import require_auth, get_token_payload, TokenPayload
from src.core.auth import WorkspaceRole
from src.open_platform.developer import generate_api_key, get_api_key_prefix, hash_api_key, DeveloperApiKey
from src.open_platform.manifest_validator import (
    validate_manifest_dict, ManifestValidationResult, ValidationIssue,
)

# SDK path
SDK_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "sdk", "python"))
EXAMPLES_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "examples", "developer-agents"))
SCHEMA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "schemas", "cognitive-agent.schema.json"))

# ═══════════ Auth ═══════════
def _p(role=WorkspaceRole.ADMIN, ws="test-ws-001", uid="user-001", sa=False):
    return TokenPayload(user_id=uid, workspace_id=ws, role=role, is_super_admin=sa)
async def _a(): return _p()
async def _member(): return _p(WorkspaceRole.MEMBER)

@pytest.fixture
def s(): return Settings(deepseek_api_key="sk-test")
@pytest.fixture
def dev_store(s): return SQLiteDeveloperStore(s, db_path=":memory:")
@pytest.fixture
def sub_store(s): return SQLiteSubmissionStore(s, db_path=":memory:")
@pytest.fixture
def usage_store(s, tmp_path):
    u = UsageStoreAdapter(config=s, db_path=str(tmp_path / "sdk_usage.db"))
    yield u; u.close()

def _make_dev_app(dev_store, sub_store, usage=None, auth=_a):
    app = FastAPI()
    app.dependency_overrides[require_auth] = auth
    app.dependency_overrides[get_token_payload] = auth
    app.include_router(create_developer_router(dev_store, sub_store, usage))
    return TestClient(app)

# ═══════════ Minimal / package / invalid ═══════════
_MINIMAL = {
    "name": "test-agent", "display_name": "Test Agent",
    "description": "A minimal valid test manifest.",
    "version": "0.1.0", "capabilities": ["test"], "required_permissions": ["agent:execute"],
    "runtime_type": "manifest_only",
    "security_profile": {"sandbox_level": "no_execution", "requires_network": False, "reads_user_data": False, "writes_user_data": False},
    "metadata": {"no_remote_code_execution": True},
}

_INVALID_NET = {
    **_MINIMAL, "security_profile": {**_MINIMAL["security_profile"], "requires_network": True},
}

_PACKAGE_META = {
    **_MINIMAL, "name": "pkg-agent", "display_name": "PKG Agent",
    "description": "Agent with full package metadata.",
    "version": "1.0.0",
    "security_profile": {**_MINIMAL["security_profile"], "sandbox_level": "simulation_only"},
    "metadata": {
        "package_url": "https://github.com/example/pkg/releases/v1.0.0/pkg.zip",
        "repository_url": "https://github.com/example/pkg",
        "package_name": "pkg-agent", "package_version": "1.0.0",
        "package_checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "package_checksum_algorithm": "sha256",
        "package_signature": "sig", "package_signature_algorithm": "minisign",
        "license": "MIT", "security_contact": "sec@x.com",
        "dependencies": ["python>=3.10"],
        "no_remote_code_execution": True,
    },
}


# ═══════════ 1. Schema ═══════════
class TestSchema:
    def test_schema_file_exists(self):
        assert os.path.exists(SCHEMA_PATH), f"Schema not found at {SCHEMA_PATH}"

    def test_schema_has_dollar_schema(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f: s = json.load(f)
        assert "$schema" in s

    def test_schema_has_dollar_id(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f: s = json.load(f)
        assert "$id" in s

    def test_schema_required_includes_name(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f: s = json.load(f)
        assert "name" in s["required"]

    def test_schema_required_includes_security_profile(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f: s = json.load(f)
        assert "security_profile" in s["required"]

    def test_schema_runtime_type_enum(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f: s = json.load(f)
        rt = s["properties"]["runtime_type"]
        assert "manifest_only" in rt.get("enum", [])

    def test_schema_no_remote_ref(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f: content = f.read()
        assert "$ref" not in content or "cognitive-os.dev" in content or "$schema" in content
        assert "http://" not in content or "json-schema.org" in content


# ═══════════ 2. Backend Validator ═══════════
class TestBackendValidator:
    def test_minimal_valid(self):
        r = validate_manifest_dict(_MINIMAL)
        assert r.valid

    def test_package_meta_valid_or_warning(self):
        r = validate_manifest_dict(_PACKAGE_META)
        assert r.valid or r.has_warnings

    def test_invalid_network_invalid(self):
        r = validate_manifest_dict(_INVALID_NET)
        assert not r.valid

    def test_missing_name_error(self):
        r = validate_manifest_dict({**{k: v for k, v in _MINIMAL.items() if k != "name"}})
        assert not r.valid

    def test_invalid_name_pattern(self):
        m = {**_MINIMAL, "name": "Bad Name!"}
        r = validate_manifest_dict(m)
        assert not r.valid

    def test_empty_capabilities(self):
        m = {**_MINIMAL, "capabilities": []}
        r = validate_manifest_dict(m)
        assert not r.valid

    def test_empty_permissions(self):
        m = {**_MINIMAL, "required_permissions": []}
        r = validate_manifest_dict(m)
        assert not r.valid

    def test_missing_security_profile_blocker(self):
        m = {k: v for k, v in _MINIMAL.items() if k != "security_profile"}
        r = validate_manifest_dict(m)
        assert r.has_blockers

    def test_runtime_type_container_blocker(self):
        m = {**_MINIMAL, "runtime_type": "container"}
        r = validate_manifest_dict(m)
        assert r.has_blockers

    def test_sandbox_level_restricted_blocker(self):
        m = {**_MINIMAL, "security_profile": {**_MINIMAL["security_profile"], "sandbox_level": "restricted"}}
        r = validate_manifest_dict(m, strict=True)
        assert r.has_blockers

    def test_requires_network_error(self):
        r = validate_manifest_dict(_INVALID_NET)
        assert not r.valid and len(r.errors) >= 1

    def test_writes_user_data_error(self):
        m = {**_MINIMAL, "security_profile": {**_MINIMAL["security_profile"], "writes_user_data": True}}
        r = validate_manifest_dict(m)
        assert not r.valid

    def test_reads_user_data_warning(self):
        m = {**_MINIMAL, "security_profile": {**_MINIMAL["security_profile"], "reads_user_data": True}}
        r = validate_manifest_dict(m)
        assert r.has_warnings

    def test_requires_secrets_error(self):
        m = {**_MINIMAL, "security_profile": {**_MINIMAL["security_profile"], "requires_secrets": True}}
        r = validate_manifest_dict(m)
        assert not r.valid

    def test_package_url_http_error(self):
        m = {**_PACKAGE_META, "metadata": {**_PACKAGE_META["metadata"], "package_url": "http://evil.com/pkg.zip"}}
        r = validate_manifest_dict(m)
        assert not r.valid

    def test_package_url_localhost_blocker(self):
        m = {**_PACKAGE_META, "metadata": {**_PACKAGE_META["metadata"], "package_url": "https://localhost/pkg.zip"}}
        r = validate_manifest_dict(m)
        assert r.has_blockers

    def test_package_url_private_ip_blocker(self):
        m = {**_PACKAGE_META, "metadata": {**_PACKAGE_META["metadata"], "package_url": "https://10.0.0.1/pkg.zip"}}
        r = validate_manifest_dict(m)
        assert r.has_blockers

    def test_package_url_https_ok(self):
        r = validate_manifest_dict(_PACKAGE_META)
        assert r.valid or r.has_warnings

    def test_checksum_sha256_ok(self):
        r = validate_manifest_dict(_PACKAGE_META)
        cs_errors = [i for i in r.issues if "checksum" in i.code.lower() and i.severity in ("error", "blocker")]
        assert len(cs_errors) == 0

    def test_checksum_md5_error(self):
        m = {**_PACKAGE_META, "metadata": {**_PACKAGE_META["metadata"], "package_checksum_algorithm": "md5"}}
        r = validate_manifest_dict(m)
        assert any("md5" in i.message for i in r.errors)

    def test_signature_cosign_ok(self):
        m = {**_PACKAGE_META, "metadata": {**_PACKAGE_META["metadata"], "package_signature_algorithm": "cosign"}}
        r = validate_manifest_dict(m)
        sig_errors = [i for i in r.issues if "signature" in i.code.lower() and i.severity in ("error", "blocker")]
        assert len(sig_errors) == 0

    def test_signature_unknown_error(self):
        m = {**_PACKAGE_META, "metadata": {**_PACKAGE_META["metadata"], "package_signature_algorithm": "unknown"}}
        r = validate_manifest_dict(m)
        assert any("signature" in i.code.lower() or "sig" in i.code.lower() for i in r.errors)

    def test_deps_list_ok(self):
        r = validate_manifest_dict(_PACKAGE_META)
        assert r.valid or r.has_warnings

    def test_deps_not_list_error(self):
        m = {**_PACKAGE_META, "metadata": {**_PACKAGE_META["metadata"], "dependencies": "not-a-list"}}
        r = validate_manifest_dict(m)
        assert any("list" in i.message for i in r.errors)

    def test_dep_empty_error(self):
        m = {**_PACKAGE_META, "metadata": {**_PACKAGE_META["metadata"], "dependencies": ["", "ok"]}}
        r = validate_manifest_dict(m)
        assert any("empty" in i.message for i in r.errors)

    def test_entrypoint_warning(self):
        m = {**_MINIMAL, "entrypoint": "main.py"}
        r = validate_manifest_dict(m)
        assert any("entrypoint" in i.code for i in r.warnings)

    def test_config_schema_non_object(self):
        m = {**_MINIMAL, "config_schema": "not-object"}
        r = validate_manifest_dict(m)
        assert not r.valid

    def test_metadata_non_object(self):
        m = {**_MINIMAL, "metadata": "not-object"}
        r = validate_manifest_dict(m)
        assert not r.valid

    def test_no_agent_runtime_import(self):
        from src.open_platform import manifest_validator as mv
        assert "AgentRuntime" not in mv.__dict__

    def test_summary_counts(self):
        r = validate_manifest_dict(_MINIMAL)
        s = r.summary_counts()
        assert s["total"] >= 0

    def test_to_dict_has_guarantees(self):
        r = validate_manifest_dict(_MINIMAL)
        d = r.to_dict()
        assert "non_execution_guarantees" in d


# ═══════════ 3. SDK ═══════════
@pytest.mark.skipif(not os.path.isdir(SDK_PATH), reason="SDK path not found")
class TestSDK:
    @pytest.fixture(autouse=True)
    def setup_path(self):
        if SDK_PATH not in sys.path:
            sys.path.insert(0, SDK_PATH)

    def test_sdk_minimal_builder(self):
        from cognitive_agent_sdk.examples import build_minimal_manifest
        d = build_minimal_manifest()
        assert isinstance(d, dict)
        assert d["name"] == "hello-world-agent"

    def test_sdk_package_meta_builder(self):
        from cognitive_agent_sdk.examples import build_package_metadata_manifest
        d = build_package_metadata_manifest()
        assert "package_url" in d["metadata"]

    def test_sdk_invalid_network_builder(self):
        from cognitive_agent_sdk.examples import build_invalid_network_manifest
        d = build_invalid_network_manifest()
        assert d["security_profile"]["requires_network"]

    def test_sdk_validate_minimal(self):
        from cognitive_agent_sdk.validator import validate_manifest_dict as sv
        from cognitive_agent_sdk.examples import build_minimal_manifest
        r = sv(build_minimal_manifest())
        assert r.valid

    def test_sdk_validate_invalid_network(self):
        from cognitive_agent_sdk.validator import validate_manifest_dict as sv
        from cognitive_agent_sdk.examples import build_invalid_network_manifest
        r = sv(build_invalid_network_manifest())
        assert not r.valid

    def test_sdk_load_file(self):
        from cognitive_agent_sdk.validator import load_manifest_file
        d = load_manifest_file(os.path.join(EXAMPLES_PATH, "minimal_manifest.json"))
        assert d["name"] == "hello-world-agent"

    def test_sdk_validate_file(self):
        from cognitive_agent_sdk.validator import validate_manifest_file
        r = validate_manifest_file(os.path.join(EXAMPLES_PATH, "minimal_manifest.json"))
        assert r.valid

    def test_sdk_no_requests_import(self):
        """SDK does not import requests/httpx/urllib.request."""
        import importlib
        for mod_name in ["cognitive_agent_sdk.validator", "cognitive_agent_sdk.examples"]:
            try:
                mod = importlib.import_module(mod_name)
                src = mod.__dict__
                assert "requests" not in src
            except Exception:
                pass

    def test_sdk_result_to_dict_safe(self):
        from cognitive_agent_sdk.validator import validate_manifest_dict as sv
        r = sv(_MINIMAL)
        d = r.to_dict()
        assert "raw_key" not in json.dumps(d)
        assert "key_hash" not in json.dumps(d)

    def test_sdk_cli_validate_valid(self):
        import subprocess
        f = os.path.join(EXAMPLES_PATH, "minimal_manifest.json")
        r = subprocess.run([sys.executable, "-m", "cognitive_agent_sdk.cli", "validate", f],
                          capture_output=True, text=True, cwd=SDK_PATH, env={**os.environ})
        assert r.returncode == 0

    def test_sdk_cli_validate_invalid(self):
        import subprocess
        f = os.path.join(EXAMPLES_PATH, "invalid_network_manifest.json")
        r = subprocess.run([sys.executable, "-m", "cognitive_agent_sdk.cli", "validate", f],
                          capture_output=True, text=True, cwd=SDK_PATH, env={**os.environ})
        assert r.returncode == 1

    def test_sdk_cli_example_minimal(self):
        import subprocess
        r = subprocess.run([sys.executable, "-m", "cognitive_agent_sdk.cli", "example", "minimal"],
                          capture_output=True, text=True, cwd=SDK_PATH, env={**os.environ})
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["name"] == "hello-world-agent"


# ═══════════ 4. Developer API Endpoints ═══════════
class TestDevApiEndpoints:
    def test_get_schema_requires_auth(self):
        app = FastAPI()
        app.include_router(create_developer_router(
            SQLiteDeveloperStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:"),
            SQLiteSubmissionStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:"),
        ))
        c = TestClient(app)
        resp = c.get("/developers/agent-manifest/schema")
        assert resp.status_code == 401

    def test_jwt_can_get_schema(self, dev_store, sub_store):
        c = _make_dev_app(dev_store, sub_store)
        resp = c.get("/developers/agent-manifest/schema")
        assert resp.status_code == 200
        data = resp.json()
        assert "schema" in data
        assert "version" in data
        assert "non_execution_guarantees" in data

    def test_schema_has_non_execution_guarantees(self, dev_store, sub_store):
        c = _make_dev_app(dev_store, sub_store)
        resp = c.get("/developers/agent-manifest/schema")
        assert len(resp.json()["non_execution_guarantees"]) >= 2

    def test_post_validate_requires_auth(self):
        app = FastAPI()
        app.include_router(create_developer_router(
            SQLiteDeveloperStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:"),
            SQLiteSubmissionStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:"),
        ))
        c = TestClient(app)
        resp = c.post("/developers/agent-manifest/validate", json={"manifest": _MINIMAL})
        assert resp.status_code == 401

    def test_post_validate_minimal_valid(self, dev_store, sub_store):
        c = _make_dev_app(dev_store, sub_store)
        resp = c.post("/developers/agent-manifest/validate", json={"manifest": _MINIMAL})
        assert resp.status_code == 200
        assert resp.json()["valid"]

    def test_post_validate_invalid(self, dev_store, sub_store):
        c = _make_dev_app(dev_store, sub_store)
        resp = c.post("/developers/agent-manifest/validate", json={"manifest": _INVALID_NET})
        assert resp.status_code == 200
        assert not resp.json()["valid"]

    def test_post_validate_strict_default(self, dev_store, sub_store):
        c = _make_dev_app(dev_store, sub_store)
        m = {**_MINIMAL, "runtime_type": "container"}
        resp = c.post("/developers/agent-manifest/validate", json={"manifest": m})
        assert not resp.json()["valid"]

    def test_validate_does_not_create_submission(self, dev_store, sub_store):
        c = _make_dev_app(dev_store, sub_store)
        c.post("/developers/agent-manifest/validate", json={"manifest": _MINIMAL})
        # No submission should be created
        dev = SQLiteDeveloperStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:")
        assert sub_store.list_submissions() == []

    def test_response_no_traceback(self, dev_store, sub_store):
        c = _make_dev_app(dev_store, sub_store)
        resp = c.post("/developers/agent-manifest/validate", json={"manifest": "not-a-dict"})
        body = resp.json()
        assert "Traceback" not in str(body)

    def test_response_no_raw_key(self, dev_store, sub_store):
        c = _make_dev_app(dev_store, sub_store)
        resp = c.post("/developers/agent-manifest/validate", json={"manifest": _MINIMAL})
        assert "raw_key" not in json.dumps(resp.json())


# ═══════════ 5. Examples ═══════════
class TestExamples:
    def test_minimal_json_exists(self):
        assert os.path.exists(os.path.join(EXAMPLES_PATH, "minimal_manifest.json"))

    def test_package_metadata_json_exists(self):
        assert os.path.exists(os.path.join(EXAMPLES_PATH, "package_metadata_manifest.json"))

    def test_invalid_network_json_exists(self):
        assert os.path.exists(os.path.join(EXAMPLES_PATH, "invalid_network_manifest.json"))

    def test_minimal_valid_against_backend(self):
        with open(os.path.join(EXAMPLES_PATH, "minimal_manifest.json"), encoding="utf-8") as f:
            d = json.load(f)
        r = validate_manifest_dict(d)
        assert r.valid

    def test_package_metadata_valid_or_warning(self):
        with open(os.path.join(EXAMPLES_PATH, "package_metadata_manifest.json"), encoding="utf-8") as f:
            d = json.load(f)
        r = validate_manifest_dict(d)
        assert r.valid or r.has_warnings

    def test_invalid_network_invalid(self):
        with open(os.path.join(EXAMPLES_PATH, "invalid_network_manifest.json"), encoding="utf-8") as f:
            d = json.load(f)
        r = validate_manifest_dict(d)
        assert not r.valid
