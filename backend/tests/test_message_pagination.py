"""Bounded chronological history pages preserve scope and full Runtime history."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

from app.models.message import Message
from app.services.conversation_service import build_conversation_history
from test_conversation_api_contract import create
from test_conversation_pagination import database_rows
from test_mcp_runtime_api import demo_api  # noqa: F401


def fixture_messages(client, ids, sessions, count=45):
    own = create(client, ids["agent_id"], "Long conversation")
    empty = create(client, ids["agent_id"], "Empty conversation")
    foreign = create(client, ids["mcp_agent_id"], "Foreign conversation")
    with sessions() as db:
        # Deliberately tie timestamps and put a high ID earlier in time.
        for index in range(count):
            timestamp = datetime(2026, 10, 10) + timedelta(seconds=index // 3)
            if index == count - 1:
                timestamp = datetime(2026, 10, 9)
            db.add(Message(conversation_id=own["id"], role="user" if index % 2 == 0 else "assistant",
                           content=f"Saved message {index}", created_at=timestamp))
        db.add(Message(conversation_id=foreign["id"], role="user", content="Foreign transcript"))
        db.commit()
        foreign_id = db.query(Message).filter(Message.conversation_id == foreign["id"]).one().id
    ordered = client.get(f'/conversations/{own["id"]}/messages?agent_id={ids["agent_id"]}').json()
    return own, empty, foreign, foreign_id, ordered


def page(client, conversation_id, agent_id, **params):
    result = client.get(f"/conversations/{conversation_id}/messages/page", params={"agent_id": agent_id, **params})
    assert result.status_code == 200, result.text
    return result.json()


def test_latest_default_then_older_pages_are_ordered_complete_and_read_only(demo_api):
    client, ids, sessions = demo_api
    own, _, _, _, expected = fixture_messages(client, ids, sessions)
    before = database_rows(sessions)
    first = page(client, own["id"], ids["agent_id"])
    assert first == {"conversation_id": own["id"], "agent_id": ids["agent_id"], "limit": 20,
                     "before_id": None, "has_more": True, "next_before_id": expected[-20]["id"], "items": expected[-20:]}
    second = page(client, own["id"], ids["agent_id"], before_id=first["next_before_id"])
    assert second["items"] == expected[-40:-20] and second["has_more"] is True
    last = page(client, own["id"], ids["agent_id"], before_id=second["next_before_id"])
    assert last["items"] == expected[:-40] and last["has_more"] is False and last["next_before_id"] is None
    assert last["items"] + second["items"] + first["items"] == expected
    assert page(client, own["id"], ids["agent_id"], before_id=expected[0]["id"])["items"] == []
    assert database_rows(sessions) == before
    with sessions() as db:
        history = build_conversation_history(db, own["id"])
    assert all(row["content"] in history for row in expected)


def test_empty_transcript_exact_boundary_and_custom_limits(demo_api):
    client, ids, sessions = demo_api
    own, empty, _, _, expected = fixture_messages(client, ids, sessions, count=20)
    assert page(client, empty["id"], ids["agent_id"])["items"] == []
    exact = page(client, own["id"], ids["agent_id"])
    assert exact["items"] == expected and exact["has_more"] is False
    assert exact["next_before_id"] is None
    assert page(client, own["id"], ids["agent_id"], limit=100)["items"] == expected
    single = page(client, own["id"], ids["agent_id"], limit=1)
    assert single["items"] == expected[-1:] and single["has_more"] is True


def test_new_messages_do_not_shift_an_existing_older_cursor(demo_api):
    client, ids, sessions = demo_api
    own, _, _, _, expected = fixture_messages(client, ids, sessions)
    first = page(client, own["id"], ids["agent_id"])
    with sessions() as db:
        db.add(Message(conversation_id=own["id"], role="assistant", content="New latest turn", created_at=datetime(2027, 1, 1)))
        db.commit()
    older = page(client, own["id"], ids["agent_id"], before_id=first["next_before_id"])
    assert older["items"] == expected[-40:-20]
    assert page(client, own["id"], ids["agent_id"])["items"][-1]["content"] == "New latest turn"


def test_foreign_missing_or_deleted_cursors_never_leak_or_repair_data(demo_api):
    client, ids, sessions = demo_api
    own, _, foreign, foreign_id, expected = fixture_messages(client, ids, sessions)
    before = database_rows(sessions)
    for conversation_id, agent_id, cursor in [
        (own["id"], ids["mcp_agent_id"], None), (foreign["id"], ids["agent_id"], None),
        (999999, ids["agent_id"], None), (own["id"], ids["agent_id"], foreign_id),
        (own["id"], ids["agent_id"], 999999),
    ]:
        params = {"agent_id": agent_id}
        if cursor is not None:
            params["before_id"] = cursor
        assert client.get(f"/conversations/{conversation_id}/messages/page", params=params).status_code == 404
    assert database_rows(sessions) == before
    cursor_id = expected[-20]["id"]
    with sessions() as db:
        db.query(Message).filter(Message.id == cursor_id).delete()
        db.commit()
    after_delete = database_rows(sessions)
    assert client.get(f'/conversations/{own["id"]}/messages/page', params={"agent_id": ids["agent_id"], "before_id": cursor_id}).status_code == 404
    assert database_rows(sessions) == after_delete


@pytest.mark.parametrize("params", [
    {}, {"agent_id": 0}, {"agent_id": "wrong"}, {"agent_id": 9223372036854775808},
    {"limit": 0}, {"limit": 101}, {"limit": "wrong"},
    {"before_id": 0}, {"before_id": -1}, {"before_id": "wrong"}, {"before_id": 9223372036854775808},
])
def test_invalid_parameters_are_read_only(demo_api, params):
    client, ids, sessions = demo_api
    own = create(client, ids["agent_id"])
    before = database_rows(sessions)
    query = {"agent_id": ids["agent_id"], **params} if params else {}
    assert client.get(f'/conversations/{own["id"]}/messages/page', params=query).status_code == 422
    assert database_rows(sessions) == before
    assert client.get('/conversations/9223372036854775808/messages/page', params={"agent_id": ids["agent_id"]}).status_code == 422


def test_sql_fetch_is_bounded_instead_of_loading_the_full_transcript(demo_api):
    client, ids, sessions = demo_api
    own, _, _, _, _ = fixture_messages(client, ids, sessions)
    queries = []
    with sessions() as db:
        engine = db.get_bind()
    def capture(_connection, _cursor, statement, parameters, _context, _many):
        if "FROM messages" in statement:
            queries.append((statement, parameters))
    event.listen(engine, "before_cursor_execute", capture)
    try:
        page(client, own["id"], ids["agent_id"])
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(queries) == 1
    assert "LIMIT" in queries[0][0] and queries[0][1][-2:] == (21, 0)
