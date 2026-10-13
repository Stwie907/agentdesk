"""Verify ranked previews, multilingual matching, and the actual Runtime context."""

import pytest

from app.models.conversation import Conversation
from app.models.execution import Execution
from app.models.memory import Memory
from app.models.message import Message
from app.services.memory_service import build_memory_context, retrieve_relevant_memories
from app.workers import execution_worker
from test_mcp_runtime_api import demo_api  # noqa: F401


def save(client, agent_id, content):
    response = client.post("/memories", json={"agent_id": agent_id, "content": content})
    assert response.status_code == 200, response.text
    return response.json()


def search(client, agent_id, query, limit=5):
    response = client.get(f"/memories/{agent_id}/search", params={"query": query, "limit": limit})
    assert response.status_code == 200, response.text
    return response.json()


def test_rank_limit_ties_and_duplicate_terms_match_runtime(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    agent_id = ids["agent_id"]
    strongest = save(client, agent_id, "Python SQLite concise answers.")
    older = save(client, agent_id, "Python only.")
    newer = save(client, agent_id, "Rust SQLite guide.")
    full = search(client, agent_id, "  PYTHON, SQLite Python  ")
    assert full["query"] == "PYTHON, SQLite Python"
    assert [row["memory"]["id"] for row in full["results"]] == [strongest["id"], newer["id"], older["id"]]
    assert [row["score"] for row in full["results"]] == [2, 1, 1]
    assert full["results"][0]["matched_terms"] == ["python", "sqlite"]
    assert search(client, agent_id, "Python SQLite", 2)["results"] == full["results"][:2]
    captured = []
    original = execution_worker.run_agent
    def run(*args, **kwargs):
        captured.append(args[2])
        return original(*args, **kwargs)
    monkeypatch.setattr(execution_worker, "run_agent", run)
    reply = client.post(f"/agents/{agent_id}/chat", json={"message": "PYTHON, SQLite Python"})
    assert reply.status_code == 200 and reply.json()["status"] == "completed"
    assert captured == ["\n".join(row["memory"]["content"] for row in full["results"])]
    with sessions() as db:
        assert [row.id for row in retrieve_relevant_memories(db, agent_id, "Python SQLite", 2)] == [strongest["id"], newer["id"]]


@pytest.mark.parametrize("content,query,expected", [
    ("Python, Rust.", "PYTHON/RUST", ["python", "rust"]),
    ("Python guide.", "ＰＹＴＨＯＮ", ["python"]),
    ("C++ and C# notes.", "C++", ["c++"]),
    ("C++ and C# notes.", "C#", ["c#"]),
    ("Use Node.js.", "Node.js", ["node.js"]),
    ("The user's name is Tom.", "What is the user’s name?", ["name", "user's"]),
    ("用户喜欢机器学习和Python。", "机器学习Python", ["python", "器学", "学习", "机器"]),
    ("我喜欢猫。", "猫", ["猫"]),
])
def test_multilingual_punctuation_and_literal_terms(demo_api, content, query, expected):
    client, ids, _ = demo_api
    saved = save(client, ids["agent_id"], content)
    rows = search(client, ids["agent_id"], query)["results"]
    assert len(rows) == 1 and rows[0]["memory"] == saved
    assert rows[0]["matched_terms"] == expected
    assert rows[0]["score"] == len(expected)


@pytest.mark.parametrize("content,query", [
    ("Python guide.", "weather tomorrow"),
    ("Python guide.", "what is the"),
    ("我喜欢Python", "我喜欢Rust"),
    ("C++ notes.", "C#"),
    ("The user likes Python.", "What is the user's name?"),
])
def test_unrelated_queries_return_no_memories(demo_api, content, query):
    client, ids, _ = demo_api
    save(client, ids["agent_id"], content)
    assert search(client, ids["agent_id"], query)["results"] == []


def test_search_is_read_only_and_never_crosses_agent_scope(demo_api):
    client, ids, sessions = demo_api
    own = save(client, ids["agent_id"], "Python scoped memory.")
    other = save(client, ids["mcp_agent_id"], "Python other memory.")
    with sessions() as db:
        before = {model: db.query(model).count() for model in (Memory, Execution, Conversation, Message)}
    assert [row["memory"] for row in search(client, ids["agent_id"], "Python")["results"]] == [own]
    assert [row["memory"] for row in search(client, ids["mcp_agent_id"], "Python")["results"]] == [other]
    assert client.get(f'/memories/{ids["agent_id"]}').json() == [own]
    with sessions() as db:
        assert {model: db.query(model).count() for model in before} == before


@pytest.mark.parametrize("params", [
    {}, {"query": ""}, {"query": " \n\t"}, {"query": "x" * 501},
    {"query": "Python", "limit": 0}, {"query": "Python", "limit": 21},
    {"query": "Python", "limit": "bad"}, {"query": "Python", "limit": "1.5"},
])
def test_invalid_search_returns_422_without_writes(demo_api, params):
    client, ids, sessions = demo_api
    assert client.get(f'/memories/{ids["agent_id"]}/search', params=params).status_code == 422
    with sessions() as db:
        assert db.query(Memory).count() == db.query(Execution).count() == 0


def test_missing_agent_positive_path_and_maximum_query(demo_api):
    client, ids, _ = demo_api
    assert client.get("/memories/100000/search", params={"query": "Python"}).status_code == 404
    assert client.get("/memories/0/search", params={"query": "Python"}).status_code == 422
    result = search(client, ids["agent_id"], "字" * 500, 20)
    assert result["query"] == "字" * 500 and result["limit"] == 20 and result["results"] == []


def test_exact_duplicate_policy_and_internal_empty_query_remain_compatible(demo_api):
    client, ids, sessions = demo_api
    first = save(client, ids["agent_id"], "Python guide.")
    second = save(client, ids["agent_id"], "Rust guide.")
    assert save(client, ids["agent_id"], "  Python guide.  ") == first
    assert search(client, ids["agent_id"], "Python")["results"][0]["memory"] == first
    with sessions() as db:
        assert build_memory_context(db, ids["agent_id"], "", 1) == first["content"]
        assert [row.id for row in retrieve_relevant_memories(db, ids["agent_id"], " ", 2)] == [first["id"], second["id"]]
        assert build_memory_context(db, ids["agent_id"], "Python", 0) == ""


def test_preview_limit_does_not_change_runtime_default(demo_api):
    client, ids, sessions = demo_api
    saved = [save(client, ids["agent_id"], f"Python guide {index}.") for index in range(7)]
    default = search(client, ids["agent_id"], "Python")
    assert [row["memory"]["id"] for row in default["results"]] == [row["id"] for row in reversed(saved[-5:])]
    assert len(search(client, ids["agent_id"], "Python", 1)["results"]) == 1
    with sessions() as db:
        assert build_memory_context(db, ids["agent_id"], "Python") == "\n".join(row["memory"]["content"] for row in default["results"])
