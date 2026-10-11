"""Read-only message context acceptance using original import/search evidence."""

import argparse
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
from app.check_message_search import digest


CHECKS = ["older_unloaded_message_context", "chronological_neighbours_and_anchor",
          "bounded_symmetric_and_asymmetric_windows", "zero_sided_and_history_boundaries",
          "complete_literal_text_and_all_roles", "agent_and_conversation_isolation", "read_only_validation",
          "original_search_exports_and_saved_data", "original_context_results_after_restart"]


def default_state_file():
    return importer.default_state_file().with_name("conversation-message-context-acceptance.json")


def assert_context(value, conversation, messages, index, before, after):
    expected = {"conversation_id": conversation["id"], "agent_id": conversation["agent_id"],
                "anchor_message_id": messages[index]["id"], "before": before, "after": after,
                "anchor_index": min(index, before), "has_more_before": index > before,
                "has_more_after": len(messages) - index - 1 > after,
                "items": messages[max(0, index - before):index + after + 1]}
    require(value == expected, "Context identity, neighbours, literal text, or boundaries differ")


def check_message_context(base_url, verify_persistence=False, state_file=None):
    path = Path(state_file) if state_file is not None else default_state_file()
    sources = {"import": path.with_name("conversation-import-acceptance.json"),
               "search": path.with_name("conversation-message-search-acceptance.json")}
    require(path.suffix == ".json" and path not in sources.values(), "Use a separate JSON context checkpoint")
    require(not verify_persistence or path.is_file(), "Message context checkpoint is missing; verification will not recreate it")
    for name, source_path in sources.items():
        require(source_path.is_file(), f"Original conversation {name} checkpoint is missing; finish its acceptance first")
    source_bytes = {name: source_path.read_bytes() for name, source_path in sources.items()}
    source_hashes = {name: sha256(raw).hexdigest() for name, raw in source_bytes.items()}
    imported, searched = json.loads(source_bytes["import"]), json.loads(source_bytes["search"])
    for value, kind in ((imported, "conversation-import"), (searched, "conversation-message-search")):
        require(isinstance(value, dict) and value.get("kind") == kind and type(value.get("version")) is int
                and value["version"] == 1, "Original import or search checkpoint is invalid")
    require(searched.get("source_sha256") == source_hashes["import"], "Original import/search evidence no longer agrees")
    saved_responses = searched.get("response_sha256")
    require(isinstance(saved_responses, dict) and len(saved_responses) == 30
            and all(isinstance(uri, str) and uri.startswith("/conversations/") and isinstance(value, str) and len(value) == 64
                    for uri, value in saved_responses.items()), "Original search response evidence is invalid")
    original = path.read_bytes() if path.exists() else None
    before_db, previous = database_fingerprints(), checkpoint_hashes(path)
    if original is not None:
        state = json.loads(original)
        require(isinstance(state, dict) and state.get("kind") == "conversation-message-context" and type(state.get("version")) is int
                and state["version"] == 1, "Message context checkpoint is invalid")
        require(state.get("source_sha256") == source_hashes, "Original import or search checkpoint changed")
        require(state.get("database") == before_db, "Saved SQLite records or vectors changed before context verification")
        require(state.get("previous_checkpoints") == previous, "An earlier acceptance checkpoint was lost or changed")

    # Validate original fixture IDs/text, while allowing unrelated normal activity
    # before this milestone establishes its own complete SQLite baseline.
    importer.validate_records(base_url, imported, imported["agent_id"], imported["other_agent_id"])
    for uri, expected_hash in saved_responses.items():
        response = request_response(base_url, uri)
        headers = {key.lower(): value for key, value in response["headers"].items()}
        require(headers.get("cache-control") == "no-store" and sha256(response["content"]).hexdigest() == expected_hash,
                "An original search, full-message, or export response changed")

    responses = {}
    def read(uri, status=200):
        response = request_response(base_url, uri, status)
        if status != 200: return None
        headers = {key.lower(): value for key, value in response["headers"].items()}
        require(headers.get("cache-control") == "no-store" and headers.get("x-content-type-options") == "nosniff",
                "Message context must disable caching and preserve literal text")
        responses[uri] = sha256(response["content"]).hexdigest()
        return json.loads(response["content"])
    def window(row, messages, index, before=3, after=3):
        params = {"agent_id": row["agent_id"], "before": before, "after": after}
        uri = f'/conversations/{row["id"]}/messages/{messages[index]["id"]}/context?' + urlencode(params)
        result = read(uri)
        assert_context(result, row, messages, index, before, after)
        return result

    main, foreign, empty = (imported[name] for name in ("conversation", "foreign", "empty"))
    messages = imported["messages"]
    latest = importer.request_json(base_url, f'/conversations/{main["id"]}/messages/page?agent_id={main["agent_id"]}')
    require(len(messages) == 25 and latest["items"] == messages[-20:] and latest["has_more"] is True,
            "Original history must retain 25 messages with only 20 currently loaded")
    require(messages[0]["id"] not in {row["id"] for row in latest["items"]}, "The context anchor must use an unloaded older message")
    oldest, newest, middle = window(main, messages, 0), window(main, messages, 24), window(main, messages, 12)
    maximum = window(main, messages, 12, 10, 10)
    window(main, messages, 12, 0, 0)
    window(main, messages, 0, 10, 0)
    window(main, messages, 24, 0, 10)
    window(main, messages, 12, 1, 5)
    window(foreign, imported["foreign_messages"], 0)
    require(len(maximum["items"]) == 21 and {row["role"] for row in middle["items"]} == {"user", "assistant"},
            "Context must include other roles and honour its 21-message bound")
    require(oldest["items"][0]["content"] == messages[0]["content"] and "<script>" in messages[0]["content"]
            and newest["items"][-1]["content"] == messages[-1]["content"], "Full context must retain original literal text and whitespace")

    invalid_scopes = [(main, messages[0]["id"], foreign["agent_id"]),
                      (foreign, imported["foreign_messages"][0]["id"], main["agent_id"]),
                      (main, imported["foreign_messages"][0]["id"], main["agent_id"]),
                      (empty, messages[0]["id"], empty["agent_id"]),
                      (main, 9223372036854775807, main["agent_id"])]
    for row, anchor, agent in invalid_scopes:
        read(f'/conversations/{row["id"]}/messages/{anchor}/context?agent_id={agent}', 404)
    invalid = [{}, {"agent_id": 0}, {"agent_id": 9223372036854775808},
               {"before": -1}, {"before": 11}, {"before": "bad"}, {"before": "1.5"},
               {"after": -1}, {"after": 11}, {"after": "bad"}, {"after": "1.5"}]
    for params in invalid:
        params = {"agent_id": main["agent_id"], **params} if params else {}
        read(f'/conversations/{main["id"]}/messages/{messages[0]["id"]}/context?' + urlencode(params), 422)
    require(importer.request_json(base_url, f'/conversations/{main["id"]}/messages/page?agent_id={main["agent_id"]}') == latest,
            "Reading context changed the loaded-history response")
    require(database_fingerprints() == before_db, "Context/validation probes changed saved SQLite records or vectors")
    require(checkpoint_hashes(path) == previous and all(sources[name].read_bytes() == raw for name, raw in source_bytes.items()),
            "Context probes changed earlier acceptance files")
    if original is not None:
        require(state.get("response_sha256") == responses, "Original message context responses changed after restart")
        require(path.read_bytes() == original, "Message context checkpoint changed during verification")
    else:
        write_checkpoint(path, {"kind": "conversation-message-context", "version": 1, "source_sha256": source_hashes,
                                "database": before_db, "previous_checkpoints": previous, "response_sha256": responses})
    return {"status": "passed", "checks_passed": len(CHECKS), "checks": CHECKS, "agent_id": main["agent_id"],
            "conversation_id": main["id"], "foreign_conversation_id": foreign["id"], "older_message_id": messages[0]["id"],
            "saved_message_count": len(messages), "latest_page_count": len(latest["items"]),
            "older_context_message_count": len(oldest["items"]), "newest_context_message_count": len(newest["items"]),
            "middle_context_message_count": len(middle["items"]), "maximum_context_message_count": len(maximum["items"]),
            "context_response_count": len(responses), "preserved_response_count": len(saved_responses),
            "response_sha256": digest(responses), "source_checkpoint_sha256": digest(source_hashes),
            "persistence_verified": verify_persistence, "checkpoint_reused": original is not None, "read_only": True,
            "conversations_created": 0, "messages_created": 0, "chat_executions_created": 0,
            "original_records_and_vectors_unchanged": True, "previous_checkpoints_unchanged": True, "checkpoint_file": str(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--state-file")
    parser.add_argument("--verify-persistence", action="store_true")
    args = parser.parse_args()
    try:
        result = check_message_context(args.base_url, args.verify_persistence, args.state_file)
    except (RuntimeError, AssertionError, KeyError, IndexError, TypeError, ValueError, OSError, URLError, SQLAlchemyError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1) from error
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
