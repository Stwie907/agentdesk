"""Verify scoped conversation writes, previous-turn context, and memory extraction."""

import pytest

from app.models.execution import Execution
from app.models.message import Message
from app.services import conversation_service
from test_mcp_runtime_api import demo_api  # noqa: F401


def create(client, agent_id, title="Memory chat"):
    reply = client.post("/conversations", json={"agent_id": agent_id, "title": title})
    assert reply.status_code == 200, reply.text
    return reply.json()


def test_scoped_multiturn_chat_extracts_memory_and_preserves_previous_context(demo_api, monkeypatch):
    client, ids, _ = demo_api
    agent_id = ids["agent_id"]
    conversation = create(client, agent_id, "  Memory chat  ")
    assert conversation["title"] == "Memory chat"
    captured = []
    original = conversation_service.execute_agent
    def execute(execution_id, conversation_history=""):
        captured.append(conversation_history)
        return original(execution_id, conversation_history)
    monkeypatch.setattr(conversation_service, "execute_agent", execute)
    chat = f'/conversations/{conversation["id"]}/chat?agent_id={agent_id}'
    first = client.post(chat, json={"message": "  I like Python  "}).json()
    second = client.post(chat, json={"message": "What do I like about Python?"}).json()
    assert first["status"] == second["status"] == "completed"
    assert first["execution_id"] != second["execution_id"]
    assert captured == ["", f'User: I like Python\nAssistant: {first["response"]}']
    memories = client.get(f"/memories/{agent_id}").json()
    assert [row["content"] for row in memories] == ["User likes Python."]
    logs = client.get(f'/execution-logs/{second["execution_id"]}').json()
    assert any(row["message"] == "memory_retrieved: Relevant memory loaded" for row in logs)
    messages = client.get(f'/conversations/{conversation["id"]}/messages?agent_id={agent_id}').json()
    assert [row["role"] for row in messages] == ["user", "assistant", "user", "assistant"]
    assert [row["content"] for row in messages] == ["I like Python", first["response"], "What do I like about Python?", second["response"]]
    assert client.get(f'/executions/{second["execution_id"]}/snapshot').json()["output_snapshot"] == second["response"]


def test_agent_filter_and_scope_checks_block_reads_and_writes(demo_api):
    client, ids, sessions = demo_api
    conversation = create(client, ids["agent_id"])
    other = create(client, ids["mcp_agent_id"])
    assert client.get(f'/conversations?agent_id={ids["agent_id"]}').json() == [conversation]
    assert client.get(f'/conversations?agent_id={ids["mcp_agent_id"]}').json() == [other]
    query = f'?agent_id={ids["mcp_agent_id"]}'
    prefix = f'/conversations/{conversation["id"]}'
    for method, path, body in [
        ("GET", prefix, None), ("GET", prefix + "/messages", None),
        ("POST", prefix + "/messages", {"role": "user", "content": "wrong Agent"}),
        ("POST", prefix + "/chat", {"message": "I like Python"}),
        ("DELETE", prefix, None),
    ]:
        assert client.request(method, path + query, json=body).status_code == 404
    with sessions() as db:
        assert db.query(Message).count() == db.query(Execution).count() == 0
    assert client.get(f'/memories/{ids["agent_id"]}').json() == []
    assert client.get(prefix).json() == conversation


@pytest.mark.parametrize("title", ["", " \n ", "x" * 201, None, 123, False])
def test_invalid_title_never_creates_conversation(demo_api, title):
    client, ids, _ = demo_api
    assert client.post("/conversations", json={"agent_id": ids["agent_id"], "title": title}).status_code == 422
    assert client.get(f'/conversations?agent_id={ids["agent_id"]}').json() == []


@pytest.mark.parametrize("agent_id", [0, -1, "1", True])
def test_invalid_agent_never_creates_conversation(demo_api, agent_id):
    client, _, _ = demo_api
    assert client.post("/conversations", json={"agent_id": agent_id, "title": "Chat"}).status_code == 422
    assert client.get("/conversations").json() == []


@pytest.mark.parametrize("message", ["", " \n ", "x" * 4001, None, 123])
def test_invalid_chat_does_not_save_messages_or_execute(demo_api, message):
    client, ids, sessions = demo_api
    conversation = create(client, ids["agent_id"])
    assert client.post(f'/conversations/{conversation["id"]}/chat', json={"message": message}).status_code == 422
    with sessions() as db:
        assert db.query(Message).count() == db.query(Execution).count() == 0


def test_unknown_agent_and_conversation_are_404(demo_api):
    client, _, sessions = demo_api
    assert client.post("/conversations", json={"agent_id": 100000, "title": "Chat"}).status_code == 404
    assert client.get("/conversations?agent_id=100000").status_code == 404
    assert client.get("/conversations/100000/messages").status_code == 404
    assert client.post("/conversations/100000/messages", json={"role": "user", "content": "x"}).status_code == 404
    assert client.post("/conversations/100000/chat", json={"message": "I like Python"}).status_code == 404
    with sessions() as db:
        assert db.query(Message).count() == db.query(Execution).count() == 0


def test_maximum_title_and_message_and_legacy_unscoped_calls(demo_api):
    client, ids, _ = demo_api
    conversation = create(client, ids["agent_id"], " " + "t" * 200 + " ")
    assert len(conversation["title"]) == 200
    reply = client.post(f'/conversations/{conversation["id"]}/chat', json={"message": " " + "x" * 4000 + " "})
    assert reply.status_code == 200 and reply.json()["status"] == "completed"
    assert len(client.get(f'/conversations/{conversation["id"]}/messages').json()[0]["content"]) == 4000
    assert client.get("/conversations").json() == [conversation]


def test_duplicate_preferences_and_name_updates_share_existing_policy(demo_api):
    client, ids, _ = demo_api
    conversation = create(client, ids["agent_id"])
    for message in ("My name is Tom", "My name is Jane", "I like Python", "我喜欢Python"):
        reply = client.post(f'/conversations/{conversation["id"]}/chat', json={"message": message})
        assert reply.status_code == 200 and reply.json()["status"] == "completed"
    assert [row["content"] for row in client.get(f'/memories/{ids["agent_id"]}').json()] == ["User's name is Jane.", "User likes Python."]


@pytest.mark.parametrize("url", ["/conversations?agent_id=0", "/conversations/0/messages", "/conversations/1/messages?agent_id=0"])
def test_nonpositive_scope_or_path_is_422(demo_api, url):
    client, _, _ = demo_api
    assert client.get(url).status_code == 422
