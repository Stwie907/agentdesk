"""The search milestone uses retained imported IDs and never creates DB fixtures."""

import json

import pytest

from app import check_conversation_import as importer
from app import check_message_search as checker
from app.models.message import Message
from test_conversation_import_acceptance import acceptance  # noqa: F401
from test_mcp_runtime_api import demo_api  # noqa: F401


@pytest.fixture
def search_acceptance(acceptance, monkeypatch):
    client, ids, sessions, source, calls = acceptance
    importer.check_conversation_import("http://frontend", state_file=source)
    calls.clear()
    def response(base_url, uri, status=200):
        calls.append(("GET", uri))
        result = client.get(uri)
        assert result.status_code == status, result.text
        return {"status": result.status_code, "headers": dict(result.headers), "content": result.content}
    monkeypatch.setattr(checker, "request_response", response)
    return client, ids, sessions, source, source.with_name("conversation-message-search-acceptance.json"), calls


def test_initial_and_restart_are_read_only_with_unchanged_source_and_response_hashes(search_acceptance):
    _, _, _, source, path, calls = search_acceptance
    before, original_source = checker.database_fingerprints(), source.read_bytes()
    initial = checker.check_message_search("http://frontend", state_file=path)
    original = path.read_bytes()
    assert initial["checks_passed"] == 9 and initial["saved_message_count"] == initial["matching_message_count"] == 25
    assert initial["latest_page_count"] == 20 and initial["role_counts"]["user"] == 13 and initial["role_counts"]["assistant"] == 12
    for verify in (False, True):
        reused = checker.check_message_search("http://frontend", verify, path)
        assert reused["persistence_verified"] is verify and reused["checkpoint_reused"] is True
        assert reused["response_sha256"] == initial["response_sha256"] and reused["older_message_id"] == initial["older_message_id"]
    assert all(method == "GET" for method, _ in calls)
    assert initial["read_only"] is True and initial["conversations_created"] == initial["messages_created"] == initial["chat_executions_created"] == 0
    assert checker.database_fingerprints() == before and path.read_bytes() == original and source.read_bytes() == original_source


@pytest.mark.parametrize("missing", ["source", "verification"])
def test_missing_evidence_fails_before_http_and_never_recreates_records(search_acceptance, missing):
    _, _, _, source, path, calls = search_acceptance
    if missing == "source": source.unlink()
    before = checker.database_fingerprints()
    with pytest.raises(RuntimeError, match="checkpoint is missing"):
        checker.check_message_search("http://frontend", missing == "verification", path)
    assert calls == [] and not path.exists() and checker.database_fingerprints() == before


@pytest.mark.parametrize("change", ["source", "message", "database", "response", "kind", "previous_missing", "previous_changed"])
def test_changed_evidence_fails_without_repair(search_acceptance, change):
    _, _, sessions, source, path, calls = search_acceptance
    earlier = source.with_name("conversation-export-acceptance.json")
    earlier.write_bytes(b'{"original":true}\n')
    initial = checker.check_message_search("http://frontend", state_file=path)
    state = json.loads(path.read_bytes())
    if change == "source": source.write_bytes(source.read_bytes() + b" ")
    if change == "message":
        with sessions() as db:
            db.get(Message, initial["older_message_id"]).content = "Changed text"
            db.commit()
    if change == "database": state["database"]["messages"]["sha256"] = "changed"
    if change == "response": state["response_sha256"] = {}
    if change == "kind": state["kind"] = "conversation-import"
    if change in ("database", "response", "kind"): path.write_text(json.dumps(state))
    if change == "previous_missing": earlier.unlink()
    if change == "previous_changed": earlier.write_bytes(b'{"changed":true}\n')
    before, original = checker.database_fingerprints(), path.read_bytes()
    calls.clear()
    with pytest.raises(RuntimeError): checker.check_message_search("http://frontend", True, path)
    assert checker.database_fingerprints() == before and path.read_bytes() == original
    assert all(method == "GET" for method, _ in calls)


def test_invalid_preview_or_missing_route_does_not_save_a_checkpoint(search_acceptance, monkeypatch):
    _, _, _, source, path, _ = search_acceptance
    before, original_source = checker.database_fingerprints(), source.read_bytes()
    request = checker.request_response
    def corrupt(base, uri, status=200):
        result = request(base, uri, status)
        if status == 200 and "/messages/search?" in uri:
            body = json.loads(result["content"])
            if body["items"]:
                body["items"][0]["snippet"] += "x" * 241
                result["content"] = json.dumps(body).encode()
        return result
    monkeypatch.setattr(checker, "request_response", corrupt)
    with pytest.raises(RuntimeError, match="preview"): checker.check_message_search("http://frontend", state_file=path)
    assert not path.exists() and source.read_bytes() == original_source and checker.database_fingerprints() == before


def test_search_checkpoint_cannot_overwrite_the_import_checkpoint(search_acceptance):
    _, _, _, source, _, calls = search_acceptance
    original = source.read_bytes()
    with pytest.raises(RuntimeError, match="separate JSON"): checker.check_message_search("http://frontend", state_file=source)
    assert source.read_bytes() == original and calls == []
