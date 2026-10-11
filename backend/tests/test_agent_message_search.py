"""Joined Agent searches keep complete conversation APIs and records intact."""

from datetime import datetime

import pytest
from sqlalchemy import event

from app.models.message import Message
from test_conversation_api_contract import create
from test_conversation_pagination import database_rows
from test_message_search import history  # noqa: F401
from test_mcp_runtime_api import demo_api  # noqa: F401


def search(client, agent, query="中文", **params):
    response = client.get(f"/agents/{agent}/messages/search", params={"query": query, **params})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    return response.json()


def test_complete_agent_history_pages_titles_scopes_and_roles_are_read_only(history):
    client, ids, sessions, own, sibling, foreign, _, messages = history
    sibling_rows = client.get(f'/conversations/{sibling["id"]}/messages?agent_id={ids["agent_id"]}').json()
    expected = sorted(messages + sibling_rows, key=lambda row: (datetime.fromisoformat(row["created_at"]), row["id"]), reverse=True)
    before = database_rows(sessions)
    pages = [search(client, ids["agent_id"], "  中文  ", offset=offset) for offset in (0, 10, 20)]
    assert [row["id"] for page in pages for row in page["items"]] == [row["id"] for row in expected]
    assert all(page["agent_id"] == ids["agent_id"] and page["query"] == "中文" and page["total"] == 26 for page in pages)
    assert [page["has_more"] for page in pages] == [True, True, False]
    titles = {own["id"]: own["title"], sibling["id"]: sibling["title"]}
    for page in pages:
        for row in page["items"]:
            assert row["agent_id"] == ids["agent_id"]
            assert row["conversation_title"] == titles[row["conversation_id"]]
            assert len(row["snippet"]) <= 240
    for role in ("user", "assistant", "system", "tool"):
        page = search(client, ids["agent_id"], role=role, limit=50)
        assert [row["id"] for row in page["items"]] == [row["id"] for row in expected if row["role"] == role]
    for offset in (26, 9223372036854775807):
        assert search(client, ids["agent_id"], offset=offset)["items"] == []
    other = search(client, ids["mcp_agent_id"], limit=50)
    assert other["total"] == 1 and other["items"][0]["conversation_id"] == foreign["id"]
    assert not {row["id"] for row in other["items"]}.intersection(row["id"] for row in expected)
    assert database_rows(sessions) == before


@pytest.mark.parametrize("query,expected", [("SAVED", 26), ("🐍", 26), ("Title only token", 0), ("%", 0), ("_", 0), ("missing", 0)])
def test_matches_only_literal_message_content_across_conversations(history, query, expected):
    client, ids, sessions, *_ = history
    before = database_rows(sessions)
    assert search(client, ids["agent_id"], query, limit=50)["total"] == expected
    assert database_rows(sessions) == before


@pytest.mark.parametrize("query", ["100%_ready", "_", "%", "\\", "O'Reilly", '<script>alert("literal")</script>', "Ä", "a\nb"])
def test_literal_code_quotes_unicode_and_custom_roles(demo_api, query):
    client, ids, sessions = demo_api
    own = create(client, ids["agent_id"], '<script>Literal title</script> — 中文')
    content = '100%_ready \\ O\'Reilly\r\n<script>alert("literal")</script> Ä a\nb  \n'
    with sessions() as db:
        db.add(Message(conversation_id=own["id"], role="archived/custom", content=content))
        db.commit()
    before = database_rows(sessions)
    page = search(client, ids["agent_id"], query)
    assert page["total"] == 1
    row = page["items"][0]
    assert row["conversation_title"] == own["title"] and row["role"] == "archived/custom"
    assert row["snippet"] == content and row["snippet"][row["match_start"]:row["match_end"]] == query
    assert search(client, ids["agent_id"], "ä")["total"] == 0
    assert database_rows(sessions) == before


@pytest.mark.parametrize("position", [0, 1000, 2000])
def test_bounded_unicode_previews_keep_microseconds_and_use_existing_scoped_reads(demo_api, position):
    client, ids, sessions = demo_api
    own = create(client, ids["agent_id"])
    content = "🐍" * position + "中文Needle" + "🐍" * (2000 - position) + "\r\nTail:  \n"
    with sessions() as db:
        message = Message(conversation_id=own["id"], role="system", content=content,
                          created_at=datetime(1, 1, 1, 0, 0, 0, 123456))
        db.add(message); db.commit(); message_id = message.id
    before = database_rows(sessions)
    row = search(client, ids["agent_id"], "中文NEEDLE")["items"][0]
    assert len(row["snippet"]) == 240
    assert row["snippet"][row["match_start"]:row["match_end"]] == "中文Needle"
    assert row["created_at"] == "0001-01-01T00:00:00.123456"
    uri = f'/conversations/{own["id"]}/messages/{message_id}'
    detail = client.get(uri, params={"agent_id": ids["agent_id"]})
    assert detail.json()["content"] == content
    for suffix in ("", "/context", "/context/export"):
        assert client.get(uri + suffix, params={"agent_id": ids["mcp_agent_id"]}).status_code == 404
    excerpt = client.get(uri + "/context/export", params={"agent_id": ids["agent_id"]}).json()
    assert excerpt["context"]["items"][0]["content"] == content
    assert database_rows(sessions) == before


@pytest.mark.parametrize("params", [
    {}, {"query": ""}, {"query": "   "}, {"query": "x" * 201}, {"query": "a\x00b"},
    {"query": "中文", "limit": 0}, {"query": "中文", "limit": 51}, {"query": "中文", "limit": "1.5"},
    {"query": "中文", "offset": -1}, {"query": "中文", "offset": 9223372036854775808},
    {"query": "中文", "offset": "bad"}, {"query": "中文", "role": "USER"}, {"query": "中文", "role": "custom"},
])
def test_invalid_requests_do_not_write(history, params):
    client, ids, sessions, *_ = history
    before = database_rows(sessions)
    assert client.get(f'/agents/{ids["agent_id"]}/messages/search', params=params).status_code == 422
    assert database_rows(sessions) == before


@pytest.mark.parametrize("agent,status", [(0, 422), (-1, 422), ("bad", 422), ("1.5", 422),
                                         (9223372036854775808, 422), (9223372036854775807, 404)])
def test_invalid_and_missing_agents_are_explicit(history, agent, status):
    client, _, sessions, *_ = history
    before = database_rows(sessions)
    assert client.get(f"/agents/{agent}/messages/search", params={"query": "中文"}).status_code == status
    assert database_rows(sessions) == before


def test_joined_page_is_bounded_without_loading_every_conversation_or_n_plus_one(history):
    client, ids, sessions, own, sibling, *_ = history
    with sessions() as db:
        db.add_all([Message(conversation_id=sibling["id"], role="tool", content=f"中文 bounded {index}") for index in range(80)])
        db.commit(); engine = db.get_bind()
    statements = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement.lower())
    event.listen(engine, "before_cursor_execute", capture)
    try:
        page = search(client, ids["agent_id"], limit=50)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert page["total"] == 106 and len(page["items"]) == 50 and page["has_more"] is True
    assert len(statements) == 3
    assert "count(" in statements[1] and "join conversations" in statements[2] and "limit" in statements[2]


def test_global_reads_preserve_old_search_context_export_and_latest_page_bytes(history):
    client, ids, sessions, own, _, _, _, messages = history
    base = f'/conversations/{own["id"]}'
    paths = [base + "/messages/page", base + "/messages/search?query=" + "中文",
             base + f'/messages/{messages[0]["id"]}', base + f'/messages/{messages[0]["id"]}/context',
             base + f'/messages/{messages[0]["id"]}/context/export?format=json',
             base + f'/messages/{messages[0]["id"]}/context/export?format=markdown', base + "/export?format=json"]
    paths = [path + ("&" if "?" in path else "?") + f'agent_id={ids["agent_id"]}' for path in paths]
    before = database_rows(sessions)
    responses = [client.get(path) for path in paths]
    assert all(reply.status_code == 200 for reply in responses)
    search(client, ids["agent_id"], limit=50)
    assert [client.get(path).content for path in paths] == [reply.content for reply in responses]
    assert database_rows(sessions) == before
