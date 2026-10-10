"""Search the complete transcript without loading it into the chat or writing rows."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

from app.models.message import Message
from test_conversation_api_contract import create
from test_conversation_pagination import database_rows
from test_mcp_runtime_api import demo_api  # noqa: F401


@pytest.fixture
def history(demo_api):
    client, ids, sessions = demo_api
    own = create(client, ids["agent_id"], "Title only token %_")
    sibling = create(client, ids["agent_id"], "Same Agent, another conversation")
    foreign = create(client, ids["mcp_agent_id"], "Another Agent")
    empty = create(client, ids["agent_id"], "Empty")
    with sessions() as db:
        for index in range(25):
            # Timestamp ties need the ID tie-breaker; a newer ID can have an older date.
            timestamp = datetime(2026, 10, 10) + timedelta(microseconds=index // 3)
            if index == 24:
                timestamp = datetime(2026, 10, 9)
            db.add(Message(conversation_id=own["id"], role="user" if index % 2 == 0 else "assistant",
                           content=f"Saved turn {index:02d} — 中文 🐍", created_at=timestamp))
        db.add(Message(conversation_id=sibling["id"], role="user", content="Saved turn sibling — 中文 🐍"))
        db.add(Message(conversation_id=foreign["id"], role="user", content="Saved turn foreign — 中文 🐍"))
        db.commit()
    messages = client.get(f'/conversations/{own["id"]}/messages?agent_id={ids["agent_id"]}').json()
    return client, ids, sessions, own, sibling, foreign, empty, messages


def search(client, conversation, agent, query="中文", **params):
    response = client.get(f'/conversations/{conversation}/messages/search', params={"agent_id": agent, "query": query, **params})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    return response.json()


def test_complete_history_pages_roles_and_order_are_read_only(history):
    client, ids, sessions, own, _, _, empty, messages = history
    before = database_rows(sessions)
    latest = client.get(f'/conversations/{own["id"]}/messages/page', params={"agent_id": ids["agent_id"]}).json()
    assert len(latest["items"]) == 20
    expected = list(reversed(messages))
    pages = [search(client, own["id"], ids["agent_id"], "  中文  ", offset=offset) for offset in (0, 10, 20)]
    assert [row["id"] for page in pages for row in page["items"]] == [row["id"] for row in expected]
    assert all(page["total"] == 25 and page["query"] == "中文" and page["role"] is None for page in pages)
    assert [page["has_more"] for page in pages] == [True, True, False]
    assert pages[-1]["items"][-1]["id"] not in {row["id"] for row in latest["items"]}
    for role in ("user", "assistant", "system", "tool"):
        page = search(client, own["id"], ids["agent_id"], role=role, limit=50)
        assert [row["id"] for row in page["items"]] == [row["id"] for row in expected if row["role"] == role]
    assert search(client, own["id"], ids["agent_id"], limit=1)["items"][0]["id"] == expected[0]["id"]
    assert search(client, own["id"], ids["agent_id"], offset=25)["items"] == []
    assert search(client, own["id"], ids["agent_id"], offset=9223372036854775807)["has_more"] is False
    assert search(client, empty["id"], ids["agent_id"])["total"] == 0
    assert database_rows(sessions) == before


@pytest.mark.parametrize("query,expected", [("SAVED", 25), ("🐍", 25), ("Title only token", 0), ("%", 0), ("_", 0), ("missing", 0)])
def test_matching_is_literal_and_searches_content_only(history, query, expected):
    client, ids, sessions, own, *_ = history
    before = database_rows(sessions)
    assert search(client, own["id"], ids["agent_id"], query)["total"] == expected
    assert database_rows(sessions) == before


@pytest.mark.parametrize("query", ["100%_ready", "_", "%", "\\", "O'Reilly", '<script>alert("literal")</script>', "Ä", "a\nb"])
def test_quotes_wildcards_code_and_non_ascii_are_preserved(demo_api, query):
    client, ids, sessions = demo_api
    own = create(client, ids["agent_id"])
    content = '100%_ready \\ O\'Reilly\r\n<script>alert("literal")</script> Ä a\nb  \n'
    with sessions() as db:
        db.add(Message(conversation_id=own["id"], role="archived/custom", content=content))
        db.commit()
    page = search(client, own["id"], ids["agent_id"], query)
    assert page["total"] == 1 and page["items"][0]["role"] == "archived/custom"
    item = page["items"][0]
    assert item["snippet"] == content and item["snippet"][item["match_start"]:item["match_end"]] == query
    assert search(client, own["id"], ids["agent_id"], "ä")["total"] == 0


@pytest.mark.parametrize("position", [0, 1000, 2000])
def test_unicode_preview_is_bounded_and_full_detail_is_exact(demo_api, position):
    client, ids, sessions = demo_api
    own = create(client, ids["agent_id"])
    content = "🐍" * position + "中文Needle" + "🐍" * (2000 - position) + "\r\nTail:  \n"
    with sessions() as db:
        row = Message(conversation_id=own["id"], role="system", content=content, created_at=datetime(1, 1, 1, 0, 0, 0, 123456))
        db.add(row)
        db.commit()
        message_id = row.id
    before = database_rows(sessions)
    item = search(client, own["id"], ids["agent_id"], "中文NEEDLE")["items"][0]
    assert len(item["snippet"]) == 240
    assert item["snippet"][item["match_start"]:item["match_end"]] == "中文Needle"
    assert item["truncated_before"] is (position > 0)
    assert item["truncated_after"] is (position < 2000)
    response = client.get(f'/conversations/{own["id"]}/messages/{message_id}', params={"agent_id": ids["agent_id"]})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["content"] == content and response.json()["created_at"] == "0001-01-01T00:00:00.123456"
    assert database_rows(sessions) == before


def test_foreign_conversations_and_message_ids_return_404_without_writes(history):
    client, ids, sessions, own, sibling, foreign, _, messages = history
    foreign_message = client.get(f'/conversations/{foreign["id"]}/messages').json()[0]
    sibling_message = client.get(f'/conversations/{sibling["id"]}/messages').json()[0]
    before = database_rows(sessions)
    for conversation_id, agent_id in ((own["id"], ids["mcp_agent_id"]), (foreign["id"], ids["agent_id"]), (999999, ids["agent_id"])):
        assert client.get(f'/conversations/{conversation_id}/messages/search', params={"agent_id": agent_id, "query": "中文"}).status_code == 404
        assert client.get(f'/conversations/{conversation_id}/messages/{messages[0]["id"]}', params={"agent_id": agent_id}).status_code == 404
    for message_id in (foreign_message["id"], sibling_message["id"], 999999):
        assert client.get(f'/conversations/{own["id"]}/messages/{message_id}', params={"agent_id": ids["agent_id"]}).status_code == 404
    assert database_rows(sessions) == before


@pytest.mark.parametrize("params", [
    {}, {"query": ""}, {"query": " \t\n "}, {"query": "x" * 201}, {"query": "\x00"},
    {"agent_id": 0}, {"agent_id": "wrong"}, {"agent_id": 9223372036854775808},
    {"limit": 0}, {"limit": 51}, {"limit": "wrong"},
    {"offset": -1}, {"offset": "wrong"}, {"offset": 9223372036854775808}, {"role": "all"}, {"role": ""},
])
def test_search_validation_is_read_only(history, params):
    client, ids, sessions, own, *_ = history
    before = database_rows(sessions)
    query = {"agent_id": ids["agent_id"], "query": "中文", **params} if params else {}
    assert client.get(f'/conversations/{own["id"]}/messages/search', params=query).status_code == 422
    assert database_rows(sessions) == before


@pytest.mark.parametrize("suffix,params", [
    ("search", {"agent_id": 1, "query": "中文"}), ("0", {"agent_id": 1}),
    ("9223372036854775808", {"agent_id": 1}), ("1", {}), ("1", {"agent_id": 0}),
])
def test_invalid_detail_and_path_identities_are_rejected(demo_api, suffix, params):
    client, _, _ = demo_api
    assert client.get(f'/conversations/9223372036854775808/messages/{suffix}', params=params).status_code == 422


def test_query_parameters_remain_bound_and_only_the_page_is_loaded(history):
    client, ids, sessions, own, *_ = history
    statements = []
    with sessions() as db:
        engine = db.get_bind()
    def capture(_connection, _cursor, statement, parameters, _context, _many):
        if "FROM messages" in statement:
            statements.append((statement, parameters))
    event.listen(engine, "before_cursor_execute", capture)
    try:
        search(client, own["id"], ids["agent_id"], "SAVED", limit=5, offset=10)
        assert search(client, own["id"], ids["agent_id"], "' OR 1=1 --")["total"] == 0
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(statements) == 4
    assert "count(" in statements[0][0] and "LIMIT" in statements[1][0]
    assert statements[1][1][-2:] == (5, 10)
    assert "' OR 1=1 --" not in statements[-1][0]
