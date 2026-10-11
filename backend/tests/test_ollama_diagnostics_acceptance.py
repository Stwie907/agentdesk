"""Metadata acceptance reuses existing evidence without writing new checkpoints."""

import json

import pytest
import requests

from app import check_ollama_diagnostics as checker
from app import check_runtime_configuration as reads
from app.models.agent import Agent
from test_mcp_runtime_api import demo_api  # noqa: F401
from test_runtime_configuration_acceptance import configuration_acceptance  # noqa: F401
from test_ollama_diagnostics import inventory, response  # noqa: F401


def test_repeated_mock_reads_are_stable_and_preserve_original_checkpoints(configuration_acceptance):
    _, ids, _, anchor, calls = configuration_acceptance
    before, prior = reads.database_fingerprints(), reads.checkpoint_hashes(anchor)
    reports = [checker.check_ollama_diagnostics("http://frontend", ids["agent_id"], expected_provider="mock") for _ in range(2)]
    assert reports[0] == reports[1] and reports[0]["checks_passed"] == 8
    assert reports[0]["previous_checkpoint_count"] == 2 and reports[0]["model_probe_performed"] is False
    assert reports[0]["inference_performed"] is False
    assert reports[0]["conversations_created"] == reports[0]["messages_created"] == reports[0]["chat_executions_created"] == 0
    assert all(method == "GET" for method, _ in calls)
    assert reads.database_fingerprints() == before and reads.checkpoint_hashes(anchor) == prior and not anchor.exists()


def test_real_provider_expectations_use_only_two_inventory_reads(configuration_acceptance, inventory, monkeypatch):
    _, ids, _, anchor, _ = configuration_acceptance
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    result = checker.check_ollama_diagnostics("http://frontend", ids["agent_id"], expected_provider="ollama", require_installed=True)
    assert result["checks_passed"] == 8 and result["connection_status"] == "available"
    assert result["model_probe_performed"] is True and result["inference_performed"] is False
    assert len(inventory["calls"]) == 2 and not anchor.exists()


@pytest.mark.parametrize("agent", [0, -1, True, "1", 9223372036854775808])
def test_bad_ids_stop_before_database_or_http(configuration_acceptance, monkeypatch, agent):
    _, _, _, _, calls = configuration_acceptance
    monkeypatch.setattr(reads, "checkpoint_anchor", lambda: pytest.fail("No database read expected"))
    with pytest.raises(RuntimeError, match="positive saved Agent"):
        checker.check_ollama_diagnostics("http://frontend", agent)
    assert calls == []


@pytest.mark.parametrize("corruption", ["version", "scope", "inference", "probe", "missing", "private_field", "headers"])
def test_corrupt_reply_is_rejected_and_not_repaired(configuration_acceptance, monkeypatch, corruption):
    _, ids, _, anchor, _ = configuration_acceptance
    original = reads.request_configuration
    def corrupt(base_url, uri, status=200):
        reply = original(base_url, uri, status)
        if uri.startswith("/runtime/ollama") and status == 200:
            value = json.loads(reply["content"])
            if corruption == "version": value["schema_version"] = True
            if corruption == "scope": value["selected_agent_id"] = 999
            if corruption == "inference": value["inference_performed"] = True
            if corruption == "probe": value["model_probe_performed"] = True
            if corruption == "missing": value.pop("models")
            if corruption == "private_field": value["ollama_base_url"] = "private-secret-url"
            if corruption == "headers": reply["headers"]["cache-control"] = "max-age=3600"
            reply["content"] = json.dumps(value).encode()
        return reply
    monkeypatch.setattr(reads, "request_configuration", corrupt)
    before, prior = reads.database_fingerprints(), reads.checkpoint_hashes(anchor)
    with pytest.raises((RuntimeError, ValueError)):
        checker.check_ollama_diagnostics("http://frontend", ids["agent_id"])
    assert reads.database_fingerprints() == before and reads.checkpoint_hashes(anchor) == prior and not anchor.exists()


@pytest.mark.parametrize("reason", ["disconnected", "missing"])
def test_required_installation_failure_preserves_original_data(configuration_acceptance, inventory, reason):
    _, ids, _, anchor, _ = configuration_acceptance
    if reason == "disconnected": inventory["error"] = requests.ConnectionError("private-server-url")
    else: inventory["response"] = response({"models": []})
    before, prior = reads.database_fingerprints(), reads.checkpoint_hashes(anchor)
    with pytest.raises(RuntimeError, match="unavailable|missing or unconfigured"):
        checker.check_ollama_diagnostics("http://frontend", ids["agent_id"], require_installed=True)
    assert reads.database_fingerprints() == before and reads.checkpoint_hashes(anchor) == prior and not anchor.exists()


def test_concurrent_external_record_edit_is_detected_and_retained(configuration_acceptance, monkeypatch):
    _, ids, sessions, anchor, _ = configuration_acceptance
    original = reads.request_configuration
    def mutate(base_url, uri, status=200):
        reply = original(base_url, uri, status)
        if "agent_id=0" in uri:
            with sessions() as db:
                db.get(Agent, ids["agent_id"]).name = "Concurrent diagnostic edit"
                db.commit()
        return reply
    monkeypatch.setattr(reads, "request_configuration", mutate)
    prior = reads.checkpoint_hashes(anchor)
    with pytest.raises(RuntimeError, match="records or vectors changed"):
        checker.check_ollama_diagnostics("http://frontend", ids["agent_id"])
    with sessions() as db: assert db.get(Agent, ids["agent_id"]).name == "Concurrent diagnostic edit"
    assert reads.checkpoint_hashes(anchor) == prior and not anchor.exists()


def test_concurrent_checkpoint_edit_is_detected_and_retained(configuration_acceptance, monkeypatch):
    _, ids, _, anchor, _ = configuration_acceptance
    original = reads.request_configuration
    checkpoint = anchor.parent / "original-acceptance.json"
    def mutate(base_url, uri, status=200):
        reply = original(base_url, uri, status)
        if "agent_id=0" in uri: checkpoint.write_bytes(b'{"external":true}\n')
        return reply
    monkeypatch.setattr(reads, "request_configuration", mutate)
    with pytest.raises(RuntimeError, match="checkpoint changed"):
        checker.check_ollama_diagnostics("http://frontend", ids["agent_id"])
    assert checkpoint.read_bytes() == b'{"external":true}\n' and not anchor.exists()
