"""Agent search checks reuse prior IDs and never regenerate missing evidence."""

import json

import pytest

from app import check_agent_message_search as checker
from app import check_message_context_export as export_checker
from app.models.conversation import Conversation
from app.models.message import Message
from test_conversation_import_acceptance import acceptance  # noqa: F401
from test_message_context_acceptance import context_acceptance  # noqa: F401
from test_message_context_export_acceptance import export_acceptance  # noqa: F401
from test_message_search_acceptance import search_acceptance  # noqa: F401
from test_mcp_runtime_api import demo_api  # noqa: F401


@pytest.fixture
def agent_search_acceptance(export_acceptance, monkeypatch):
    client, ids, sessions, imported, searched, contextual, exported, calls = export_acceptance
    export_checker.check_message_context_export("http://frontend", state_file=exported)
    # Earlier milestones may precede unrelated activity. This saved sibling is
    # setup, not a checker write; the new checker must preserve all old evidence.
    sibling = client.post("/conversations", json={"agent_id": ids["agent_id"], "title": "Earlier sibling — 中文"}).json()
    assert client.post(f'/conversations/{sibling["id"]}/messages',
                       json={"role": "tool", "content": 'Saved sibling turn 01 — 中文 🐍\n<script>literal</script>\n'}).status_code == 200
    calls.clear()
    def request(base_url, uri, status=200):
        calls.append(("GET", uri))
        response = client.get(uri)
        assert response.status_code == status, response.text
        return {"status": response.status_code, "headers": dict(response.headers), "content": response.content}
    monkeypatch.setattr(checker, "request_response", request)
    return client, ids, sessions, [imported, searched, contextual, exported], exported.with_name("agent-message-search-acceptance.json"), calls


def test_initial_reuse_restart_preserve_all_records_original_responses_and_checkpoint_bytes(agent_search_acceptance):
    _, _, _, sources, path, calls = agent_search_acceptance
    before, raw = checker.database_fingerprints(), [source.read_bytes() for source in sources]
    first = checker.check_agent_message_search("http://frontend", state_file=path)
    original = path.read_bytes()
    assert first["checks_passed"] == 10 and first["matching_message_count"] == 26 and first["matching_conversation_count"] == 2
    assert first["saved_message_count"] == 25 and first["latest_page_count"] == 20
    assert first["preserved_response_count"] == 57 and first["preserved_context_attachment_count"] == 18
    assert first["download_response_count"] == 4 and first["original_conversation_id"] != first["other_conversation_id"]
    assert first["conversations_created"] == first["messages_created"] == first["chat_executions_created"] == 0
    for verify in (False, True):
        reused = checker.check_agent_message_search("http://frontend", verify, path)
        assert reused["response_sha256"] == first["response_sha256"]
        assert reused["source_checkpoint_sha256"] == first["source_checkpoint_sha256"]
        assert reused["checkpoint_reused"] is True and reused["persistence_verified"] is verify
    assert all(method == "GET" for method, _ in calls)
    assert checker.database_fingerprints() == before and path.read_bytes() == original
    assert [source.read_bytes() for source in sources] == raw


@pytest.mark.parametrize("missing", ["import", "search", "context", "context_export", "verification"])
def test_missing_evidence_stops_before_http_and_never_repairs_it(agent_search_acceptance, missing):
    _, _, _, sources, path, calls = agent_search_acceptance
    source = dict(zip(("import", "search", "context", "context_export"), sources)).get(missing)
    if source is not None:
        source.unlink()
    before = checker.database_fingerprints()
    with pytest.raises(RuntimeError, match="checkpoint is missing"):
        checker.check_agent_message_search("http://frontend", missing == "verification", path)
    assert calls == [] and not path.exists() and checker.database_fingerprints() == before
    if source is not None:
        assert not source.exists()


@pytest.mark.parametrize("change", ["import", "search", "context", "context_export", "record", "title",
                                   "database", "responses", "kind", "previous_missing", "previous_changed"])
def test_changed_sources_records_or_evidence_fail_without_replacement(agent_search_acceptance, change):
    _, _, sessions, sources, path, calls = agent_search_acceptance
    prior = path.with_name("original-acceptance.json"); prior.write_bytes(b'{"original":true}\n')
    first = checker.check_agent_message_search("http://frontend", state_file=path)
    state = json.loads(path.read_bytes())
    source = dict(zip(("import", "search", "context", "context_export"), sources)).get(change)
    if source is not None:
        source.write_bytes(source.read_bytes() + b" ")
    if change in ("record", "title"):
        with sessions() as db:
            if change == "record": db.get(Message, first["older_message_id"]).content = "Changed text"
            else: db.get(Conversation, first["original_conversation_id"]).title = "Changed title"
            db.commit()
    if change == "database": state["database"]["messages"]["sha256"] = "changed"
    if change == "responses": state["response_sha256"] = {}
    if change == "kind": state["kind"] = "conversation-message-search"
    if change in ("database", "responses", "kind"): path.write_text(json.dumps(state))
    if change == "previous_missing": prior.unlink()
    if change == "previous_changed": prior.write_bytes(b'{"changed":true}\n')
    original, before = path.read_bytes(), checker.database_fingerprints(); calls.clear()
    with pytest.raises(RuntimeError):
        checker.check_agent_message_search("http://frontend", True, path)
    assert path.read_bytes() == original and checker.database_fingerprints() == before
    assert all(method == "GET" for method, _ in calls)


@pytest.mark.parametrize("change", ["scope", "item_scope", "title", "order", "snippet", "count", "old_response", "attachment"])
def test_invalid_global_pages_or_changed_original_bytes_do_not_save_evidence(agent_search_acceptance, monkeypatch, change):
    _, _, _, sources, path, _ = agent_search_acceptance
    request = checker.request_response
    def corrupt(base_url, uri, status=200):
        reply = request(base_url, uri, status)
        if status == 200 and uri.startswith("/agents/"):
            value = json.loads(reply["content"])
            if change == "scope": value["agent_id"] += 1
            if change == "count": value["total"] += 1
            if value["items"]:
                if change == "item_scope": value["items"][0]["agent_id"] += 1
                if change == "title": value["items"][0]["conversation_title"] = "Wrong title"
                if change == "order": value["items"].reverse()
                if change == "snippet": value["items"][0]["snippet"] = "x" * 241
            reply["content"] = json.dumps(value, ensure_ascii=False).encode()
        if change == "old_response" and status == 200 and "/context?" in uri: reply["content"] += b" "
        if change == "attachment" and status == 200 and "/context/export?" in uri: reply["content"] += b" "
        return reply
    monkeypatch.setattr(checker, "request_response", corrupt)
    before, originals = checker.database_fingerprints(), [source.read_bytes() for source in sources]
    with pytest.raises(RuntimeError):
        checker.check_agent_message_search("http://frontend", state_file=path)
    assert not path.exists() and checker.database_fingerprints() == before
    assert [source.read_bytes() for source in sources] == originals


@pytest.mark.parametrize("index", range(4))
def test_new_checkpoint_cannot_replace_any_source(agent_search_acceptance, index):
    _, _, _, sources, _, calls = agent_search_acceptance
    source = sources[index]; original = source.read_bytes()
    with pytest.raises(RuntimeError, match="separate JSON"):
        checker.check_agent_message_search("http://frontend", state_file=source)
    assert calls == [] and source.read_bytes() == original
