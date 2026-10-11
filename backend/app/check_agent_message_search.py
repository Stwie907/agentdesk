"""Read-only cross-conversation searches retaining all original acceptance evidence."""

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode

from sqlalchemy.exc import SQLAlchemyError

from app import check_conversation_import as importer
from app.check_conversation_export import checkpoint_hashes, request_export as request_response
from app.check_conversation_pagination import database_fingerprints, write_checkpoint
from app.check_demo import require
from app.check_message_context_export import assert_attachment, expected_context, response_evidence
from app.check_message_search import digest
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.conversation import ConversationResponse
from app.schemas.message import MessageResponse


CHECKS = ["complete_history_across_agent_conversations", "literal_unicode_and_ascii_case",
          "role_filters_and_bounded_previews", "stable_newest_first_pages", "agent_isolation",
          "original_full_message_context_and_downloads", "read_only_validation",
          "original_fifty_seven_responses", "preserved_records_vectors_and_checkpoints",
          "original_agent_search_results_after_restart"]


def default_state_file():
    return importer.default_state_file().with_name("agent-message-search-acceptance.json")


def ascii_fold(value):
    return value.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"))


def message_order(row):
    return datetime.fromisoformat(row["created_at"]), row["id"]


def local_history(agent_ids):
    with importer.SessionLocal() as db:
        conversations = {row.id: ConversationResponse.model_validate(row).model_dump(mode="json")
                         for row in db.query(Conversation).filter(Conversation.agent_id.in_(agent_ids)).all()}
        messages = [MessageResponse.model_validate(row).model_dump(mode="json") for row in
                    db.query(Message).join(Conversation, Message.conversation_id == Conversation.id)
                    .filter(Conversation.agent_id.in_(agent_ids)).all()]
    return conversations, sorted(messages, key=message_order, reverse=True)


def assert_page(reply, agent_id, query, role, limit, offset, conversations, messages):
    headers = {key.lower(): value for key, value in reply["headers"].items()}
    require(headers.get("cache-control") == "no-store" and headers.get("x-content-type-options") == "nosniff",
            "Agent search must return uncached literal JSON")
    page = json.loads(reply["content"])
    expected = [row for row in messages if conversations[row["conversation_id"]]["agent_id"] == agent_id
                and ascii_fold(query) in ascii_fold(row["content"]) and (role is None or row["role"] == role)]
    selected = expected[offset:offset + limit]
    require(isinstance(page, dict) and page.get("agent_id") == agent_id and page.get("query") == query
            and page.get("role") == role and page.get("limit") == limit and page.get("offset") == offset
            and type(page.get("total")) is int and page["total"] == len(expected)
            and page.get("has_more") is (offset + len(selected) < len(expected))
            and isinstance(page.get("items"), list) and len(page["items"]) == len(selected),
            "Agent search scope, counts, or page boundaries differ from saved history")
    for item, row in zip(page["items"], selected):
        conversation = conversations[row["conversation_id"]]
        require(isinstance(item, dict) and all(item.get(key) == row[key] for key in ("id", "conversation_id", "role", "created_at"))
                and item.get("agent_id") == agent_id and item.get("conversation_title") == conversation["title"],
                "Agent search returned a foreign identity, changed title, role, or timestamp")
        snippet, start, end = (item.get(key) for key in ("snippet", "match_start", "match_end"))
        require(isinstance(snippet, str) and 0 < len(snippet) <= 240 and type(start) is int and type(end) is int
                and 0 <= start < end <= len(snippet) and ascii_fold(snippet[start:end]) == ascii_fold(query),
                "Agent search preview is oversized or its literal match is invalid")
        source_start = ascii_fold(row["content"]).find(ascii_fold(query)) - start
        require(source_start >= 0 and row["content"][source_start:source_start + len(snippet)] == snippet
                and item.get("truncated_before") is (source_start > 0)
                and item.get("truncated_after") is (source_start + len(snippet) < len(row["content"])),
                "Agent search preview changed saved text or truncation flags")
    return page


def check_agent_message_search(base_url, verify_persistence=False, state_file=None):
    path = Path(state_file) if state_file is not None else default_state_file()
    sources = {name: path.with_name(filename) for name, filename in (
        ("import", "conversation-import-acceptance.json"), ("search", "conversation-message-search-acceptance.json"),
        ("context", "conversation-message-context-acceptance.json"),
        ("context_export", "conversation-message-context-export-acceptance.json"))}
    require(path.suffix == ".json" and path not in sources.values(), "Use a separate JSON Agent search checkpoint")
    require(not verify_persistence or path.is_file(), "Agent search checkpoint is missing; verification will not recreate it")
    for name, source in sources.items():
        require(source.is_file(), f"Original {name} checkpoint is missing; finish its acceptance first")
    source_bytes = {name: source.read_bytes() for name, source in sources.items()}
    source_hashes = {name: sha256(raw).hexdigest() for name, raw in source_bytes.items()}
    imported, searched, contextual, exported = (json.loads(source_bytes[name]) for name in sources)
    kinds = ("conversation-import", "conversation-message-search", "conversation-message-context", "conversation-message-context-export")
    for value, kind in zip((imported, searched, contextual, exported), kinds):
        require(isinstance(value, dict) and value.get("kind") == kind and type(value.get("version")) is int
                and value["version"] == 1, "Original acceptance checkpoint kind or version is invalid")
    require(searched.get("source_sha256") == source_hashes["import"]
            and contextual.get("source_sha256") == {key: source_hashes[key] for key in ("import", "search")}
            and exported.get("source_sha256") == {key: source_hashes[key] for key in ("import", "search", "context")},
            "Original acceptance checkpoint chain changed")
    old_search = response_evidence(searched.get("response_sha256"), 30, "search")
    old_context = response_evidence(contextual.get("response_sha256"), 9, "context")
    old_exports = response_evidence(exported.get("attachment_sha256"), 18, "context export")
    preserved = {**old_search, **old_context, **old_exports}
    require(len(preserved) == 57 and all("/context?" in uri for uri in old_context)
            and all("/context/export?" in uri for uri in old_exports), "Original response evidence must identify 57 distinct reads")
    original = path.read_bytes() if path.exists() else None
    before, previous = database_fingerprints(), checkpoint_hashes(path)
    if original is not None:
        state = json.loads(original)
        require(isinstance(state, dict) and state.get("kind") == "agent-message-search"
                and type(state.get("version")) is int and state["version"] == 1, "Agent search checkpoint is invalid")
        require(state.get("source_sha256") == source_hashes, "Original acceptance checkpoints changed before verification")
        require(state.get("database") == before, "Saved SQLite records or vectors changed before Agent search verification")
        require(state.get("previous_checkpoints") == previous, "An earlier acceptance checkpoint was lost or changed")

    importer.validate_records(base_url, imported, imported["agent_id"], imported["other_agent_id"])
    for uri, expected_hash in preserved.items():
        reply = request_response(base_url, uri)
        require({key.lower(): value for key, value in reply["headers"].items()}.get("cache-control") == "no-store"
                and sha256(reply["content"]).hexdigest() == expected_hash, "An original search, context, detail, or export response changed")
    agent_id, other_id = imported["agent_id"], imported["other_agent_id"]
    conversations, messages = local_history((agent_id, other_id))
    matches = [row for row in messages if conversations[row["conversation_id"]]["agent_id"] == agent_id and "中文" in row["content"]]
    matching_conversations = {row["conversation_id"] for row in matches}
    require(len(matching_conversations) >= 2, "Retain original bilingual fixtures across at least two Agent conversations")
    main, saved = imported["conversation"], imported["messages"]
    require(saved[0]["id"] in {row["id"] for row in matches}, "The original unloaded message must remain searchable")
    responses = {}
    def get(uri, status=200):
        reply = request_response(base_url, uri, status)
        if status == 200:
            responses[uri] = sha256(reply["content"]).hexdigest()
        return reply
    def search(agent, query="中文", role=None, limit=10, offset=0):
        params = {"query": query, "limit": limit, "offset": offset}
        if role is not None:
            params["role"] = role
        uri = f"/agents/{agent}/messages/search?" + urlencode(params)
        return assert_page(get(uri), agent, query, role, limit, offset, conversations, messages)
    walked = [row for offset in range(0, len(matches), 10) for row in search(agent_id, offset=offset)["items"]]
    require([row["id"] for row in walked] == [row["id"] for row in matches], "Cross-conversation pages lost or duplicated saved messages")
    for query in ("TURN", "turn 01", "🐍", "%", "_", "\\", "O'Reilly", "<script>",
                  "no-match-" + imported["prefix"], main["title"]):
        search(agent_id, query, limit=50)
    for role in ("user", "assistant", "system", "tool"):
        search(agent_id, role=role, limit=50)
    for limit in (1, 5, 20, 50):
        search(agent_id, limit=limit)
    for offset in (len(matches), 9223372036854775807):
        require(search(agent_id, offset=offset)["items"] == [], "An out-of-range Agent page must be empty")
    other_page = search(other_id, limit=50)
    require(other_page["total"] >= 25 and all(row["agent_id"] == other_id for row in other_page["items"])
            and not {row["id"] for row in other_page["items"]}.intersection(row["id"] for row in matches),
            "Another Agent's matching history leaked into this Agent's results")

    other = next(row for row in reversed(matches) if row["conversation_id"] != main["id"])
    download_count = 0
    for selected in (saved[0], other):
        conversation = conversations[selected["conversation_id"]]
        chronology = sorted((row for row in messages if row["conversation_id"] == selected["conversation_id"]), key=message_order)
        index = next(index for index, row in enumerate(chronology) if row["id"] == selected["id"])
        uri = f'/conversations/{selected["conversation_id"]}/messages/{selected["id"]}'
        require(json.loads(get(uri + "?" + urlencode({"agent_id": agent_id}))["content"]) == selected,
                "A cross-conversation result did not load its complete original message")
        context = expected_context(conversation, chronology, index, 3, 3)
        require(json.loads(get(uri + "/context?" + urlencode({"agent_id": agent_id, "before": 3, "after": 3}))["content"]) == context,
                "A cross-conversation result did not load its own saved context")
        for format in ("json", "markdown"):
            assert_attachment(get(uri + "/context/export?" + urlencode({"agent_id": agent_id, "before": 3, "after": 3, "format": format})), context, format)
            download_count += 1
        for suffix in ("", "/context", "/context/export"):
            get(uri + suffix + "?" + urlencode({"agent_id": other_id}), 404)
    latest_uri = f'/conversations/{main["id"]}/messages/page?' + urlencode({"agent_id": agent_id})
    latest = json.loads(get(latest_uri)["content"])
    require(len(saved) == 25 and latest["items"] == saved[-20:] and latest["has_more"] is True
            and saved[0]["id"] not in {row["id"] for row in latest["items"]}, "Search changed the original loaded 20-message page")
    for params in ({}, {"query": ""}, {"query": "   "}, {"query": "x" * 201}, {"query": "a\x00b"},
                   {"query": "中文", "role": "USER"}, {"query": "中文", "limit": 0}, {"query": "中文", "limit": 51},
                   {"query": "中文", "limit": "1.5"}, {"query": "中文", "offset": -1},
                   {"query": "中文", "offset": 9223372036854775808}):
        get(f"/agents/{agent_id}/messages/search?" + urlencode(params), 422)
    for bad_agent in (0, -1, 9223372036854775808, "bad"):
        get(f"/agents/{bad_agent}/messages/search?query=test", 422)
    get("/agents/9223372036854775807/messages/search?query=test", 404)
    require(database_fingerprints() == before, "Agent search or validation changed SQLite records or vectors")
    require(checkpoint_hashes(path) == previous and all(sources[key].read_bytes() == raw for key, raw in source_bytes.items()),
            "Agent search changed original checkpoint files")
    if original is not None:
        require(state.get("response_sha256") == responses, "Original Agent search, detail, context, or download bytes changed after restart")
        require(path.read_bytes() == original, "Agent search checkpoint changed during verification")
    else:
        write_checkpoint(path, {"kind": "agent-message-search", "version": 1, "source_sha256": source_hashes,
                                "database": before, "previous_checkpoints": previous, "response_sha256": responses})
    return {"status": "passed", "checks_passed": len(CHECKS), "checks": CHECKS, "agent_id": agent_id,
            "original_conversation_id": main["id"], "older_message_id": saved[0]["id"], "saved_message_count": 25,
            "latest_page_count": 20, "matching_message_count": len(matches), "matching_conversation_count": len(matching_conversations),
            "other_conversation_id": other["conversation_id"], "other_message_id": other["id"], "snippet_character_limit": 240,
            "response_count": len(responses), "response_sha256": digest(responses), "download_response_count": download_count,
            "preserved_response_count": len(preserved), "preserved_context_attachment_count": len(old_exports),
            "source_checkpoint_sha256": digest(source_hashes), "persistence_verified": verify_persistence,
            "checkpoint_reused": original is not None, "read_only": True, "conversations_created": 0,
            "messages_created": 0, "chat_executions_created": 0, "original_records_and_vectors_unchanged": True,
            "previous_checkpoints_unchanged": True, "checkpoint_file": str(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://frontend")
    parser.add_argument("--verify-persistence", action="store_true")
    args = parser.parse_args()
    try:
        report = check_agent_message_search(args.base_url, args.verify_persistence)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, URLError, SQLAlchemyError) as error:
        print(json.dumps({"status": "failed", "message": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
