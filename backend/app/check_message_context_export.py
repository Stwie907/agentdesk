"""Read-only context attachment acceptance using original import/search/context evidence."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.error import URLError
from urllib.parse import urlencode

from sqlalchemy.exc import SQLAlchemyError

from app import check_conversation_import as importer
from app.check_conversation_export import checkpoint_hashes, markdown_blocks, request_export as request_response
from app.check_conversation_pagination import database_fingerprints, write_checkpoint
from app.check_demo import require
from app.check_message_search import digest


CHECKS = ["scoped_json_context_attachments", "literal_unicode_markdown_context",
          "anchor_metadata_and_download_headers", "unloaded_oldest_newest_and_middle_windows",
          "bounded_zero_and_asymmetric_windows", "agent_and_conversation_isolation", "read_only_validation",
          "original_search_context_and_export_responses", "preserved_records_vectors_and_checkpoints",
          "original_context_attachment_bytes_after_restart"]


def default_state_file():
    return importer.default_state_file().with_name("conversation-message-context-export-acceptance.json")


def expected_context(conversation, messages, index, before, after):
    return {"conversation_id": conversation["id"], "agent_id": conversation["agent_id"],
            "anchor_message_id": messages[index]["id"], "before": before, "after": after,
            "anchor_index": min(index, before), "has_more_before": index > before,
            "has_more_after": len(messages) - index - 1 > after,
            "items": messages[max(0, index - before):index + after + 1]}


def assert_attachment(reply, context, format):
    headers = {key.lower(): value for key, value in reply["headers"].items()}
    extension, mime = ("json", "application/json") if format == "json" else ("md", "text/markdown")
    filename = f'conversation-{context["conversation_id"]}-message-{context["anchor_message_id"]}-context.{extension}'
    require(headers.get("content-disposition") == f'attachment; filename="{filename}"'
            and headers.get("content-type", "").split(";")[0].strip() == mime
            and headers.get("cache-control") == "no-store" and headers.get("x-content-type-options") == "nosniff"
            and headers.get("x-conversation-id") == str(context["conversation_id"])
            and headers.get("x-agent-id") == str(context["agent_id"])
            and headers.get("x-anchor-message-id") == str(context["anchor_message_id"])
            and headers.get("x-message-count") == str(len(context["items"]))
            and headers.get("x-context-export-kind") == "agentdesk.message_context"
            and headers.get("x-context-export-schema-version") == "1", "Context attachment headers or identity are invalid")
    require(0 < len(reply["content"]) <= 10 * 1024 * 1024, "Context attachment is empty or oversized")
    text = reply["content"].decode("utf-8")
    if format == "json":
        value = json.loads(text)
        require(isinstance(value, dict) and type(value.get("schema_version")) is int
                and type(value.get("message_count")) is int
                and value == {"export_kind": "agentdesk.message_context", "schema_version": 1,
                              "message_count": len(context["items"]), "context": context},
                "Context JSON changed scope, boundaries, roles, literal text, or timestamps")
    else:
        prefix = ("# Saved message context\n\n"
                  "This is a saved-message excerpt. Import conversation requires a full conversation JSON backup.\n\n"
                  "- Export kind: agentdesk.message_context\n- Export schema: 1\n"
                  f'- Conversation ID: {context["conversation_id"]}\n- Agent ID: {context["agent_id"]}\n'
                  f'- Selected message ID: {context["anchor_message_id"]}\n'
                  f'- Requested earlier messages: {context["before"]}\n- Requested later messages: {context["after"]}\n'
                  f'- Selected message index: {context["anchor_index"]}\n'
                  f'- Earlier saved messages outside excerpt: {str(context["has_more_before"]).lower()}\n'
                  f'- Later saved messages outside excerpt: {str(context["has_more_after"]).lower()}\n'
                  f'- Saved messages: {len(context["items"])}\n')
        require(text.startswith(prefix), "Context Markdown metadata or selected-message index differs")
        blocks = []
        for row in context["items"]:
            label = "Selected message" if row["id"] == context["anchor_message_id"] else "Saved message"
            require(f'\n## {label} {row["id"]}\n' in text and f'Created at: {row["created_at"]}\n' in text,
                    "Context Markdown lost a selected marker, message identity, or timestamp")
            blocks.extend((row["role"], row["content"]))
        require(markdown_blocks(text) == blocks, "Context Markdown changed literal roles, text, whitespace, or order")


def response_evidence(value, count, label):
    require(isinstance(value, dict) and len(value) == count
            and all(isinstance(uri, str) and uri.startswith("/conversations/")
                    and isinstance(checksum, str) and re.fullmatch(r"[0-9a-f]{64}", checksum)
                    for uri, checksum in value.items()), f"Original {label} response evidence is invalid")
    return value


def check_message_context_export(base_url, verify_persistence=False, state_file=None):
    path = Path(state_file) if state_file is not None else default_state_file()
    sources = {name: path.with_name(filename) for name, filename in (
        ("import", "conversation-import-acceptance.json"), ("search", "conversation-message-search-acceptance.json"),
        ("context", "conversation-message-context-acceptance.json"))}
    require(path.suffix == ".json" and path not in sources.values(), "Use a separate JSON context-export checkpoint")
    require(not verify_persistence or path.is_file(), "Context-export checkpoint is missing; verification will not recreate it")
    for name, source_path in sources.items():
        require(source_path.is_file(), f"Original conversation {name} checkpoint is missing; finish its acceptance first")
    source_bytes = {name: source_path.read_bytes() for name, source_path in sources.items()}
    source_hashes = {name: sha256(raw).hexdigest() for name, raw in source_bytes.items()}
    imported, searched, contextual = (json.loads(source_bytes[name]) for name in ("import", "search", "context"))
    for value, kind in ((imported, "conversation-import"), (searched, "conversation-message-search"),
                        (contextual, "conversation-message-context")):
        require(isinstance(value, dict) and value.get("kind") == kind and type(value.get("version")) is int
                and value["version"] == 1, "Original import/search/context checkpoint is invalid")
    require(searched.get("source_sha256") == source_hashes["import"]
            and contextual.get("source_sha256") == {name: source_hashes[name] for name in ("import", "search")},
            "Original import/search/context evidence no longer agrees")
    saved_search = response_evidence(searched.get("response_sha256"), 30, "search")
    saved_context = response_evidence(contextual.get("response_sha256"), 9, "context")
    require(all("/context?" in uri for uri in saved_context) and not set(saved_search).intersection(saved_context),
            "Original context response evidence does not identify distinct context reads")
    saved_responses = {**saved_search, **saved_context}
    original = path.read_bytes() if path.exists() else None
    before_db, previous = database_fingerprints(), checkpoint_hashes(path)
    if original is not None:
        state = json.loads(original)
        require(isinstance(state, dict) and state.get("kind") == "conversation-message-context-export"
                and type(state.get("version")) is int and state["version"] == 1, "Context-export checkpoint is invalid")
        require(state.get("source_sha256") == source_hashes, "Original import, search, or context checkpoint changed")
        require(state.get("database") == before_db, "Saved SQLite records or vectors changed before context-export verification")
        require(state.get("previous_checkpoints") == previous, "An earlier acceptance checkpoint was lost or changed")

    # Reuse source fixture identities and their actual old response bytes. Older
    # global snapshots can predate unrelated normal activity before this milestone.
    importer.validate_records(base_url, imported, imported["agent_id"], imported["other_agent_id"])
    for uri, expected_hash in saved_responses.items():
        reply = request_response(base_url, uri)
        headers = {key.lower(): value for key, value in reply["headers"].items()}
        require(headers.get("cache-control") == "no-store" and sha256(reply["content"]).hexdigest() == expected_hash,
                "An original search, context, full-message, or conversation-export response changed")

    main, foreign, empty = (imported[name] for name in ("conversation", "foreign", "empty"))
    messages = imported["messages"]
    latest_uri = f'/conversations/{main["id"]}/messages/page?agent_id={main["agent_id"]}'
    latest = importer.request_json(base_url, latest_uri)
    require(len(messages) == 25 and latest["items"] == messages[-20:] and latest["has_more"] is True
            and messages[0]["id"] not in {row["id"] for row in latest["items"]},
            "Original history must retain 25 messages and an unloaded older anchor beyond the loaded 20")
    attachments = {}
    windows = [(main, messages, index, before, after) for index, before, after in
               [(0, 3, 3), (24, 3, 3), (12, 3, 3), (12, 10, 10), (12, 0, 0), (0, 10, 0), (24, 0, 10), (12, 1, 5)]]
    windows.append((foreign, imported["foreign_messages"], 0, 3, 3))
    for row, saved, index, before, after in windows:
        context = expected_context(row, saved, index, before, after)
        for format in ("json", "markdown"):
            params = {"agent_id": row["agent_id"], "before": before, "after": after, "format": format}
            uri = f'/conversations/{row["id"]}/messages/{saved[index]["id"]}/context/export?' + urlencode(params)
            reply = request_response(base_url, uri)
            assert_attachment(reply, context, format)
            attachments[uri] = sha256(reply["content"]).hexdigest()
    require("<script>" in messages[0]["content"] and messages[-1]["content"].endswith("  \n")
            and {row["role"] for row in messages[9:16]} == {"user", "assistant"},
            "Original context fixtures must retain literal script text, trailing spaces, and multiple roles")
    invalid_scopes = [(main, messages[0]["id"], foreign["agent_id"]),
                      (foreign, imported["foreign_messages"][0]["id"], main["agent_id"]),
                      (main, imported["foreign_messages"][0]["id"], main["agent_id"]),
                      (empty, messages[0]["id"], empty["agent_id"]),
                      (main, 9223372036854775807, main["agent_id"])]
    for row, anchor, agent in invalid_scopes:
        for format in ("json", "markdown"):
            request_response(base_url, f'/conversations/{row["id"]}/messages/{anchor}/context/export?' +
                             urlencode({"agent_id": agent, "format": format}), 404)
    for params in [{}, {"agent_id": 0}, {"agent_id": 9223372036854775808}, {"before": -1}, {"before": 11},
                   {"before": "1.5"}, {"after": -1}, {"after": 11}, {"after": "bad"},
                   {"format": "html"}, {"format": "md"}, {"format": "JSON"}]:
        actual = {"agent_id": main["agent_id"], **params} if params else {}
        request_response(base_url, f'/conversations/{main["id"]}/messages/{messages[0]["id"]}/context/export?' + urlencode(actual), 422)
    require(importer.request_json(base_url, latest_uri) == latest, "Context exports changed the loaded-history response")
    require(database_fingerprints() == before_db, "Context-export or validation probes changed SQLite records or vectors")
    require(checkpoint_hashes(path) == previous and all(sources[name].read_bytes() == raw for name, raw in source_bytes.items()),
            "Context exports changed earlier acceptance files")
    if original is not None:
        require(state.get("attachment_sha256") == attachments, "Original context attachment bytes changed after restart")
        require(path.read_bytes() == original, "Context-export checkpoint changed during verification")
    else:
        write_checkpoint(path, {"kind": "conversation-message-context-export", "version": 1, "source_sha256": source_hashes,
                                "database": before_db, "previous_checkpoints": previous, "attachment_sha256": attachments})
    return {"status": "passed", "checks_passed": len(CHECKS), "checks": CHECKS, "agent_id": main["agent_id"],
            "conversation_id": main["id"], "foreign_conversation_id": foreign["id"], "older_message_id": messages[0]["id"],
            "saved_message_count": len(messages), "latest_page_count": len(latest["items"]),
            "older_context_message_count": 4, "newest_context_message_count": 4, "middle_context_message_count": 7,
            "maximum_context_message_count": 21, "exported_window_count": len(windows),
            "attachment_response_count": len(attachments), "json_attachment_count": len(windows),
            "markdown_attachment_count": len(windows), "preserved_response_count": len(saved_responses),
            "preserved_context_response_count": len(saved_context), "attachment_sha256": digest(attachments),
            "source_checkpoint_sha256": digest(source_hashes), "persistence_verified": verify_persistence,
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
        result = check_message_context_export(args.base_url, args.verify_persistence, args.state_file)
    except (RuntimeError, AssertionError, KeyError, IndexError, TypeError, ValueError, OSError, URLError, SQLAlchemyError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1) from error
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
