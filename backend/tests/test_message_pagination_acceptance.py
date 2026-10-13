"""Restart verification keeps original data and rejects changed evidence without repair."""

import json
from urllib.parse import urlsplit

import pytest

from app import check_conversation_pagination as fingerprints
from app import check_message_pagination as checker
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
        result = client.request(method, path, json=payload)
        assert result.status_code == 200, result.text
        return result.json()
    def expected_request(base_url, path, payload=None, *, method=None, status=200):
        method = method or ("GET" if payload is None else "POST")
        calls.append((method, path))
        result = client.request(method, path, json=payload)
        assert result.status_code == status, result.text
        return result.json()
    monkeypatch.setattr(checker, "SessionLocal", sessions)
    monkeypatch.setattr(fingerprints, "SessionLocal", sessions)
    monkeypatch.setattr(checker, "request_json", request)
    monkeypatch.setattr(checker, "memory_request", expected_request)
    return client, ids, sessions, tmp_path / "message-pagination-acceptance.json", calls


def run(path, verify=False):
    return checker.check_message_pagination("http://frontend", verify, path)


@pytest.mark.parametrize("existing", [False, True])
def test_initial_reuse_restart_preserve_full_history_vectors_and_previous_checkpoints(acceptance, existing):
    client, ids, _, path, calls = acceptance
    if existing:
        conversation = client.post('/conversations', json={"agent_id": ids["agent_id"], "title": "Existing user chat"}).json()
        client.post(f'/conversations/{conversation["id"]}/messages?agent_id={ids["agent_id"]}',
                    json={"role": "user", "content": "Preserve my old message"})
    older = path.with_name("conversation-pagination-acceptance.json")
    older.write_bytes(b'{"old": "checkpoint"}\n')
    before = checker.database_fingerprints()
    first = run(path)
    assert first["checks_passed"] == 8 and first["pages_walked"] == 3 and first["saved_message_count"] == 45
    assert first["conversations_created"] == 3 and first["messages_created"] == 46
    assert first["chat_executions_created"] == 0
    after = checker.database_fingerprints()
    for table in before.keys() - {"conversations", "messages"}:
        assert after[table] == before[table]
    assert after["conversations"]["rows"] == before["conversations"]["rows"] + 3
    assert after["messages"]["rows"] == before["messages"]["rows"] + 46
    original = path.read_bytes()
    for verify in (False, True):
        calls.clear()
        reused = run(path, verify)
        assert reused["checkpoint_reused"] is True and reused["read_only"] is True
        assert reused["persistence_verified"] is verify and reused["checks_passed"] == 8
        assert reused["conversations_created"] == reused["messages_created"] == reused["chat_executions_created"] == 0
        for key in ("conversation_id", "empty_conversation_id", "foreign_conversation_id", "message_ids"):
            assert reused[key] == first[key]
        assert all(method == "GET" for method, _ in calls)
        assert checker.database_fingerprints() == after and path.read_bytes() == original
        assert older.read_bytes() == b'{"old": "checkpoint"}\n'


def test_missing_checkpoint_stops_before_http_or_writes(acceptance):
    _, _, _, path, calls = acceptance
    before = checker.database_fingerprints()
    with pytest.raises(RuntimeError, match="checkpoint is missing"):
        run(path, True)
    assert not path.exists() and calls == []
    assert checker.database_fingerprints() == before


@pytest.mark.parametrize("change", ["conversation", "message", "title", "content", "timestamp", "unrelated", "checkpoint_kind", "checkpoint_id", "fingerprint"])
def test_changed_or_missing_restart_evidence_is_never_repaired(acceptance, change):
    client, ids, sessions, path, calls = acceptance
    first = run(path)
    state = json.loads(path.read_bytes())
    with sessions() as db:
        conversation = db.get(Conversation, first["conversation_id"])
        message = db.get(Message, first["message_ids"][0])
        if change == "conversation": db.delete(conversation)
        elif change == "message": db.delete(message)
        elif change == "title": conversation.title = "Changed saved title"
        elif change == "content": message.content = "Changed saved content"
        elif change == "timestamp": message.created_at = message.created_at.replace(year=2025)
        db.commit()
    if change == "unrelated":
        client.post('/conversations', json={"agent_id": ids["agent_id"], "title": "New outside chat"})
    if change in ("checkpoint_kind", "checkpoint_id", "fingerprint"):
        if change == "checkpoint_kind": state["kind"] = "semantic-memory"
        elif change == "checkpoint_id": state["conversation"]["id"] = state["foreign"]["id"]
        else: state["database"]["messages"]["sha256"] = "changed"
        path.write_text(json.dumps(state))
    before, checkpoint = checker.database_fingerprints(), path.read_bytes()
    calls.clear()
    with pytest.raises((RuntimeError, AssertionError)):
        run(path, True)
    assert all(method == "GET" for method, _ in calls)
    assert checker.database_fingerprints() == before and path.read_bytes() == checkpoint


@pytest.mark.parametrize("existing", [False, True])
def test_unavailable_page_route_fails_before_any_fixture_write(acceptance, monkeypatch, existing):
    client, ids, _, path, calls = acceptance
    if existing:
        client.post('/conversations', json={"agent_id": ids["agent_id"], "title": "Existing chat"})
        original = checker.request_json
        def unavailable(base_url, query, payload=None):
            if urlsplit(query).path.endswith('/messages/page'):
                raise RuntimeError("Message page API unavailable")
            return original(base_url, query, payload)
        monkeypatch.setattr(checker, "request_json", unavailable)
    else:
        monkeypatch.setattr(checker, "memory_request", lambda *args, **kwargs: {"detail": "Not Found"})
    before = checker.database_fingerprints()
    with pytest.raises(RuntimeError, match="unavailable"):
        run(path)
    assert all(method == "GET" for method, _ in calls)
    assert checker.database_fingerprints() == before and not path.exists()


def test_wrong_page_scope_fails_read_only(acceptance, monkeypatch):
    _, _, _, path, calls = acceptance
    run(path)
    original = checker.request_json
    def wrong_scope(base_url, query, payload=None):
        value = original(base_url, query, payload)
        if urlsplit(query).path.endswith('/messages/page'):
            value["conversation_id"] += 1
        return value
    monkeypatch.setattr(checker, "request_json", wrong_scope)
    calls.clear()
    before = checker.database_fingerprints()
    with pytest.raises(RuntimeError, match="scope"):
        run(path, True)
    assert all(method == "GET" for method, _ in calls)
    assert checker.database_fingerprints() == before


def test_checkpoint_requires_separate_json_path_and_correct_kind(acceptance):
    _, _, _, path, calls = acceptance
    with pytest.raises(RuntimeError, match="separate .json"):
        run(path.with_suffix('.db'))
    assert calls == []
    path.write_text('{"kind":"wrong","version":1}')
    with pytest.raises(RuntimeError, match="checkpoint is invalid"):
        run(path)
    assert all(method == "GET" for method, _ in calls)


def test_ollama_semantic_configuration_never_executes_a_chat(acceptance, monkeypatch):
    _, _, _, path, calls = acceptance
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    monkeypatch.setenv("MEMORY_VECTOR_CACHE_ENABLED", "true")
    assert run(path)["chat_executions_created"] == 0
    calls.clear()
    assert run(path, True)["read_only"] is True
    assert all(method == "GET" and not query.endswith('/chat') for method, query in calls)
