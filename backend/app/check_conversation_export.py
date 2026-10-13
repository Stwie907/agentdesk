"""Check full JSON/Markdown exports, then immutable restart evidence.

Initial preparation saves three conversations and 26 messages without running chat.
Successful checkpoint reuse and restart verification only read records and files.
"""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.check_conversation_pagination import database_fingerprints, write_checkpoint
from app.check_demo import request_json, require
from app.config import DATABASE_URL
from app.database import SessionLocal
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.conversation import ConversationResponse
from app.schemas.message import MessageResponse


CHECKS = ["complete_json_transcript", "literal_unicode_markdown", "attachment_identity_and_headers",
          "empty_transcript_export", "agent_scope_and_validation", "history_beyond_loaded_page",
          "read_only_records_vectors_and_checkpoints", "original_export_bytes_and_restart"]


def default_state_file():
    database = make_url(DATABASE_URL)
    require(database.get_backend_name() == "sqlite" and database.database not in (None, "", ":memory:"),
            "Use persistent SQLite for this check")
    return Path(database.database).resolve().parent / "conversation-export-acceptance.json"


def request_export(base_url, path, status=200):
    request = Request(base_url.rstrip("/") + path, method="GET")
    try:
        response = build_opener(ProxyHandler({})).open(request, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        require(response.status == status, f"Export request returned {response.status}, expected {status}")
        content = response.read(10 * 1024 * 1024 + 1)
        require(len(content) <= 10 * 1024 * 1024, "Export response exceeds its size limit")
        return {"status": response.status, "headers": {key.lower(): value for key, value in response.headers.items()},
                "content": content}


def export_path(conversation_id, agent_id, format="json"):
    return f"/conversations/{conversation_id}/export?" + urlencode({"agent_id": agent_id, "format": format})


def transcript(base_url, conversation):
    return request_json(base_url, f'/conversations/{conversation["id"]}/messages?agent_id={conversation["agent_id"]}')


def fixture_content(prefix, index):
    value = f"{prefix} turn {index + 1:02d} — 中文导出"
    if index == 0:
        value += '\n\n```markdown\n# literal heading\n<script>alert("literal text")</script>\n```\n'
    if index == 24:
        value += "\r\nTrailing whitespace stays:  \n"
    return value


def checkpoint_hashes(path):
    return {file.name: sha256(file.read_bytes()).hexdigest()
            for file in path.parent.glob("*acceptance.json") if file != path}


def validate_records(base_url, state, agent_id, other_id):
    require(isinstance(state, dict) and state.get("kind") == "conversation-export" and state.get("version") == 1,
            "Conversation export checkpoint is invalid")
    require(state.get("agent_id") == agent_id and state.get("other_agent_id") == other_id,
            "Saved acceptance Agents changed")
    prefix = state.get("prefix")
    rows = [state.get(name) for name in ("conversation", "empty", "foreign")]
    messages = state.get("messages")
    foreign_messages = state.get("foreign_messages")
    require(isinstance(prefix, str) and all(isinstance(row, dict) for row in rows)
            and isinstance(messages, list) and len(messages) == 25
            and isinstance(foreign_messages, list) and len(foreign_messages) == 1,
            "Saved export records are invalid")
    require(len({row.get("id") for row in rows}) == 3
            and all(type(row.get("id")) is int and row["id"] > 0 for row in rows), "Saved export identities are invalid")
    for row, suffix, scope in zip(rows, (' 中文 "notes" %_ /../../', " Empty", " Foreign"), (agent_id, agent_id, other_id)):
        require(row.get("title") == prefix + suffix and row.get("agent_id") == scope
                and request_json(base_url, f'/conversations/{row["id"]}?agent_id={scope}') == row,
                "Saved export conversation was lost or changed")
    require(all(type(row.get("id")) is int and row["id"] > 0 and row.get("conversation_id") == rows[0]["id"]
                and row.get("role") == ("user" if index % 2 == 0 else "assistant")
                and row.get("content") == fixture_content(prefix, index) for index, row in enumerate(messages))
            and len({row["id"] for row in messages}) == 25, "Saved export messages changed")
    require(foreign_messages[0].get("conversation_id") == rows[2]["id"]
            and foreign_messages[0].get("role") == "user"
            and foreign_messages[0].get("content") == prefix + " foreign message", "Foreign transcript changed")
    for row, expected in zip(rows, (messages, [], foreign_messages)):
        require(transcript(base_url, row) == expected, "Saved export transcript changed before verification")
    with SessionLocal() as db:
        for scope in (agent_id, other_id):
            local = db.query(Conversation).filter(Conversation.agent_id == scope).order_by(Conversation.created_at, Conversation.id).all()
            require([ConversationResponse.model_validate(row).model_dump(mode="json") for row in local]
                    == request_json(base_url, f"/conversations?agent_id={scope}"), "Running API and local SQLite differ")
        for row in rows:
            local = db.query(Message).filter(Message.conversation_id == row["id"]).order_by(Message.created_at, Message.id).all()
            require([MessageResponse.model_validate(message).model_dump(mode="json") for message in local]
                    == transcript(base_url, row), "Running API and local SQLite messages differ")


def markdown_blocks(text):
    lines, blocks, index = text.splitlines(keepends=True), [], 0
    while index < len(lines):
        match = re.fullmatch(r"(`{3,})text\n", lines[index])
        if match is None:
            index += 1
            continue
        closing = match[1] + "\n"
        index += 1
        start = index
        while index < len(lines) and lines[index] != closing:
            index += 1
        require(index < len(lines), "Markdown literal block is unterminated")
        value = "".join(lines[start:index])
        require(value.endswith("\n"), "Markdown literal block lost its delimiter")
        blocks.append(value[:-1])
        index += 1
    return blocks


def assert_attachment(reply, conversation, messages, format):
    headers = reply["headers"]
    extension, mime = ("json", "application/json") if format == "json" else ("md", "text/markdown")
    require(headers.get("content-disposition") == f'attachment; filename="conversation-{conversation["id"]}.{extension}"'
            and headers.get("content-type", "").split(";")[0] == mime
            and headers.get("cache-control") == "no-store" and headers.get("x-content-type-options") == "nosniff"
            and headers.get("x-conversation-id") == str(conversation["id"])
            and headers.get("x-agent-id") == str(conversation["agent_id"])
            and headers.get("x-message-count") == str(len(messages))
            and headers.get("x-export-schema-version") == "1", "Export attachment headers are invalid")
    text = reply["content"].decode("utf-8")
    if format == "json":
        require(json.loads(text) == {"schema_version": 1, "conversation": conversation,
                                    "message_count": len(messages), "messages": messages}, "JSON export is incomplete or foreign")
    else:
        require(text.startswith(f'# Conversation {conversation["id"]}\n')
                and f'- Agent ID: {conversation["agent_id"]}\n' in text
                and f'- Saved messages: {len(messages)}\n' in text, "Markdown metadata differs")
        expected = [conversation["title"] if conversation["title"] is not None else "(untitled)"]
        for row in messages:
            expected.extend((row["role"], row["content"]))
            require(f'\n## Message {row["id"]}\n' in text and f'Created at: {row["created_at"]}\n' in text,
                    "Markdown message identity or timestamp is missing")
        require(markdown_blocks(text) == expected, "Markdown changed literal titles, roles, or message contents")


def check_conversation_export(base_url, verify_persistence=False, state_file=None):
    path = Path(state_file) if state_file is not None else default_state_file()
    require(path.suffix == ".json", "Use a separate .json acceptance checkpoint")
    require(not verify_persistence or path.is_file(), "Conversation export checkpoint is missing; verification will not recreate it")
    original = path.read_bytes() if path.exists() else None
    before_initial, previous = database_fingerprints(), checkpoint_hashes(path)
    agents = request_json(base_url, "/agents")
    demo = [row for row in agents if row["name"] == "Demo Agent"]
    other = [row for row in agents if row["name"] == "MCP Order Agent"]
    require(len(demo) == len(other) == 1, "Run the existing demo initializer first")
    agent_id, other_id = demo[0]["id"], other[0]["id"]
    if original is not None:
        state = json.loads(original)
    else:
        probe = request_export(base_url, export_path(9223372036854775807, agent_id), 404)
        require(json.loads(probe["content"]).get("detail") == "Conversation not found", "Conversation export API is unavailable")
        require(database_fingerprints() == before_initial, "Initial export probe changed SQLite")
        prefix = "AgentDeskConversationExport-" + uuid4().hex[:12]
        rows = [request_json(base_url, "/conversations", {"agent_id": scope, "title": prefix + suffix})
                for scope, suffix in ((agent_id, ' 中文 "notes" %_ /../../'), (agent_id, " Empty"), (other_id, " Foreign"))]
        for index in range(25):
            request_json(base_url, f'/conversations/{rows[0]["id"]}/messages?agent_id={agent_id}',
                         {"role": "user" if index % 2 == 0 else "assistant", "content": fixture_content(prefix, index)})
        request_json(base_url, f'/conversations/{rows[2]["id"]}/messages?agent_id={other_id}',
                     {"role": "user", "content": prefix + " foreign message"})
        state = {"kind": "conversation-export", "version": 1, "prefix": prefix, "agent_id": agent_id,
                 "other_agent_id": other_id, "conversation": rows[0], "empty": rows[1], "foreign": rows[2],
                 "messages": transcript(base_url, rows[0]), "foreign_messages": transcript(base_url, rows[2])}
    validate_records(base_url, state, agent_id, other_id)
    before = database_fingerprints()
    if original is not None:
        require(state.get("database") == before, "Saved SQLite records or vectors changed before export verification")
        require(state.get("previous_checkpoints") == previous, "An earlier acceptance checkpoint was lost or changed")
    else:
        for table, initial in before_initial.items():
            if table in ("conversations", "messages"):
                require(not (Counter(initial["row_hashes"]) - Counter(before[table]["row_hashes"])), "Original conversations or messages changed")
                require(before[table]["rows"] == initial["rows"] + (3 if table == "conversations" else 26), "Unexpected fixture writes")
            else:
                require(before[table] == initial, "Fixture preparation changed unrelated records or vectors")
    digests = {}
    for name, messages in (("conversation", state["messages"]), ("empty", []), ("foreign", state["foreign_messages"])):
        conversation = state[name]
        for format in ("json", "markdown"):
            reply = request_export(base_url, export_path(conversation["id"], conversation["agent_id"], format))
            assert_attachment(reply, conversation, messages, format)
            digests[name + "." + format] = sha256(reply["content"]).hexdigest()
    first_page = request_json(base_url, f'/conversations/{state["conversation"]["id"]}/messages/page?agent_id={agent_id}')
    require(first_page["items"] == state["messages"][-20:] and first_page["has_more"] is True,
            "Latest page must contain 20 messages while the complete export contains 25")
    for name, scope in (("conversation", other_id), ("foreign", agent_id)):
        for format in ("json", "markdown"):
            request_export(base_url, export_path(state[name]["id"], scope, format), 404)
    for query in ("", "agent_id=0", f"agent_id={agent_id}&format=html", "agent_id=9223372036854775808"):
        request_export(base_url, f'/conversations/{state["conversation"]["id"]}/export?{query}', 422)
    if original is not None:
        require(state.get("export_sha256") == digests, "Original exported file bytes changed after restart")
    require(database_fingerprints() == before, "Export probes changed SQLite records or vectors")
    require(checkpoint_hashes(path) == previous, "Export probes changed earlier acceptance checkpoints")
    if original is not None:
        require(path.read_bytes() == original, "Export checkpoint changed")
    else:
        write_checkpoint(path, {**state, "database": before, "previous_checkpoints": previous, "export_sha256": digests})
    return {"status": "passed", "checks_passed": len(CHECKS), "checks": CHECKS, "agent_id": agent_id,
            "conversation_id": state["conversation"]["id"], "empty_conversation_id": state["empty"]["id"],
            "foreign_conversation_id": state["foreign"]["id"], "message_ids": [row["id"] for row in state["messages"]],
            "saved_message_count": 25, "latest_page_count": 20, "formats_verified": ["json", "markdown"], "export_sha256": digests,
            "persistence_verified": verify_persistence, "checkpoint_reused": original is not None,
            "read_only": original is not None, "probe_read_only": True,
            "conversations_created": 0 if original is not None else 3, "messages_created": 0 if original is not None else 26,
            "chat_executions_created": 0, "records_and_vectors_unchanged": True, "previous_checkpoints_unchanged": True,
            "checkpoint_file": str(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--state-file")
    parser.add_argument("--verify-persistence", action="store_true")
    args = parser.parse_args()
    try:
        result = check_conversation_export(args.base_url, args.verify_persistence, args.state_file)
    except (RuntimeError, AssertionError, KeyError, TypeError, ValueError, OSError, HTTPError, URLError, SQLAlchemyError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
