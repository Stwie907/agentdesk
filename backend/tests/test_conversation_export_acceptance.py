"""Acceptance keeps original vectors, source records, and checkpoint evidence."""

import json

import pytest

from app import check_conversation_export as checker
from app import check_conversation_pagination as fingerprints
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
    def export(base_url, path, status=200):
        calls.append(("GET", path))
        reply = client.get(path)
        assert reply.status_code == status, reply.text
        return {"status": reply.status_code, "headers": dict(reply.headers), "content": reply.content}
    monkeypatch.setattr(checker, "SessionLocal", sessions)
    monkeypatch.setattr(fingerprints, "SessionLocal", sessions)
    monkeypatch.setattr(checker, "request_json", request)
    monkeypatch.setattr(checker, "request_export", export)
    return client, ids, sessions, tmp_path / "conversation-export-acceptance.json", calls


def run(path, verify=False):
    return checker.check_conversation_export("http://frontend", verify, path)


def test_initial_and_restart_preserve_all_export_bytes_and_earlier_records(acceptance):
    client, ids, _, path, calls = acceptance
    existing = client.post('/conversations', json={"agent_id": ids["agent_id"], "title": "Original chat"}).json()
    client.post(f'/conversations/{existing["id"]}/messages', json={"role": "user", "content": "Keep original message"})
    previous = path.with_name("message-pagination-acceptance.json")
    previous.write_bytes(b'{"previous":"unchanged"}\n')
    before = checker.database_fingerprints()
    first = run(path)
    assert first["checks_passed"] == 8 and first["saved_message_count"] == 25 and first["latest_page_count"] == 20
    assert first["conversations_created"] == 3 and first["messages_created"] == 26 and first["chat_executions_created"] == 0
    after, checkpoint = checker.database_fingerprints(), path.read_bytes()
    for table in before.keys() - {"conversations", "messages"}: assert before[table] == after[table]
    assert after["conversations"]["rows"] == before["conversations"]["rows"] + 3
    assert after["messages"]["rows"] == before["messages"]["rows"] + 26
    for verify in (False, True):
        calls.clear()
        reused = run(path, verify)
        assert reused["checkpoint_reused"] is True and reused["read_only"] is True
        assert reused["persistence_verified"] is verify
        assert reused["export_sha256"] == first["export_sha256"] and reused["message_ids"] == first["message_ids"]
        assert reused["conversations_created"] == reused["messages_created"] == reused["chat_executions_created"] == 0
        assert all(method == "GET" for method, _ in calls)
        assert checker.database_fingerprints() == after and path.read_bytes() == checkpoint
        assert previous.read_bytes() == b'{"previous":"unchanged"}\n'


def test_missing_checkpoint_fails_before_http_or_repair(acceptance):
    _, _, _, path, calls = acceptance
    before = checker.database_fingerprints()
    with pytest.raises(RuntimeError, match="checkpoint is missing"): run(path, True)
    assert not path.exists() and calls == [] and checker.database_fingerprints() == before


@pytest.mark.parametrize("change", ["conversation", "message", "title", "content", "timestamp", "unrelated",
                                   "kind", "scope", "fingerprint", "digest", "previous_missing", "previous_changed"])
def test_changed_or_missing_evidence_fails_without_repair(acceptance, change):
    client, ids, sessions, path, calls = acceptance
    previous = path.with_name("message-pagination-acceptance.json")
    previous.write_text('{"previous":"unchanged"}\n')
    first = run(path)
    state = json.loads(path.read_bytes())
    with sessions() as db:
        conversation = db.get(Conversation, first["conversation_id"])
        message = db.get(Message, first["message_ids"][0])
        if change == "conversation": db.delete(conversation)
        elif change == "message": db.delete(message)
        elif change == "title": conversation.title = "Changed title"
        elif change == "content": message.content = "Changed message"
        elif change == "timestamp": message.created_at = message.created_at.replace(year=2025)
        db.commit()
    if change == "unrelated": client.post('/conversations', json={"agent_id": ids["agent_id"], "title": "Unrelated new chat"})
    if change == "kind": state["kind"] = "message-pagination"
    if change == "scope": state["agent_id"] = ids["mcp_agent_id"]
    if change == "fingerprint": state["database"]["messages"]["sha256"] = "changed"
    if change == "digest": state["export_sha256"]["conversation.json"] = "changed"
    if change in ("kind", "scope", "fingerprint", "digest"): path.write_text(json.dumps(state))
    if change == "previous_missing": previous.unlink()
    if change == "previous_changed": previous.write_text('{"changed":true}\n')
    before, checkpoint = checker.database_fingerprints(), path.read_bytes()
    calls.clear()
    with pytest.raises((RuntimeError, AssertionError)): run(path, True)
    assert all(method == "GET" for method, _ in calls)
    assert checker.database_fingerprints() == before and path.read_bytes() == checkpoint


def test_unavailable_export_route_stops_before_fixture_writes(acceptance, monkeypatch):
    _, _, _, path, calls = acceptance
    def unavailable(*args):
        return {"status":404, "headers":{}, "content":b'{"detail":"Not Found"}'}
    monkeypatch.setattr(checker, "request_export", unavailable)
    before = checker.database_fingerprints()
    with pytest.raises(RuntimeError, match="unavailable"): run(path)
    assert all(method == "GET" for method, _ in calls)
    assert checker.database_fingerprints() == before and not path.exists()
