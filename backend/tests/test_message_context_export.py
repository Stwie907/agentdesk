"""Scoped excerpts preserve complete saved text, chronology, and attachment bounds."""

from datetime import datetime
import json

import pytest
from sqlalchemy import event

from app.check_conversation_export import markdown_blocks
from app.check_message_context_export import assert_attachment, expected_context
from app.models.message import Message
from app.services import message_context_export as exporter
from test_conversation_pagination import database_rows
from test_mcp_runtime_api import demo_api  # noqa: F401
from test_message_search import history  # noqa: F401


def attachment(client, conversation, agent, message, format="json", **params):
    return client.get(f"/conversations/{conversation}/messages/{message}/context/export",
                      params={"agent_id": agent, "format": format, **params})


@pytest.mark.parametrize("format", ["json", "markdown"])
@pytest.mark.parametrize("index,before,after", [(0, 3, 3), (24, 3, 3), (12, 3, 3), (12, 10, 10),
                                               (12, 0, 0), (0, 10, 0), (24, 0, 10), (12, 1, 5)])
def test_scoped_windows_keep_complete_original_messages_without_writes(history, format, index, before, after):
    client, ids, sessions, own, _, _, _, messages = history
    original = database_rows(sessions)
    latest_uri = f'/conversations/{own["id"]}/messages/page?agent_id={ids["agent_id"]}'
    latest = client.get(latest_uri).content
    response = attachment(client, own["id"], ids["agent_id"], messages[index]["id"], format, before=before, after=after)
    assert response.status_code == 200, response.text
    assert_attachment({"headers": dict(response.headers), "content": response.content},
                      expected_context(own, messages, index, before, after), format)
    assert client.get(latest_uri).content == latest and database_rows(sessions) == original
    if index == 0: assert messages[0]["id"] not in {row["id"] for row in json.loads(latest)["items"]}


def test_defaults_are_json_and_three_neighbours_on_each_side(history):
    client, ids, _, own, _, _, _, messages = history
    response = client.get(f'/conversations/{own["id"]}/messages/{messages[12]["id"]}/context/export',
                          params={"agent_id": ids["agent_id"]})
    assert response.status_code == 200 and response.json()["context"] == expected_context(own, messages, 12, 3, 3)
    assert response.json()["message_count"] == 7


@pytest.mark.parametrize("format", ["json", "markdown"])
def test_long_unicode_literal_fences_empty_custom_roles_and_calendar_dates(demo_api, format):
    from test_conversation_api_contract import create
    client, ids, sessions = demo_api
    own = create(client, ids["agent_id"])
    content = '中文🐍' * 3000 + '\r\n```````markdown\n<script>alert("literal")</script>\n```````\nTail:  \n'
    with sessions() as db:
        db.add_all([Message(conversation_id=own["id"], role="", content="", created_at=datetime(1, 1, 1, 0, 0, 0, 123456)),
                    Message(conversation_id=own["id"], role="archived/```custom", content=content,
                            created_at=datetime(9999, 12, 31, 23, 59, 59, 999999))])
        db.commit()
    messages = client.get(f'/conversations/{own["id"]}/messages').json()
    original = database_rows(sessions)
    response = attachment(client, own["id"], ids["agent_id"], messages[0]["id"], format)
    assert response.status_code == 200
    assert_attachment({"headers": dict(response.headers), "content": response.content},
                      expected_context(own, messages, 0, 3, 3), format)
    if format == "markdown":
        assert "````````text\n" in response.text
        assert markdown_blocks(response.text) == ["", "", messages[1]["role"], content]
    assert database_rows(sessions) == original


@pytest.mark.parametrize("format", ["json", "markdown"])
def test_attachment_queries_remain_scoped_and_limited(history, format):
    client, ids, sessions, own, _, _, _, messages = history
    with sessions() as db: engine = db.get_bind()
    queries = []
    def capture(connection, cursor, statement, parameters, execution_context, executemany):
        if statement.startswith("SELECT messages."): queries.append((statement, parameters))
    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = attachment(client, own["id"], ids["agent_id"], messages[12]["id"], format, before=10, after=10)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200 and response.headers["x-message-count"] == "21"
    assert len(queries) == 3 and [params[-2] for _, params in queries] == [1, 11, 11]
    assert all("LIMIT" in query and "messages.conversation_id =" in query for query, _ in queries)


@pytest.mark.parametrize("format", ["json", "markdown"])
def test_foreign_sibling_missing_deleted_and_empty_anchors_cannot_export(history, format):
    client, ids, sessions, own, sibling, foreign, empty, messages = history
    sibling_message = client.get(f'/conversations/{sibling["id"]}/messages').json()[0]
    foreign_message = client.get(f'/conversations/{foreign["id"]}/messages').json()[0]
    with sessions() as db:
        db.delete(db.get(Message, messages[-1]["id"])); db.commit()
    original = database_rows(sessions)
    cases = [(own["id"], ids["mcp_agent_id"], messages[0]["id"]),
             (foreign["id"], ids["agent_id"], foreign_message["id"]),
             (own["id"], ids["agent_id"], sibling_message["id"]),
             (own["id"], ids["agent_id"], foreign_message["id"]),
             (empty["id"], ids["agent_id"], messages[0]["id"]),
             (own["id"], ids["agent_id"], messages[-1]["id"]),
             (own["id"], ids["agent_id"], 9223372036854775807),
             (9223372036854775807, ids["agent_id"], messages[0]["id"])]
    for conversation, agent, message in cases:
        response = attachment(client, conversation, agent, message, format)
        assert response.status_code == 404 and "content-disposition" not in response.headers
    assert attachment(client, foreign["id"], ids["mcp_agent_id"], foreign_message["id"], format).status_code == 200
    assert database_rows(sessions) == original


@pytest.mark.parametrize("params", [{}, {"agent_id": 0}, {"agent_id": "bad"}, {"agent_id": 9223372036854775808},
                                   {"before": -1}, {"before": 11}, {"before": "1.5"}, {"before": "bad"},
                                   {"after": -1}, {"after": 11}, {"after": "1.5"}, {"after": "bad"},
                                   {"format": "html"}, {"format": "md"}, {"format": "JSON"}, {"format": ""}])
def test_invalid_scope_window_and_formats_return_422_without_attachments(history, params):
    client, ids, sessions, own, _, _, _, messages = history
    before = database_rows(sessions)
    actual = {"agent_id": ids["agent_id"], **params} if params else {}
    response = client.get(f'/conversations/{own["id"]}/messages/{messages[0]["id"]}/context/export', params=actual)
    assert response.status_code == 422 and "content-disposition" not in response.headers
    assert database_rows(sessions) == before


@pytest.mark.parametrize("conversation,message", [(0, 1), (-1, 1), (9223372036854775808, 1),
                                                 (1, 0), (1, -1), (1, 9223372036854775808)])
def test_path_identities_must_fit_sqlite(history, conversation, message):
    client, ids, sessions, *_ = history
    before = database_rows(sessions)
    assert attachment(client, conversation, ids["agent_id"], message).status_code == 422
    assert database_rows(sessions) == before


@pytest.mark.parametrize("format", ["json", "markdown"])
def test_utf8_byte_limit_accepts_exact_size_and_rejects_overflow_without_partial_file(history, monkeypatch, format):
    client, ids, sessions, own, _, _, _, messages = history
    expected = attachment(client, own["id"], ids["agent_id"], messages[0]["id"], format).content
    assert len(expected) > len(expected.decode("utf-8"))
    monkeypatch.setattr(exporter, "MAX_CONTEXT_EXPORT_BYTES", len(expected))
    assert attachment(client, own["id"], ids["agent_id"], messages[0]["id"], format).content == expected
    monkeypatch.setattr(exporter, "MAX_CONTEXT_EXPORT_BYTES", len(expected) - 1)
    before = database_rows(sessions)
    failed = attachment(client, own["id"], ids["agent_id"], messages[0]["id"], format)
    assert failed.status_code == 413 and "No partial file" in failed.json()["detail"]
    assert "content-disposition" not in failed.headers and database_rows(sessions) == before


def test_context_json_is_an_excerpt_and_cannot_be_imported_as_a_full_backup(history):
    client, ids, sessions, own, _, _, _, messages = history
    raw = attachment(client, own["id"], ids["agent_id"], messages[0]["id"]).content
    before = database_rows(sessions)
    response = client.post(f'/conversations/import?agent_id={ids["agent_id"]}', content=raw,
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 422 and database_rows(sessions) == before
