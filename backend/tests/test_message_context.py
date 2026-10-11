"""Neighbour windows preserve saved text and scope, including unloaded anchors."""

from datetime import datetime

import pytest
from sqlalchemy import event

from app.models.message import Message
from test_conversation_pagination import database_rows
from test_mcp_runtime_api import demo_api  # noqa: F401
from test_message_search import history  # noqa: F401


def context(client, conversation, agent, message, **params):
    return client.get(f"/conversations/{conversation}/messages/{message}/context", params={"agent_id": agent, **params})


@pytest.mark.parametrize("index,before,after", [(0, 3, 3), (24, 3, 3), (12, 3, 3), (12, 10, 10), (12, 0, 0), (0, 10, 0), (24, 0, 10), (12, 1, 5)])
def test_complete_chronological_windows_and_boundaries_are_read_only(history, index, before, after):
    client, ids, sessions, own, _, _, _, messages = history
    original = database_rows(sessions)
    response = context(client, own["id"], ids["agent_id"], messages[index]["id"], before=before, after=after)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store" and response.headers["x-content-type-options"] == "nosniff"
    value = response.json()
    assert value == {"conversation_id": own["id"], "agent_id": ids["agent_id"], "anchor_message_id": messages[index]["id"],
                     "before": before, "after": after, "anchor_index": min(index, before),
                     "has_more_before": index > before, "has_more_after": len(messages) - index - 1 > after,
                     "items": messages[max(0, index - before):index + after + 1]}
    assert database_rows(sessions) == original


def test_default_context_reads_an_unloaded_anchor_and_includes_other_roles(history):
    client, ids, sessions, own, _, _, _, messages = history
    latest = client.get(f'/conversations/{own["id"]}/messages/page', params={"agent_id": ids["agent_id"]}).json()
    assert messages[0]["id"] not in {row["id"] for row in latest["items"]}
    value = context(client, own["id"], ids["agent_id"], messages[0]["id"]).json()
    assert value["before"] == value["after"] == 3 and value["items"] == messages[:4]
    assert {row["role"] for row in value["items"]} == {"user", "assistant"}
    assert messages[0]["id"] > messages[1]["id"]  # Timestamp order precedes numeric ID order.
    assert client.get(f'/conversations/{own["id"]}/messages/page', params={"agent_id": ids["agent_id"]}).json() == latest


def test_zero_limits_still_report_neighbours_and_tied_timestamps_use_ids(history):
    client, ids, _, own, _, _, _, messages = history
    tied = next(index for index in range(1, len(messages) - 1)
                if messages[index - 1]["created_at"] == messages[index]["created_at"] == messages[index + 1]["created_at"])
    value = context(client, own["id"], ids["agent_id"], messages[tied]["id"], before=1, after=1).json()
    assert value["items"] == messages[tied - 1:tied + 2]
    zero = context(client, own["id"], ids["agent_id"], messages[tied]["id"], before=0, after=0).json()
    assert zero["items"] == [messages[tied]] and zero["anchor_index"] == 0
    assert zero["has_more_before"] is zero["has_more_after"] is True


def test_full_literal_content_custom_roles_and_extreme_calendar_dates(demo_api):
    from test_conversation_api_contract import create
    client, ids, sessions = demo_api
    own = create(client, ids["agent_id"])
    with sessions() as db:
        for role, text, stamp in [("", "", datetime(1, 1, 1, 0, 0, 0, 123456)),
                                  ("archived/custom", '🐍' * 3000 + '<script>alert("literal")</script>\r\nTail:  \n', datetime(9999, 12, 31, 23, 59, 59, 999999))]:
            db.add(Message(conversation_id=own["id"], role=role, content=text, created_at=stamp))
        db.commit()
    messages = client.get(f'/conversations/{own["id"]}/messages').json()
    original = database_rows(sessions)
    value = context(client, own["id"], ids["agent_id"], messages[0]["id"]).json()
    assert value["items"] == messages and value["anchor_index"] == 0
    assert value["has_more_before"] is value["has_more_after"] is False
    assert database_rows(sessions) == original


def test_anchor_and_neighbour_queries_have_sql_limits(history):
    client, ids, sessions, own, _, _, _, messages = history
    with sessions() as db: engine = db.get_bind()
    statements = []
    def capture(connection, cursor, statement, parameters, execution_context, executemany):
        if statement.startswith("SELECT messages."): statements.append((statement, parameters))
    event.listen(engine, "before_cursor_execute", capture)
    try:
        value = context(client, own["id"], ids["agent_id"], messages[12]["id"], before=10, after=10).json()
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(value["items"]) == 21 and len(statements) == 3
    assert all("LIMIT" in query and "messages.conversation_id =" in query for query, _ in statements)
    assert [parameters[-2] for _, parameters in statements] == [1, 11, 11]


def test_foreign_missing_sibling_and_empty_anchors_return_404_without_writes(history):
    client, ids, sessions, own, sibling, foreign, empty, messages = history
    sibling_message = client.get(f'/conversations/{sibling["id"]}/messages').json()[0]
    foreign_message = client.get(f'/conversations/{foreign["id"]}/messages').json()[0]
    original = database_rows(sessions)
    cases = [(own["id"], ids["mcp_agent_id"], messages[0]["id"]),
             (foreign["id"], ids["agent_id"], foreign_message["id"]),
             (own["id"], ids["agent_id"], foreign_message["id"]),
             (own["id"], ids["agent_id"], sibling_message["id"]),
             (empty["id"], ids["agent_id"], messages[0]["id"]),
             (own["id"], ids["agent_id"], 9223372036854775807),
             (9223372036854775807, ids["agent_id"], messages[0]["id"])]
    for conversation, agent, message in cases: assert context(client, conversation, agent, message).status_code == 404
    assert context(client, foreign["id"], ids["mcp_agent_id"], foreign_message["id"]).status_code == 200
    assert database_rows(sessions) == original


@pytest.mark.parametrize("params", [{}, {"agent_id": 0}, {"agent_id": "bad"}, {"agent_id": 9223372036854775808},
                                   {"before": -1}, {"before": 11}, {"before": "bad"}, {"before": "1.5"},
                                   {"after": -1}, {"after": 11}, {"after": "bad"}, {"after": "1.5"}])
def test_invalid_scope_or_counts_are_rejected_without_writes(history, params):
    client, ids, sessions, own, _, _, _, messages = history
    original = database_rows(sessions)
    actual = {"agent_id": ids["agent_id"], **params} if params else {}
    response = client.get(f'/conversations/{own["id"]}/messages/{messages[0]["id"]}/context', params=actual)
    assert response.status_code == 422 and database_rows(sessions) == original


@pytest.mark.parametrize("conversation,message", [(0, 1), (-1, 1), (9223372036854775808, 1), (1, 0), (1, -1), (1, 9223372036854775808)])
def test_invalid_path_identities_return_422(history, conversation, message):
    client, ids, sessions, *_ = history
    original = database_rows(sessions)
    assert context(client, conversation, ids["agent_id"], message).status_code == 422
    assert database_rows(sessions) == original
