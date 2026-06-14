"""Sandbox v2 Red-Team Test Runner — 安全回归测试执行脚本。

运行所有 red-team 测试并输出简短 summary。
不执行真实恶意代码，不联网，不启用真实容器。
"""

import subprocess, sys, os

def main():
    red_team_dir = os.path.join(os.path.dirname(__file__), "..", "tests", "test_open_platform", "red_team")
    if not os.path.isdir(red_team_dir):
        print("ERROR: red_team directory not found.")
        sys.exit(1)

    cmd = [sys.executable, "-m", "pytest", red_team_dir, "-q", "--tb=short"]
    print(f"Running: {' '.join(cmd)}")
    print("=" * 60)

    result = subprocess.run(cmd, cwd=os.path.dirname(red_team_dir))

    print("=" * 60)
    if result.returncode == 0:
        print("Red-Team Suite: ALL PASSED ✓")
        print("Sandbox v2 control plane security verified.")
    else:
        print(f"Red-Team Suite: FAILURES DETECTED (exit {result.returncode})")
        print("Review failures above. Do NOT relax security rules to pass.")

    print("No real malicious code was executed. No network access occurred.")
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
