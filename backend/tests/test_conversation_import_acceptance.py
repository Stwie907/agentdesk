"""Imports append only intended fixtures; restart evidence is never repaired."""

import json

import pytest

from app import check_conversation_import as checker
from app import check_conversation_pagination as fingerprints
from app.models.conversation import Conversation
from app.models.message import Message
from test_mcp_runtime_api import demo_api  # noqa: F401


@pytest.fixture
def acceptance(demo_api, monkeypatch, tmp_path):
    client, ids, sessions = demo_api
    calls = []
    def request(base_url, path):
        calls.append(("GET", path))
        reply = client.get(path)
        assert reply.status_code == 200, reply.text
        return reply.json()
    def export(base_url, path, status=200):
        calls.append(("GET", path))
        reply = client.get(path)
        assert reply.status_code == status, reply.text
        return {"status": reply.status_code, "headers": dict(reply.headers), "content": reply.content}
    def upload(base_url, agent_id, raw, status=201):
        calls.append(("POST", f"/conversations/import?agent_id={agent_id}"))
        reply = client.post(f"/conversations/import?agent_id={agent_id}", content=raw, headers={"Content-Type": "application/json"})
        assert reply.status_code == status, reply.text
        return reply.json() if status == 201 else None
    monkeypatch.setattr(checker, "SessionLocal", sessions)
    monkeypatch.setattr(fingerprints, "SessionLocal", sessions)
    monkeypatch.setattr(checker, "request_json", request)
    monkeypatch.setattr(checker, "request_export", export)
    monkeypatch.setattr(checker, "transcript", lambda base, row: request(base, f'/conversations/{row["id"]}/messages?agent_id={row["agent_id"]}'))
    monkeypatch.setattr(checker, "request_import", upload)
    return client, ids, sessions, tmp_path / "conversation-import-acceptance.json", calls


def run(path, verify=False):
    return checker.check_conversation_import("http://frontend", verify, path)


def test_initial_imports_and_read_only_reuse_preserve_originals_and_all_export_hashes(acceptance):
    client, ids, _, path, calls = acceptance
    existing = client.post('/conversations', json={"agent_id": ids["agent_id"], "title": "Original chat"}).json()
    client.post(f'/conversations/{existing["id"]}/messages', json={"role": "user", "content": "Keep original message"})
    previous = path.with_name("conversation-export-acceptance.json")
    previous.write_bytes(b'{"previous":"unchanged"}\n')
    before = checker.database_fingerprints()
    first = run(path)
    assert first["checks_passed"] == 8 and first["saved_message_count"] == 25 and first["latest_page_count"] == 20
    assert first["conversations_created"] == 3 and first["messages_created"] == 50 and first["chat_executions_created"] == 0
    assert first["large_upload_bytes"] > 1024 * 1024
    after, checkpoint = checker.database_fingerprints(), path.read_bytes()
    for table in before.keys() - {"conversations", "messages"}: assert before[table] == after[table]
    assert after["conversations"]["rows"] == before["conversations"]["rows"] + 3
    assert after["messages"]["rows"] == before["messages"]["rows"] + 50
    for verify in (False, True):
        calls.clear()
        reused = run(path, verify)
        assert reused["checkpoint_reused"] is True and reused["read_only"] is True and reused["persistence_verified"] is verify
        assert reused["export_sha256"] == first["export_sha256"] and reused["message_ids"] == first["message_ids"]
        assert reused["foreign_message_ids"] == first["foreign_message_ids"]
        assert reused["conversations_created"] == reused["messages_created"] == reused["chat_executions_created"] == 0
        assert all(method == "GET" for method, _ in calls)
        assert checker.database_fingerprints() == after and path.read_bytes() == checkpoint
        assert previous.read_bytes() == b'{"previous":"unchanged"}\n'


def test_missing_checkpoint_fails_before_http_or_fixture_recreation(acceptance):
    _, _, _, path, calls = acceptance
    before = checker.database_fingerprints()
    with pytest.raises(RuntimeError, match="checkpoint is missing"): run(path, True)
    assert not path.exists() and calls == [] and checker.database_fingerprints() == before


def test_missing_checkpoint_after_initial_run_also_refuses_normal_recreation(acceptance):
    _, _, _, path, calls = acceptance
    run(path)
    path.unlink()
    before = checker.database_fingerprints()
    calls.clear()
    with pytest.raises(RuntimeError, match="have no checkpoint"): run(path)
    assert not path.exists() and checker.database_fingerprints() == before
    assert all(method == "GET" for method, _ in calls)


@pytest.mark.parametrize("change", ["conversation", "message", "title", "content", "timestamp", "unrelated", "kind", "scope",
                                   "backup", "fingerprint", "digest", "large_upload", "previous_missing", "previous_changed"])
def test_changed_or_missing_evidence_fails_read_only_without_repair(acceptance, change):
    client, ids, sessions, path, calls = acceptance
    previous = path.with_name("conversation-export-acceptance.json")
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
    if change == "kind": state["kind"] = "conversation-export"
    if change == "scope": state["agent_id"] = ids["mcp_agent_id"]
    if change == "backup": state["backup"]["messages"][0]["content"] = "Changed archive"
    if change == "fingerprint": state["database"]["messages"]["sha256"] = "changed"
    if change == "digest": state["export_sha256"]["conversation.json"] = "changed"
    if change == "large_upload": state["large_upload_bytes"] = 100
    if change in ("kind", "scope", "backup", "fingerprint", "digest", "large_upload"): path.write_text(json.dumps(state))
    if change == "previous_missing": previous.unlink()
    if change == "previous_changed": previous.write_text('{"changed":true}\n')
    before, checkpoint = checker.database_fingerprints(), path.read_bytes()
    calls.clear()
    with pytest.raises((RuntimeError, AssertionError)): run(path, True)
    assert all(method == "GET" for method, _ in calls)
    assert checker.database_fingerprints() == before and path.read_bytes() == checkpoint


def test_missing_route_stops_before_any_import_or_checkpoint_write(acceptance, monkeypatch):
    _, _, _, path, calls = acceptance
    request = checker.request_json
    monkeypatch.setattr(checker, "request_json", lambda base, uri: {"paths": {}} if uri == "/openapi.json" else request(base, uri))
    before = checker.database_fingerprints()
    with pytest.raises(RuntimeError, match="unavailable"): run(path)
    assert all(method == "GET" for method, _ in calls)
    assert checker.database_fingerprints() == before and not path.exists()
