"""Exercise bounded, literal title search without changing saved Agent data."""

from datetime import datetime

import pytest
from sqlalchemy import inspect, text

from app.models.conversation import Conversation
from test_conversation_api_contract import create
from test_mcp_runtime_api import demo_api  # noqa: F401


def page(client, agent_id, **params):
    response = client.get("/conversations/page", params={"agent_id": agent_id, **params})
    assert response.status_code == 200, response.text
    return response.json()


def database_rows(sessions):
    with sessions() as db:
        connection = db.connection()
        return {name: sorted(repr(tuple(row)) for row in connection.execute(text(
            "SELECT * FROM " + connection.dialect.identifier_preparer.quote(name))))
            for name in inspect(connection).get_table_names()}


def test_default_page_is_bounded_scoped_and_newest_first_with_ties(demo_api):
    client, ids, sessions = demo_api
    own = [create(client, ids["agent_id"], f"Chat {index}") for index in range(13)]
    create(client, ids["mcp_agent_id"], "Foreign chat")
    with sessions() as db:
        db.query(Conversation).update({Conversation.created_at: datetime(2026, 10, 10)})
        db.commit()
    first = page(client, ids["agent_id"])
    assert first == {**first, "agent_id": ids["agent_id"], "query": "", "limit": 10, "offset": 0, "total": 13, "has_more": True}
    assert [row["id"] for row in first["items"]] == [row["id"] for row in reversed(own)][0:10]
    last = page(client, ids["agent_id"], offset=10)
    assert last["total"] == 13 and last["has_more"] is False
    assert [row["id"] for row in last["items"]] == [row["id"] for row in reversed(own)][10:]
    assert page(client, ids["agent_id"], offset=13)["items"] == []
    assert page(client, ids["agent_id"], offset=1000)["total"] == 13
    # The legacy endpoint retains its ascending, unpaginated list contract.
    assert [row["id"] for row in client.get(f'/conversations?agent_id={ids["agent_id"]}').json()] == [row["id"] for row in own]


@pytest.mark.parametrize("query,expected", [
    ("  PYTHON  ", ["Python planning", "python review"]),
    ("记忆", ["中文记忆回顾"]), ("%", ["100% ready"]),
    ("_", ["file_name"]), ("/", ["folder/file"]),
    ("' OR 1=1 --", ["literal ' OR 1=1 --"]),
    ("&", ["A&B"]), ("unrelated title", []),
])
def test_search_is_literal_bilingual_and_agent_scoped(demo_api, query, expected):
    client, ids, _ = demo_api
    titles = ["Python planning", "python review", "中文记忆回顾", "100% ready", "file_name", "folder/file", "literal ' OR 1=1 --", "A&B"]
    own = [create(client, ids["agent_id"], title) for title in titles]
    for title in titles:
        create(client, ids["mcp_agent_id"], title)
    result = page(client, ids["agent_id"], query=query)
    assert result["query"] == query.strip()
    assert result["total"] == len(expected)
    assert [row["title"] for row in result["items"]] == list(reversed(expected))
    assert {row["id"] for row in result["items"]} <= {row["id"] for row in own}


def test_empty_search_custom_limits_and_missing_agent(demo_api):
    client, ids, _ = demo_api
    assert page(client, ids["agent_id"], query=" \t ")["query"] == ""
    rows = [create(client, ids["agent_id"], "Repeated title") for _ in range(3)]
    result = page(client, ids["agent_id"], query="Repeated", limit=1, offset=1)
    assert result["items"] == [rows[1]]
    assert result["total"] == 3 and result["has_more"] is True
    assert page(client, ids["agent_id"], limit=50)["total"] == 3
    assert client.get("/conversations/page", params={"agent_id": 999999}).status_code == 404


@pytest.mark.parametrize("params", [
    {}, {"agent_id": 0}, {"agent_id": -1}, {"agent_id": "wrong"},
    {"limit": 0}, {"limit": -1}, {"limit": 51}, {"limit": "wrong"},
    {"offset": -1}, {"offset": "wrong"}, {"query": "x" * 201},
    {"agent_id": 9223372036854775808}, {"offset": 9223372036854775808},
])
def test_invalid_page_requests_are_read_only(demo_api, params):
    client, ids, sessions = demo_api
    create(client, ids["agent_id"])
    before = database_rows(sessions)
    request = {"agent_id": ids["agent_id"], **params} if params else {}
    assert client.get("/conversations/page", params=request).status_code == 422
    assert database_rows(sessions) == before


def test_search_pagination_and_rename_delete_keep_transcript_and_runtime_data(demo_api):
    client, ids, sessions = demo_api
    agent_id = ids["agent_id"]
    keeper = create(client, agent_id, "Python keeper")
    disposable = create(client, agent_id, "Python disposable")
    foreign = create(client, ids["mcp_agent_id"], "Python foreign")
    reply = client.post(f'/conversations/{keeper["id"]}/chat?agent_id={agent_id}', json={"message": "I like Python"})
    assert reply.status_code == 200 and reply.json()["status"] == "completed"
    before = database_rows(sessions)
    assert page(client, agent_id, query="python", limit=1)["items"] == [disposable]
    assert page(client, agent_id, query="python", limit=1, offset=1)["items"] == [keeper]
    assert page(client, ids["mcp_agent_id"], query="python")["items"] == [foreign]
    assert database_rows(sessions) == before
    client.patch(f'/conversations/{disposable["id"]}?agent_id={agent_id}', json={"title": "Other topic"})
    assert page(client, agent_id, query="python")["items"] == [keeper]
    client.delete(f'/conversations/{disposable["id"]}?agent_id={agent_id}')
    assert page(client, agent_id)["total"] == 1
    after = database_rows(sessions)
    for name in before.keys() - {"conversations"}:
        assert after[name] == before[name]
