"""Sandbox v2 performance smoke script tests (Step 16)."""
import json
import subprocess
import sys

from scripts.run_sandbox_v2_performance_smoke import run_performance_smoke


def test_script_unenabled_returns_skipped(monkeypatch):
    monkeypatch.setenv("SANDBOX_V2_PERF_TESTS_ENABLED", "false")
    result = run_performance_smoke(force_smoke=False)
    assert result["status"] == "skipped"
    assert result["total_operations"] == 0


def test_force_smoke_limits_data(monkeypatch, tmp_path):
    monkeypatch.setenv("SANDBOX_V2_PERF_OUTPUT_DIR", str(tmp_path / "reports"))
    result = run_performance_smoke(force_smoke=True)
    assert result["profile"] == "smoke"
    assert result["total_operations"] <= 12
    assert result["synthetic_fixture_only"] is True
    assert result["external_network"] is False
    assert result["container_execution"] is False
    assert result["microvm_execution"] is False


def test_script_json_mode_outputs_json(monkeypatch, tmp_path):
    monkeypatch.setenv("SANDBOX_V2_PERF_TESTS_ENABLED", "false")
    proc = subprocess.run(
        [sys.executable, "scripts/run_sandbox_v2_performance_smoke.py", "--json"],
        check=True,
        text=True,
        capture_output=True,
    )
    parsed = json.loads(proc.stdout)
    assert parsed["status"] == "skipped"


def test_script_output_no_secret(monkeypatch):
    monkeypatch.setenv("SANDBOX_V2_PERF_TESTS_ENABLED", "false")
    result = run_performance_smoke(force_smoke=False)
    text = json.dumps(result)
    assert "SECRET" not in text.upper()
    assert "POSTGRES_DSN" not in text
    assert "ACCESS_KEY" not in text
