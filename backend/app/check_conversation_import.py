"""Check JSON backup imports and then verify the original IDs after restart.

The initial run imports three conversations and 50 messages without running chat.
Checkpoint reuse and restart verification only read the original records and files.
"""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.check_conversation_export import assert_attachment, checkpoint_hashes, export_path, request_export, transcript
from app.check_conversation_pagination import database_fingerprints, write_checkpoint
from app.check_demo import request_json, require
from app.config import DATABASE_URL
from app.database import SessionLocal
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.conversation import ConversationResponse
from app.schemas.message import MessageResponse


CHECKS = ["complete_json_round_trip", "new_local_ids_and_destination_scope", "literal_unicode_and_original_timestamps",
          "empty_backup_and_large_proxy_body", "invalid_backups_leave_no_records", "history_beyond_loaded_page",
          "preserved_records_vectors_and_checkpoints", "original_imports_and_restart"]


def default_state_file():
    database = make_url(DATABASE_URL)
    require(database.get_backend_name() == "sqlite" and database.database not in (None, "", ":memory:"),
            "Use persistent SQLite for this check")
    return Path(database.database).resolve().parent / "conversation-import-acceptance.json"


def encode_backup(backup):
    return (json.dumps(backup, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")


def request_import(base_url, agent_id, raw, status=201):
    request = Request(base_url.rstrip("/") + f"/conversations/import?agent_id={agent_id}", data=raw,
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        response = build_opener(ProxyHandler({})).open(request, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        require(response.status == status, f"Import request returned {response.status}, expected {status}")
        body = response.read(10 * 1024 * 1024 + 1)
        require(len(body) <= 10 * 1024 * 1024, "Import response exceeds its size limit")
        return json.loads(body) if status == 201 else None


def fixture_content(prefix, index):
    value = f"{prefix} turn {index + 1:02d} — 中文备份 🐍"
    if index == 0: value += '\n\n```markdown\n# literal heading\n<script>alert("literal text")</script>\n```\n'
    if index == 24: value += "\r\nTrailing whitespace stays:  \n"
    return value


def fixture_backup(prefix, empty=False):
    source_id = 8000000002 if empty else 8000000000
    return {"schema_version": 1,
            "conversation": {"id": source_id, "agent_id": 8000000001, "title": prefix + (" Empty" if empty else ' 中文 "backup" %_'),
                             "created_at": "2026-10-10T06:00:00.123456"},
            "message_count": 0 if empty else 25,
            "messages": [] if empty else [{"id": 8000000100 + index, "conversation_id": source_id,
                "role": "user" if index % 2 == 0 else "assistant", "content": fixture_content(prefix, index),
                "created_at": f"2026-10-10T06:00:00.{123456 + index // 3:06d}"} for index in range(25)]}


def assert_copy(result, backup, agent_id):
    require(isinstance(result, dict) and result.get("schema_version") == 1 and result.get("message_count") == backup["message_count"],
            "Import result has invalid version or message count")
    row = result.get("conversation")
    require(isinstance(row, dict) and type(row.get("id")) is int and 0 < row["id"] != backup["conversation"]["id"]
            and row.get("agent_id") == agent_id and row.get("title") == backup["conversation"]["title"]
            and row.get("created_at") == backup["conversation"]["created_at"], "Import did not create a separate scoped conversation")
    return row


def validate_records(base_url, state, agent_id, other_id):
    require(isinstance(state, dict) and state.get("kind") == "conversation-import" and type(state.get("version")) is int
            and state["version"] == 1, "Conversation import checkpoint is invalid")
    require(state.get("agent_id") == agent_id and state.get("other_agent_id") == other_id, "Saved acceptance Agents changed")
    prefix = state.get("prefix")
    require(isinstance(prefix, str) and prefix.startswith("AgentDeskConversationImport-"), "Saved import prefix is invalid")
    backup = fixture_backup(prefix)
    require(state.get("backup") == backup, "Original JSON backup changed")
    rows = [state.get(name) for name in ("conversation", "empty", "foreign")]
    require(all(isinstance(row, dict) and type(row.get("id")) is int and row["id"] > 0 for row in rows)
            and len({row["id"] for row in rows}) == 3, "Saved import identities are invalid")
    for row, scope, title in zip(rows, (agent_id, agent_id, other_id), (backup["conversation"]["title"], prefix + " Empty", backup["conversation"]["title"])):
        require(row.get("agent_id") == scope and row.get("title") == title and row.get("created_at") == backup["conversation"]["created_at"]
                and request_json(base_url, f'/conversations/{row["id"]}?agent_id={scope}') == row,
                "Original imported conversation was lost or changed")
    all_ids = set()
    for row, expected in zip((rows[0], rows[2]), (state.get("messages"), state.get("foreign_messages"))):
        require(isinstance(expected, list) and len(expected) == 25 and transcript(base_url, row) == expected,
                "Original imported messages were lost or changed")
        for saved, source in zip(expected, backup["messages"]):
            require(isinstance(saved, dict) and type(saved.get("id")) is int and saved["id"] > 0
                    and saved["id"] not in all_ids and saved["id"] != source["id"] and saved.get("conversation_id") == row["id"]
                    and all(saved.get(key) == source[key] for key in ("role", "content", "created_at")),
                    "Imported text, timestamps, or fresh message identities differ")
            all_ids.add(saved["id"])
    require(transcript(base_url, rows[1]) == [], "The empty imported transcript changed")
    with SessionLocal() as db:
        for scope in (agent_id, other_id):
            local = db.query(Conversation).filter(Conversation.agent_id == scope).order_by(Conversation.created_at, Conversation.id).all()
            require([ConversationResponse.model_validate(row).model_dump(mode="json") for row in local]
                    == request_json(base_url, f"/conversations?agent_id={scope}"), "Running API and local SQLite conversations differ")
        for row in rows:
            local = db.query(Message).filter(Message.conversation_id == row["id"]).order_by(Message.created_at, Message.id).all()
            require([MessageResponse.model_validate(message).model_dump(mode="json") for message in local]
                    == transcript(base_url, row), "Running API and local SQLite imported messages differ")


def check_conversation_import(base_url, verify_persistence=False, state_file=None):
    path = Path(state_file) if state_file is not None else default_state_file()
    require(path.suffix == ".json", "Use a separate .json acceptance checkpoint")
    require(not verify_persistence or path.is_file(), "Conversation import checkpoint is missing; verification will not recreate it")
    original = path.read_bytes() if path.exists() else None
    before_initial = database_fingerprints()
    previous = checkpoint_hashes(path)
    agents = request_json(base_url, "/agents")
    demo = [row for row in agents if row["name"] == "Demo Agent"]
    other = [row for row in agents if row["name"] == "MCP Order Agent"]
    require(len(demo) == len(other) == 1, "Run the existing demo initializer first")
    agent_id, other_id = demo[0]["id"], other[0]["id"]
    if original is not None:
        state = json.loads(original)
        require(isinstance(state, dict) and state.get("database") == before_initial, "Saved SQLite records or vectors changed before import verification")
        require(state.get("previous_checkpoints") == previous, "An earlier acceptance checkpoint was lost or changed")
    else:
        for scope in (agent_id, other_id):
            existing = request_json(base_url, f"/conversations?agent_id={scope}")
            require(not any(isinstance(row.get("title"), str) and row["title"].startswith("AgentDeskConversationImport-") for row in existing),
                    "Existing import acceptance records have no checkpoint; acceptance will not recreate or replace them")
        spec = request_json(base_url, "/openapi.json")
        require("201" in spec.get("paths", {}).get("/conversations/import", {}).get("post", {}).get("responses", {}),
                "Conversation import endpoint is unavailable; rebuild backend and frontend before fixture writes")
        prefix = "AgentDeskConversationImport-" + uuid4().hex[:10]
        backup, empty_backup = fixture_backup(prefix), fixture_backup(prefix, True)
        raw = encode_backup(backup)
        invalid = {**backup, "message_count": 24}
        oversized = {**backup, "message_count": 10001}
        for body, status in ((b"{}", 422), (encode_backup(invalid), 422), (encode_backup(oversized), 413),
                             (b'{"schema_version":1,' + raw.lstrip()[1:], 422)):
            request_import(base_url, agent_id, body, status)
        request_import(base_url, 0, raw, 422)
        request_import(base_url, 9223372036854775807, raw, 404)
        require(database_fingerprints() == before_initial, "Rejected backups changed SQLite records")
        conversation = assert_copy(request_import(base_url, agent_id, raw), backup, agent_id)
        # Valid JSON with leading whitespace proves uploads exceed Nginx's old
        # 1 MiB default without creating oversized message content in the UI.
        empty_raw = b" " * (1024 * 1024 + 1) + encode_backup(empty_backup)
        empty = assert_copy(request_import(base_url, agent_id, empty_raw), empty_backup, agent_id)
        actual = request_export(base_url, export_path(conversation["id"], agent_id))
        exported = json.loads(actual["content"])
        foreign = assert_copy(request_import(base_url, other_id, actual["content"]), exported, other_id)
        state = {"kind": "conversation-import", "version": 1, "agent_id": agent_id, "other_agent_id": other_id,
                 "prefix": prefix, "backup": backup, "conversation": conversation, "empty": empty, "foreign": foreign,
                 "messages": transcript(base_url, conversation), "foreign_messages": transcript(base_url, foreign),
                 "large_upload_bytes": len(empty_raw)}
    require(type(state.get("large_upload_bytes")) is int and 1024 * 1024 < state["large_upload_bytes"] <= 10 * 1024 * 1024,
            "Large JSON upload evidence is invalid")
    validate_records(base_url, state, agent_id, other_id)
    before = database_fingerprints()
    if original is None:
        for table, initial in before_initial.items():
            if table in ("conversations", "messages"):
                require(not (Counter(initial["row_hashes"]) - Counter(before[table]["row_hashes"])), "Original conversations or messages changed")
                require(before[table]["rows"] == initial["rows"] + (3 if table == "conversations" else 50), "Unexpected import fixture writes")
            else:
                require(before[table] == initial, "Imports changed unrelated records or vectors")
    digests = {}
    for name, messages in (("conversation", state["messages"]), ("empty", []), ("foreign", state["foreign_messages"])):
        conversation = state[name]
        for format in ("json", "markdown"):
            reply = request_export(base_url, export_path(conversation["id"], conversation["agent_id"], format))
            assert_attachment(reply, conversation, messages, format)
            digests[name + "." + format] = sha256(reply["content"]).hexdigest()
    page = request_json(base_url, f'/conversations/{state["conversation"]["id"]}/messages/page?agent_id={agent_id}')
    require(page["items"] == state["messages"][-20:] and page["has_more"] is True, "Imported history must contain 25 saved messages beyond the latest page")
    for name, scope in (("conversation", other_id), ("empty", other_id), ("foreign", agent_id)):
        request_export(base_url, export_path(state[name]["id"], scope), 404)
    if original is not None:
        require(state.get("export_sha256") == digests, "Original imported export bytes changed after restart")
    require(database_fingerprints() == before, "Import verification probes changed SQLite records or vectors")
    require(checkpoint_hashes(path) == previous, "Import acceptance changed earlier checkpoint files")
    if original is not None:
        require(path.read_bytes() == original, "Import checkpoint changed")
    else:
        write_checkpoint(path, {**state, "database": before, "previous_checkpoints": previous, "export_sha256": digests})
    return {"status": "passed", "checks_passed": len(CHECKS), "checks": CHECKS, "agent_id": agent_id,
            "conversation_id": state["conversation"]["id"], "empty_conversation_id": state["empty"]["id"],
            "foreign_conversation_id": state["foreign"]["id"], "message_ids": [row["id"] for row in state["messages"]],
            "foreign_message_ids": [row["id"] for row in state["foreign_messages"]], "saved_message_count": 25, "latest_page_count": 20,
            "large_upload_bytes": state["large_upload_bytes"], "export_sha256": digests, "persistence_verified": verify_persistence,
            "checkpoint_reused": original is not None, "read_only": original is not None, "probe_read_only": True,
            "conversations_created": 0 if original is not None else 3, "messages_created": 0 if original is not None else 50,
            "chat_executions_created": 0, "original_records_and_vectors_unchanged": True, "previous_checkpoints_unchanged": True,
            "checkpoint_file": str(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--state-file")
    parser.add_argument("--verify-persistence", action="store_true")
    args = parser.parse_args()
    try:
        result = check_conversation_import(args.base_url, args.verify_persistence, args.state_file)
    except (RuntimeError, AssertionError, KeyError, TypeError, ValueError, OSError, URLError, SQLAlchemyError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1) from error
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
