"""Runtime Smoke Test — 验证系统 7 大核心组件真实可用性。

运行方式:
    cd D:\dma\day2
    python tests/smoke_test.py
"""

import io
import json
import os
import sys
import time
import traceback

# 注意：本文件是独立运行脚本（python tests/smoke_test.py），不是 pytest 用例。
# 不要在模块导入期改写 sys.stdout/sys.stderr —— 那会在 pytest 收集本文件时
# 覆盖 pytest 的全局 capture，导致 "I/O operation on closed file" 等进程级污染。
# UTF-8 输出包装只在作为 main 独立运行时才生效（见下方 __main__ 块）。

# ── ensure project root on path ──
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS = []


def test(name: str):
    """装饰器风格的测试注册，但手动实现。返回 True/False。"""
    pass


def record(name: str, passed: bool, detail: str = "", error: str = ""):
    entry = {
        "test": name,
        "result": "PASS" if passed else "FAIL",
        "detail": detail,
        "error": error[:2000] if error else "",
    }
    RESULTS.append(entry)
    icon = "✅" if passed else "❌"
    print(f"  {icon} {name}")
    if detail:
        print(f"     {detail}")
    if error:
        print(f"     ERR: {error[:300]}")
    print()


def sep(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


# ═══════════════════════════════════════════════════════════════
# 1. SQLite Store
# ═══════════════════════════════════════════════════════════════
def test_sqlite_store():
    sep("1. SQLite Store")
    try:
        from datetime import datetime, timezone
        from src.adapters.config import Settings
        from src.adapters.sqlite_store import SQLiteStoreAdapter
        from src.core.types import Memory

        settings = Settings()  # type: ignore[call-arg]
        record("1.1 Settings 加载", True,
               f"sqlite_db_path={settings.sqlite_db_path}")

        # 使用独立测试数据库，避免污染生产数据
        test_db = "./data/smoke_test_sqlite.db"
        for suffix in ["", "-shm", "-wal"]:
            fpath = test_db + suffix
            if os.path.exists(fpath):
                os.remove(fpath)

        store = SQLiteStoreAdapter(settings, db_path=test_db)
        record("1.2 连接 + Schema 初始化", True,
               f"path={test_db}")

        # 写入 — Memory 需要 summary 和 timestamp
        now = datetime.now(timezone.utc)
        m = Memory(
            content="烟测记忆-你好世界",
            summary=None,
            timestamp=now,
            source="smoke_test",
        )
        mem_id = store.store(m)
        saved = store.get_by_id(mem_id)
        assert saved is not None, "store() 后 get_by_id() 返回 None"
        record("1.3 写入 Memory (store)", True,
               f"id={mem_id} content={saved.content[:30]}")

        # 读取 (API 是 get_by_id)
        loaded = store.get_by_id(mem_id)
        assert loaded is not None, "读取失败：get_by_id() 返回 None"
        assert loaded.content == m.content, f"内容不匹配"
        record("1.4 读取 Memory (get_by_id)", True,
               f"content 一致: {loaded.content[:30]}")

        # 列出 (list_all 无 limit 参数)
        all_memories = store.list_all()
        assert len(all_memories) > 0, "list_all 返回空"
        record("1.5 list_all()", True,
               f"count={len(all_memories)}")

        # 删除
        store.delete(mem_id)
        deleted_check = store.get_by_id(mem_id)
        assert deleted_check is None, f"删除后仍能读取"
        record("1.6 删除 Memory", True, "删除后 get_by_id() 返回 None")

        store.close()

        # 清理
        for suffix in ["", "-shm", "-wal"]:
            fpath = test_db + suffix
            if os.path.exists(fpath):
                os.remove(fpath)

    except Exception as e:
        record("1.x SQLite Store", False, "", traceback.format_exc())


# ═══════════════════════════════════════════════════════════════
# 2. ChromaDB
# ═══════════════════════════════════════════════════════════════
def test_chromadb():
    sep("2. ChromaDB")
    try:
        import chromadb  # type: ignore[import-untyped]
        from chromadb.api import ClientAPI

        record("2.1 导入 chromadb", True,
               f"version={chromadb.__version__}")

        # 使用临时目录测试
        import tempfile
        test_dir = tempfile.mkdtemp(prefix="smoke_chroma_")
        client = chromadb.PersistentClient(path=test_dir)
        record("2.2 PersistentClient 创建", True,
               f"path={test_dir}")

        col = client.get_or_create_collection(name="smoke_test_collection")
        record("2.3 get_or_create_collection", True,
               f"name=smoke_test_collection count={col.count()}")

        # Upsert
        import numpy as np
        test_vec = np.random.rand(128).tolist()
        col.upsert(
            ids=["smoke-1"],
            embeddings=[test_vec],
            metadatas=[{"source": "smoke_test"}],
        )
        record("2.4 upsert", True,
               f"id=smoke-1 dim=128")

        # Query
        result = col.query(
            query_embeddings=[test_vec],
            n_results=1,
            include=["metadatas", "distances"],
        )
        got_ids = result.get("ids", [[]])[0]
        assert len(got_ids) == 1 and got_ids[0] == "smoke-1", \
            f"query 返回异常: {got_ids}"
        distance = result.get("distances", [[-1]])[0][0]
        record("2.5 query", True,
               f"hit={got_ids[0]} distance={distance:.4f}")

        # 清理
        col.delete(ids=["smoke-1"])
        # reset() 在 chromadb 1.5.9 的 PersistentClient 上可能抛异常
        # (需要运行中的 server)，改用直接删除底层文件
        try:
            client.reset()
        except Exception:
            pass
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)

    except Exception as e:
        record("2.x ChromaDB", False, "", traceback.format_exc())


# ═══════════════════════════════════════════════════════════════
# 3. Embedding
# ═══════════════════════════════════════════════════════════════
def test_embedding():
    sep("3. Embedding")
    try:
        from src.adapters.config import Settings
        from src.adapters.embedding import LocalEmbeddingProvider

        settings = Settings()  # type: ignore[call-arg]
        record("3.1 Settings 加载", True,
               f"embedding_model={settings.embedding_model}")

        provider = LocalEmbeddingProvider(settings)
        record("3.2 LocalEmbeddingProvider 初始化", True,
               f"device={provider._device}")

        provider.warmup()
        record("3.3 warmup()", True,
               f"model loaded")

        vec = provider.encode("你好世界")
        assert isinstance(vec, list), f"返回类型错误: {type(vec)}"
        assert len(vec) == 512, f"维度错误: {len(vec)} != 512"
        assert all(isinstance(v, float) for v in vec), "元素类型非 float"

        record("3.4 encode('你好世界')", True,
               f"dim={len(vec)} sample=[{vec[0]:.4f}, {vec[1]:.4f}, ...]")

        # 验证 cosine similarity（归一化后自身点积 ≈ 1）
        import math
        self_sim = sum(a * b for a, b in zip(vec, vec))
        record("3.5 embedding 自相似度", abs(self_sim - 1.0) < 0.01,
               f"self_similarity={self_sim:.6f} (应为 1.0)")

        provider.close()

    except Exception as e:
        record("3.x Embedding", False, "", traceback.format_exc())


# ═══════════════════════════════════════════════════════════════
# 4. Memory (端到端: 写入 → 检索 → 删除)
# ═══════════════════════════════════════════════════════════════
def test_memory():
    sep("4. Memory (端到端)")
    try:
        from src.adapters.config import Settings
        from src.adapters.sqlite_store import SQLiteStoreAdapter
        from src.adapters.vector_store import ChromaDBAdapter
        from src.adapters.embedding import LocalEmbeddingProvider
        from src.core.retrieval import MemoryRetrievalService
        from src.core.types import Memory

        import tempfile, shutil
        settings = Settings()  # type: ignore[call-arg]

        # 使用临时目录避免污染
        tmp = tempfile.mkdtemp(prefix="smoke_mem_")
        test_db = os.path.join(tmp, "test.db")
        test_chroma = os.path.join(tmp, "chroma")

        mem_store = SQLiteStoreAdapter(settings, db_path=test_db)
        vec_store = ChromaDBAdapter.__new__(ChromaDBAdapter)

        import chromadb
        chroma_client = chromadb.PersistentClient(path=test_chroma)
        col = chroma_client.get_or_create_collection(name="memory_embeddings")
        vec_store._client = chroma_client
        vec_store._collection = col

        emb_provider = LocalEmbeddingProvider(settings)
        emb_provider.warmup()

        retrieval = MemoryRetrievalService(mem_store, vec_store, emb_provider)

        # 写入 3 条记忆
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        memories = []
        for i, content in enumerate([
            "Python 是 Guido van Rossum 于 1991 年创建的编程语言",
            "FastAPI 是一个现代高性能 Web 框架",
            "sentence-transformers 用于生成文本嵌入向量",
        ]):
            m = Memory(content=content, summary=None, timestamp=now, source="smoke_test")
            mem_id = mem_store.store(m)
            saved = mem_store.get_by_id(mem_id)
            emb = emb_provider.encode(content)
            vec_store.store(saved.id, emb, {"memory_id": saved.id})
            memories.append(saved)

        record("4.1 写入 3 条记忆", True,
               f"ids={[m.id[:8]+'...' for m in memories]}")

        # 检索
        hits = retrieval.retrieve("Python 编程语言", top_k=3)
        assert len(hits) >= 1, f"检索结果为空"
        assert any("Python" in h.content for h in hits), \
            f"检索结果不包含 'Python': {[h.content[:30] for h in hits]}"
        record("4.2 语义检索 'Python 编程语言'", True,
               f"hits={len(hits)} top1={hits[0].content[:40]}...")

        # 删除
        mem_store.delete(memories[0].id)
        col.delete(ids=[memories[0].id])
        after_del = retrieval.retrieve("Python 编程语言", top_k=3)
        still_present = [h for h in after_del if h.id == memories[0].id]
        assert len(still_present) == 0, "删除后仍被检索到"
        record("4.3 删除记忆后检索", True,
               f"已删除 id={memories[0].id[:8]}..., 检索中不再出现")

        # 清理
        mem_store.close()
        shutil.rmtree(tmp, ignore_errors=True)

    except Exception as e:
        record("4.x Memory", False, "", traceback.format_exc())


# ═══════════════════════════════════════════════════════════════
# 5. OpenAI Adapter (仅验证初始化路径，不发真实请求)
# ═══════════════════════════════════════════════════════════════
def test_openai_adapter():
    sep("5. OpenAI Adapter")
    try:
        from src.adapters.config import Settings
        from src.adapters.llm import DeepSeekAdapter, LLMError

        settings = Settings()  # type: ignore[call-arg]

        record("5.1 Settings 加载", True,
               f"base_url={settings.deepseek_base_url} model={settings.deepseek_model}")

        api_key = settings.deepseek_api_key
        has_key = bool(api_key and len(api_key) > 10)

        adapter = DeepSeekAdapter(settings)
        record("5.2 DeepSeekAdapter 初始化", True,
               f"model={adapter._model} client_created={adapter._client is not None}")

        # 验证客户端属性
        assert adapter._client is not None
        assert adapter._client.base_url.host == "api.deepseek.com" or \
               "deepseek.com" in str(adapter._client.base_url), \
               f"base_url 异常: {adapter._client.base_url}"

        record("5.3 OpenAI client 配置", True,
               f"base_url={adapter._client.base_url}")

        # 验证 chat 方法签名可调用
        import inspect
        sig = inspect.signature(adapter.chat)
        params = list(sig.parameters.keys())
        record("5.4 chat() 方法签名", True,
               f"params={params}")

        # 如果没有 API key，仅验证到这里
        if not has_key:
            record("5.5 API Key", True,
                   "没有检测到有效 DEEPSEEK_API_KEY，跳过真实请求")
        else:
            record("5.5 API Key", True,
                   f"检测到 API Key (长度={len(api_key)}), 跳过真实请求（按计划）")

        adapter.close()

    except Exception as e:
        record("5.x OpenAI Adapter", False, "", traceback.format_exc())


# ═══════════════════════════════════════════════════════════════
# 6. FastAPI (TestClient)
# ═══════════════════════════════════════════════════════════════
def test_fastapi():
    sep("6. FastAPI")
    try:
        # 必须设置工作目录，否则 sqlite db path 解析错误
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        from fastapi.testclient import TestClient

        # 导入 app 对象（会触发完整的模块级初始化）
        # 为避免重复启动所有后台线程，用 TestClient 直接测
        from main import app
        client = TestClient(app)

        # /health
        resp = client.get("/health")
        assert resp.status_code == 200, f"HTTP {resp.status_code}"
        data = resp.json()
        assert data["status"] == "healthy", f"status={data.get('status')}"
        record("6.1 GET /health", True,
               f"status=200 body={json.dumps(data)}")

        # /docs
        resp = client.get("/docs")
        assert resp.status_code == 200
        assert "swagger" in resp.text.lower() or "openapi" in resp.text.lower() \
               or "swagger-ui" in resp.text.lower() or "redoc" in resp.text.lower(), \
               "docs 页面不包含预期的 UI 标识"
        record("6.2 GET /docs", True,
               f"status=200 content_len={len(resp.text)}")

        # /openapi.json — 大项目可能序列化超时，容错处理
        try:
            resp = client.get("/openapi.json")
            if resp.status_code == 200:
                schema = resp.json()
                paths_count = len(schema.get("paths", {}))
                title = schema.get("info", {}).get("title", "N/A")
                record("6.3 GET /openapi.json", True,
                       f"paths_count={paths_count} title={title}")
            else:
                record("6.3 GET /openapi.json", False,
                       f"HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as oe:
            record("6.3 GET /openapi.json", False,
                   f"schema generation error: {str(oe)[:200]}")

        # Runtime Admin 路由存在性
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        admin_routes = [r for r in routes if 'admin' in r.lower()]
        record("6.4 Runtime Admin 路由", len(admin_routes) > 0,
               f"admin routes={len(admin_routes)} 条, "
               f"示例: {admin_routes[:3] if admin_routes else 'NONE'}")

        # 总路由数
        all_paths = [r.path for r in app.routes if hasattr(r, 'path') and hasattr(r, 'methods')]
        record("6.5 路由总数", True,
               f"total_endpoints={len(all_paths)}")

    except Exception as e:
        record("6.x FastAPI", False, "", traceback.format_exc())
    finally:
        # 恢复原始工作目录
        original = os.environ.get("SMOKE_ORIGINAL_CWD", "")
        if original:
            os.chdir(original)


# ═══════════════════════════════════════════════════════════════
# 7. Sandbox V2
# ═══════════════════════════════════════════════════════════════
def test_sandbox_v2():
    sep("7. Sandbox V2")
    try:
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)

        # Sandbox V2 路由前缀 = /api/runtime/sandbox-v2
        prefix = "/api/runtime/sandbox-v2"

        # Readiness
        resp = client.get(f"{prefix}/monitoring/health")
        data = resp.json()
        record("7.1 GET .../monitoring/health", resp.status_code == 200,
               f"status={resp.status_code} healthy={data.get('healthy')} "
               f"checks={data.get('total', 'N/A')}")

        # Runtime API 可用性
        resp2 = client.get(f"{prefix}/monitoring/alerts/rules")
        record("7.2 GET .../monitoring/alerts/rules",
               resp2.status_code == 200,
               f"status={resp2.status_code} total={resp2.json().get('total', 'N/A')}")

        # Sandbox v2 router 路由覆盖 (前缀 /api/runtime/sandbox-v2)
        routes = [r.path for r in app.routes if hasattr(r, 'path') and 'sandbox' in r.path.lower()]
        record("7.3 Sandbox V2 路由数", len(routes) > 0,
               f"count={len(routes)} 示例: {routes[:3]}")

    except Exception as e:
        record("7.x Sandbox V2", False, "", traceback.format_exc())


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # 仅独立运行时启用 UTF-8 输出，避免 Windows GBK 终端 emoji 编码问题
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.environ["SMOKE_ORIGINAL_CWD"] = os.getcwd()
    print("=" * 60)
    print("  D:\\dma\\day2  Runtime Smoke Test")
    print(f"  Python: {sys.version}")
    print(f"  Time:   {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    print("=" * 60)

    test_sqlite_store()
    test_chromadb()
    test_embedding()
    test_memory()
    test_openai_adapter()
    test_fastapi()
    test_sandbox_v2()

    # ── 汇总 ──
    print("\n" + "=" * 60)
    print("  汇总")
    print("=" * 60)
    passed = sum(1 for r in RESULTS if r["result"] == "PASS")
    failed = sum(1 for r in RESULTS if r["result"] == "FAIL")
    total = len(RESULTS)
    print(f"\n  Total: {total}  |  PASS: {passed}  |  FAIL: {failed}")
    if failed == 0:
        print("  🟢 全部通过 — 系统核心能力就绪")
    else:
        print(f"  🔴 {failed} 项失败 — 详情见上方错误信息")
        print("\n  失败项:")
        for r in RESULTS:
            if r["result"] == "FAIL":
                print(f"    ❌ {r['test']}")
                if r["error"]:
                    print(f"       {r['error'][:200]}")
    print()

    # 写入 JSON 报告
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "smoke_test_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "python": sys.version,
            "total": total,
            "passed": passed,
            "failed": failed,
            "results": RESULTS,
        }, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {report_path}")

    sys.exit(0 if failed == 0 else 1)
