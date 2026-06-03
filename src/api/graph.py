"""Graph API — 知识图谱读取层。

从已有 SQLite 表(entities / relations / memory_entities / notes)派生节点和边。
不引入 Neo4j，不新增存储层。
"""
import json
import logging
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query

from src.api.schemas import EntityDetail, GraphData, GraphEdge, GraphNode
from src.core.agent import CognitiveAgent

logger = logging.getLogger(__name__)

# 同一条记忆中共同出现的实体 → co_occurrence 边权重系数
CO_OCCURRENCE_WEIGHT = 0.5
# subgraph BFS 最大深度
MAX_BFS_DEPTH = 3


def create_graph_router(agent: CognitiveAgent) -> APIRouter:
    router = APIRouter(prefix="/graph", tags=["graph"])

    def _db():
        return agent._memory_store._db

    # ── GET /graph ──────────────────────────────────────────────────

    @router.get("", response_model=GraphData)
    async def get_graph(
        entity_type: str = "",
        min_importance: int = Query(default=0, ge=0, le=10),
        limit: int = Query(default=200, ge=10, le=1000),
    ):
        """返回完整图谱的节点和边。

        节点来源：entities 表 + semantic/procedural 概念记忆
        边来源：relations 表 (subject→object) + co_occurrence (同记忆共现实体)
        """
        try:
            db = _db()

            # ── 节点─实体 ──
            entity_filter = "WHERE mention_count > 0"
            eparams: list = []
            if entity_type:
                entity_filter += " AND entity_type = ?"
                eparams.append(entity_type)

            entity_rows = db.execute(
                f"""SELECT id, name, entity_type, mention_count, first_seen
                    FROM entities {entity_filter}
                    ORDER BY mention_count DESC
                    LIMIT ?""",
                eparams + [limit],
            ).fetchall()

            nodes: dict[str, GraphNode] = {}
            for r in entity_rows:
                rid = f"entity_{r['id']}"
                nodes[rid] = GraphNode(
                    id=rid,
                    label=str(r["name"]),
                    type="entity",
                    importance=min(r["mention_count"], 10),
                    memory_count=r["mention_count"],
                    group=r["entity_type"] or "entity",
                )

            # ── 节点─概念记忆 (semantic / procedural) ──
            concept_rows = db.execute(
                """SELECT id, summary, content, importance, entities_json,
                          memory_type, source, status
                   FROM notes
                   WHERE memory_type IN ('semantic', 'procedural')
                   AND status = 'active'
                   ORDER BY importance DESC
                   LIMIT ?""",
                (limit // 2,),
            ).fetchall()

            for r in concept_rows:
                rid = r["id"]
                label = (r["summary"] or r["content"])[:40]
                ents = json.loads(r.get("entities_json") or "[]")
                nodes[rid] = GraphNode(
                    id=rid,
                    label=label,
                    type="concept",
                    importance=r["importance"],
                    memory_count=len(ents),
                    group="concept",
                )
                # 连接概念记忆 → 其实体
                for ename in ents:
                    eid = _find_entity_id(db, ename)
                    if eid:
                        ekey = f"entity_{eid}"
                        if ekey in nodes:
                            # 不新增边，但从概念继承重要性
                            pass

            # ── 边─relations 表 ──
            edges: list[GraphEdge] = []
            edge_set: set[tuple[str, str, str]] = set()

            rel_rows = db.execute(
                """SELECT subject, predicate, object, COUNT(*) as cnt
                   FROM relations
                   GROUP BY subject, predicate, object
                   ORDER BY cnt DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()

            for r in rel_rows:
                sid = _find_entity_id(db, r["subject"])
                oid = _find_entity_id(db, r["object"])
                if sid and oid:
                    skey = f"entity_{sid}"
                    okey = f"entity_{oid}"
                    weight = min(r["cnt"] * 0.3, 3.0)
                    key = (skey, okey, r["predicate"])
                    if key not in edge_set:
                        edge_set.add(key)
                        edges.append(GraphEdge(
                            source=skey, target=okey,
                            relation=r["predicate"], weight=round(weight, 2),
                        ))

            # ── 边─co_occurrence (同一记忆中出现的实体) ──
            co_occur = _build_co_occurrence(db, nodes, limit)
            for (skey, okey), cnt in co_occur.items():
                key = (skey, okey, "co_occurrence")
                if key not in edge_set:
                    edge_set.add(key)
                    edges.append(GraphEdge(
                        source=skey, target=okey,
                        relation="co_occurrence",
                        weight=round(min(cnt * CO_OCCURRENCE_WEIGHT, 5.0), 2),
                    ))

            # ── 统计 ──
            stats = {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "entity_nodes": sum(1 for n in nodes.values() if n.type == "entity"),
                "concept_nodes": sum(1 for n in nodes.values() if n.type == "concept"),
            }

            # 高频实体 top 10
            top_entities = sorted(
                [n for n in nodes.values() if n.type == "entity"],
                key=lambda n: n.memory_count, reverse=True,
            )[:10]
            stats["top_entities"] = [n.label for n in top_entities]
            stats["top_entities_count"] = [n.memory_count for n in top_entities]

            return GraphData(
                nodes=list(nodes.values()),
                edges=edges,
                stats=stats,
            )

        except Exception:
            logger.warning("graph_build_failed", exc_info=True)
            return GraphData()

    # ── GET /graph/entity/{entity} ───────────────────────────────────

    @router.get("/entity/{entity_name}", response_model=EntityDetail)
    async def entity_detail(entity_name: str):
        """查看实体详情：相关记忆、相关实体、最近活动。"""
        try:
            db = _db()
            erow = db.execute(
                "SELECT id, name, entity_type, mention_count, first_seen FROM entities WHERE name = ?",
                (entity_name,),
            ).fetchone()

            if erow is None:
                raise HTTPException(status_code=404, detail=f"实体 '{entity_name}' 不存在")

            eid = erow["id"]

            # 相关记忆
            mem_rows = db.execute(
                """SELECT n.id, n.content, n.summary, n.source, n.timestamp,
                          n.importance, n.memory_type
                   FROM notes n
                   JOIN memory_entities me ON n.id = me.memory_id
                   WHERE me.entity_id = ?
                   ORDER BY n.timestamp DESC LIMIT 20""",
                (eid,),
            ).fetchall()

            related_memories = [
                {
                    "id": r["id"],
                    "content_preview": (r["summary"] or r["content"])[:150],
                    "source": r["source"],
                    "timestamp": r["timestamp"],
                    "importance": r["importance"],
                    "memory_type": r["memory_type"],
                }
                for r in mem_rows
            ]

            # 相关实体(co-occurrence)
            co_entity_rows = db.execute(
                """SELECT e.name, e.entity_type, e.mention_count, COUNT(*) as co_count
                   FROM entities e
                   JOIN memory_entities me ON e.id = me.entity_id
                   WHERE me.memory_id IN (
                       SELECT memory_id FROM memory_entities WHERE entity_id = ?
                   )
                   AND e.id != ?
                   GROUP BY e.id
                   ORDER BY co_count DESC LIMIT 15""",
                (eid, eid),
            ).fetchall()

            related_entities = [
                {
                    "name": r["name"],
                    "entity_type": r["entity_type"] or "",
                    "mention_count": r["mention_count"],
                    "co_count": r["co_count"],
                }
                for r in co_entity_rows
            ]

            # 最近活动
            recent_rows = db.execute(
                """SELECT n.id, n.summary, n.content, n.timestamp, n.memory_type,
                          n.importance, n.source
                   FROM notes n
                   JOIN memory_entities me ON n.id = me.memory_id
                   WHERE me.entity_id = ?
                   ORDER BY n.timestamp DESC LIMIT 5""",
                (eid,),
            ).fetchall()

            recent_activity = [
                {
                    "id": r["id"],
                    "content_preview": (r["summary"] or r["content"])[:120],
                    "timestamp": r["timestamp"],
                    "memory_type": r["memory_type"],
                    "importance": r["importance"],
                }
                for r in recent_rows
            ]

            return EntityDetail(
                name=str(erow["name"]),
                entity_type=erow["entity_type"] or "",
                mention_count=erow["mention_count"],
                first_seen=erow["first_seen"],
                related_memories=related_memories,
                related_entities=related_entities,
                recent_activity=recent_activity,
            )

        except HTTPException:
            raise
        except Exception:
            logger.warning("entity_detail_failed", exc_info=True)
            raise HTTPException(status_code=500, detail="查询失败")

    # ── GET /graph/subgraph ──────────────────────────────────────────

    @router.get("/subgraph", response_model=GraphData)
    async def subgraph(
        entity: str = Query(...),
        depth: int = Query(default=2, ge=1, le=MAX_BFS_DEPTH),
    ):
        """返回围绕某个实体的局部图谱(BFS)。"""
        try:
            db = _db()
            eid = _find_entity_id(db, entity)
            if eid is None:
                raise HTTPException(status_code=404, detail=f"实体 '{entity}' 不存在")

            # BFS
            visited_entities: set[int] = {eid}
            visited_memories: set[str] = set()
            frontier: set[int] = {eid}

            for _ in range(depth):
                next_frontier: set[int] = set()
                for feid in frontier:
                    # 找共享此实体的记忆
                    mem_rows = db.execute(
                        "SELECT memory_id FROM memory_entities WHERE entity_id = ?",
                        (feid,),
                    ).fetchall()
                    for mr in mem_rows:
                        mid = mr["memory_id"]
                        if mid in visited_memories:
                            continue
                        visited_memories.add(mid)
                        # 找到记忆中的其他实体
                        co_rows = db.execute(
                            "SELECT entity_id FROM memory_entities WHERE memory_id = ?",
                            (mid,),
                        ).fetchall()
                        for cr in co_rows:
                            ceid = cr["entity_id"]
                            if ceid not in visited_entities:
                                visited_entities.add(ceid)
                                next_frontier.add(ceid)
                frontier = next_frontier

            # 构建节点
            nodes: dict[str, GraphNode] = {}
            for eid_i in visited_entities:
                erow = db.execute(
                    "SELECT id, name, entity_type, mention_count FROM entities WHERE id = ?",
                    (eid_i,),
                ).fetchone()
                if erow:
                    rid = f"entity_{erow['id']}"
                    nodes[rid] = GraphNode(
                        id=rid,
                        label=str(erow["name"]),
                        type="entity",
                        importance=min(erow["mention_count"], 10),
                        memory_count=erow["mention_count"],
                        group=erow["entity_type"] or "entity",
                    )

            for mid in visited_memories:
                mrow = db.execute(
                    "SELECT id, summary, content, importance, memory_type FROM notes WHERE id = ?",
                    (mid,),
                ).fetchone()
                if mrow:
                    nodes[mid] = GraphNode(
                        id=mid,
                        label=(mrow["summary"] or mrow["content"])[:50],
                        type="memory",
                        importance=mrow["importance"],
                        memory_count=1,
                        group=mrow["memory_type"],
                    )

            # 构建边
            edges: list[GraphEdge] = []
            edge_set: set[tuple[str, str]] = set()

            # entity ← memory → entity
            for mid in visited_memories:
                me_rows = db.execute(
                    "SELECT entity_id FROM memory_entities WHERE memory_id = ?",
                    (mid,),
                ).fetchall()
                eids_in_mem = [r["entity_id"] for r in me_rows]
                for eid_a in eids_in_mem:
                    ekey_a = f"entity_{eid_a}"
                    if ekey_a not in nodes:
                        continue
                    # memory-to-entity edge
                    key = (mid, ekey_a)
                    if key not in edge_set:
                        edge_set.add(key)
                        edges.append(GraphEdge(source=mid, target=ekey_a, relation="has_entity", weight=1.0))
                    # entity-to-entity co-occurrence
                    for eid_b in eids_in_mem:
                        if eid_b <= eid_a:
                            continue
                        ekey_b = f"entity_{eid_b}"
                        if ekey_b not in nodes:
                            continue
                        key2 = (ekey_a, ekey_b)
                        if key2 not in edge_set:
                            edge_set.add(key2)
                            edges.append(GraphEdge(source=ekey_a, target=ekey_b, relation="co_occurrence", weight=0.5))

            return GraphData(
                nodes=list(nodes.values()),
                edges=edges,
                stats={
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                    "center_entity": entity,
                    "depth": depth,
                },
            )

        except HTTPException:
            raise
        except Exception:
            logger.warning("subgraph_failed", exc_info=True)
            return GraphData()

    return router


# ── 辅助函数 ──


def _find_entity_id(db, name: str) -> int | None:
    """根据实体名查找 entity id。"""
    row = db.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()
    return row["id"] if row else None


def _build_co_occurrence(db, nodes: dict, limit: int) -> dict[tuple[str, str], int]:
    """从 memory_entities 表构建实体共现矩阵。"""
    co_occur: dict[tuple[str, str], int] = defaultdict(int)
    try:
        # 获取最近记忆中的实体对
        rows = db.execute(
            """SELECT memory_id, entity_id FROM memory_entities
               ORDER BY memory_id LIMIT ?""",
            (limit * 5,),
        ).fetchall()

        mem_to_entities: dict[str, list[int]] = defaultdict(list)
        for r in rows:
            mem_to_entities[r["memory_id"]].append(r["entity_id"])

        for eid_list in mem_to_entities.values():
            for i in range(len(eid_list)):
                for j in range(i + 1, len(eid_list)):
                    ekey_a = f"entity_{eid_list[i]}"
                    ekey_b = f"entity_{eid_list[j]}"
                    if ekey_a in nodes and ekey_b in nodes:
                        if ekey_a < ekey_b:
                            co_occur[(ekey_a, ekey_b)] += 1
                        else:
                            co_occur[(ekey_b, ekey_a)] += 1
    except Exception:
        logger.debug("co_occurrence_build_failed", exc_info=True)

    return co_occur
