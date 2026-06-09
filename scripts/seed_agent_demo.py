"""Enterprise AI Agent Demo Seed Data — 演示数据初始化。

为黔智脑 Cognitive OS 比赛/路演提供可重复使用的演示数据。
所有数据使用 demo_ 前缀的 workspace/tenant 标识，不会污染真实数据。

安全设计：
- 默认 dry-run：不加 --apply 不会写入任何数据
- 去重检查：已存在的记忆不会重复写入
- 隔离标记：所有数据使用 demo-ws-01 workspace
- 无外部依赖：不联网，不使用外部 API

用法:
    python scripts/seed_agent_demo.py              # dry-run 预览（默认安全）
    python scripts/seed_agent_demo.py --dry-run     # 明确 dry-run
    python scripts/seed_agent_demo.py --apply       # 确认写入演示数据
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Demo Data
# ═══════════════════════════════════════════

DEMO_TENANT = "demo_cognitive_os"
DEMO_WORKSPACE = "demo-ws-01"
DEMO_USER = "demo-admin"

DEMO_DEPARTMENTS = ["研发部", "产品部", "销售部", "人力资源部", "客服部"]

DEMO_MEETINGS = [
    {
        "title": "黔智脑 Cognitive OS v2.0 项目复盘会议",
        "notes": """参会人：张总(项目负责人)、李工(研发组长)、王经理(产品经理)、赵运营(运营)

会议内容：
1. 项目进度回顾：
   - v2.0 已完成核心功能：AI Coach、Knowledge Graph、Memory Search Center
   - Enterprise AI Agent 平台已完成 Runtime 和 Registry，支持 12 个内置 Agent
   - 决定下周启动内部测试，测试范围涵盖所有已实现模块

2. 技术方案讨论：
   - 李工汇报：后端已采用六边形架构，API 响应时间降到 50ms 以下
   - 决策：继续采用事件驱动架构，下一步加入 Agent 工作流编排
   - 已搭建 CI/CD 流水线，代码覆盖率目标 90%+

3. 下一步计划：
   - 张总：负责确定比赛演示方案，本周五前完成
   - 李工：负责性能优化和压力测试，目标支撑 1000 并发
   - 王经理：负责梳理演示场景，重点展示"会议→知识→培训"闭环
   - 赵运营：负责准备企业案例数据，覆盖 6 个部门

4. 风险点：
   - 比赛日期临近，需要集中精力打磨演示效果
   - 企业数据脱敏方案需要尽快确定
   - Workflow 执行历史目前仅内存存储，生产环境需持久化""",
        "participants": ["张总", "李工", "王经理", "赵运营"],
        "department": "研发部",
    },
    {
        "title": "新人入职培训 — Enterprise AI Agent 平台能力介绍",
        "notes": """参会人：刘HR、新员工小陈、新员工小林、导师李工

会议内容：
1. 平台认知：
   - 刘HR：黔智脑 Cognitive OS 是面向企业知识管理的 AI 操作系统
   - 核心模块：长期记忆(Memory)、知识图谱(KG)、AI Coach、Enterprise AI Agent
   - 已有 12 个内置 Agent + 6 个部门 Agent

2. 关键技术：
   - 导师李工讲解：六边形架构 Ports & Adapters
   - Agent Runtime 采用 PEOR 循环：Plan → Execute → Observe → Reflect
   - WorkflowEngine 支持 9 种节点类型，包括 Agent/Human/Tool/Memory/KG/Condition
   - 所有 Agent 执行有完整 trace，每一步可审计

3. 新人 7 天学习计划：
   - 第1-2天：熟悉项目代码结构和开发规范
   - 第3-4天：深入学习 Memory System 和 Knowledge Graph
   - 第5天：理解 Agent Runtime 和 Workflow Engine
   - 第6天：实践业务场景（Meeting-to-Training、Department Assistant）
   - 第7天：写一个自己的 Agent 并通过测试""",
        "participants": ["刘HR", "小陈", "小林", "李工"],
        "department": "人力资源部",
    },
]

DEMO_QUESTIONS = [
    {
        "department": "研发部",
        "question": "当前 Enterprise AI Agent 平台的技术风险有哪些？下一步应如何排期？",
    },
    {
        "department": "产品部",
        "question": "如何用最简单的话让企业客户理解 Cognitive OS 的差异化价值？",
    },
    {
        "department": "销售部",
        "question": "客户问「企业为什么要为内部知识管理付费」时，应该如何回答？",
    },
    {
        "department": "人力资源部",
        "question": "请为新入职的 AI 工程师生成一份 7 天学习计划。",
    },
    {
        "department": "客服部",
        "question": "客户问「知识图谱对企业有什么实际用处」时，应该如何回答？",
    },
]

DEMO_MEMORIES = [
    {
        "content": "Memory Search Center：支持语义搜索（Embedding + RRF 融合）、实体匹配、时间衰减排序。使用 ChromaDB 向量存储 + SQLite 结构化存储双写。",
        "source": "agent",
        "metadata": {"workspace": DEMO_WORKSPACE, "module": "memory"},
    },
    {
        "content": "Knowledge Graph：自动从 Memory 中提取实体和关系（subject-predicate-object 三元组），支持图谱遍历、实体关联查询。已支持概念(concept)、人物(person)、组织(org)等实体类型。",
        "source": "agent",
        "metadata": {"workspace": DEMO_WORKSPACE, "module": "knowledge_graph"},
    },
    {
        "content": "Team Brain：支持 Workspace 级别的团队协作，含 ActionPlan（行动项分配/状态跟踪）、AuditLog（操作审计）、ActivityEvent（成员动态）。",
        "source": "agent",
        "metadata": {"workspace": DEMO_WORKSPACE, "module": "team_brain"},
    },
    {
        "content": "Enterprise Brain：支持 Organization → BusinessUnit → Department 三层组织架构，含 RBAC+ABAC 权限体系（6 级角色层级）、合规审计、Policy 策略引擎。",
        "source": "agent",
        "metadata": {"workspace": DEMO_WORKSPACE, "module": "enterprise_brain"},
    },
    {
        "content": "SaaS Platform：支持 Free/Personal/Professional/Team/Enterprise 5 级套餐，含 Billing（计费）、Subscription（订阅管理）、Usage Tracking（用量统计）、Tenant（多租户）完整能力。",
        "source": "agent",
        "metadata": {"workspace": DEMO_WORKSPACE, "module": "saas"},
    },
    {
        "content": "Growth Analytics：含 Invite（邀请）、Referral（推荐）、Coupon（优惠券）、Trial（试用）增长引擎。UsageCollector 后台线程实时采集用量事件，支持同期对比和趋势预测。",
        "source": "agent",
        "metadata": {"workspace": DEMO_WORKSPACE, "module": "analytics"},
    },
    {
        "content": "Enterprise AI Agent Platform：12 个内置 Agent（Knowledge、Meeting、Research、Sales、Support、Training） + 6 个部门 Agent（R&D、Product、Operations、Sales、HR、CS）。采用 PEOR 循环，每一步有 execution trace。",
        "source": "agent",
        "metadata": {"workspace": DEMO_WORKSPACE, "module": "agent"},
    },
    {
        "content": "Workflow Engine：支持 9 种节点类型（Agent/Human/Condition/Parallel/Tool/Memory/KG/Start/End）。每个节点生成 WorkflowExecutionStep，含 step_index/node_type/status/duration/error/output_summary，完整可审计。",
        "source": "agent",
        "metadata": {"workspace": DEMO_WORKSPACE, "module": "workflow"},
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enterprise AI Agent Demo Seed — 演示数据初始化",
        epilog="注意：不加 --apply 不会写入任何数据。这是默认安全行为。"
    )
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入数据（默认行为）")
    parser.add_argument("--apply", action="store_true", help="确认写入演示数据")
    args = parser.parse_args()

    if not args.apply:
        logger.info("=" * 50)
        logger.info("  黔智脑 Cognitive OS — Demo Seed 数据预览")
        logger.info("=" * 50)
        logger.info(">>> DRY-RUN — 不会写入任何数据 <<<")
        if not args.dry_run:
            logger.info("提示: 使用 --apply 确认写入，使用 --dry-run 明确预览")
        _print_demo_data()
        return

    # --apply: 确认写入
    logger.info("=" * 50)
    logger.info("  黔智脑 Cognitive OS — Demo Seed 数据写入")
    logger.info("=" * 50)
    logger.info(">>> APPLY 模式 — 将写入演示数据 <<<")
    logger.info(f"  Tenant: {DEMO_TENANT}")
    logger.info(f"  Workspace: {DEMO_WORKSPACE}")

    try:
        from src.adapters.config import Settings
        from src.adapters.sqlite_store import SQLiteStoreAdapter
        from src.adapters.vector_store import ChromaDBAdapter
        from src.adapters.embedding import LocalEmbeddingProvider

        settings = Settings(deepseek_api_key="sk-demo")
        memory_store = SQLiteStoreAdapter(settings)
        vector_store = ChromaDBAdapter(settings)
        embedding = LocalEmbeddingProvider(settings)

        _seed_memories(memory_store, vector_store, embedding)

        logger.info("-" * 50)
        logger.info("演示数据写入完成。")
        logger.info(f"  Tenant: {DEMO_TENANT} | Workspace: {DEMO_WORKSPACE}")
        logger.info(f"  Memories: {len(DEMO_MEMORIES)} 条")
        logger.info(f"  Meetings: {len(DEMO_MEETINGS)} 场 (仅预览用，实际使用前端输入)")
        logger.info(f"  Questions: {len(DEMO_QUESTIONS)} 题 (仅预览用，实际使用前端输入)")
        logger.info("")
        logger.info("启动后端后访问: http://localhost:3000/agents/scenarios")

    except Exception as e:
        logger.error(f"初始化失败: {e}")
        logger.info("")
        logger.info("常见原因:")
        logger.info("  1. data/agent_memory.db 不存在 — 先启动一次后端 python main.py 自动创建")
        logger.info("  2. SQLite 文件被锁定 — 关闭其他使用该数据库的进程")
        logger.info("  3. embedding 模型未下载 — 确保 BAAI/bge-small-zh-v1.5 已缓存")
        sys.exit(1)


def _seed_memories(
    memory_store: "SQLiteStoreAdapter",
    vector_store: "ChromaDBAdapter",
    embedding: "LocalEmbeddingProvider",
) -> None:
    """写入演示记忆，含去重检查。"""
    from src.core.types import Memory

    existing_keys: set[str] = set()
    try:
        recent = memory_store.get_recent(200)
        existing_keys = {m.content[:80] for m in recent}
    except Exception as e:
        logger.warning(f"无法读取现有记忆（可能数据库为空）: {e}")

    written = 0
    skipped = 0
    for dm in DEMO_MEMORIES:
        key = dm["content"][:80]
        if key in existing_keys:
            skipped += 1
            continue
        m = Memory(
            content=dm["content"],
            source=dm.get("source", "agent"),
            importance=7,
            memory_type="semantic",
        )
        memory_store.store(m)
        try:
            emb = embedding.encode(dm["content"])
            vector_store.store(m.id, emb, dm.get("metadata", {}))
        except Exception as e:
            logger.warning(f"向量写入跳过: {e}")
        existing_keys.add(key)
        written += 1

    logger.info(f"  记忆: {written} 条写入, {skipped} 条跳过(已存在)")


def _print_demo_data() -> None:
    """打印演示数据预览。"""
    print()
    print("=" * 60)
    print(f"  Demo Tenant  : {DEMO_TENANT}")
    print(f"  Workspace    : {DEMO_WORKSPACE}")
    print(f"  Departments  : {', '.join(DEMO_DEPARTMENTS)}")
    print("=" * 60)

    for i, meeting in enumerate(DEMO_MEETINGS, 1):
        print(f"\n── 演示会议 {i}: {meeting['title']}")
        print(f"   部门: {meeting['department']}")
        print(f"   参与人: {', '.join(meeting['participants'])}")
        preview = meeting['notes'][:150].replace('\n', ' ')
        print(f"   内容: {preview}...")

    print(f"\n── 演示部门问答 ({len(DEMO_QUESTIONS)} 题)")
    for q in DEMO_QUESTIONS:
        print(f"   [{q['department']}] {q['question'][:80]}")
        if len(q['question']) > 80:
            print(f"   {' ' * (len(q['department']) + 4)}{q['question'][80:]}")

    print(f"\n── 演示记忆 ({len(DEMO_MEMORIES)} 条)")
    for i, m in enumerate(DEMO_MEMORIES, 1):
        module_tag = m['metadata'].get('module', '?')
        print(f"   {i}. [{module_tag:20s}] {m['content'][:70]}...")
    print()


if __name__ == "__main__":
    main()
