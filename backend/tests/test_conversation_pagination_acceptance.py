"""Verify immutable restart evidence and read-only HTTP acceptance probes."""

import json
from urllib.parse import urlsplit

import pytest

from app import check_conversation_pagination as checker
from app.models.conversation import Conversation
from app.models.message import Message
from test_mcp_runtime_api import demo_api  # noqa: F401


@pytest.fixture
def acceptance(demo_api, monkeypatch, tmp_path):
    client, ids, sessions = demo_api
    calls = []
    def request(base_url, path, payload=None):
        method = "GET" if payload is None else "POST"
        calls.append((method, path))
        reply = client.request(method, path, json=payload)
        assert reply.status_code == 200, reply.text
        return reply.json()
    def expected_request(base_url, path, payload=None, *, method=None, status=200):
        method = method or ("GET" if payload is None else "POST")
        calls.append((method, path))
        reply = client.request(method, path, json=payload)
        assert reply.status_code == status, reply.text
        return reply.json()
    monkeypatch.setattr(checker, "SessionLocal", sessions)
    monkeypatch.setattr(checker, "request_json", request)
    monkeypatch.setattr(checker, "memory_request", expected_request)
    return client, ids, sessions, tmp_path / "conversation-pagination-acceptance.json", calls


def run(path, verify=False):
    return checker.check_conversation_pagination("http://frontend", verify, path)


def test_first_check_reuse_and_restart_preserve_ids_messages_all_tables_and_other_checkpoints(acceptance):
    client, ids, sessions, path, calls = acceptance
    existing = client.post("/conversations", json={"agent_id": ids["agent_id"], "title": "Keep my existing chat"}).json()
    reply = client.post(f'/conversations/{existing["id"]}/chat?agent_id={ids["agent_id"]}', json={"message": "I like Python"})
    assert reply.status_code == 200
    legacy = path.with_name("legacy-acceptance.json")
    legacy.write_bytes(b'{"saved": true}\n')
    before = checker.database_fingerprints()
    first = run(path)
    assert first["checks_passed"] == 8 and first["read_only"] is False
    assert first["conversations_created"] == 6 and first["messages_created"] == 1
    assert first["chat_executions_created"] == 0
    after = checker.database_fingerprints()
    assert after["conversations"]["rows"] == before["conversations"]["rows"] + 6
    assert after["messages"]["rows"] == before["messages"]["rows"] + 1
    for table in before.keys() - {"conversations", "messages"}:
        assert after[table] == before[table]
    original = path.read_bytes()
    for verify in (False, True):
        calls.clear()
        reused = run(path, verify)
        assert reused["checks_passed"] == 8 and reused["read_only"] is True
        assert reused["checkpoint_reused"] is True and reused["persistence_verified"] is verify
        assert reused["conversations_created"] == reused["messages_created"] == reused["chat_executions_created"] == 0
        for key in ("conversation_ids", "foreign_conversation_id", "saved_message_id"):
            assert reused[key] == first[key]
        assert all(method == "GET" for method, _ in calls)
        assert checker.database_fingerprints() == after
        assert path.read_bytes() == original
        assert legacy.read_bytes() == b'{"saved": true}\n'


def test_missing_checkpoint_fails_without_http_or_database_writes(acceptance):
    _, _, _, path, calls = acceptance
    before = checker.database_fingerprints()
    with pytest.raises(RuntimeError, match="checkpoint is missing"):
        run(path, True)
    assert calls == [] and not path.exists()
    assert checker.database_fingerprints() == before


@pytest.mark.parametrize("change", ["conversation", "message", "title", "timestamp", "unrelated", "checkpoint_kind", "checkpoint_id", "fingerprint"])
def test_changed_restart_evidence_fails_without_repairing_anything(acceptance, change):
    client, ids, sessions, path, calls = acceptance
    result = run(path)
    state = json.loads(path.read_bytes())
    with sessions() as db:
        conversation = db.get(Conversation, result["conversation_ids"][0])
        if change == "conversation": db.delete(conversation)
        elif change == "message": db.delete(db.get(Message, result["saved_message_id"]))
        elif change == "title": conversation.title = "Changed title"
        elif change == "timestamp": conversation.created_at = conversation.created_at.replace(year=2025)
        db.commit()
    if change == "unrelated":
        client.post("/conversations", json={"agent_id": ids["agent_id"], "title": "Changed outside acceptance"})
    if change.startswith("checkpoint") or change == "fingerprint":
        if change == "checkpoint_kind": state["kind"] = "semantic-memory"
        elif change == "checkpoint_id": state["conversations"][0]["id"] = state["foreign"]["id"]
        else: state["database"]["conversations"]["sha256"] = "changed"
        path.write_text(json.dumps(state))
    before, checkpoint = checker.database_fingerprints(), path.read_bytes()
    calls.clear()
    with pytest.raises((RuntimeError, AssertionError)):
        run(path, True)
    assert all(method == "GET" for method, _ in calls)
    assert checker.database_fingerprints() == before and path.read_bytes() == checkpoint


def test_invalid_checkpoint_never_creates_a_replacement_fixture(acceptance):
    _, _, _, path, calls = acceptance
    path.write_text('{"kind":"wrong","version":1}')
    before = checker.database_fingerprints()
    with pytest.raises(RuntimeError, match="checkpoint is invalid"):
        run(path)
    assert all(method == "GET" for method, _ in calls)
    assert checker.database_fingerprints() == before


def test_checkpoint_cannot_use_a_database_filename(acceptance):
    _, _, _, path, calls = acceptance
    with pytest.raises(RuntimeError, match="separate .json"):
        run(path.with_suffix(".db"))
    assert calls == []


def test_acceptance_works_with_an_ollama_configured_backend_without_model_calls(acceptance, monkeypatch):
    _, _, _, path, _ = acceptance
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    monkeypatch.setenv("MEMORY_VECTOR_CACHE_ENABLED", "true")
    assert run(path)["checks_passed"] == 8
    assert run(path, True)["read_only"] is True


def test_checker_rejects_a_wrong_page_scope_even_with_valid_fixture_records(acceptance, monkeypatch):
    _, _, _, path, calls = acceptance
    run(path)
    original = checker.request_json
    def wrong_page(base_url, query, payload=None):
        reply = original(base_url, query, payload)
        if urlsplit(query).path == "/conversations/page": reply["agent_id"] += 1
        return reply
    monkeypatch.setattr(checker, "request_json", wrong_page)
    calls.clear()
    before = checker.database_fingerprints()
    with pytest.raises(RuntimeError, match="metadata differ"):
        run(path, True)
    assert all(method == "GET" for method, _ in calls)
    assert checker.database_fingerprints() == before


def test_unavailable_page_api_fails_before_fixture_creation(acceptance, monkeypatch):
    _, _, _, path, calls = acceptance
    original = checker.request_json
    def unavailable(base_url, query, payload=None):
        if urlsplit(query).path == "/conversations/page":
            raise RuntimeError("Page API unavailable")
        return original(base_url, query, payload)
    monkeypatch.setattr(checker, "request_json", unavailable)
    before = checker.database_fingerprints()
    with pytest.raises(RuntimeError, match="Page API unavailable"):
        run(path)
    assert all(method == "GET" for method, _ in calls)
    assert checker.database_fingerprints() == before and not path.exists()
