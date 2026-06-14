"""Sandbox v2 Core Contract — Step 1 工程基础。

本模块建立 Sandbox v2 的数据模型、策略模型、执行记录、状态流转、只读模拟 API。
不实现真实第三方代码执行、Docker、MicroVM、不可信代码运行。

能力边界：
- 核心数据模型 (SandboxJob, SandboxExecutionRecord, SandboxPolicyV2, ...)
- 策略引擎 (默认 deny / fail closed)
- Store 接口 + SQLite 默认实现
- Service 层 (模拟执行，不运行代码)
- FastAPI 路由
"""
