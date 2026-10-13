"""Verify conversation management without losing Agent memory or executions."""

import pytest

from app.crud.conversation import delete_conversation, update_conversation_title
from app.models.conversation import Conversation
from app.models.message import Message
from test_conversation_api_contract import create
from test_mcp_runtime_api import demo_api  # noqa: F401


def test_rename_keeps_identity_transcript_memory_and_execution(demo_api):
    client, ids, _ = demo_api
    agent_id = ids["agent_id"]
    conversation = create(client, agent_id)
    prefix = f'/conversations/{conversation["id"]}'
    reply = client.post(prefix + "/chat", json={"message": "I like Python"}).json()
    before = client.get(prefix + "/messages").json()
    memories = client.get(f"/memories/{agent_id}").json()
    execution = client.get(f'/executions/{reply["execution_id"]}').json()
    renamed = client.patch(prefix + f"?agent_id={agent_id}", json={"title": "  Renamed chat  "})
    assert renamed.status_code == 200
    assert renamed.json() == {**conversation, "title": "Renamed chat"}
    assert client.get(f"/conversations?agent_id={agent_id}").json() == [renamed.json()]
    assert client.get(prefix + "/messages").json() == before
    assert client.get(f"/memories/{agent_id}").json() == memories
    assert client.get(f'/executions/{reply["execution_id"]}').json() == execution


@pytest.mark.parametrize("payload", [
    {}, {"title": ""}, {"title": " \n\t "}, {"title": "x" * 201},
    {"title": None}, {"title": 12}, {"title": False},
    {"title": "New", "agent_id": 999}, {"title": "New", "created_at": "2026-01-01"},
])
def test_invalid_rename_is_rejected_without_changing_conversation(demo_api, payload):
    client, ids, _ = demo_api
    conversation = create(client, ids["agent_id"])
    prefix = f'/conversations/{conversation["id"]}'
    assert client.patch(prefix, json=payload).status_code == 422
    assert client.get(prefix).json() == conversation
    assert client.get(prefix + "/messages").json() == []


def test_rename_accepts_trimmed_maximum_title_and_legacy_unscoped_call(demo_api):
    client, ids, _ = demo_api
    conversation = create(client, ids["agent_id"])
    prefix = f'/conversations/{conversation["id"]}'
    response = client.patch(prefix, json={"title": " " + "会" * 200 + " "})
    assert response.status_code == 200
    assert response.json() == {**conversation, "title": "会" * 200}


def test_scope_and_missing_checks_block_rename_and_delete(demo_api):
    client, ids, _ = demo_api
    conversation = create(client, ids["agent_id"])
    prefix = f'/conversations/{conversation["id"]}'
    wrong = prefix + f'?agent_id={ids["mcp_agent_id"]}'
    assert client.patch(wrong, json={"title": "Wrong Agent"}).status_code == 404
    assert client.delete(wrong).status_code == 404
    assert client.patch("/conversations/100000", json={"title": "Missing"}).status_code == 404
    assert client.delete("/conversations/100000").status_code == 404
    for query in ("?agent_id=0", "?agent_id=-1"):
        assert client.patch(prefix + query, json={"title": "Invalid scope"}).status_code == 422
        assert client.delete(prefix + query).status_code == 422
    assert client.patch("/conversations/0", json={"title": "Invalid ID"}).status_code == 422
    assert client.get(prefix).json() == conversation


def test_delete_removes_only_its_messages_and_preserves_memory_and_inspection(demo_api):
    client, ids, sessions = demo_api
    agent_id = ids["agent_id"]
    conversation = create(client, agent_id, "Delete this")
    protected = [create(client, agent_id, "Keep same Agent"), create(client, ids["mcp_agent_id"], "Keep other Agent")]
    for row in protected:
        client.post(f'/conversations/{row["id"]}/messages', json={"role": "user", "content": "Keep me"})
    prefix = f'/conversations/{conversation["id"]}'
    reply = client.post(prefix + "/chat", json={"message": "I like Python"}).json()
    messages = client.get(prefix + "/messages").json()
    assert len(messages) == 2
    memories = client.get(f"/memories/{agent_id}").json()
    assert [row["content"] for row in memories] == ["User likes Python."]
    execution_prefix = f'/executions/{reply["execution_id"]}'
    inspection = {suffix: client.get(execution_prefix + suffix).json() for suffix in ("", "/trace", "/snapshot")}
    response = client.delete(prefix + f"?agent_id={agent_id}")
    assert response.status_code == 200 and response.json() == {"message": "deleted"}
    assert client.get(prefix).status_code == client.get(prefix + "/messages").status_code == 404
    assert client.post(prefix + "/chat", json={"message": "I like Rust"}).status_code == 404
    assert client.post(prefix + "/messages", json={"role": "user", "content": "gone"}).status_code == 404
    assert client.patch(prefix, json={"title": "gone"}).status_code == 404
    assert client.delete(prefix).status_code == 404
    with sessions() as db:
        assert db.get(Conversation, conversation["id"]) is None
        assert db.query(Message).filter(Message.conversation_id == conversation["id"]).count() == 0
        assert db.query(Message).count() == 2
    for row in protected:
        assert client.get(f'/conversations/{row["id"]}').json() == row
        assert [item["content"] for item in client.get(f'/conversations/{row["id"]}/messages').json()] == ["Keep me"]
    assert client.get(f"/memories/{agent_id}").json() == memories
    assert {suffix: client.get(execution_prefix + suffix).json() for suffix in inspection} == inspection


def test_delete_empty_conversation_keeps_legacy_response(demo_api):
    client, ids, _ = demo_api
    conversation = create(client, ids["agent_id"])
    assert client.delete(f'/conversations/{conversation["id"]}').json() == {"message": "deleted"}


def test_delete_with_foreign_keys_enabled_and_loaded_messages(demo_api):
    client, ids, sessions = demo_api
    conversation = create(client, ids["agent_id"])
    client.post(f'/conversations/{conversation["id"]}/messages', json={"role": "user", "content": "Child row"})
    with sessions() as db:
        db.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
        assert db.connection().exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        loaded = db.get(Conversation, conversation["id"])
        assert len(loaded.messages) == 1
        delete_conversation(db, loaded.id)
        assert db.get(Conversation, conversation["id"]) is None
        assert db.query(Message).count() == 0


@pytest.mark.parametrize("action", ["rename", "delete"])
def test_failed_commit_rolls_back_parent_and_messages(demo_api, monkeypatch, action):
    client, ids, sessions = demo_api
    conversation = create(client, ids["agent_id"])
    client.post(f'/conversations/{conversation["id"]}/messages', json={"role": "user", "content": "Keep on failure"})
    with sessions() as db:
        loaded = db.get(Conversation, conversation["id"])
        def failed_commit():
            db.flush()
            raise RuntimeError("simulated commit failure")
        monkeypatch.setattr(db, "commit", failed_commit)
        with pytest.raises(RuntimeError, match="simulated commit failure"):
            if action == "rename":
                update_conversation_title(db, loaded, "Must roll back")
            else:
                delete_conversation(db, loaded.id)
        assert db.get(Conversation, conversation["id"]).title == conversation["title"]
        assert [row.content for row in db.query(Message).all()] == ["Keep on failure"]
