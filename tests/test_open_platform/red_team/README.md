# Sandbox v2 Red-Team / Escape Test Suite

这些测试是 Sandbox v2 安全回归测试，用于验证策略控制面默认拒绝和 fail closed。

## 安全原则

- **不执行真实恶意代码**：所有测试使用纯策略断言和 fixture 数据
- **不联网**：不发起真实 HTTP/DNS 请求
- **不启用真实容器**：不启动 Docker/Podman
- **不杀进程**：只测试策略和命令构建
- **不安装包**：不运行 pip/npm install

## 测试分类

| 文件 | 覆盖风险 |
|------|----------|
| `test_sandbox_v2_red_team_artifact_escape.py` | 路径穿越、危险扩展名、伪装 MIME、超大 artifact、root 外文件访问 |
| `test_sandbox_v2_red_team_network_ssrf.py` | SSRF、内网扫描、metadata 访问、危险 scheme、域名绕过、IP 欺骗 |
| `test_sandbox_v2_red_team_package_supply_chain.py` | 供应链投毒、未签名包、缺 SBOM、缺扫描、危险 URL、路径穿越包名 |
| `test_sandbox_v2_red_team_kill_switch_abuse.py` | 任意 PID kill、跨 org kill、伪造 container_id、terminal 伪装 |
| `test_sandbox_v2_red_team_container_escape.py` | 特权容器、主机网络、docker.sock 挂载、root 用户、custom image/command |
| `test_sandbox_v2_red_team_policy_fail_closed.py` | 策略缺失、异常 fail closed、高风险动作关键字拦截 |
| `test_sandbox_v2_red_team_api_abuse.py` | API 恶意输入、路径穿越、超长字符串、信息泄露 |
| `test_sandbox_v2_red_team_worker_queue_abuse.py` | 重复 lease、dead_letter 逃逸、cancel bypass、future mode auto-execute |

## 运行

```bash
# 运行所有 red-team 测试
python -m pytest tests/test_open_platform/red_team -q -v

# 运行单个类
python -m pytest tests/test_open_platform/red_team -q

# 运行全部 sandbox v2 测试（含 red-team）
python -m pytest tests/test_open_platform/test_sandbox_v2_*.py tests/test_open_platform/red_team -q
```

## 断言标准

- 所有危险输入 → `rejected` / `failed` / `quarantined`
- 异常/缺失输入 → `fail_closed=true`, `allowed=false`
- 不泄露本地路径、stack trace
- API 不返回 500
