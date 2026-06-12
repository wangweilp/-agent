"""Trusted Fixture Registry — static built-in fixtures only. No dynamic import/eval/exec/subprocess/network/filesystem/secrets."""
from __future__ import annotations
from hashlib import sha256
from typing import Any
from .trusted_fixture_execution import *

class TrustedFixtureRegistry:
    def __init__(self):
        self._fixtures: dict[str,TrustedFixtureDefinition] = {}
        self._register_builtins()

    def _register_builtins(self):
        for f in [
            TrustedFixtureDefinition(fixture_id="tfix_noop_builtin",fixture_name="Noop",fixture_kind=TrustedFixtureKind.NOOP,description="No-operation fixture. Returns ok.",allowed_input_keys=[],output_schema_version="1.0.0"),
            TrustedFixtureDefinition(fixture_id="tfix_echo_metadata_builtin",fixture_name="Echo Metadata",fixture_kind=TrustedFixtureKind.ECHO_METADATA,description="Echoes sanitized input metadata keys and hash.",allowed_input_keys=["*"],max_input_size_bytes=4096,output_schema_version="1.0.0"),
            TrustedFixtureDefinition(fixture_id="tfix_policy_proof_summary_builtin",fixture_name="Policy Proof Summary",fixture_kind=TrustedFixtureKind.POLICY_PROOF_SUMMARY,description="Summarizes enforcement proof status.",allowed_input_keys=["proof_status","decision","blockers_count","warnings_count","scope"],output_schema_version="1.0.0"),
            TrustedFixtureDefinition(fixture_id="tfix_queue_gate_summary_builtin",fixture_name="Queue Gate Summary",fixture_kind=TrustedFixtureKind.QUEUE_GATE_SUMMARY,description="Summarizes queue gate decision and enabled flags.",allowed_input_keys=["queue_enabled","dispatch_enabled","decision","status"],output_schema_version="1.0.0"),
            TrustedFixtureDefinition(fixture_id="tfix_static_health_check_builtin",fixture_name="Static Health Check",fixture_kind=TrustedFixtureKind.STATIC_HEALTH_CHECK,description="Returns fixture registry health metadata.",allowed_input_keys=[],output_schema_version="1.0.0"),
        ]:
            self._fixtures[f.fixture_id] = f

    def list_fixtures(self) -> list[TrustedFixtureDefinition]: return list(self._fixtures.values())
    def get_fixture(self, fixture_id: str) -> TrustedFixtureDefinition | None: return self._fixtures.get(fixture_id)
    def is_fixture_allowed(self, fixture_id: str) -> bool:
        f = self._fixtures.get(fixture_id)
        return f is not None and f.fixture_status == TrustedFixtureStatus.AVAILABLE

    def run_trusted_fixture(self, fixture_id: str, input_metadata: dict[str,Any]) -> dict[str,Any]:
        f = self._fixtures.get(fixture_id)
        if f is None: return {"ok":False,"error":"fixture_not_found","fixture_id":fixture_id}
        if f.fixture_status != TrustedFixtureStatus.AVAILABLE: return {"ok":False,"error":"fixture_disabled","fixture_id":fixture_id}
        # Sanitize input
        safe_input = {k: (str(v)[:200] if not isinstance(v,(dict,list)) else "<complex>") for k,v in (input_metadata or {}).items() if k in f.allowed_input_keys or "*" in f.allowed_input_keys}

        if f.fixture_kind == TrustedFixtureKind.NOOP:
            return {"ok":True,"fixture":"noop","input_keys":list(safe_input.keys())}
        elif f.fixture_kind == TrustedFixtureKind.ECHO_METADATA:
            return {"ok":True,"fixture":"echo_metadata","input_keys":list(safe_input.keys()),"input_hash":sha256(str(safe_input).encode()).hexdigest()[:16]}
        elif f.fixture_kind == TrustedFixtureKind.POLICY_PROOF_SUMMARY:
            return {"ok":True,"fixture":"policy_proof_summary","proof_status":safe_input.get("proof_status",""),"decision":safe_input.get("decision",""),"blockers":safe_input.get("blockers_count","0"),"warnings":safe_input.get("warnings_count","0")}
        elif f.fixture_kind == TrustedFixtureKind.QUEUE_GATE_SUMMARY:
            return {"ok":True,"fixture":"queue_gate_summary","queue_enabled":safe_input.get("queue_enabled","false"),"dispatch_enabled":safe_input.get("dispatch_enabled","false"),"decision":safe_input.get("decision","")}
        elif f.fixture_kind == TrustedFixtureKind.STATIC_HEALTH_CHECK:
            return {"ok":True,"fixture":"static_health_check","fixture_count":len(self._fixtures),"available_fixtures":[x.fixture_id for x in self._fixtures.values() if x.fixture_status==TrustedFixtureStatus.AVAILABLE],"third_party_execution_enabled":False,"package_execution_enabled":False}
        return {"ok":False,"error":"unknown_fixture_kind","fixture_id":fixture_id}
