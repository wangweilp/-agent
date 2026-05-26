# CLAUDE.md — 项目运行时规则

> 本文件由 Claude Code 在每次对话启动时自动加载。
> 以下规则优先级从高到低排列。当规则冲突时，编号小的优先。

---

## 1. 绝对红线（不可违反）

### 1.1 架构隔离
- `src/core/` **禁止** 导入 `src/adapters/`、`src/api/`、`src/tools/`，也禁止导入任何第三方库（`openai`、`chromadb`、`sqlite_utils` 等）。
- `src/core/` 只能使用标准库和自身定义的 Protocol/ABC 抽象。
- 任何跨层依赖都通过 `main.py` 的依赖注入完成，不在模块内部 new 具体实现。

### 1.2 文件修改隔离
- **每次只改一个模块**。如果你需要同时动 `core/` 和 `adapters/`，先完成一个、确认无误，再动下一个。
- 修改前先用 `rg` 搜索该符号的所有引用，确保理解影响面。
- 修改后立即运行相关测试，不通过不进入下一步。

### 1.3 Git 提交纪律
- 每完成一个独立功能点立即提交，不要攒一堆文件一次性提交。
- 提交信息严格遵循 `type(scope): subject` 格式（详见 `docs/DEV_GUIDE.md`）。
- 不提交 `.env`、`chroma_db/`、`*.db`、`data/` 等运行时产物。
- 每次提交前执行 `git diff --staged` 确认改动内容与意图一致。

### 1.4 禁止沉默破坏
- 如果发现现有代码的问题，**先报告，后修改**。不要静默重写你认为"不对"的代码。
- 如果必须破坏性变更，在提交信息中标注 `BREAKING CHANGE:` 并在 `docs/adr/` 中记录。

---

## 2. 开发流程规则

### 2.1 开始任何功能前（5 分钟检视）
```
1. 读取 docs/ROADMAP.md，确认当前版本目标
2. 读取 docs/ARCHITECTURE.md 中相关模块的边界定义
3. 检查 git status，确认当前分支和未提交改动
4. 如果是新功能，从 develop 切 feature/xxx 分支
```

### 2.2 编写代码时（持续检查）
- **先写类型签名，再写实现**。所有公共函数的参数和返回值必须有 type hints。
- 新增的类/函数必须有 docstring（Google 风格，至少一行描述）。
- 不写超过 50 行的函数。超过就拆分。
- 不写超过 3 层的缩进。超过就提取。
- 不引入新的第三方依赖，除非给出明确理由并在 commit body 中说明。

### 2.3 编写测试时
- 每个新模块必须有一个对应的 `tests/test_<module>.py`。
- 测试文件放在镜像路径下：`src/core/memory.py` → `tests/test_core/test_memory.py`。
- 至少覆盖：正常路径、边界值、异常路径。
- 测试函数命名：`test_<被测方法>_<条件>_<期望结果>`。

### 2.4 完成功能后（提交前检查清单）
```
[ ] 所有测试通过（python -m pytest tests/ -v）
[ ] core/ 无违规导入（rg "from openai|from chromadb|from sqlite_utils" src/core/）
[ ] 无 print 残留（rg "print\(" src/）
[ ] 提交信息符合规范
[ ] 无敏感信息（rg "sk-" . 不含 .env）
```

---

## 3. 模块职责速查

| 模块 | 可以做的事 | 禁止做的事 |
|------|----------|-----------|
| `src/core/` | 定义抽象、纯逻辑算法、数据模型 | 不能 import 第三方库、不能访问文件系统 |
| `src/adapters/` | 实现 core 定义的协议，封装外部 API | 不能包含业务逻辑判断 |
| `src/tools/` | 纯函数，接收输入返回输出 | 不能持有状态、不能直接调用外部 API（通过 adapter） |
| `src/api/` | 请求解析、路由、响应格式化 | 不能包含业务逻辑、不能直接访问数据库 |

---

## 4. 遇到不确定时

### 4.1 技术选型
- 不要自己拍板。去搜索业界最佳实践（例如 "RAG hybrid search best practice 2025"），给出 2-3 个方案对比，再让用户决策。
- 用 `docs/adr/` 记录所有非平凡的架构决策。

### 4.2 产品方向
- 如果发现自己在做用户没要求的功能，立即停止并确认。
- 每完成一个 milestone 的 50%，停下来让用户验收一次，不要闷头做到 100%。

### 4.3 Bug 修复
- 先写复现测试，再修代码。不要跳过复现直接改。
- 修复后检查：这个 bug 的同类型问题在代码库其他位置是否存在？

---

## 5. 对话行为规则

- 每次回复用户前，先完成正在进行的文件操作和测试验证。
- 提供状态更新时，「已完成 X / 总数 Y」格式简洁汇报。
- 如果遇到权限错误、环境问题，直接说明需要什么权限，不绕过。
- 不要过度解释代码。解释只写在 docstring 和必要注释（`# NOTE:` 或 `# BUG:` 风格）里。

---

## 6. 特定技术约束

- 数据库 schema 变更必须写在 `src/adapters/sqlite_store.py` 的 migration 段落，并加版本号注释。
- 所有 LLM prompt 模板集中在 `src/core/agent.py` 和 `src/core/report.py`，不在其他文件散落 prompt 字符串。
- 日志统一用 `logging.getLogger(__name__)`，不使用 `print`。
- 配置项统一在 `src/adapters/config.py` 中定义 pydantic `Settings` 类，其他地方只引用该实例。

---

## 7. 快速自检命令

```bash
# 运行测试
python -m pytest tests/ -v --tb=short

# 检查 core 层违规导入
rg -n "from openai|from chromadb|from sqlite_utils|from fastapi" src/core/

# 检查 print 残留
rg -n "print\(" src/

# 检查提交状态
git status
git log --oneline -5
```
