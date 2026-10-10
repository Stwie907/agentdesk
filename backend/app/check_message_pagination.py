"""Verify bounded message history through the running API without executing chat.

First run: create three isolated conversations and 46 saved fixture messages.
Reuse/restart: read the immutable checkpoint and database without repairing data.
"""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from uuid import uuid4

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.check_conversation_pagination import database_fingerprints, write_checkpoint
from app.check_demo import request_json, require
from app.check_memory import memory_request
from app.config import DATABASE_URL
from app.database import SessionLocal
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.conversation import ConversationResponse
from app.schemas.message import MessageResponse


CHECKS = ["latest_bounded_chronological_page", "complete_older_cursor_walk", "custom_limits_and_empty_history",
          "foreign_agent_and_cursor_isolation", "bounded_request_validation", "legacy_full_history_preserved",
          "saved_message_identity_and_restart", "read_only_records_vectors_and_checkpoints"]


def default_state_file():
    database = make_url(DATABASE_URL)
    require(database.get_backend_name() == "sqlite" and database.database not in (None, "", ":memory:"),
            "Use persistent SQLite for this check")
    return Path(database.database).resolve().parent / "message-pagination-acceptance.json"


def read_page(base_url, conversation_id, agent_id, limit=20, before_id=None):
    params = {"agent_id": agent_id, "limit": limit}
    if before_id is not None:
        params["before_id"] = before_id
    return request_json(base_url, f"/conversations/{conversation_id}/messages/page?" + urlencode(params))


def assert_page(page, conversation_id, agent_id, limit, before_id, expected):
    require(isinstance(page, dict) and set(page) == {
        "conversation_id", "agent_id", "limit", "before_id", "has_more", "next_before_id", "items",
    }, "Message page has invalid fields")
    eligible = expected
    if before_id is not None:
        matches = [index for index, row in enumerate(expected) if row["id"] == before_id]
        require(len(matches) == 1, "Expected message cursor is missing")
        eligible = expected[:matches[0]]
    items = eligible[-limit:]
    has_more = len(eligible) > limit
    require(page == {"conversation_id": conversation_id, "agent_id": agent_id, "limit": limit,
                     "before_id": before_id, "has_more": has_more,
                     "next_before_id": items[0]["id"] if has_more else None, "items": items},
            "Message page contents, chronology, scope, or cursor differ")


def transcript(base_url, conversation):
    return request_json(base_url, f'/conversations/{conversation["id"]}/messages?agent_id={conversation["agent_id"]}')


def validate_records(base_url, state, agent_id, other_id):
    require(isinstance(state, dict) and state.get("version") == 1 and state.get("kind") == "message-pagination",
            "Message pagination checkpoint is invalid")
    require(state.get("agent_id") == agent_id and state.get("other_agent_id") == other_id,
            "Saved acceptance Agents changed")
    prefix = state.get("prefix")
    rows = [state.get(name) for name in ("conversation", "empty", "foreign")]
    messages, foreign_messages = state.get("messages"), state.get("foreign_messages")
    require(isinstance(prefix, str) and all(isinstance(row, dict) for row in rows)
            and isinstance(messages, list) and len(messages) == 45
            and isinstance(foreign_messages, list) and len(foreign_messages) == 1,
            "Saved acceptance records are invalid")
    require(len({row.get("id") for row in rows}) == 3 and all(type(row.get("id")) is int and row["id"] > 0 for row in rows),
            "Saved conversation identities are invalid")
    for row, suffix, scope in zip(rows, (" History", " Empty", " Foreign"), (agent_id, agent_id, other_id)):
        require(row.get("title") == prefix + suffix and row.get("agent_id") == scope
                and request_json(base_url, f'/conversations/{row["id"]}?agent_id={scope}') == row,
                "Saved conversation identity, title, or Agent changed")
    require(all(type(row.get("id")) is int and row["id"] > 0 and row.get("conversation_id") == rows[0]["id"]
                and row.get("role") == ("user" if index % 2 == 0 else "assistant")
                and row.get("content") == f"{prefix} message {index + 1:02d} — 中文 history"
                for index, row in enumerate(messages)) and len({row["id"] for row in messages}) == 45,
            "Saved message identities, roles, or contents changed")
    require(foreign_messages[0].get("conversation_id") == rows[2]["id"]
            and foreign_messages[0].get("content") == prefix + " foreign message"
            and foreign_messages[0].get("role") == "user", "Foreign message checkpoint changed")
    require(transcript(base_url, rows[0]) == messages and transcript(base_url, rows[1]) == []
            and transcript(base_url, rows[2]) == foreign_messages,
            "Saved transcripts were lost or changed before verification")
    # Fingerprints must describe the same SQLite data served by the running API.
    with SessionLocal() as db:
        for scope in (agent_id, other_id):
            local = db.query(Conversation).filter(Conversation.agent_id == scope).order_by(Conversation.created_at, Conversation.id).all()
            require([ConversationResponse.model_validate(row).model_dump(mode="json") for row in local]
                    == request_json(base_url, f"/conversations?agent_id={scope}"), "Running API and local SQLite conversations differ")
        for conversation in rows:
            local = db.query(Message).filter(Message.conversation_id == conversation["id"]).order_by(Message.created_at, Message.id).all()
            require([MessageResponse.model_validate(row).model_dump(mode="json") for row in local]
                    == transcript(base_url, conversation), "Running API and local SQLite messages differ")


def check_message_pagination(base_url, verify_persistence=False, state_file=None):
    path = Path(state_file) if state_file is not None else default_state_file()
    require(path.suffix == ".json", "Use a separate .json acceptance checkpoint")
    require(not verify_persistence or path.is_file(), "Message pagination checkpoint is missing; verification will not recreate it")
    original = path.read_bytes() if path.exists() else None
    initial_database = database_fingerprints()
    other_checkpoints = {str(file): sha256(file.read_bytes()).hexdigest()
                         for file in path.parent.glob("*acceptance.json") if file != path}
    agents = request_json(base_url, "/agents")
    demo = [row for row in agents if row["name"] == "Demo Agent"]
    other = [row for row in agents if row["name"] == "MCP Order Agent"]
    require(len(demo) == len(other) == 1, "Run the existing demo initializer first")
    agent_id, other_id = demo[0]["id"], other[0]["id"]
    if original is not None:
        state = json.loads(original)
    else:
        # Detect an old/missing page route before writing any fixture.
        existing = request_json(base_url, f"/conversations?agent_id={agent_id}")
        if existing:
            current = existing[0]
            assert_page(read_page(base_url, current["id"], agent_id, limit=1), current["id"], agent_id, 1, None, transcript(base_url, current))
        else:
            probe = memory_request(base_url, f"/conversations/9223372036854775807/messages/page?agent_id={agent_id}", status=404)
            require(probe.get("detail") == "Conversation not found", "The new message page API is unavailable")
        require(database_fingerprints() == initial_database, "Initial message page probe changed SQLite data")
        prefix = "AgentDeskMessagePage-" + uuid4().hex[:12]
        rows = [request_json(base_url, "/conversations", {"agent_id": scope, "title": prefix + suffix})
                for scope, suffix in ((agent_id, " History"), (agent_id, " Empty"), (other_id, " Foreign"))]
        for index in range(45):
            request_json(base_url, f'/conversations/{rows[0]["id"]}/messages?agent_id={agent_id}',
                         {"role": "user" if index % 2 == 0 else "assistant",
                          "content": f"{prefix} message {index + 1:02d} — 中文 history"})
        request_json(base_url, f'/conversations/{rows[2]["id"]}/messages?agent_id={other_id}',
                     {"role": "user", "content": prefix + " foreign message"})
        state = {"kind": "message-pagination", "version": 1, "prefix": prefix, "agent_id": agent_id,
                 "other_agent_id": other_id, "conversation": rows[0], "empty": rows[1], "foreign": rows[2],
                 "messages": transcript(base_url, rows[0]), "foreign_messages": transcript(base_url, rows[2])}
    validate_records(base_url, state, agent_id, other_id)
    before = database_fingerprints()
    if original is not None:
        require(state.get("database") == before, "Saved SQLite records or vectors changed before restart verification")
    else:
        for table, initial in initial_database.items():
            if table in ("conversations", "messages"):
                require(not (Counter(initial["row_hashes"]) - Counter(before[table]["row_hashes"])),
                        "Fixture preparation changed an original conversation or message")
                require(before[table]["rows"] == initial["rows"] + (3 if table == "conversations" else 46),
                        "Fixture preparation wrote an unexpected number of records")
            else:
                require(before[table] == initial, "Fixture preparation changed unrelated records or vectors")
    conversation_id = state["conversation"]["id"]
    expected = state["messages"]
    first = read_page(base_url, conversation_id, agent_id)
    assert_page(first, conversation_id, agent_id, 20, None, expected)
    collected = first["items"]
    current = first
    visited = set()
    while current["has_more"]:
        cursor = current["next_before_id"]
        require(cursor not in visited, "Message cursor walk repeated a page")
        visited.add(cursor)
        current = read_page(base_url, conversation_id, agent_id, before_id=cursor)
        assert_page(current, conversation_id, agent_id, 20, cursor, expected)
        collected = current["items"] + collected
    require(collected == expected, "Message cursor walk lost or duplicated saved history")
    for limit in (1, 45, 100):
        assert_page(read_page(base_url, conversation_id, agent_id, limit), conversation_id, agent_id, limit, None, expected)
    first_id = expected[0]["id"]
    assert_page(read_page(base_url, conversation_id, agent_id, before_id=first_id), conversation_id, agent_id, 20, first_id, expected)
    empty_id = state["empty"]["id"]
    assert_page(read_page(base_url, empty_id, agent_id), empty_id, agent_id, 20, None, [])
    foreign_id = state["foreign"]["id"]
    assert_page(read_page(base_url, foreign_id, other_id), foreign_id, other_id, 20, None, state["foreign_messages"])
    for path_suffix, params in [
        (conversation_id, {"agent_id": other_id}), (foreign_id, {"agent_id": agent_id}),
        (conversation_id, {"agent_id": agent_id, "before_id": state["foreign_messages"][0]["id"]}),
    ]:
        memory_request(base_url, f"/conversations/{path_suffix}/messages/page?" + urlencode(params), status=404)
    for params in ({}, {"agent_id": 0}, {"agent_id": agent_id, "limit": 0}, {"agent_id": agent_id, "limit": 101},
                   {"agent_id": agent_id, "before_id": 0}, {"agent_id": agent_id, "before_id": 9223372036854775808}):
        memory_request(base_url, f"/conversations/{conversation_id}/messages/page?" + urlencode(params), status=422)
    require(transcript(base_url, state["conversation"]) == expected, "Legacy full transcript changed")
    require(database_fingerprints() == before, "Message page probes changed SQLite records or vectors")
    require(all(Path(file).is_file() and sha256(Path(file).read_bytes()).hexdigest() == digest
                for file, digest in other_checkpoints.items()), "Another acceptance checkpoint changed")
    if original is not None:
        require(path.read_bytes() == original, "Message pagination checkpoint changed")
    else:
        write_checkpoint(path, {**state, "database": before})
    return {"status": "passed", "checks_passed": len(CHECKS), "checks": CHECKS, "agent_id": agent_id,
            "conversation_id": conversation_id, "empty_conversation_id": empty_id, "foreign_conversation_id": foreign_id,
            "message_ids": [row["id"] for row in expected], "saved_message_count": len(expected), "pages_walked": len(visited) + 1,
            "persistence_verified": verify_persistence, "checkpoint_reused": original is not None,
            "read_only": original is not None, "probe_read_only": True,
            "conversations_created": 0 if original is not None else 3, "messages_created": 0 if original is not None else 46,
            "chat_executions_created": 0, "records_and_vectors_unchanged": True, "checkpoint_file": str(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--state-file")
    parser.add_argument("--verify-persistence", action="store_true")
    args = parser.parse_args()
    try:
        result = check_message_pagination(args.base_url, args.verify_persistence, args.state_file)
    except (RuntimeError, AssertionError, KeyError, TypeError, ValueError, OSError, HTTPError, URLError, SQLAlchemyError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
