"""Configuration acceptance never creates or replaces saved evidence."""

import json
import sys

import pytest

from app import check_runtime_configuration as checker
from app import check_conversation_pagination as paginator
from app.models.agent import Agent
from test_mcp_runtime_api import demo_api  # noqa: F401


@pytest.fixture
def configuration_acceptance(demo_api, monkeypatch, tmp_path):
    client, ids, sessions = demo_api
    anchor = tmp_path / ".runtime-configuration-read-anchor"
    (tmp_path / "original-acceptance.json").write_bytes(b'{"original":true}\n')
    (tmp_path / "agent-message-search-acceptance.json").write_bytes(b'{"retained":true}\n')
    monkeypatch.setattr(checker, "checkpoint_anchor", lambda: anchor)
    monkeypatch.setattr(checker, "SessionLocal", sessions)
    monkeypatch.setattr(paginator, "SessionLocal", sessions)
    calls = []
    def request(base_url, uri, status=200):
        calls.append(("GET", uri))
        response = client.get(uri)
        assert response.status_code == status, response.text
        return {"status": response.status_code, "headers": dict(response.headers), "content": response.content}
    monkeypatch.setattr(checker, "request_configuration", request)
    return client, ids, sessions, anchor, calls


def test_initial_and_repeated_reads_preserve_all_rows_vectors_and_original_checkpoint_bytes(configuration_acceptance):
    _, ids, _, anchor, calls = configuration_acceptance
    before, prior = checker.database_fingerprints(), checker.checkpoint_hashes(anchor)
    reports = [checker.check_runtime_configuration("http://frontend", ids["agent_id"],
        expected_provider="mock", expected_chat_model="qwen2.5:7b", expected_planner_model="qwen2.5:7b",
        expected_memory_mode="keyword", expected_vector_cache=True) for _ in range(2)]
    assert reports[0] == reports[1] and reports[0]["checks_passed"] == 8
    assert reports[0]["previous_checkpoint_count"] == 2 and reports[0]["model_probe_performed"] is False
    assert reports[0]["conversations_created"] == reports[0]["messages_created"] == reports[0]["chat_executions_created"] == 0
    assert all(method == "GET" for method, _ in calls)
    assert checker.database_fingerprints() == before and checker.checkpoint_hashes(anchor) == prior
    assert not anchor.exists()


@pytest.mark.parametrize("agent", [0, -1, True, "1", 9223372036854775808])
def test_invalid_id_stops_before_database_or_http(configuration_acceptance, monkeypatch, agent):
    _, _, _, _, calls = configuration_acceptance
    monkeypatch.setattr(checker, "checkpoint_anchor", lambda: pytest.fail("Invalid ID must stop before database reads"))
    with pytest.raises(RuntimeError, match="positive saved Agent"):
        checker.check_runtime_configuration("http://frontend", agent)
    assert calls == []


def test_missing_agent_is_not_created_and_stops_before_http(configuration_acceptance):
    _, _, _, anchor, calls = configuration_acceptance
    before, prior = checker.database_fingerprints(), checker.checkpoint_hashes(anchor)
    with pytest.raises(RuntimeError, match="Selected Agent is missing"):
        checker.check_runtime_configuration("http://frontend", 9223372036854775807)
    assert calls == [] and not anchor.exists()
    assert checker.database_fingerprints() == before and checker.checkpoint_hashes(anchor) == prior


@pytest.mark.parametrize("expected", [
    {"expected_provider": "ollama"}, {"expected_chat_model": "wrong-model"},
    {"expected_planner_model": "wrong-planner"}, {"expected_memory_mode": "semantic"},
    {"expected_vector_cache": False},
])
def test_configuration_mismatch_fails_without_repairing_settings_or_data(configuration_acceptance, expected):
    _, ids, _, anchor, calls = configuration_acceptance
    before, prior = checker.database_fingerprints(), checker.checkpoint_hashes(anchor)
    with pytest.raises(RuntimeError, match="does not match the expected"):
        checker.check_runtime_configuration("http://frontend", ids["agent_id"], **expected)
    assert all(method == "GET" for method, _ in calls)
    assert checker.database_fingerprints() == before and checker.checkpoint_hashes(anchor) == prior and not anchor.exists()


@pytest.mark.parametrize("corruption", ["version", "scope", "activity", "probe", "missing", "private_field", "headers"])
def test_invalid_contract_or_proxy_response_does_not_save_new_evidence(configuration_acceptance, monkeypatch, corruption):
    _, ids, _, anchor, _ = configuration_acceptance
    original = checker.request_configuration
    def corrupt(base_url, uri, status=200):
        reply = original(base_url, uri, status)
        if status == 200:
            value = json.loads(reply["content"])
            if corruption == "version": value["schema_version"] = True
            if corruption == "scope" and value["selected_agent"]: value["selected_agent"]["id"] += 1
            if corruption == "activity": value["memory"]["vector_cache_active"] = True
            if corruption == "probe": value["model_probe_performed"] = True
            if corruption == "missing": value.pop("read_only")
            if corruption == "private_field": value["ollama_base_url"] = "private-secret-url"
            if corruption == "headers": reply["headers"]["cache-control"] = "max-age=3600"
            reply["content"] = json.dumps(value).encode()
        return reply
    monkeypatch.setattr(checker, "request_configuration", corrupt)
    before, prior = checker.database_fingerprints(), checker.checkpoint_hashes(anchor)
    with pytest.raises((RuntimeError, ValueError)):
        checker.check_runtime_configuration("http://frontend", ids["agent_id"])
    assert checker.database_fingerprints() == before and checker.checkpoint_hashes(anchor) == prior and not anchor.exists()


def test_concurrent_record_change_is_reported_and_not_repaired(configuration_acceptance, monkeypatch):
    _, ids, sessions, anchor, _ = configuration_acceptance
    original = checker.request_configuration
    def mutate(base_url, uri, status=200):
        reply = original(base_url, uri, status)
        if "agent_id=0" in uri:
            with sessions() as db:
                db.get(Agent, ids["agent_id"]).name = "Concurrent external edit"
                db.commit()
        return reply
    monkeypatch.setattr(checker, "request_configuration", mutate)
    prior = checker.checkpoint_hashes(anchor)
    with pytest.raises(RuntimeError, match="records or vectors changed"):
        checker.check_runtime_configuration("http://frontend", ids["agent_id"])
    with sessions() as db:
        assert db.get(Agent, ids["agent_id"]).name == "Concurrent external edit"
    assert checker.checkpoint_hashes(anchor) == prior and not anchor.exists()


@pytest.mark.parametrize("change", ["changed", "removed", "added"])
def test_checkpoint_changes_fail_without_replacing_any_evidence(configuration_acceptance, monkeypatch, change):
    _, ids, _, anchor, _ = configuration_acceptance
    original = checker.request_configuration
    path = anchor.with_name("original-acceptance.json")
    def mutate(base_url, uri, status=200):
        reply = original(base_url, uri, status)
        if "agent_id=0" in uri:
            if change == "changed": path.write_bytes(b'{"external":true}\n')
            if change == "removed": path.unlink()
            if change == "added": anchor.with_name("external-acceptance.json").write_bytes(b'{}')
        return reply
    monkeypatch.setattr(checker, "request_configuration", mutate)
    with pytest.raises(RuntimeError, match="checkpoint changed"):
        checker.check_runtime_configuration("http://frontend", ids["agent_id"])
    assert not anchor.exists()
    if change == "changed": assert path.read_bytes() == b'{"external":true}\n'
    if change == "removed": assert not path.exists()
    if change == "added": assert anchor.with_name("external-acceptance.json").read_bytes() == b'{}'


def test_cli_failure_redacts_validation_details_and_returns_nonzero(configuration_acceptance, monkeypatch, capsys):
    _, ids, _, _, _ = configuration_acceptance
    monkeypatch.setattr(sys, "argv", ["check_runtime_configuration", "--agent-id", str(ids["agent_id"])])
    monkeypatch.setattr(checker, "check_runtime_configuration", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("private-connection-password")))
    assert checker.main() == 1
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "failed" and "private" not in value["error"]
