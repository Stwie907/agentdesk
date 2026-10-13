"""Verify scoped SQLite vector reuse and persistence with existing Mock fixtures."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app import check_semantic_memory as semantic
from app.check_demo import request_json, require
from app.check_memory import memory_request
from app.check_memory_evidence import read_capture
from app.check_user_memory import inspection
from app.database import SessionLocal
from app.models.memory_vector_cache import MemoryVectorCache
from app.services.memory_embeddings import get_embedding_settings
from app.services.memory_vector_cache import MOCK_DIGEST, _cached_vector, namespace


def default_state_file():
    return semantic.default_state_file().with_name("memory-vector-cache-acceptance.json")


def cache_record(row):
    return {column.name: (getattr(row, column.name).isoformat() if isinstance(getattr(row, column.name), datetime)
                          else getattr(row, column.name)) for column in MemoryVectorCache.__table__.columns}


def fixture_vectors(source):
    settings = get_embedding_settings()
    require(settings.provider == "mock" and settings.memory.cache_enabled, "Use the Mock backend with vector cache enabled")
    records = {}
    with SessionLocal() as db:
        for label, kind, owner in (("private", "agent", source["agent_id"]), ("shared", "user", source["user_id"]),
                                   ("isolated", "user", source["isolation_user_id"])):
            saved = source[label]
            row = db.query(MemoryVectorCache).filter_by(source_type=kind, owner_id=owner, memory_id=saved["id"],
                                                      namespace=namespace(settings)).first()
            require(row is not None and _cached_vector(row, (kind, owner, saved["id"], saved["content"],
                    datetime.fromisoformat(saved["created_at"])), MOCK_DIGEST) is not None,
                    "Original fixture vector cache was lost or changed")
            records[label] = cache_record(row)
    return records


def cache_stats(base_url, execution_id):
    logs = request_json(base_url, f"/executions/{execution_id}/logs")
    records = [json.loads(row["message"].split(": ", 1)[1]) for row in logs
               if row["message"].startswith("memory_embedding_cache: ")]
    require(len(records) == 1, "Runtime cache metrics are missing or duplicated")
    stats = records[0]
    require(isinstance(stats, dict) and type(stats.get("version")) is int and stats["version"] == 1
            and stats.get("status") == "active" and stats.get("provider") == "mock" and stats.get("model") == "mock-fixtures-v1"
            and all(type(stats.get(key)) is int and stats[key] >= 0 for key in ("documents", "hits", "misses", "written"))
            and stats["documents"] == stats["hits"] + stats["misses"] and stats["written"] <= stats["misses"],
            "Runtime cache metrics are invalid or caching is disabled")
    return stats


def captured_chat(base_url, agent_id, query=semantic.QUERY):
    reply = request_json(base_url, f"/agents/{agent_id}/chat", {"message": query})
    require(reply["status"] == "completed" and reply["response"].startswith("[MOCK]"), "Expected a fixed Mock reply")
    execution_id = reply["execution_id"]
    return {"execution_id": execution_id, "agent_id": agent_id, "query": query, "inspection": inspection(base_url, execution_id),
            "memory_context": read_capture(base_url, execution_id, agent_id, query), "cache": cache_stats(base_url, execution_id)}


def require_warm(case):
    stats = case["cache"]
    require(stats["documents"] > 0 and stats["hits"] == stats["documents"] and stats["misses"] == stats["written"] == 0,
            "Warm Runtime regenerated saved document vectors")


def check_memory_vector_cache(base_url, verify_persistence=False, state_file=None, semantic_state_file=None):
    settings = get_embedding_settings()
    require(settings.provider == "mock" and settings.memory.cache_enabled, "Run from the Mock backend with vector cache enabled")
    state_file = default_state_file() if state_file is None else Path(state_file)
    source_file = semantic.default_state_file() if semantic_state_file is None else Path(semantic_state_file)
    require(not verify_persistence or state_file.is_file(), "Vector cache checkpoint is missing; run the initial check first")
    require(source_file.is_file(), "Keep the existing semantic memory checkpoint")
    source_bytes = source_file.read_bytes(); source = json.loads(source_bytes)
    agents = request_json(base_url, "/agents")
    demos = [row for row in agents if row["name"] == "Demo Agent"]
    peers = [row for row in agents if row["name"] == "MCP Order Agent"]
    require(len(demos) == len(peers) == 1, "Run the demo initializer first")
    agent_id, peer_id = demos[0]["id"], peers[0]["id"]
    owner = request_json(base_url, f"/user-memories/for-agent/{agent_id}")["user_id"]
    semantic.validate_checkpoint(base_url, source, agent_id, peer_id, owner, agents, read=request_json)
    reused = state_file.is_file()
    if reused:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        require(isinstance(state, dict) and type(state.get("version")) is int and state["version"] == 1
                and state.get("source_checkpoint") == source and state.get("namespace") == namespace(settings),
                "Vector cache checkpoint is invalid or its source/model changed")
        require(fixture_vectors(source) == state.get("vectors"), "Original fixture vectors were lost or changed")
        cases = state.get("cases")
        require(isinstance(cases, dict) and set(cases) == {"first", "warm", "isolation_first", "isolation_warm"},
                "Vector cache checkpoint executions are invalid")
        for label, case in cases.items():
            chosen = source["isolation_agent_id"] if label.startswith("isolation") else agent_id
            require(isinstance(case, dict) and type(case.get("execution_id")) is int and case["execution_id"] > 0
                    and case.get("agent_id") == chosen and case.get("query") == semantic.QUERY,
                    "Vector cache checkpoint contains invalid execution IDs")
            require(read_capture(base_url, case["execution_id"], chosen, semantic.QUERY) == case.get("memory_context")
                    and inspection(base_url, case["execution_id"]) == case.get("inspection")
                    and cache_stats(base_url, case["execution_id"]) == case.get("cache"),
                    "Original cache execution, evidence, trace, or snapshot was lost or changed")
        require_warm(cases["warm"]); require_warm(cases["isolation_warm"])
    else:
        probe = semantic.preview(base_url, agent_id)
        require(probe["provider"] == "mock" and probe["runtime_mode"] == "semantic", "Enable semantic mode on the running Mock backend")
        cases = {"first": captured_chat(base_url, agent_id), "warm": captured_chat(base_url, agent_id),
                 "isolation_first": captured_chat(base_url, source["isolation_agent_id"]),
                 "isolation_warm": captured_chat(base_url, source["isolation_agent_id"])}
        require_warm(cases["warm"]); require_warm(cases["isolation_warm"])
        facts = cases["warm"]["memory_context"]["evidence"]
        require(facts["mode"] == "semantic" and any(row["memory_id"] == source["private"]["id"] and row["similarity"] == 0.96
                    for row in facts["agent_memories"]) and any(row["memory_id"] == source["shared"]["id"] and row["similarity"] == 0.96
                    for row in facts["shared_memories"]), "Cached ranking changed the semantic fixtures")
        foreign = cases["isolation_warm"]["memory_context"]["evidence"]
        require(foreign["user_id"] == source["isolation_user_id"] and foreign["agent_memories"] == []
                and all(row["scope_id"] == source["isolation_user_id"] for row in foreign["shared_memories"]), "Cached vectors crossed user scope")
        vectors = fixture_vectors(source)
        prefix = "AgentDeskSemanticTemporary " + uuid4().hex + " | "
        transient = memory_request(base_url, "/memories", {"agent_id": agent_id, "content": prefix + "SQLite records survive restarts."})
        common = memory_request(base_url, f"/user-memories/for-agent/{agent_id}", {"user_id": owner, "content": transient["content"]})
        paths = [("agent", agent_id, transient, f'/memories/item/{transient["id"]}?agent_id={agent_id}'),
                 ("user", owner, common, f'/user-memories/item/{common["id"]}?agent_id={agent_id}&user_id={owner}')]
        try:
            captured_chat(base_url, agent_id, "Can saved information stay after reboot?")
            for kind, chosen, row, path in paths:
                with SessionLocal() as db:
                    require(db.query(MemoryVectorCache).filter_by(source_type=kind, owner_id=chosen, memory_id=row["id"]).count() > 0,
                            "Temporary fixture cache was not populated")
                memory_request(base_url, path, {"content": prefix + "Unrelated semantic fixture.", "expected_content": row["content"]}, method="PATCH")
                with SessionLocal() as db:
                    require(db.query(MemoryVectorCache).filter_by(source_type=kind, owner_id=chosen, memory_id=row["id"]).count() == 0,
                            "Edited fixture retained stale cache entries")
                require(all(result["memory"]["id"] != row["id"] for result in semantic.preview(base_url, agent_id,
                    "Can saved information stay after reboot?", shared=kind == "user")["results"]), "Edit reused stale cached vectors")
            captured_chat(base_url, agent_id, "Unrelated semantic fixture.")
        finally:
            for _, _, _, path in paths: memory_request(base_url, path, method="DELETE")
        for kind, chosen, row, _ in paths:
            with SessionLocal() as db:
                require(db.query(MemoryVectorCache).filter_by(source_type=kind, owner_id=chosen, memory_id=row["id"]).count() == 0,
                        "Deleted fixture retained cached vectors")
        require(fixture_vectors(source) == vectors, "Temporary checks changed the original fixture cache")
    # On reuse, all persistence validation precedes the single proof chat.
    proof = captured_chat(base_url, agent_id) if reused else cases["warm"]
    require_warm(proof)
    with SessionLocal() as db:
        before = [cache_record(row) for row in db.query(MemoryVectorCache).order_by(MemoryVectorCache.id).all()]
    for chosen, user in ((agent_id, False), (agent_id, True), (peer_id, True)):
        semantic.preview(base_url, chosen, shared=user)
    with SessionLocal() as db:
        require([cache_record(row) for row in db.query(MemoryVectorCache).order_by(MemoryVectorCache.id).all()] == before,
                "Read-only previews changed the vector cache")
    require(source_file.read_bytes() == source_bytes, "Original semantic checkpoint changed")
    semantic.validate_checkpoint(base_url, source, agent_id, peer_id, owner, agents, read=request_json)
    if not reused:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=state_file.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump({"version": 1, "namespace": namespace(settings), "source_checkpoint": source,
                       "vectors": fixture_vectors(source), "cases": cases}, handle, ensure_ascii=False)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        try: os.replace(temporary, state_file)
        finally: temporary.unlink(missing_ok=True)
    return {"checks_passed": 7, "persistence_verified": verify_persistence, "checkpoint_reused": reused,
            "chat_executions_created": 1 if reused else 6, "warm_execution_id": proof["execution_id"],
            "original_execution_ids": {label: case["execution_id"] for label, case in cases.items()},
            "cache_hits": proof["cache"]["hits"], "cache_misses": 0, "cache_written": 0,
            "source_memories_unchanged": True, "embedding_provider": "mock", "reply_mode": "fixed_mock_reply"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--verify-persistence", action="store_true")
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--semantic-state-file", type=Path)
    args = parser.parse_args()
    try:
        result = check_memory_vector_cache(args.base_url, args.verify_persistence, args.state_file, args.semantic_state_file)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError, TypeError, OSError, SQLAlchemyError) as error:
        parser.exit(1, f"Memory vector cache check failed: {error}\n")
    print(json.dumps({"status": "passed", **result}))


if __name__ == "__main__": main()
