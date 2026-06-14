"""Test Sandbox v2 Artifact Policy — artifact 策略测试。

覆盖：
1. 正常 text artifact 通过
2. ../ 路径穿越被拒绝
3. Windows drive path 被拒绝
4. absolute path 被拒绝
5. 危险扩展名 .exe / .bat / .ps1 / .sh 被拒绝
6. 超过大小限制被拒绝
7. 不允许 MIME 类型被拒绝
8. 文件名 sanitize
9. unknown artifact_type 被拒绝
10. 策略字段缺失 fail closed
"""
import pytest

from src.open_platform.sandbox_v2.models import (
    SandboxArtifactMaterializationRequest,
    SandboxV2ArtifactType,
    SandboxV2RiskLevel,
)
from src.open_platform.sandbox_v2.artifact_policy import (
    evaluate_artifact_policy,
    sanitize_filename,
    _has_dangerous_extension,
    _has_path_traversal,
)


class TestSanitizeFilename:
    def test_safe_filename_unchanged(self):
        assert sanitize_filename("output.log") == "output.log"

    def test_path_traversal_removed(self):
        sanitized = sanitize_filename("../../../etc/passwd")
        assert ".." not in sanitized
        assert sanitized != "../../../etc/passwd"

    def test_null_byte_removed(self):
        sanitized = sanitize_filename("test\x00.txt")
        assert "\x00" not in sanitized

    def test_empty_returns_default(self):
        assert len(sanitize_filename("")) > 0
        assert len(sanitize_filename("...")) > 0


class TestDangerousExtensions:
    def test_exe_rejected(self):
        assert _has_dangerous_extension("malware.exe") is True

    def test_bat_rejected(self):
        assert _has_dangerous_extension("install.bat") is True

    def test_ps1_rejected(self):
        assert _has_dangerous_extension("script.ps1") is True

    def test_sh_rejected(self):
        assert _has_dangerous_extension("run.sh") is True

    def test_dll_rejected(self):
        assert _has_dangerous_extension("library.dll") is True

    def test_txt_allowed(self):
        assert _has_dangerous_extension("output.txt") is False

    def test_json_allowed(self):
        assert _has_dangerous_extension("data.json") is False


class TestPathTraversal:
    def test_dot_dot_slash_rejected(self):
        assert _has_path_traversal("../etc/passwd") is True

    def test_dot_dot_backslash_rejected(self):
        assert _has_path_traversal("..\\windows\\system32") is True

    def test_windows_drive_rejected(self):
        assert _has_path_traversal("C:\\Windows\\System32") is True

    def test_absolute_unix_rejected(self):
        assert _has_path_traversal("/etc/passwd") is True

    def test_unc_rejected(self):
        assert _has_path_traversal("\\\\server\\share") is True

    def test_safe_path_ok(self):
        assert _has_path_traversal("output.log") is False
        assert _has_path_traversal("subdir/report.json") is False


class TestArtifactPolicy:
    def _make_req(self, **kw):
        return SandboxArtifactMaterializationRequest(
            artifact_name=kw.get("artifact_name", "test.txt"),
            artifact_type=kw.get("artifact_type", SandboxV2ArtifactType.TEXT),
            content_text=kw.get("content_text", "hello sandbox"),
            mime_type=kw.get("mime_type", "text/plain"),
            **{k: v for k, v in kw.items() if k not in ("artifact_name", "artifact_type", "content_text", "mime_type")},
        )

    def test_normal_text_artifact_allowed(self):
        """正常 text artifact 可以物化。"""
        req = self._make_req(content_text="test content")
        decision = evaluate_artifact_policy(req)
        assert decision.allowed is True

    def test_path_traversal_denied(self):
        """../ 路径穿越被拒绝。"""
        req = self._make_req(artifact_name="../etc/passwd")
        decision = evaluate_artifact_policy(req)
        assert decision.allowed is False
        assert "path_traversal_blocked" in decision.matched_rules

    def test_windows_drive_denied(self):
        """Windows drive path 被拒绝。"""
        req = self._make_req(artifact_name="C:\\Windows\\test.txt")
        decision = evaluate_artifact_policy(req)
        assert decision.allowed is False

    def test_absolute_path_denied(self):
        """absolute path 被拒绝。"""
        req = self._make_req(artifact_name="/etc/test.txt")
        decision = evaluate_artifact_policy(req)
        assert decision.allowed is False

    def test_dangerous_exe_denied(self):
        """危险扩展名 .exe 被拒绝。"""
        req = self._make_req(artifact_name="malware.exe", mime_type="application/octet-stream")
        decision = evaluate_artifact_policy(req)
        assert decision.allowed is False
        assert "dangerous_extension" in decision.matched_rules

    def test_dangerous_bat_denied(self):
        """危险扩展名 .bat 被拒绝。"""
        req = self._make_req(artifact_name="install.bat")
        decision = evaluate_artifact_policy(req)
        assert decision.allowed is False

    def test_size_limit_exceeded_denied(self):
        """超过大小限制被拒绝。"""
        big_content = "x" * 2_000_000  # 2 MB
        req = self._make_req(content_text=big_content)
        decision = evaluate_artifact_policy(req, max_size_bytes=1_000_000)
        assert decision.allowed is False
        assert "size_limit_exceeded" in decision.matched_rules

    def test_invalid_mime_denied(self):
        """不允许 MIME 类型被拒绝。"""
        req = self._make_req(mime_type="application/x-msdownload")
        decision = evaluate_artifact_policy(req)
        assert decision.allowed is False
        assert "mime_type_denied" in decision.matched_rules

    def test_unknown_artifact_type_denied(self):
        """unknown artifact_type 被拒绝。"""
        req = self._make_req(artifact_type="executable")
        decision = evaluate_artifact_policy(req)
        assert decision.allowed is False
        assert "artifact_type_unknown" in decision.matched_rules

    def test_missing_artifact_type_fail_closed(self):
        """artifact_type 缺失 fail closed。"""
        req = self._make_req(artifact_type="")
        decision = evaluate_artifact_policy(req)
        assert decision.allowed is False
        assert decision.fail_closed is True

    def test_exception_fail_closed(self):
        """异常时 fail closed。"""
        decision = evaluate_artifact_policy(None)  # type: ignore
        assert decision.allowed is False
        assert decision.fail_closed is True
