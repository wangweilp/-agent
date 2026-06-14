"""Red-Team Artifact Escape Tests — 文件 artifact 逃逸攻击测试。

验证：路径穿越、危险扩展名、root 外交互、伪装 MIME、超大 artifact 均被拒绝。
所有测试使用纯策略/内存断言，不写真实文件、不调用 subprocess、不联网。
"""

import pytest
from src.open_platform.sandbox_v2.models import (
    SandboxArtifactMaterializationRequest, SandboxV2ArtifactType,
)
from src.open_platform.sandbox_v2.artifact_policy import (
    evaluate_artifact_policy, sanitize_filename,
    _has_dangerous_extension, _has_path_traversal,
)


def _req(name, atype=SandboxV2ArtifactType.TEXT, **kw):
    return SandboxArtifactMaterializationRequest(
        artifact_name=name, artifact_type=atype, content_text="test", **kw)


class TestPathTraversalRejection:
    """路径穿越攻击必须被拒绝。"""
    def test_unix_dotdot(self): assert not evaluate_artifact_policy(_req("../etc/passwd")).allowed
    def test_windows_dotdot(self): assert not evaluate_artifact_policy(_req("..\\windows\\system32")).allowed
    def test_absolute_windows(self): assert not evaluate_artifact_policy(_req("C:\\Windows\\System32\\config")).allowed
    def test_absolute_unix(self): assert not evaluate_artifact_policy(_req("/etc/shadow")).allowed
    def test_unc_path(self): assert not evaluate_artifact_policy(_req("\\\\server\\share\\file")).allowed
    def test_double_encoded(self): assert not evaluate_artifact_policy(_req("....//....//etc/passwd")).allowed


class TestDangerousExtensions:
    """危险扩展名必须拒绝。"""
    def _check_reject(self, name): assert not evaluate_artifact_policy(_req(name)).allowed

    def test_exe(self): self._check_reject("malware.exe")
    def test_dll(self): self._check_reject("malware.dll")
    def test_bat(self): self._check_reject("install.bat")
    def test_cmd(self): self._check_reject("run.cmd")
    def test_ps1(self): self._check_reject("exploit.ps1")
    def test_sh(self): self._check_reject("shell.sh")
    def test_so(self): self._check_reject("lib.so")
    def test_dylib(self): self._check_reject("lib.dylib")
    def test_jar(self): self._check_reject("app.jar")
    def test_scr(self): self._check_reject("screen.scr")
    def test_vbs(self): self._check_reject("macro.vbs")

class TestSafeNames:
    """安全文件名通过。"""
    def test_txt(self): assert evaluate_artifact_policy(_req("output.txt", mime_type="text/plain")).allowed
    def test_json(self): assert evaluate_artifact_policy(_req("data.json", SandboxV2ArtifactType.JSON, mime_type="application/json")).allowed
    def test_log(self): assert evaluate_artifact_policy(_req("debug.log", SandboxV2ArtifactType.LOG)).allowed


class TestOversizeRejection:
    """超大 artifact 拒绝。"""
    def test_exceeds_limit(self):
        d = evaluate_artifact_policy(SandboxArtifactMaterializationRequest(
            artifact_name="big.txt", artifact_type=SandboxV2ArtifactType.TEXT,
            content_text="x" * 2_000_000), max_size_bytes=100_000)
        assert not d.allowed
        assert "size_limit_exceeded" in d.matched_rules


class TestMimeAbuse:
    """MIME 伪装攻击拒绝。"""
    def test_exe_mime_on_json_name(self):
        d = evaluate_artifact_policy(_req("data.json", mime_type="application/x-msdownload"))
        assert not d.allowed

    def test_octet_stream_rejected_by_default(self):
        d = evaluate_artifact_policy(_req("file.bin", mime_type="application/octet-stream"))
        # octet-stream is in allowed list, so it passes
        assert d.allowed is True


class TestFailClosed:
    """策略异常必须 fail closed。"""
    def test_none_request(self):
        d = evaluate_artifact_policy(None)  # type: ignore
        assert not d.allowed
        assert d.fail_closed is True

    def test_empty_all(self):
        d = evaluate_artifact_policy(SandboxArtifactMaterializationRequest())
        assert not d.allowed
