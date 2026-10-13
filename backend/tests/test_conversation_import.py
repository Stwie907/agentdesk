"""Actual export backups create separate transcripts in one transaction."""

import json

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from app.services import conversation_import as importer
from app.schemas.conversation_import import UNTITLED_IMPORT
from test_conversation_pagination import database_rows
from test_message_pagination import fixture_messages
from test_mcp_runtime_api import demo_api  # noqa: F401


def backup(client, ids, sessions, count=25):
    own, empty, _, _, _ = fixture_messages(client, ids, sessions, count=count)
    params = {"agent_id": ids["agent_id"], "format": "json"}
    return own, client.get(f'/conversations/{own["id"]}/export', params=params).json(), client.get(f'/conversations/{empty["id"]}/export', params=params).json()


def upload(client, agent_id, data=None, raw=None, media="application/json"):
    return client.post(f"/conversations/import?agent_id={agent_id}", content=raw if raw is not None else json.dumps(data).encode(),
                       headers={"Content-Type": media})


def check_copy(client, agent_id, result, archive):
    assert result["schema_version"] == 1 and result["message_count"] == archive["message_count"]
    conversation = result["conversation"]
    assert conversation["agent_id"] == agent_id
    assert conversation["title"] == (archive["conversation"]["title"] if archive["conversation"]["title"] is not None else UNTITLED_IMPORT)
    assert conversation["created_at"] == archive["conversation"]["created_at"]
    saved = client.get(f'/conversations/{conversation["id"]}/messages?agent_id={agent_id}').json()
    assert len(saved) == archive["message_count"]
    for imported, original in zip(saved, archive["messages"]):
        assert imported["conversation_id"] == conversation["id"]
        for key in ("role", "content", "created_at"): assert imported[key] == original[key]
    return conversation, saved


def test_real_backup_round_trip_uses_new_ids_and_preserves_all_original_tables(demo_api):
    client, ids, sessions = demo_api
    own, archive, _ = backup(client, ids, sessions)
    archive["messages"][0]["content"] = '中文 🐍\r\n```\n<script>literal</script>\n```\nTail:  \n'
    archive["messages"][0]["role"] = "assistant\n# literal role"
    before = database_rows(sessions)
    reply = upload(client, ids["agent_id"], archive)
    assert reply.status_code == 201 and reply.headers["cache-control"] == "no-store"
    imported, rows = check_copy(client, ids["agent_id"], reply.json(), archive)
    assert imported["id"] != own["id"]
    assert {row["id"] for row in rows}.isdisjoint({row["id"] for row in archive["messages"]})
    assert len(client.get(f'/conversations/{imported["id"]}/messages/page?agent_id={ids["agent_id"]}').json()["items"]) == 20
    after = database_rows(sessions)
    for table in before:
        if table not in ("conversations", "messages"): assert before[table] == after[table]
        else: assert all(row in after[table] for row in before[table])
    assert len(after["conversations"]) == len(before["conversations"]) + 1
    assert len(after["messages"]) == len(before["messages"]) + 25
    exported = client.get(f'/conversations/{imported["id"]}/export?agent_id={ids["agent_id"]}').json()
    second = upload(client, ids["mcp_agent_id"], exported)
    assert second.status_code == 201
    foreign, _ = check_copy(client, ids["mcp_agent_id"], second.json(), exported)
    assert client.get(f'/conversations/{foreign["id"]}?agent_id={ids["agent_id"]}').status_code == 404
    assert client.get(f'/conversations/{imported["id"]}?agent_id={ids["mcp_agent_id"]}').status_code == 404


def test_empty_legacy_null_title_and_unavailable_source_agent_are_supported(demo_api):
    client, ids, sessions = demo_api
    _, _, empty = backup(client, ids, sessions)
    empty["conversation"].update(id=8000000001, agent_id=8000000002, title=None)
    reply = upload(client, ids["agent_id"], empty)
    assert reply.status_code == 201
    conversation, rows = check_copy(client, ids["agent_id"], reply.json(), empty)
    assert rows == [] and conversation["id"] != 8000000001


@pytest.mark.parametrize("change", ["version", "boolean_version", "extra", "missing", "count", "boolean_count", "foreign",
                                   "duplicate", "order", "time", "zone", "precision", "boolean_id", "oversized_id",
                                   "null_content", "extra_message", "unicode", "title_type"])
def test_invalid_complete_backup_is_rejected_without_any_writes(demo_api, change):
    client, ids, sessions = demo_api
    _, archive, _ = backup(client, ids, sessions, count=3)
    if change == "version": archive["schema_version"] = 2
    if change == "boolean_version": archive["schema_version"] = True
    if change == "extra": archive["execution"] = {"run": True}
    if change == "missing": del archive["conversation"]["title"]
    if change == "count": archive["message_count"] = 2
    if change == "boolean_count": archive["message_count"] = True
    if change == "foreign": archive["messages"][0]["conversation_id"] += 1
    if change == "duplicate": archive["messages"][1]["id"] = archive["messages"][0]["id"]
    if change == "order": archive["messages"].reverse()
    if change == "time": archive["messages"][0]["created_at"] = "2026-02-30T00:00:00"
    if change == "zone": archive["conversation"]["created_at"] += "Z"
    if change == "precision": archive["messages"][0]["created_at"] = "2026-10-10T00:00:00.1234567"
    if change == "boolean_id": archive["messages"][0]["id"] = True
    if change == "oversized_id": archive["conversation"]["id"] = 9223372036854775808
    if change == "null_content": archive["messages"][0]["content"] = None
    if change == "extra_message": archive["messages"][0]["agent_id"] = ids["agent_id"]
    if change == "unicode": archive["messages"][0]["content"] = "\ud800"
    if change == "title_type": archive["conversation"]["title"] = 7
    before = database_rows(sessions)
    assert upload(client, ids["agent_id"], archive).status_code == 422
    assert database_rows(sessions) == before


@pytest.mark.parametrize("raw", [b"", b"# Markdown", b"{", b"\xff", b'{"schema_version":1,"schema_version":1}',
                                b'{"schema_version":NaN}', b'{"schema_version":Infinity}', b"[]"])
def test_non_json_duplicate_keys_and_invalid_utf8_are_rejected(demo_api, raw):
    client, ids, sessions = demo_api
    before = database_rows(sessions)
    assert upload(client, ids["agent_id"], raw=raw).status_code == 422
    assert database_rows(sessions) == before


def test_scope_media_type_and_missing_agent_do_not_write(demo_api):
    client, ids, sessions = demo_api
    _, archive, _ = backup(client, ids, sessions)
    before = database_rows(sessions)
    assert upload(client, 999999, archive).status_code == 404
    for scope in (0, -1, 9223372036854775808): assert upload(client, scope, archive).status_code == 422
    assert client.post('/conversations/import', json=archive).status_code == 422
    assert upload(client, ids["agent_id"], archive, media="text/plain").status_code == 415
    assert database_rows(sessions) == before


def test_byte_message_boundaries_chunked_body_and_utf8_bom(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    _, archive, _ = backup(client, ids, sessions, count=3)
    raw = b"\xef\xbb\xbf" + json.dumps(archive, ensure_ascii=False).encode()
    monkeypatch.setattr(importer, "MAX_IMPORT_BYTES", len(raw))
    assert upload(client, ids["agent_id"], raw=raw).status_code == 201
    before = database_rows(sessions)
    assert upload(client, ids["agent_id"], raw=raw + b" ").status_code == 413
    chunks = (chunk for chunk in (raw[:17], raw[17:], b" "))
    assert client.post(f'/conversations/import?agent_id={ids["agent_id"]}', content=chunks,
                       headers={"Content-Type": "application/json"}).status_code == 413
    monkeypatch.setattr(importer, "MAX_IMPORT_BYTES", 10 * 1024 * 1024)
    monkeypatch.setattr(importer, "MAX_IMPORT_MESSAGES", 2)
    assert upload(client, ids["agent_id"], archive).status_code == 413
    assert database_rows(sessions) == before
    monkeypatch.setattr(importer, "MAX_IMPORT_MESSAGES", 3)
    assert upload(client, ids["agent_id"], archive).status_code == 201


def test_ten_thousand_message_limit_is_complete_and_not_truncated(demo_api):
    client, ids, sessions = demo_api
    _, _, archive = backup(client, ids, sessions, count=1)
    archive["messages"] = [{"id": 8000000000 + index, "conversation_id": archive["conversation"]["id"], "role": "user",
                            "content": f"Turn {index}", "created_at": archive["conversation"]["created_at"]} for index in range(10000)]
    archive["message_count"] = 10000
    reply = upload(client, ids["agent_id"], archive)
    assert reply.status_code == 201
    _, rows = check_copy(client, ids["agent_id"], reply.json(), archive)
    assert rows[0]["content"] == "Turn 0" and rows[-1]["content"] == "Turn 9999"
    before = database_rows(sessions)
    archive["message_count"] = 10001
    assert upload(client, ids["agent_id"], archive).status_code == 413
    assert database_rows(sessions) == before


def test_failure_after_partial_inserts_rolls_back_conversation_and_every_message(demo_api):
    client, ids, sessions = demo_api
    _, archive, _ = backup(client, ids, sessions, count=5)
    before = database_rows(sessions)
    with sessions() as db: engine = db.get_bind()
    writes = 0
    def reject_third_message(_conn, _cursor, statement, parameters, _context, _many):
        nonlocal writes
        if statement.startswith("INSERT INTO messages"):
            writes += 1
            if writes == 3: raise IntegrityError(statement, parameters, RuntimeError("injected third-message failure"))
    event.listen(engine, "before_cursor_execute", reject_third_message)
    try:
        reply = upload(client, ids["agent_id"], archive)
        assert reply.status_code == 500 and writes == 3
        assert database_rows(sessions) == before
    finally:
        event.remove(engine, "before_cursor_execute", reject_third_message)
    assert upload(client, ids["agent_id"], archive).status_code == 201
