"""Verify actual embedding savings, source/model invalidation, and read-only previews."""

import json
from types import SimpleNamespace

import pytest
import requests

from app.models.memory import Memory
from app.models.memory_vector_cache import MemoryVectorCache
from app.services import memory_vector_cache as cache, semantic_memory
from app.services.memory_embeddings import get_embedding_settings, mock_vector, normalize_vector
from app.services.memory_service import build_memory_context
from test_mcp_runtime_api import demo_api  # noqa: F401
from test_memory_evidence import chat, database_rows, evidence
from test_semantic_memory import save, search, shared
from test_user_memory import add_agent


def cache_log(client, execution_id):
    logs = client.get(f"/executions/{execution_id}/logs").json()
    records = [json.loads(row["message"].split(": ", 1)[1]) for row in logs
               if row["message"].startswith("memory_embedding_cache: ")]
    assert len(records) == 1
    return records[0]


@pytest.fixture
def cache_demo(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    private = save(client, ids["agent_id"], "I prefer concise answers.")
    common = shared(client, ids["agent_id"], ids["user_id"], "我喜欢简洁的回答。")
    calls = []
    original = semantic_memory.embed_texts
    def embed(texts, settings):
        calls.append(list(texts)); return original(texts, settings)
    monkeypatch.setattr(semantic_memory, "embed_texts", embed)
    return client, ids, sessions, private, common, calls


def test_cold_preview_stays_read_only_then_runtime_reuses_document_vectors(cache_demo):
    client, ids, sessions, private, common, calls = cache_demo
    before = database_rows(sessions)
    cold = search(client, ids["agent_id"]).json()
    assert calls == [["Keep it brief.", private["content"]]]
    assert database_rows(sessions) == before
    first = chat(client, ids["agent_id"], "Keep it brief.")
    initial = cache_log(client, first["execution_id"])
    assert (initial["hits"], initial["misses"], initial["written"]) == (0, 2, 2)
    second = chat(client, ids["agent_id"], "Keep it brief.")
    warm = cache_log(client, second["execution_id"])
    assert (warm["hits"], warm["misses"], warm["written"]) == (2, 0, 0)
    assert calls[-1] == ["Keep it brief."]
    first_facts = evidence(client, first["execution_id"], ids["agent_id"])
    second_facts = evidence(client, second["execution_id"], ids["agent_id"])
    assert {**first_facts, "recorded_at": second_facts["recorded_at"]} == second_facts
    assert common["content"] in second_facts["context"]
    before = database_rows(sessions)
    assert search(client, ids["agent_id"]).json() == cold
    assert calls[-1] == ["Keep it brief."] and database_rows(sessions) == before


def test_shared_hits_reuse_one_owner_and_never_cross_source_type_or_user(cache_demo):
    client, ids, sessions, private, common, calls = cache_demo
    assert private["id"] == common["id"], "Exercise equal IDs from different tables"
    first = chat(client, ids["agent_id"], "Keep it brief.")
    assert cache_log(client, first["execution_id"])["written"] == 2
    peer = chat(client, ids["mcp_agent_id"], "Keep it brief.")
    assert cache_log(client, peer["execution_id"])["hits"] == 1 and calls[-1] == ["Keep it brief."]
    outsider, owner = add_agent(sessions)
    foreign = shared(client, outsider, owner, common["content"])
    other = chat(client, outsider, "Keep it brief.")
    assert cache_log(client, other["execution_id"])["hits"] == 0
    assert calls[-1] == ["Keep it brief.", foreign["content"]]
    facts = evidence(client, other["execution_id"], outsider)
    assert facts["agent_memories"] == [] and facts["shared_memories"][0]["scope_id"] == owner


@pytest.mark.parametrize("source", ["agent", "user"])
def test_edits_clear_all_model_entries_and_deletion_prevents_id_reuse(cache_demo, source):
    client, ids, sessions, private, common, calls = cache_demo
    chat(client, ids["agent_id"], "Keep it brief.")
    row = private if source == "agent" else common
    owner = ids["agent_id"] if source == "agent" else ids["user_id"]
    path = f'/memories/item/{row["id"]}?agent_id={ids["agent_id"]}' if source == "agent" else (
        f'/user-memories/item/{row["id"]}?agent_id={ids["agent_id"]}&user_id={owner}')
    with sessions() as db:
        saved = db.query(MemoryVectorCache).filter_by(source_type=source, memory_id=row["id"], owner_id=owner).one()
        other = MemoryVectorCache(**{column.name: getattr(saved, column.name) for column in MemoryVectorCache.__table__.columns
                                    if column.name != "id"})
        other.namespace = "f" * 64; db.add(other); db.commit()
    changed = client.patch(path, json={"content": "SQLite records survive restarts.", "expected_content": row["content"]})
    assert changed.status_code == 200
    with sessions() as db:
        assert db.query(MemoryVectorCache).filter_by(source_type=source, memory_id=row["id"], owner_id=owner).count() == 0
    before = database_rows(sessions)
    result = search(client, ids["agent_id"], "Can saved information stay after reboot?", user=source == "user").json()
    assert result["results"][0]["memory"] == changed.json() and database_rows(sessions) == before
    warmed = chat(client, ids["agent_id"], "Can saved information stay after reboot?")
    assert cache_log(client, warmed["execution_id"])["misses"] == 1
    assert client.delete(path).status_code == 200
    with sessions() as db:
        assert db.query(MemoryVectorCache).filter_by(source_type=source, memory_id=row["id"], owner_id=owner).count() == 0
    assert search(client, ids["agent_id"], "Can saved information stay after reboot?", user=source == "user").json()["results"] == []


def test_failed_conditional_edit_keeps_the_cache_and_automatic_name_replacement_clears_it(cache_demo):
    client, ids, sessions, private, _, _ = cache_demo
    chat(client, ids["agent_id"], "Keep it brief.")
    before = database_rows(sessions)
    path = f'/memories/item/{private["id"]}?agent_id={ids["agent_id"]}'
    assert client.patch(path, json={"content": "Changed", "expected_content": "Wrong original"}).status_code == 409
    assert database_rows(sessions) == before
    name = save(client, ids["agent_id"], "User's name is Alice.")
    chat(client, ids["agent_id"], "Keep it brief.")
    with sessions() as db:
        assert db.query(MemoryVectorCache).filter_by(source_type="agent", memory_id=name["id"]).count() == 1
    conversation = client.post("/conversations", json={"agent_id": ids["agent_id"], "title": "Name update"}).json()
    assert client.post(f'/conversations/{conversation["id"]}/chat', json={"message": "My name is Bob"}).status_code == 200
    with sessions() as db:
        assert db.query(MemoryVectorCache).filter_by(source_type="agent", memory_id=name["id"]).count() == 0
        assert db.get(Memory, name["id"]).content == "User's name is Bob."


@pytest.mark.parametrize("corruption", ["json", "nan", "zero", "hash", "dimensions", "source_hash", "source_time", "digest", "changed_dimensions"])
def test_corrupt_or_stale_cached_vectors_are_recomputed(cache_demo, corruption):
    client, ids, sessions, _, _, calls = cache_demo
    chat(client, ids["agent_id"], "Keep it brief.")
    with sessions() as db:
        item = db.query(MemoryVectorCache).filter_by(source_type="agent").one()
        if corruption in ("json", "nan", "zero", "changed_dimensions"):
            item.vector_json = {"json": "{invalid", "nan": "[NaN,0,0,0]", "zero": "[0,0,0,0]", "changed_dimensions": "[1,0]"}[corruption]
            item.vector_hash = cache.content_hash(item.vector_json)
        if corruption == "hash": item.vector_hash = "b" * 64
        if corruption == "dimensions": item.dimensions = 2
        if corruption == "changed_dimensions": item.dimensions = 2
        if corruption == "source_hash": item.content_hash = "b" * 64
        if corruption == "source_time": item.source_created_at = item.source_created_at.replace(year=2020)
        if corruption == "digest": item.model_digest = "b" * 64
        db.commit()
    before = database_rows(sessions)
    assert search(client, ids["agent_id"]).json()["results"][0]["similarity"] == 0.96
    assert database_rows(sessions) == before, "Preview must not repair the cache"
    reply = chat(client, ids["agent_id"], "Keep it brief.")
    stats = cache_log(client, reply["execution_id"])
    assert (stats["hits"], stats["misses"], stats["written"]) == (1, 1, 1)
    with sessions() as db:
        assert db.query(MemoryVectorCache).filter_by(source_type="agent").one().dimensions == 4


def test_disabling_cache_keeps_semantic_results_and_records_no_hits(cache_demo, monkeypatch):
    client, ids, sessions, _, _, calls = cache_demo
    chat(client, ids["agent_id"], "Keep it brief.")
    with sessions() as db:
        before = [(row.id, row.vector_json, row.created_at) for row in db.query(MemoryVectorCache).all()]
    monkeypatch.setenv("MEMORY_VECTOR_CACHE_ENABLED", "false")
    reply = chat(client, ids["agent_id"], "Keep it brief.")
    stats = cache_log(client, reply["execution_id"])
    assert stats["status"] == "disabled" and stats["hits"] == stats["written"] == 0
    assert len(calls[-1]) == 3
    assert evidence(client, reply["execution_id"], ids["agent_id"])["mode"] == "semantic"
    with sessions() as db:
        assert [(row.id, row.vector_json, row.created_at) for row in db.query(MemoryVectorCache).all()] == before


@pytest.mark.parametrize("fault", ["digest", "read", "write"])
def test_optional_cache_failure_does_not_force_keyword_fallback(cache_demo, monkeypatch, fault):
    client, ids, sessions, _, _, _ = cache_demo
    if fault == "digest": monkeypatch.setattr(cache, "model_digest", lambda settings: None)
    else:
        from sqlalchemy import event
        from sqlalchemy.exc import OperationalError
        engine = sessions.kw["bind"]
        def fail(connection, cursor, statement, parameters, context, many):
            if "memory_vector_cache" in statement and ((fault == "read" and statement.lstrip().startswith("SELECT"))
                                                        or (fault == "write" and statement.lstrip().startswith("INSERT"))):
                raise OperationalError(statement, parameters, RuntimeError("cache unavailable"))
        event.listen(engine, "before_cursor_execute", fail)
    try:
        reply = chat(client, ids["agent_id"], "Keep it brief.")
    finally:
        if fault != "digest": event.remove(engine, "before_cursor_execute", fail)
    stats = cache_log(client, reply["execution_id"])
    assert stats["status"] == {"digest": "digest_unavailable", "read": "storage_unavailable", "write": "write_unavailable"}[fault]
    assert reply["status"] == "completed" and stats["written"] == 0
    assert evidence(client, reply["execution_id"], ids["agent_id"])["mode"] == "semantic"


@pytest.mark.parametrize("change", ["edit", "delete"])
def test_late_embedding_cannot_repopulate_an_invalidated_source(demo_api, monkeypatch, change):
    client, ids, sessions = demo_api
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    private = save(client, ids["agent_id"], "I prefer concise answers.")
    original = semantic_memory.embed_texts
    changed = False
    def embed(texts, settings):
        nonlocal changed
        if not changed:
            changed = True
            path = f'/memories/item/{private["id"]}?agent_id={ids["agent_id"]}'
            response = client.delete(path) if change == "delete" else client.patch(path, json={
                "content": "SQLite records survive restarts.", "expected_content": private["content"]})
            assert response.status_code == 200
        return original(texts, settings)
    monkeypatch.setattr(semantic_memory, "embed_texts", embed)
    with sessions() as db:
        stats = []
        assert build_memory_context(db, ids["agent_id"], "Keep it brief.", populate_cache=True, on_cache=stats.append) == private["content"]
        db.commit()
    assert stats[0]["written"] == 0
    with sessions() as db: assert db.query(MemoryVectorCache).count() == 0
    assert search(client, ids["agent_id"]).json()["results"] == []


def test_ollama_model_digest_and_endpoint_changes_never_reuse_old_vectors(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    save(client, ids["agent_id"], "I prefer concise answers.")
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic"); monkeypatch.setenv("LLM_PROVIDER", "ollama")
    digest, calls = {"value": "a" * 64}, []
    monkeypatch.setattr(cache, "model_digest", lambda settings: digest["value"])
    def embed(texts, settings):
        calls.append(list(texts)); return [normalize_vector(mock_vector(text)) for text in texts]
    monkeypatch.setattr(semantic_memory, "embed_texts", embed)
    def retrieve():
        with sessions() as db:
            stats = []; text = build_memory_context(db, ids["agent_id"], "Keep it brief.", populate_cache=True, on_cache=stats.append)
            db.commit(); return text, stats[0]
    assert retrieve()[1]["written"] == 1
    assert retrieve()[1]["hits"] == 1 and calls[-1] == ["Keep it brief."]
    digest["value"] = "b" * 64
    assert retrieve()[1]["hits"] == 0 and len(calls[-1]) == 2
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11435")
    assert retrieve()[1]["hits"] == 0
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "another-local-embedding")
    assert retrieve()[1]["hits"] == 0
    with sessions() as db: assert db.query(MemoryVectorCache).count() == 3


def test_model_change_during_query_is_explicit_and_does_not_mix_spaces(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    save(client, ids["agent_id"], "I prefer concise answers.")
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic"); monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setattr(cache, "model_digest", lambda settings: "a" * 64)
    monkeypatch.setattr(semantic_memory, "embed_texts", lambda texts, settings: [normalize_vector(mock_vector(text)) for text in texts])
    with sessions() as db:
        build_memory_context(db, ids["agent_id"], "Keep it brief.", populate_cache=True); db.commit()
    before = database_rows(sessions)
    digests = iter(["a" * 64, "b" * 64]); monkeypatch.setattr(cache, "model_digest", lambda settings: next(digests))
    response = search(client, ids["agent_id"])
    assert response.status_code == 503 and "identity changed" in response.json()["detail"]
    assert database_rows(sessions) == before


@pytest.mark.parametrize("body,status", [
    ({"models": [{"model": "embeddinggemma:latest", "digest": "a" * 64}]}, 200),
    ({"models": [{"name": "embeddinggemma:latest", "digest": "sha256:" + "a" * 64}]}, 200),
    ({"models": [{"model": "embeddinggemma", "digest": "a" * 64}, {"name": "embeddinggemma", "digest": "b" * 64}]}, 200),
    ({"models": [{"model": "embeddinggemma", "digest": "invalid"}]}, 200),
    ({"models": []}, 200), ({"models": [{}]}, 200), ({"models": "bad"}, 200), ({}, 404), ({}, 302),
])
def test_model_catalog_identity_is_validated_and_proxy_is_bypassed(monkeypatch, body, status):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    seen = []
    def get(client, url, **kwargs):
        seen.append((client.trust_env, url, kwargs)); return SimpleNamespace(status_code=status, json=lambda: body)
    monkeypatch.setattr(requests.Session, "get", get)
    expected = "a" * 64 if status == 200 and isinstance(body.get("models"), list) and len(body["models"]) == 1 and (
        body["models"][0].get("digest") in {"a" * 64, "sha256:" + "a" * 64}) else None
    assert cache.model_digest(get_embedding_settings()) == expected
    assert seen[0][0] is False and seen[0][1].endswith("/api/tags")
    assert seen[0][2] == {"timeout": 5, "allow_redirects": False}


@pytest.mark.parametrize("value", ["yes", "1", "invalid", ""])
def test_invalid_cache_configuration_is_rejected(monkeypatch, value):
    from app.memory_config import get_memory_settings
    monkeypatch.setenv("MEMORY_VECTOR_CACHE_ENABLED", value)
    with pytest.raises(ValueError, match="MEMORY_VECTOR_CACHE_ENABLED"): get_memory_settings()


def test_cache_reads_are_bounded_for_older_sqlite_variable_limits(cache_demo):
    import sqlite3
    client, ids, sessions, _, _, calls = cache_demo
    engine = sessions.kw["bind"]
    with engine.connect() as connection:
        raw = connection.connection.driver_connection
        previous = raw.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)
    try:
        with sessions() as db:
            db.add_all([Memory(agent_id=ids["agent_id"], content=f"Unrelated row {index}") for index in range(300)])
            db.commit()
        first = chat(client, ids["agent_id"], "Keep it brief.")
        assert cache_log(client, first["execution_id"])["written"] == 302
        second = chat(client, ids["agent_id"], "Keep it brief.")
        assert cache_log(client, second["execution_id"])["hits"] == 302 and calls[-1] == ["Keep it brief."]
    finally:
        raw.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, previous)


def test_parallel_population_upserts_one_vector_per_source(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    from app.seed_demo import seed_demo
    monkeypatch.setenv("LLM_PROVIDER", "mock"); monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    engine = create_engine(f"sqlite:///{tmp_path / 'parallel-cache.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        ids = seed_demo(db); db.add(Memory(agent_id=ids["agent_id"], content="I prefer concise answers.")); db.commit()
    barrier = Barrier(2)
    original = semantic_memory.embed_texts
    def embed(texts, settings):
        barrier.wait(timeout=5); return original(texts, settings)
    monkeypatch.setattr(semantic_memory, "embed_texts", embed)
    def populate():
        with sessions() as db:
            text = build_memory_context(db, ids["agent_id"], "Keep it brief.", populate_cache=True)
            db.commit(); return text
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(lambda _: populate(), range(2))) == ["I prefer concise answers."] * 2
        with sessions() as db:
            assert db.query(MemoryVectorCache).count() == 1
    finally: engine.dispose()
