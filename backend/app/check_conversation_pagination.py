"""Check scoped conversation pages and literal title search over the running API.

The first run saves six small conversations and one message, then a checkpoint.
Checkpoint reuse and persistence verification perform only reads.
"""

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.check_demo import request_json, require
from app.check_memory import memory_request
from app.config import DATABASE_URL
from app.database import SessionLocal
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.conversation import ConversationResponse
from app.schemas.message import MessageResponse


MESSAGE = "Saved conversation pagination acceptance message."
CHECKS = ["scoped_newest_first_pages", "english_and_chinese_title_search", "literal_search_punctuation",
          "empty_and_unrelated_search", "bounded_request_validation", "foreign_agent_isolation",
          "saved_identity_and_transcript", "preserved_records_vectors_and_checkpoints"]


def default_state_file():
    database = make_url(DATABASE_URL)
    require(database.get_backend_name() == "sqlite" and database.database not in (None, "", ":memory:"),
            "Use persistent SQLite for this check")
    return Path(database.database).resolve().parent / "conversation-pagination-acceptance.json"


def database_fingerprints():
    with SessionLocal() as db:
        require(db.get_bind().dialect.name == "sqlite", "Use the existing SQLite backend")
        connection = db.connection()
        tables = {}
        for name in sorted(inspect(connection).get_table_names()):
            quoted = connection.dialect.identifier_preparer.quote(name)
            result = connection.execute(text("SELECT * FROM " + quoted))
            columns = list(result.keys())
            encoded = sorted(json.dumps(dict(row), sort_keys=True, ensure_ascii=False, allow_nan=False)
                             for row in result.mappings())
            tables[name] = {"columns": columns, "rows": len(encoded),
                            "sha256": sha256(json.dumps(encoded, ensure_ascii=False).encode()).hexdigest(),
                            "row_hashes": sorted(sha256(row.encode()).hexdigest() for row in encoded)}
        require("conversations" in tables and "messages" in tables, "Conversation tables are missing")
        return tables


def write_checkpoint(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(state, stream, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def read_page(base_url, agent_id, query="", limit=10, offset=0):
    return request_json(base_url, "/conversations/page?" + urlencode(
        {"agent_id": agent_id, "query": query, "limit": limit, "offset": offset}))


def assert_page(page, agent_id, query, limit, offset, expected):
    require(isinstance(page, dict) and set(page) == {"agent_id", "query", "limit", "offset", "total", "has_more", "items"},
            "Conversation page has invalid fields")
    require(page["agent_id"] == agent_id and page["query"] == query.strip()
            and page["limit"] == limit and page["offset"] == offset and page["total"] == len(expected)
            and page["has_more"] is (offset + len(page["items"]) < len(expected))
            and page["items"] == expected[offset:offset + limit], "Conversation page contents, order, or metadata differ")


def validate_records(base_url, state, agent_id, other_id):
    require(isinstance(state, dict) and state.get("kind") == "conversation-pagination" and state.get("version") == 1,
            "Conversation pagination checkpoint is invalid")
    require(state.get("agent_id") == agent_id and state.get("other_agent_id") == other_id,
            "Saved acceptance Agents changed")
    rows, foreign, messages = state.get("conversations"), state.get("foreign"), state.get("messages")
    require(isinstance(rows, list) and len(rows) == 5 and isinstance(foreign, dict)
            and isinstance(messages, list) and len(messages) == 1, "Saved acceptance records are invalid")
    expected_titles = [state["prefix"] + suffix for suffix in
                       (" Python planning", " python review", " 中文记忆", " 100%_ready / notes", " Plain topic")]
    require([row.get("title") for row in rows] == expected_titles and foreign.get("title") == expected_titles[0]
            and foreign.get("agent_id") == other_id and all(row.get("agent_id") == agent_id for row in rows),
            "Saved acceptance titles or scopes changed")
    require(len({row.get("id") for row in rows + [foreign]}) == 6,
            "Saved acceptance conversation identities overlap")
    for row in rows + [foreign]:
        require(type(row.get("id")) is int and row["id"] > 0
                and request_json(base_url, f'/conversations/{row["id"]}?agent_id={row["agent_id"]}') == row,
                "Saved conversation was lost or changed before verification")
    require(messages[0].get("role") == "user" and messages[0].get("content") == MESSAGE
            and messages[0].get("conversation_id") == rows[0]["id"], "Saved transcript checkpoint changed")
    for row in rows + [foreign]:
        expected = messages if row["id"] == rows[0]["id"] else []
        actual = request_json(base_url, f'/conversations/{row["id"]}/messages?agent_id={row["agent_id"]}')
        require(actual == expected, "Saved transcript was lost or changed before verification")
    # Confirm that this CLI reads the same scoped SQLite data as the running API.
    with SessionLocal() as db:
        for scope in (agent_id, other_id):
            local = db.query(Conversation).filter(Conversation.agent_id == scope).order_by(Conversation.created_at, Conversation.id).all()
            require([ConversationResponse.model_validate(row).model_dump(mode="json") for row in local]
                    == request_json(base_url, f"/conversations?agent_id={scope}"), "Running API and local SQLite conversations differ")
        local_messages = db.query(Message).filter(Message.conversation_id == rows[0]["id"]).order_by(Message.created_at, Message.id).all()
        require([MessageResponse.model_validate(row).model_dump(mode="json") for row in local_messages] == messages,
                "Running API and local SQLite transcript differ")


def check_conversation_pagination(base_url, verify_persistence=False, state_file=None):
    path = Path(state_file) if state_file is not None else default_state_file()
    require(path.suffix == ".json", "Use a separate .json acceptance checkpoint")
    require(not verify_persistence or path.is_file(), "Conversation pagination checkpoint is missing; verification will not recreate it")
    original = path.read_bytes() if path.exists() else None
    initial_database = database_fingerprints()
    agents = request_json(base_url, "/agents")
    demo = [row for row in agents if row["name"] == "Demo Agent"]
    other = [row for row in agents if row["name"] == "MCP Order Agent"]
    require(len(demo) == len(other) == 1, "Run the existing demo initializer first")
    agent_id, other_id = demo[0]["id"], other[0]["id"]
    if original is not None:
        state = json.loads(original)
    else:
        # A missing/old page API must fail before any fixture write.
        current_rows = request_json(base_url, f"/conversations?agent_id={agent_id}")
        current_rows.sort(key=lambda row: (row["created_at"], row["id"]), reverse=True)
        assert_page(read_page(base_url, agent_id, limit=1), agent_id, "", 1, 0, current_rows)
        require(database_fingerprints() == initial_database, "Initial page probe changed SQLite data")
        prefix = "AgentDeskConversationPage-" + uuid4().hex[:12]
        rows = [request_json(base_url, "/conversations", {"agent_id": agent_id, "title": prefix + suffix})
                for suffix in (" Python planning", " python review", " 中文记忆", " 100%_ready / notes", " Plain topic")]
        foreign = request_json(base_url, "/conversations", {"agent_id": other_id, "title": rows[0]["title"]})
        request_json(base_url, f'/conversations/{rows[0]["id"]}/messages?agent_id={agent_id}',
                     {"role": "user", "content": MESSAGE})
        messages = request_json(base_url, f'/conversations/{rows[0]["id"]}/messages?agent_id={agent_id}')
        state = {"version": 1, "kind": "conversation-pagination", "prefix": prefix,
                 "agent_id": agent_id, "other_agent_id": other_id, "conversations": rows, "foreign": foreign, "messages": messages}
    validate_records(base_url, state, agent_id, other_id)
    before = database_fingerprints()
    if original is not None:
        require(state.get("database") == before, "Saved SQLite records or vectors changed before restart verification")
    else:
        for table, original_table in initial_database.items():
            if table in ("conversations", "messages"):
                require(not (Counter(original_table["row_hashes"]) - Counter(before[table]["row_hashes"])),
                        "Fixture preparation changed an original conversation or message")
                expected_additions = 6 if table == "conversations" else 1
                require(before[table]["rows"] == original_table["rows"] + expected_additions,
                        "Fixture preparation wrote an unexpected number of records")
            else:
                require(before[table] == original_table, "Fixture preparation changed unrelated records or vectors")
    other_checkpoints = {str(file): sha256(file.read_bytes()).hexdigest()
                         for file in path.parent.glob("*acceptance.json") if file != path}
    own = sorted(state["conversations"], key=lambda row: (row["created_at"], row["id"]), reverse=True)
    prefix = state["prefix"]
    for offset in (0, 2, 4, 5, 50):
        assert_page(read_page(base_url, agent_id, prefix, 2, offset), agent_id, prefix, 2, offset, own)
    for suffix in (" PYTHON", " 中文记忆", " %", " _", " /"):
        query = prefix + suffix if suffix in (" PYTHON", " 中文记忆") else suffix.strip()
        # Literal punctuation may occur in unrelated user titles; compare all scoped rows.
        all_rows = request_json(base_url, f"/conversations?agent_id={agent_id}")
        expected = sorted([row for row in all_rows if query.lower() in row["title"].lower()],
                          key=lambda row: (row["created_at"], row["id"]), reverse=True)
        assert_page(read_page(base_url, agent_id, "  " + query + "  ", 50), agent_id, query, 50, 0, expected)
    unrelated = prefix + " absent topic"
    assert_page(read_page(base_url, agent_id, unrelated), agent_id, unrelated, 10, 0, [])
    all_rows = request_json(base_url, f"/conversations?agent_id={agent_id}")
    all_ordered = sorted(all_rows, key=lambda row: (row["created_at"], row["id"]), reverse=True)
    assert_page(read_page(base_url, agent_id, "   "), agent_id, "", 10, 0, all_ordered)
    assert_page(read_page(base_url, agent_id, prefix, 1), agent_id, prefix, 1, 0, own)
    assert_page(read_page(base_url, other_id, prefix, 50), other_id, prefix, 50, 0, [state["foreign"]])
    for params in ({}, {"agent_id": 0}, {"agent_id": agent_id, "limit": 0}, {"agent_id": agent_id, "limit": 51},
                   {"agent_id": agent_id, "offset": -1}, {"agent_id": agent_id, "query": "x" * 201}):
        memory_request(base_url, "/conversations/page?" + urlencode(params), status=422)
    missing = max(row["id"] for row in agents) + 1000
    memory_request(base_url, "/conversations/page?" + urlencode({"agent_id": missing}), status=404)
    require(database_fingerprints() == before, "Conversation queries changed SQLite records or vectors")
    require(all(Path(file).is_file() and sha256(Path(file).read_bytes()).hexdigest() == digest
                for file, digest in other_checkpoints.items()), "Another acceptance checkpoint changed")
    if original is not None:
        require(path.read_bytes() == original, "Conversation pagination checkpoint changed")
    else:
        write_checkpoint(path, {**state, "database": before})
    return {"status": "passed", "checks_passed": len(CHECKS), "checks": CHECKS, "agent_id": agent_id,
            "conversation_ids": [row["id"] for row in state["conversations"]], "foreign_conversation_id": state["foreign"]["id"],
            "saved_message_id": state["messages"][0]["id"], "persistence_verified": verify_persistence,
            "checkpoint_reused": original is not None, "read_only": original is not None, "probe_read_only": True,
            "conversations_created": 0 if original is not None else 6, "messages_created": 0 if original is not None else 1,
            "chat_executions_created": 0, "records_and_vectors_unchanged": True, "checkpoint_file": str(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--verify-persistence", action="store_true")
    args = parser.parse_args()
    try:
        result = check_conversation_pagination(args.base_url, args.verify_persistence, args.state_file)
    except (HTTPError, URLError, OSError, SQLAlchemyError, RuntimeError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(1, f"Conversation pagination check failed: {error}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
