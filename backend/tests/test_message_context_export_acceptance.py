"""Context attachment acceptance retains all earlier evidence and never repairs it."""

import json

import pytest

from app import check_message_context as context_checker
from app import check_message_context_export as checker
from app.models.message import Message
from test_conversation_import_acceptance import acceptance  # noqa: F401
from test_message_context_acceptance import context_acceptance  # noqa: F401
from test_message_search_acceptance import search_acceptance  # noqa: F401
from test_mcp_runtime_api import demo_api  # noqa: F401


@pytest.fixture
def export_acceptance(context_acceptance, monkeypatch):
    client, ids, sessions, imported, searched, contextual, calls = context_acceptance
    context_checker.check_message_context("http://frontend", state_file=contextual)
    calls.clear()
    def request(base_url, uri, status=200):
        calls.append(("GET", uri))
        response = client.get(uri)
        assert response.status_code == status, response.text
        return {"status": response.status_code, "headers": dict(response.headers), "content": response.content}
    monkeypatch.setattr(checker, "request_response", request)
    return client, ids, sessions, imported, searched, contextual, contextual.with_name("conversation-message-context-export-acceptance.json"), calls


def test_initial_reuse_restart_preserve_every_record_source_and_attachment(export_acceptance):
    _, _, _, imported, searched, contextual, path, calls = export_acceptance
    before = checker.database_fingerprints()
    sources = [source.read_bytes() for source in (imported, searched, contextual)]
    first = checker.check_message_context_export("http://frontend", state_file=path)
    original = path.read_bytes()
    assert first["checks_passed"] == 10 and first["saved_message_count"] == 25 and first["latest_page_count"] == 20
    assert [first[name] for name in ("older_context_message_count", "newest_context_message_count",
                                   "middle_context_message_count", "maximum_context_message_count")] == [4, 4, 7, 21]
    assert first["attachment_response_count"] == 18 and first["exported_window_count"] == 9
    assert first["json_attachment_count"] == first["markdown_attachment_count"] == 9
    assert first["preserved_response_count"] == 39 and first["preserved_context_response_count"] == 9
    for verify in (False, True):
        reused = checker.check_message_context_export("http://frontend", verify, path)
        assert reused["checkpoint_reused"] is True and reused["persistence_verified"] is verify
        assert reused["attachment_sha256"] == first["attachment_sha256"]
        assert reused["source_checkpoint_sha256"] == first["source_checkpoint_sha256"]
        assert reused["older_message_id"] == first["older_message_id"]
    assert all(method == "GET" for method, _ in calls)
    assert first["conversations_created"] == first["messages_created"] == first["chat_executions_created"] == 0
    assert path.read_bytes() == original and checker.database_fingerprints() == before
    assert [source.read_bytes() for source in (imported, searched, contextual)] == sources


@pytest.mark.parametrize("missing", ["import", "search", "context", "verification"])
def test_missing_evidence_stops_before_http_and_never_recreates_any_data(export_acceptance, missing):
    _, _, _, imported, searched, contextual, path, calls = export_acceptance
    source = {"import": imported, "search": searched, "context": contextual}.get(missing)
    if source is not None: source.unlink()
    before = checker.database_fingerprints()
    with pytest.raises(RuntimeError, match="checkpoint is missing"):
        checker.check_message_context_export("http://frontend", missing == "verification", path)
    assert calls == [] and not path.exists() and checker.database_fingerprints() == before
    if source is not None: assert not source.exists()


def test_unrelated_activity_before_first_export_check_becomes_the_new_baseline(export_acceptance):
    client, ids, _, imported, searched, contextual, path, calls = export_acceptance
    sources = [source.read_bytes() for source in (imported, searched, contextual)]
    assert client.post("/conversations", json={"agent_id": ids["agent_id"], "title": "Activity before context export"}).status_code in (200, 201)
    before = checker.database_fingerprints(); calls.clear()
    checker.check_message_context_export("http://frontend", state_file=path)
    checker.check_message_context_export("http://frontend", True, path)
    assert checker.database_fingerprints() == before and all(method == "GET" for method, _ in calls)
    assert [source.read_bytes() for source in (imported, searched, contextual)] == sources


@pytest.mark.parametrize("change", ["import", "search", "context", "record", "database", "attachment", "kind", "previous_missing", "previous_changed"])
def test_changed_evidence_fails_without_repair_or_replacement(export_acceptance, change):
    _, _, sessions, imported, searched, contextual, path, calls = export_acceptance
    prior = path.with_name("original-acceptance.json"); prior.write_bytes(b'{"original":true}\n')
    first = checker.check_message_context_export("http://frontend", state_file=path)
    state = json.loads(path.read_bytes())
    source = {"import": imported, "search": searched, "context": contextual}.get(change)
    if source is not None: source.write_bytes(source.read_bytes() + b" ")
    if change == "record":
        with sessions() as db:
            db.get(Message, first["older_message_id"]).content = "Changed text"; db.commit()
    if change == "database": state["database"]["messages"]["sha256"] = "changed"
    if change == "attachment": state["attachment_sha256"] = {}
    if change == "kind": state["kind"] = "conversation-message-context"
    if change in ("database", "attachment", "kind"): path.write_text(json.dumps(state))
    if change == "previous_missing": prior.unlink()
    if change == "previous_changed": prior.write_bytes(b'{"changed":true}\n')
    original, before = path.read_bytes(), checker.database_fingerprints(); calls.clear()
    with pytest.raises(RuntimeError): checker.check_message_context_export("http://frontend", True, path)
    assert path.read_bytes() == original and checker.database_fingerprints() == before
    assert all(method == "GET" for method, _ in calls)


@pytest.mark.parametrize("change", ["headers", "json", "markdown", "prior_response"])
def test_invalid_attachments_or_changed_old_responses_do_not_save_evidence(export_acceptance, monkeypatch, change):
    _, _, _, imported, searched, contextual, path, _ = export_acceptance
    request = checker.request_response
    def corrupt(base_url, uri, status=200):
        result = request(base_url, uri, status)
        if status == 200 and "/context/export?" in uri:
            if change == "headers": result["headers"]["x-anchor-message-id"] = "999999"
            if change == "json" and "format=json" in uri:
                body = json.loads(result["content"]); body["context"]["items"].reverse(); result["content"] = json.dumps(body).encode()
            if change == "markdown" and "format=markdown" in uri: result["content"] += b'```text\nUnexpected extra text\n```\n'
        if status == 200 and change == "prior_response" and "/context?" in uri: result["content"] += b" "
        return result
    monkeypatch.setattr(checker, "request_response", corrupt)
    before, original = checker.database_fingerprints(), [source.read_bytes() for source in (imported, searched, contextual)]
    with pytest.raises(RuntimeError): checker.check_message_context_export("http://frontend", state_file=path)
    assert not path.exists() and checker.database_fingerprints() == before
    assert [source.read_bytes() for source in (imported, searched, contextual)] == original


@pytest.mark.parametrize("name", ["conversation-import-acceptance.json", "conversation-message-search-acceptance.json", "conversation-message-context-acceptance.json"])
def test_export_checkpoint_cannot_replace_a_source_checkpoint(export_acceptance, name):
    _, _, _, _, _, _, path, calls = export_acceptance
    source = path.with_name(name); original = source.read_bytes()
    with pytest.raises(RuntimeError, match="separate JSON"):
        checker.check_message_context_export("http://frontend", state_file=source)
    assert calls == [] and source.read_bytes() == original
