"""Context acceptance is GET-only and retains the earlier search evidence."""

import json

import pytest

from app import check_message_context as checker
from app import check_message_search as search_checker
from app.models.message import Message
from test_conversation_import_acceptance import acceptance  # noqa: F401
from test_mcp_runtime_api import demo_api  # noqa: F401
from test_message_search_acceptance import search_acceptance  # noqa: F401


@pytest.fixture
def context_acceptance(search_acceptance, monkeypatch):
    client, ids, sessions, imported, searched, calls = search_acceptance
    search_checker.check_message_search("http://frontend", state_file=searched)
    calls.clear()
    def request(base_url, uri, status=200):
        calls.append(("GET", uri))
        response = client.get(uri)
        assert response.status_code == status, response.text
        return {"status": response.status_code, "headers": dict(response.headers), "content": response.content}
    monkeypatch.setattr(checker, "request_response", request)
    return client, ids, sessions, imported, searched, searched.with_name("conversation-message-context-acceptance.json"), calls


def test_initial_reuse_and_restart_preserve_every_record_and_original_response(context_acceptance):
    _, _, _, imported, searched, path, calls = context_acceptance
    before = checker.database_fingerprints()
    source_bytes = [imported.read_bytes(), searched.read_bytes()]
    first = checker.check_message_context("http://frontend", state_file=path)
    original = path.read_bytes()
    assert first["checks_passed"] == 9 and first["saved_message_count"] == 25 and first["latest_page_count"] == 20
    assert first["older_context_message_count"] == first["newest_context_message_count"] == 4
    assert first["middle_context_message_count"] == 7 and first["maximum_context_message_count"] == 21
    assert first["context_response_count"] == 9 and first["preserved_response_count"] == 30
    for verify in (False, True):
        reused = checker.check_message_context("http://frontend", verify, path)
        assert reused["checkpoint_reused"] is True and reused["persistence_verified"] is verify
        assert reused["response_sha256"] == first["response_sha256"] and reused["older_message_id"] == first["older_message_id"]
    assert all(method == "GET" for method, _ in calls)
    assert first["conversations_created"] == first["messages_created"] == first["chat_executions_created"] == 0
    assert checker.database_fingerprints() == before and path.read_bytes() == original
    assert [imported.read_bytes(), searched.read_bytes()] == source_bytes


@pytest.mark.parametrize("missing", ["import", "search", "verification"])
def test_missing_evidence_fails_before_http_and_never_recreates_data(context_acceptance, missing):
    _, _, _, imported, searched, path, calls = context_acceptance
    if missing == "import": imported.unlink()
    if missing == "search": searched.unlink()
    before = checker.database_fingerprints()
    with pytest.raises(RuntimeError, match="checkpoint is missing"):
        checker.check_message_context("http://frontend", missing == "verification", path)
    assert calls == [] and not path.exists() and checker.database_fingerprints() == before


def test_unrelated_activity_before_initial_acceptance_becomes_the_new_read_only_baseline(context_acceptance):
    client, ids, _, _, searched, path, calls = context_acceptance
    original_search = searched.read_bytes()
    response = client.post("/conversations", json={"agent_id": ids["agent_id"], "title": "Normal activity before context"})
    assert response.status_code in (200, 201)
    before = checker.database_fingerprints()
    calls.clear()
    checker.check_message_context("http://frontend", state_file=path)
    checker.check_message_context("http://frontend", True, path)
    assert checker.database_fingerprints() == before and searched.read_bytes() == original_search
    assert all(method == "GET" for method, _ in calls)


@pytest.mark.parametrize("change", ["import", "search", "record", "database", "response", "kind", "previous_missing", "previous_changed"])
def test_changed_evidence_is_rejected_without_repair(context_acceptance, change):
    _, _, sessions, imported, searched, path, calls = context_acceptance
    earlier = path.with_name("original-acceptance.json")
    earlier.write_bytes(b'{"original":true}\n')
    first = checker.check_message_context("http://frontend", state_file=path)
    state = json.loads(path.read_bytes())
    if change == "import": imported.write_bytes(imported.read_bytes() + b" ")
    if change == "search": searched.write_bytes(searched.read_bytes() + b" ")
    if change == "record":
        with sessions() as db:
            db.get(Message, first["older_message_id"]).content = "Changed text"
            db.commit()
    if change == "database": state["database"]["messages"]["sha256"] = "changed"
    if change == "response": state["response_sha256"] = {}
    if change == "kind": state["kind"] = "conversation-message-search"
    if change in ("database", "response", "kind"): path.write_text(json.dumps(state))
    if change == "previous_missing": earlier.unlink()
    if change == "previous_changed": earlier.write_bytes(b'{"changed":true}\n')
    original, before = path.read_bytes(), checker.database_fingerprints()
    calls.clear()
    with pytest.raises(RuntimeError): checker.check_message_context("http://frontend", True, path)
    assert path.read_bytes() == original and checker.database_fingerprints() == before
    assert all(method == "GET" for method, _ in calls)


def test_invalid_context_stops_before_saving_evidence(context_acceptance, monkeypatch):
    _, _, _, imported, searched, path, _ = context_acceptance
    request = checker.request_response
    def corrupt(base_url, uri, status=200):
        result = request(base_url, uri, status)
        if status == 200 and "/context?" in uri:
            body = json.loads(result["content"])
            body["items"].reverse()
            result["content"] = json.dumps(body).encode()
        return result
    monkeypatch.setattr(checker, "request_response", corrupt)
    before, original = checker.database_fingerprints(), [imported.read_bytes(), searched.read_bytes()]
    with pytest.raises(RuntimeError, match="Context"):
        checker.check_message_context("http://frontend", state_file=path)
    assert not path.exists() and checker.database_fingerprints() == before
    assert [imported.read_bytes(), searched.read_bytes()] == original


@pytest.mark.parametrize("name", ["conversation-import-acceptance.json", "conversation-message-search-acceptance.json"])
def test_context_checkpoint_cannot_replace_earlier_evidence(context_acceptance, name):
    _, _, _, _, _, path, calls = context_acceptance
    source = path.with_name(name)
    before = source.read_bytes()
    with pytest.raises(RuntimeError, match="separate JSON"):
        checker.check_message_context("http://frontend", state_file=source)
    assert calls == [] and source.read_bytes() == before
