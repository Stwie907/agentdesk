"""Verify real Ollama vectors through Runtime retrieval without creating chats.

The first run may populate document cache rows and creates a JSON checkpoint.
Reuse validates saved data before embedding anything and remains read-only.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app import check_ollama_memory as quality, check_semantic_memory as semantic
from app.check_demo import require
from app.database import SessionLocal
from app.models.memory_vector_cache import MemoryVectorCache
from app.schemas.memory_evidence import MemoryEvidence
from app.services import semantic_memory
from app.services.memory_embeddings import get_embedding_settings
from app.services.memory_service import build_memory_context, get_agent_memories
from app.services.memory_vector_cache import _cached_vector, model_digest, namespace, source_key
from app.services.user_memory_service import list_user_memories, owner_for_agent


def default_state_file():
    return semantic.default_state_file().with_name("ollama-memory-vector-cache-acceptance.json")


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def database_fingerprints():
    """Fingerprint every table, including rows outside the acceptance fixtures."""
    business, cache = {}, {}
    with SessionLocal() as db:
        require(db.get_bind().dialect.name == "sqlite", "Use the existing SQLite backend")
        connection = db.connection()
        for name in sorted(inspect(connection).get_table_names()):
            quoted = connection.dialect.identifier_preparer.quote(name)
            result = connection.execute(text("SELECT * FROM " + quoted))
            columns = list(result.keys())
            rows = [dict(row) for row in result.mappings()]
            if name == "memory_vector_cache":
                for row in rows:
                    key = json.dumps([row[field] for field in ("source_type", "owner_id", "memory_id", "namespace")])
                    require(key not in cache, "Duplicate document cache identity")
                    cache[key] = fingerprint(row)
            else:
                business[name] = {"columns": columns, "rows": len(rows), "sha256": fingerprint(sorted(fingerprint(row) for row in rows))}
    require("memories" in business and "user_memories" in business, "Existing memory tables are missing")
    return business, cache


def cases_for(source):
    return {
        "agent_english": (source["agent_id"], source["user_id"], semantic.QUERY),
        "agent_chinese": (source["agent_id"], source["user_id"], semantic.CHINESE_QUERY),
        "same_user": (source["peer_agent_id"], source["user_id"], semantic.QUERY),
        "isolated_user": (source["isolation_agent_id"], source["isolation_user_id"], semantic.QUERY),
    }


def scoped_sources(source, records):
    rows = {}
    expected = {}
    with SessionLocal() as db:
        for agent_id, owner_id, _ in cases_for(source).values():
            owner = owner_for_agent(db, agent_id)
            require(owner is not None and owner.id == owner_id, "Local SQLite owner differs from the saved API fixtures")
            for row in [*get_agent_memories(db, agent_id), *list_user_memories(db, owner_id)]:
                rows[source_key(row)] = (*source_key(row), row.content, row.created_at)
            for kind, owner, records_in_scope in (
                    ("agent", agent_id, records[f"/memories/{agent_id}"]),
                    ("user", owner_id, records[f"/user-memories/for-agent/{agent_id}"]["memories"])):
                quality.validate_rows(records_in_scope, "agent_id" if kind == "agent" else "user_id", owner)
                for row in records_in_scope:
                    key = (kind, owner, row["id"])
                    expected[key] = (*key, row["content"], datetime.fromisoformat(row["created_at"]))
    require(rows == expected, "Local SQLite memory rows differ from the running API")
    return rows


def validate_cached_sources(sources, settings, digest):
    with SessionLocal() as db:
        entries = {(row.source_type, row.owner_id, row.memory_id): row for row in
                   db.query(MemoryVectorCache).filter_by(namespace=namespace(settings))}
        require(all(key in entries and _cached_vector(entries[key], snapshot, digest) is not None
                    for key, snapshot in sources.items()), "Original scoped document vectors are missing, corrupt, or incompatible")
        return sorted({entries[key].dimensions for key in sources})


@contextmanager
def observe_embedding_inputs():
    """Forward unchanged inputs to the production client in this CLI process."""
    original = semantic_memory.embed_texts
    observed = []
    def forward(texts, settings):
        observed.append(list(texts))
        return original(texts, settings)
    semantic_memory.embed_texts = forward
    try:
        yield observed
    finally:
        semantic_memory.embed_texts = original


def validate_case(case, identity, settings, *, warm):
    require(isinstance(case, dict), "Saved Runtime retrieval case is invalid")
    evidence = MemoryEvidence.model_validate_json(json.dumps(case["memory_context"]))
    require((evidence.agent_id, evidence.user_id, evidence.query) == identity
            and evidence.mode == evidence.requested_mode == "semantic" and evidence.limit == 5
            and evidence.provider == "ollama" and evidence.model == settings.model
            and evidence.min_similarity == settings.memory.min_similarity,
            "Runtime retrieval used a different provider, scope, mode, or threshold")
    stats = case.get("cache")
    require(isinstance(stats, dict) and type(stats.get("version")) is int and stats["version"] == 1
            and stats.get("status") == "active" and stats.get("provider") == "ollama" and stats.get("model") == settings.model
            and all(type(stats.get(key)) is int and stats[key] >= 0 for key in ("documents", "hits", "misses", "written"))
            and stats["documents"] > 0 and stats["documents"] == stats["hits"] + stats["misses"]
            and stats["written"] <= stats["misses"]
            and type(case.get("embedding_inputs")) is int and case["embedding_inputs"] == 1 + stats["misses"],
            "Runtime cache statistics or observed embedding inputs are invalid")
    if warm:
        require(stats["hits"] == stats["documents"] and stats["misses"] == stats["written"] == 0
                and case["embedding_inputs"] == 1, "Warm retrieval regenerated document vectors")
    return evidence


def runtime_case(identity, settings, *, populate):
    captures, stats, fallbacks = [], [], []
    with SessionLocal() as db:
        with observe_embedding_inputs() as inputs:
            build_memory_context(db, identity[0], identity[2], on_details=captures.append,
                                 on_cache=stats.append, on_fallback=fallbacks.append, populate_cache=populate)
        require(not fallbacks and len(captures) == len(stats) == 1,
                "Ollama Runtime retrieval fell back or did not produce cache evidence: " + "; ".join(fallbacks))
        case = {"memory_context": captures[0].model_dump(mode="json"), "cache": stats[0],
                "embedding_inputs": sum(len(batch) for batch in inputs)}
        validate_case(case, identity, settings, warm=not populate)
        require(inputs and inputs[0][0] == identity[2], "Every retrieval must generate its current query vector")
        if not populate:
            require(inputs == [[identity[2]]], "Warm retrieval must send only the query to Ollama")
        db.commit() if populate else db.rollback()
    return case


def compare_evidence(current, saved):
    current = dict(current); saved = dict(saved)
    current.pop("recorded_at", None); saved.pop("recorded_at", None)
    for field in ("agent_memories", "shared_memories"):
        left, right = current.pop(field), saved.pop(field)
        require(len(left) == len(right), "Warm retrieval selected different source memories")
        for first, second in zip(left, right):
            first, second = dict(first), dict(second)
            a, b = first.pop("similarity"), second.pop("similarity")
            require(first == second and math.isclose(a, b, rel_tol=0, abs_tol=0.00001),
                    "Warm retrieval changed memory selection or semantic scores")
    require(current == saved, "Warm retrieval changed its memory context or metadata")


def write_checkpoint(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(state, stream, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def check_ollama_memory_vector_cache(base_url, verify_persistence=False, state_file=None, semantic_state_file=None, timeout=180):
    settings = get_embedding_settings()
    require(settings.provider == "ollama" and settings.memory.mode == "semantic" and settings.memory.cache_enabled,
            "Use the Ollama backend with semantic retrieval and vector cache enabled, without the Mock override")
    source_file = semantic.default_state_file() if semantic_state_file is None else Path(semantic_state_file)
    state_file = default_state_file() if state_file is None else Path(state_file)
    require(state_file.suffix == ".json" and state_file.resolve() != source_file.resolve(), "Use a separate JSON vector cache checkpoint")
    require(not verify_persistence or state_file.is_file(), "Ollama vector cache checkpoint is missing; run the initial check first")
    require(source_file.is_file(), "Keep the existing semantic memory checkpoint and SQLite volume")
    source_bytes = source_file.read_bytes(); source = json.loads(source_bytes)
    require(isinstance(source, dict) and type(source.get("version")) is int and source["version"] == 1,
            "Semantic memory checkpoint is invalid")
    require(all(type(source.get(key)) is int and source[key] > 0 for key in
                ("agent_id", "peer_agent_id", "isolation_agent_id", "user_id", "isolation_user_id", "execution_id"))
            and len({source[key] for key in ("agent_id", "peer_agent_id", "isolation_agent_id")}) == 3,
            "Semantic memory checkpoint has invalid or duplicated IDs")
    api = quality.ReadOnlyAPI(base_url, timeout)
    before_api = quality.capture_records(api, source)
    semantic.validate_checkpoint(base_url, source, source["agent_id"], source["peer_agent_id"], source["user_id"],
                                 before_api["/agents"], read=lambda base, path: api.get(path))
    business_before, cache_before = database_fingerprints()
    sources = scoped_sources(source, before_api)
    digest = model_digest(settings)
    require(digest is not None, "Ollama model digest is unavailable; check the configured local model and /api/tags")
    reused = state_file.is_file()
    checkpoint_bytes = state_file.read_bytes() if reused else None
    identities = cases_for(source)
    populations, warm = {}, {}
    if reused:
        saved = json.loads(checkpoint_bytes)
        require(isinstance(saved, dict) and type(saved.get("version")) is int and saved["version"] == 1
                and saved.get("namespace") == namespace(settings) and saved.get("model_digest") == digest
                and saved.get("source_sha256") == sha256(source_bytes).hexdigest()
                and saved.get("business_records") == business_before and saved.get("cache_records") == cache_before,
                "Original Ollama cache, records, model, or checkpoint changed; verification will not repair them")
        require(isinstance(saved.get("warm_cases"), dict) and set(saved["warm_cases"]) == set(identities),
                "Ollama vector cache checkpoint has invalid saved retrieval cases")
        for label, identity in identities.items():
            validate_case(saved["warm_cases"][label], identity, settings, warm=True)
            expected_documents = sum(key[0] == "agent" and key[1] == identity[0]
                                     or key[0] == "user" and key[1] == identity[1] for key in sources)
            require(saved["warm_cases"][label]["cache"]["documents"] == expected_documents,
                    "Saved Runtime cache document count differs from its original scope")
        validate_cached_sources(sources, settings, digest)
    # Probe the running server's provider and mode only after restart preflight.
    # This GET cannot populate or repair the cache.
    quality.semantic_preview(api, source, before_api, settings.memory, source["agent_id"], semantic.QUERY)
    if not reused:
        # Each owner is warmed through the same context builder used by Runtime.
        for label in ("agent_english", "same_user", "isolated_user"):
            populations[label] = runtime_case(identities[label], settings, populate=True)
        require(database_fingerprints()[0] == business_before, "Source records changed during cache population")
    for label, identity in identities.items():
        warm[label] = runtime_case(identity, settings, populate=False)
        previous = saved["warm_cases"][label] if reused else populations.get(label)
        if previous is not None:
            compare_evidence(warm[label]["memory_context"], previous["memory_context"])
    dimensions = validate_cached_sources(sources, settings, digest)
    require(model_digest(settings) == digest, "Local embedding model changed during acceptance")
    populated_business, populated_cache = database_fingerprints()
    require(populated_business == business_before, "Business records changed during Runtime retrieval")
    allowed = {json.dumps([*key, namespace(settings)]) for key in sources}
    require({key: value for key, value in populated_cache.items() if key not in allowed}
            == {key: value for key, value in cache_before.items() if key not in allowed},
            "Cache population modified a different scope, provider, or model namespace")
    if reused:
        require(populated_cache == cache_before, "Restart verification changed saved document vectors")
    preview = quality.check_ollama_memory(base_url, source_file, timeout)
    require(database_fingerprints() == (populated_business, populated_cache)
            and quality.capture_records(api, source) == before_api and source_file.read_bytes() == source_bytes,
            "Read-only preview, source records, or semantic checkpoint changed during acceptance")
    require(model_digest(settings) == digest, "Local embedding model changed during preview acceptance")
    if reused:
        require(state_file.read_bytes() == checkpoint_bytes, "Ollama cache checkpoint changed during verification")
    else:
        write_checkpoint(state_file, {"version": 1, "namespace": namespace(settings), "model_digest": digest,
            "source_sha256": sha256(source_bytes).hexdigest(), "business_records": populated_business,
            "cache_records": populated_cache, "warm_cases": warm})
    own = warm["agent_english"]
    checks = ["saved_fixture_identity", "ollama_model_identity", "scoped_runtime_cache",
              "english_and_chinese_query_only_reuse", "same_user_shared_reuse", "foreign_user_isolation",
              "read_only_preview_quality", "preserved_records_vectors_and_checkpoints"]
    return {"checks_passed": len(checks), "checks": checks, "embedding_provider": "ollama", "embedding_model": settings.model,
            "runtime_mode": "semantic", "retrieval_component": "build_memory_context", "model_digest": digest,
            "persistence_verified": reused, "checkpoint_reused": reused, "read_only": reused,
            "chat_executions_created": 0, "source_execution_id": source["execution_id"],
            "cache_rows_written": sum(case["cache"]["written"] for case in populations.values()),
            "warm_cache_hits": own["cache"]["hits"], "warm_cache_misses": own["cache"]["misses"],
            "warm_cache_written": own["cache"]["written"], "warm_embedding_inputs": own["embedding_inputs"],
            "scoped_cache_rows": len(sources), "vector_dimensions": dimensions,
            "source_records_unchanged": True, "preview_read_only": preview["read_only"],
            "preview_checks_passed": preview["checks_passed"], "evidence": preview["evidence"],
            "warm_cases": {label: {"cache": case["cache"], "embedding_inputs": case["embedding_inputs"]}
                           for label, case in warm.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--state-file", type=Path, help="Separate Ollama cache checkpoint beside SQLite by default")
    parser.add_argument("--semantic-state-file", type=Path, help="Existing semantic fixture checkpoint")
    parser.add_argument("--verify-persistence", action="store_true", help="Require the original saved cache checkpoint")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    try:
        result = check_ollama_memory_vector_cache(args.base_url, args.verify_persistence, args.state_file,
                                                 args.semantic_state_file, args.timeout)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError, TypeError, OSError, SQLAlchemyError) as error:
        parser.exit(1, f"Ollama vector cache check failed: {error}\n")
    print(json.dumps({"status": "passed", **result}))


if __name__ == "__main__":
    main()
