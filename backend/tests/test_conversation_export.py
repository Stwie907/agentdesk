"""Complete scoped attachments stay deterministic, literal, and read-only."""

import json

import pytest
from sqlalchemy import event

from app.services import conversation_export as exporter
from app.check_conversation_export import markdown_blocks
from app.models.message import Message
from test_conversation_pagination import database_rows
from test_message_pagination import fixture_messages
from test_mcp_runtime_api import demo_api  # noqa: F401


def export(client, conversation_id, agent_id, format="json"):
    return client.get(f"/conversations/{conversation_id}/export", params={"agent_id": agent_id, "format": format})


def test_complete_json_retains_oldest_turn_timestamps_scope_and_all_saved_records(demo_api):
    client, ids, sessions = demo_api
    own, _, _, _, expected = fixture_messages(client, ids, sessions)
    before = database_rows(sessions)
    reply = export(client, own["id"], ids["agent_id"])
    assert reply.status_code == 200
    assert reply.json() == {"schema_version": 1, "conversation": own, "message_count": 45, "messages": expected}
    assert reply.headers["content-disposition"] == f'attachment; filename="conversation-{own["id"]}.json"'
    assert reply.headers["content-type"] == "application/json"
    assert reply.headers["cache-control"] == "no-store" and reply.headers["x-content-type-options"] == "nosniff"
    assert reply.headers["x-message-count"] == "45" and reply.headers["x-export-schema-version"] == "1"
    assert reply.headers["x-conversation-id"] == str(own["id"]) and reply.headers["x-agent-id"] == str(ids["agent_id"])
    assert export(client, own["id"], ids["agent_id"]).content == reply.content
    assert len(client.get(f'/conversations/{own["id"]}/messages/page', params={"agent_id": ids["agent_id"]}).json()["items"]) == 20
    assert database_rows(sessions) == before


def test_markdown_preserves_unicode_raw_fences_html_roles_whitespace_and_safe_filename(demo_api):
    client, ids, sessions = demo_api
    own, _, _, _, _ = fixture_messages(client, ids, sessions, count=3)
    title = '中文 /../../ "filename"\r\n<script>title</script>'
    own = client.patch(f'/conversations/{own["id"]}?agent_id={ids["agent_id"]}', json={"title": title}).json()
    special = '中文 🐍\r\n```md\n# raw heading\n```\n``````\n<script>alert(1)</script>\nTrailing spaces:  \n'
    with sessions() as db:
        first = db.query(Message).filter(Message.conversation_id == own["id"]).order_by(Message.id).first()
        first.content = special
        first.role = 'assistant\n# literal role <a href="x">'
        db.commit()
    expected = client.get(f'/conversations/{own["id"]}/messages?agent_id={ids["agent_id"]}').json()
    before = database_rows(sessions)
    reply = export(client, own["id"], ids["agent_id"], "markdown")
    assert reply.status_code == 200
    assert reply.headers["content-type"] == "text/markdown; charset=utf-8"
    assert reply.headers["content-disposition"] == f'attachment; filename="conversation-{own["id"]}.md"'
    blocks = [title]
    for row in expected: blocks.extend((row["role"], row["content"]))
    assert markdown_blocks(reply.text) == blocks
    assert "```````text\n" in reply.text and special in reply.text
    assert export(client, own["id"], ids["agent_id"], "markdown").content == reply.content
    assert database_rows(sessions) == before


@pytest.mark.parametrize("format", ["json", "markdown"])
def test_empty_history_is_a_valid_complete_attachment(demo_api, format):
    client, ids, sessions = demo_api
    _, empty, _, _, _ = fixture_messages(client, ids, sessions)
    before = database_rows(sessions)
    reply = export(client, empty["id"], ids["agent_id"], format)
    assert reply.status_code == 200 and reply.headers["x-message-count"] == "0"
    if format == "json":
        assert reply.json() == {"schema_version": 1, "conversation": empty, "message_count": 0, "messages": []}
    else:
        assert "No saved messages." in reply.text and markdown_blocks(reply.text) == [empty["title"]]
    assert database_rows(sessions) == before


@pytest.mark.parametrize("format", ["json", "markdown"])
def test_foreign_deleted_and_missing_conversations_are_rejected_without_records_or_attachments(demo_api, format):
    client, ids, sessions = demo_api
    own, _, foreign, _, _ = fixture_messages(client, ids, sessions)
    before = database_rows(sessions)
    for conversation_id, agent_id in [(own["id"], ids["mcp_agent_id"]), (foreign["id"], ids["agent_id"]), (999999, ids["agent_id"])]:
        reply = export(client, conversation_id, agent_id, format)
        assert reply.status_code == 404 and reply.json() == {"detail": "Conversation not found"}
        assert "content-disposition" not in reply.headers
    assert database_rows(sessions) == before
    client.delete(f'/conversations/{own["id"]}?agent_id={ids["agent_id"]}')
    deleted = database_rows(sessions)
    assert export(client, own["id"], ids["agent_id"], format).status_code == 404
    assert database_rows(sessions) == deleted


@pytest.mark.parametrize("query", [{}, {"agent_id": 0}, {"agent_id": -1}, {"agent_id": "wrong"},
                                    {"agent_id": 9223372036854775808}, {"format": "html"}, {"format": "JSON"}])
def test_invalid_request_bounds_and_formats_are_read_only(demo_api, query):
    client, ids, sessions = demo_api
    own, _, _, _, _ = fixture_messages(client, ids, sessions)
    before = database_rows(sessions)
    params = {"agent_id": ids["agent_id"], **query} if query else {}
    assert client.get(f'/conversations/{own["id"]}/export', params=params).status_code == 422
    for invalid_id in (0, -1, 9223372036854775808):
        assert export(client, invalid_id, ids["agent_id"]).status_code == 422
    assert database_rows(sessions) == before


@pytest.mark.parametrize("format", ["json", "markdown"])
def test_limits_fail_explicitly_without_truncating_or_mutating(demo_api, monkeypatch, format):
    client, ids, sessions = demo_api
    own, _, _, _, _ = fixture_messages(client, ids, sessions, count=3)
    before = database_rows(sessions)
    monkeypatch.setattr(exporter, "MAX_EXPORT_MESSAGES", 2)
    reply = export(client, own["id"], ids["agent_id"], format)
    assert reply.status_code == 413 and "message limit" in reply.json()["detail"]
    assert "content-disposition" not in reply.headers
    monkeypatch.setattr(exporter, "MAX_EXPORT_MESSAGES", 3)
    complete = export(client, own["id"], ids["agent_id"], format)
    assert complete.status_code == 200
    monkeypatch.setattr(exporter, "MAX_EXPORT_BYTES", len(complete.content))
    assert export(client, own["id"], ids["agent_id"], format).content == complete.content
    monkeypatch.setattr(exporter, "MAX_EXPORT_BYTES", len(complete.content) - 1)
    reply = export(client, own["id"], ids["agent_id"], format)
    assert reply.status_code == 413 and "file limit" in reply.json()["detail"]
    assert "content-disposition" not in reply.headers
    assert database_rows(sessions) == before


def test_title_and_message_data_use_one_bounded_read_snapshot(demo_api):
    client, ids, sessions = demo_api
    own, _, _, _, _ = fixture_messages(client, ids, sessions)
    with sessions() as db: engine = db.get_bind()
    reads = []
    def capture(_connection, _cursor, statement, parameters, _context, _many):
        reads.append((statement, parameters))
    event.listen(engine, "before_cursor_execute", capture)
    try:
        assert export(client, own["id"], ids["agent_id"]).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(reads) == 1
    assert "LEFT OUTER JOIN messages" in reads[0][0] and "LIMIT" in reads[0][0]
    assert reads[0][1][-2:] == (10001, 0)
