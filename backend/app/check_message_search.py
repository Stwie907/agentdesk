"""Read-only full-history message search using the retained JSON import fixtures."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode

from sqlalchemy.exc import SQLAlchemyError

from app import check_conversation_import as importer
from app.check_conversation_export import checkpoint_hashes, export_path, request_export as request_response
from app.check_conversation_pagination import database_fingerprints, write_checkpoint
from app.check_demo import require


CHECKS = ["complete_history_beyond_loaded_page", "literal_unicode_and_ascii_case", "role_filters",
          "bounded_previews_and_full_messages", "pages_and_timestamp_id_order", "agent_and_conversation_isolation",
          "read_only_validation", "preserved_records_vectors_and_checkpoints", "original_search_results_after_restart"]
ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def default_state_file():
    return importer.default_state_file().with_name("conversation-message-search-acceptance.json")


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def assert_page(page, conversation, query, role, limit, offset, messages):
    normalized = query.strip()
    expected = [row for row in reversed(messages) if normalized.translate(ASCII_LOWER) in row["content"].translate(ASCII_LOWER)
                and (role is None or row["role"] == role)]
    require(isinstance(page, dict) and page.get("conversation_id") == conversation["id"]
            and page.get("agent_id") == conversation["agent_id"] and page.get("query") == normalized
            and page.get("role") == role and page.get("limit") == limit and page.get("offset") == offset
            and type(page.get("total")) is int and page["total"] == len(expected) and isinstance(page.get("items"), list),
            "Search metadata, destination scope, or complete-history count differs")
    selected = expected[offset:offset + limit]
    require(len(page["items"]) == len(selected) and page.get("has_more") is (offset + len(selected) < len(expected)),
            "Search page boundaries differ")
    for item, source in zip(page["items"], selected):
        require(isinstance(item, dict) and all(item.get(key) == source[key] for key in ("id", "conversation_id", "role", "created_at")),
                "Search result identities, timestamp/ID order, or roles differ")
        snippet = item.get("snippet")
        start, end = item.get("match_start"), item.get("match_end")
        require(isinstance(snippet, str) and 0 < len(snippet) <= 240 and type(start) is int and type(end) is int
                and 0 <= start < end <= len(snippet) and snippet[start:end].translate(ASCII_LOWER) == normalized.translate(ASCII_LOWER),
                "Search preview exceeds its bound or has invalid Unicode match positions")
        position = source["content"].translate(ASCII_LOWER).find(normalized.translate(ASCII_LOWER)) - start
        require(position >= 0 and source["content"][position:position + len(snippet)] == snippet
                and item.get("truncated_before") is (position > 0)
                and item.get("truncated_after") is (position + len(snippet) < len(source["content"])),
                "Search previews changed saved text or truncation metadata")


def check_message_search(base_url, verify_persistence=False, state_file=None):
    path = Path(state_file) if state_file is not None else default_state_file()
    source_path = path.with_name("conversation-import-acceptance.json")
    require(path.suffix == ".json" and path != source_path, "Use a separate JSON search checkpoint")
    require(not verify_persistence or path.is_file(), "Message search checkpoint is missing; verification will not recreate it")
    require(source_path.is_file(), "Conversation import checkpoint is missing; finish its initial/restart acceptance first")
    source_bytes = source_path.read_bytes()
    source = json.loads(source_bytes)
    require(isinstance(source, dict) and source.get("kind") == "conversation-import" and type(source.get("version")) is int
            and source["version"] == 1, "Original conversation import checkpoint is invalid")
    original = path.read_bytes() if path.exists() else None
    before, previous = database_fingerprints(), checkpoint_hashes(path)
    if original is not None:
        state = json.loads(original)
        require(isinstance(state, dict) and state.get("kind") == "conversation-message-search" and type(state.get("version")) is int
                and state["version"] == 1, "Message search checkpoint is invalid")
        require(state.get("source_sha256") == sha256(source_bytes).hexdigest(), "Original import evidence changed")
        require(state.get("database") == before, "Saved SQLite records or vectors changed before search verification")
        require(state.get("previous_checkpoints") == previous, "An earlier acceptance checkpoint was lost or changed")

    # Validate retained IDs and literal source text, without using the older
    # checker's global snapshot (normal activity may precede this new milestone).
    importer.validate_records(base_url, source, source["agent_id"], source["other_agent_id"])
    responses = {}
    def read(uri, status=200, json_body=True):
        reply = request_response(base_url, uri, status)
        if status != 200:
            return None
        headers = {key.lower(): value for key, value in reply["headers"].items()}
        require(headers.get("cache-control") == "no-store", "Search/message evidence must disable response caching")
        responses[uri] = sha256(reply["content"]).hexdigest()
        return json.loads(reply["content"]) if json_body else reply["content"]
    def page(row, messages, query="中文备份", role=None, limit=10, offset=0):
        params = {"agent_id": row["agent_id"], "query": query, "limit": limit, "offset": offset}
        if role is not None: params["role"] = role
        result = read(f'/conversations/{row["id"]}/messages/search?' + urlencode(params))
        assert_page(result, row, query, role, limit, offset, messages)
        return result

    main, foreign, empty = (source[name] for name in ("conversation", "foreign", "empty"))
    messages = source["messages"]
    latest = importer.request_json(base_url, f'/conversations/{main["id"]}/messages/page?agent_id={main["agent_id"]}')
    require(latest["items"] == messages[-20:] and latest["has_more"] is True, "The retained 25-message fixture must extend beyond its loaded page")
    pages = [page(main, messages, offset=offset) for offset in (0, 10, 20)]
    require([row["id"] for result in pages for row in result["items"]] == [row["id"] for row in reversed(messages)],
            "Search pages lost or duplicated older saved messages")
    page(main, messages, offset=25)
    page(main, messages, limit=1)
    page(main, messages, limit=50)
    for query in ("  中文备份  ", "TURN", "🐍", "turn 01", "<script>", "%", "_", "\\", "no-such-message"):
        page(main, messages, query)
    counts = {role: page(main, messages, role=role, limit=50)["total"] for role in ("user", "assistant", "system", "tool")}
    require(counts == {"user": 13, "assistant": 12, "system": 0, "tool": 0}, "Retained role-filter counts differ")
    page(empty, [])
    page(foreign, source["foreign_messages"])
    for row, expected in ((main, messages[0]), (main, messages[-1]), (foreign, source["foreign_messages"][0])):
        actual = read(f'/conversations/{row["id"]}/messages/{expected["id"]}?agent_id={row["agent_id"]}')
        require(actual == expected, "Full message details changed literal text, timestamps, or source identity")
    require(messages[0]["id"] not in {row["id"] for row in latest["items"]}, "The full-message probe must use an unloaded older message")
    exports = {}
    for name in ("conversation", "empty", "foreign"):
        for format in ("json", "markdown"):
            row = source[name]
            uri = export_path(row["id"], row["agent_id"], format)
            read(uri, json_body=format == "json")
            exports[name + "." + format] = responses[uri]
    require(exports == source.get("export_sha256"), "Original imported JSON/Markdown export bytes changed")

    for row, wrong_agent in ((main, foreign["agent_id"]), (foreign, main["agent_id"])):
        read(f'/conversations/{row["id"]}/messages/search?' + urlencode({"agent_id": wrong_agent, "query": "中文"}), 404)
    for row, message_id, agent in ((main, source["foreign_messages"][0]["id"], main["agent_id"]),
                                    (empty, messages[0]["id"], empty["agent_id"]),
                                    (main, messages[0]["id"], foreign["agent_id"]), (main, 9223372036854775807, main["agent_id"])):
        read(f'/conversations/{row["id"]}/messages/{message_id}?agent_id={agent}', 404)
    invalid = [{}, {"query": " "}, {"query": "x" * 201}, {"query": "中文", "role": "all"},
               {"query": "中文", "limit": 0}, {"query": "中文", "limit": 51}, {"query": "中文", "offset": -1},
               {"query": "中文", "agent_id": 0}]
    for params in invalid:
        read(f'/conversations/{main["id"]}/messages/search?' + urlencode({"agent_id": main["agent_id"], **params}), 422)
    require(database_fingerprints() == before, "Search/detail/validation probes changed SQLite records or vectors")
    require(checkpoint_hashes(path) == previous and source_path.read_bytes() == source_bytes,
            "Search probes changed earlier acceptance files")
    if original is not None:
        require(state.get("response_sha256") == responses, "Original search, message-detail, or export responses changed after restart")
        require(path.read_bytes() == original, "Search checkpoint changed during verification")
    else:
        write_checkpoint(path, {"kind": "conversation-message-search", "version": 1, "source_sha256": sha256(source_bytes).hexdigest(),
                                "database": before, "previous_checkpoints": previous, "response_sha256": responses})
    return {"status": "passed", "checks_passed": len(CHECKS), "checks": CHECKS, "agent_id": main["agent_id"],
            "conversation_id": main["id"], "foreign_conversation_id": foreign["id"], "older_message_id": messages[0]["id"],
            "saved_message_count": len(messages), "latest_page_count": len(latest["items"]), "matching_message_count": pages[0]["total"],
            "role_counts": counts, "snippet_character_limit": 240, "response_count": len(responses), "response_sha256": digest(responses),
            "source_checkpoint_sha256": sha256(source_bytes).hexdigest(), "persistence_verified": verify_persistence,
            "checkpoint_reused": original is not None, "read_only": True, "conversations_created": 0,
            "messages_created": 0, "chat_executions_created": 0, "original_records_and_vectors_unchanged": True,
            "previous_checkpoints_unchanged": True, "checkpoint_file": str(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--state-file")
    parser.add_argument("--verify-persistence", action="store_true")
    args = parser.parse_args()
    try:
        result = check_message_search(args.base_url, args.verify_persistence, args.state_file)
    except (RuntimeError, AssertionError, KeyError, TypeError, ValueError, OSError, URLError, SQLAlchemyError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1) from error
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
