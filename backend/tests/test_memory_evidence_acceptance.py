"""Restart acceptance must read the saved executions and fail before writes."""

import json
from urllib.error import HTTPError

import pytest

from app import check_memory_evidence as acceptance
from app.models.execution_log import ExecutionLog
from app.models.execution_snapshot import ExecutionSnapshot
from app.models.memory import Memory
from test_mcp_runtime_api import demo_api  # noqa: F401
from test_memory_evidence import chat, database_rows
from test_semantic_memory import save, shared
from test_user_memory import add_agent


@pytest.fixture
def evidence_acceptance(demo_api, monkeypatch, tmp_path):
    client, ids, sessions = demo_api
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    private = save(client, ids["agent_id"], acceptance.semantic.PRIVATE)
    common = shared(client, ids["agent_id"], ids["user_id"], acceptance.semantic.SHARED)
    outsider, owner = add_agent(sessions)
    isolated = shared(client, outsider, owner, acceptance.semantic.PRIVATE)
    result = chat(client, ids["agent_id"], acceptance.semantic.QUERY)
    execution_id = result["execution_id"]
    source = {"version": 1, "agent_id": ids["agent_id"], "peer_agent_id": ids["mcp_agent_id"],
              "user_id": ids["user_id"], "isolation_agent_id": outsider, "isolation_user_id": owner,
              "private": private, "shared": common, "isolated": isolated, "execution_id": execution_id,
              "inspection": {suffix: client.get(f"/executions/{execution_id}" + suffix).json()
                             for suffix in ("", "/trace", "/snapshot")}}
    source_file = tmp_path / "semantic-memory-acceptance.json"
    source_file.write_text(json.dumps(source), encoding="utf-8")
    state_file = tmp_path / "memory-evidence-acceptance.json"
    writes = []
    def read(base, path, payload=None):
        if payload is not None: writes.append(path)
        response = client.get(path) if payload is None else client.post(path, json=payload)
        if response.status_code != 200: raise HTTPError(path, response.status_code, response.text, {}, None)
        return response.json()
    def request(base, path, payload=None, *, method=None, status=200):
        require_response = client.request(method or ("POST" if payload is not None else "GET"), path, json=payload)
        assert require_response.status_code == status, require_response.text
        return require_response.json()
    monkeypatch.setattr(acceptance, "request_json", read)
    monkeypatch.setattr(acceptance, "memory_request", request)
    monkeypatch.setattr(acceptance.semantic, "request_json", read)
    monkeypatch.setattr("app.check_user_memory.request_json", read)
    return client, ids, sessions, source_file, state_file, writes, source


def test_initial_check_captures_three_executions_and_restart_only_reads(evidence_acceptance):
    _, _, sessions, source_file, state_file, writes, _ = evidence_acceptance
    source_bytes = source_file.read_bytes()
    first = acceptance.check_memory_evidence("http://demo", False, state_file, source_file)
    assert first["checks_passed"] == 6 and first["chat_executions_created"] == len(writes) == 3
    checkpoint = state_file.read_bytes()
    before = database_rows(sessions)
    writes.clear()
    repeated = acceptance.check_memory_evidence("http://demo", True, state_file, source_file)
    assert repeated["persistence_verified"] is True and repeated["checkpoint_reused"] is True
    assert repeated["execution_ids"] == first["execution_ids"] and repeated["chat_executions_created"] == 0
    assert not writes and database_rows(sessions) == before
    assert state_file.read_bytes() == checkpoint and source_file.read_bytes() == source_bytes


@pytest.mark.parametrize("loss", ["checkpoint", "checkpoint_json", "checkpoint_version", "source_checkpoint", "source_memory",
                                 "source_snapshot", "evidence", "evidence_json", "snapshot", "trace"])
def test_missing_or_changed_evidence_fails_without_replacing_it(evidence_acceptance, loss):
    _, _, sessions, source_file, state_file, writes, source = evidence_acceptance
    acceptance.check_memory_evidence("http://demo", False, state_file, source_file)
    state = json.loads(state_file.read_text())
    saved_id = state["cases"]["semantic"]["execution_id"]
    if loss == "checkpoint": state_file.unlink()
    if loss == "checkpoint_json": state_file.write_text("{invalid")
    if loss == "checkpoint_version":
        state["version"] = 99; state_file.write_text(json.dumps(state))
    if loss == "source_checkpoint": source_file.unlink()
    with sessions() as db:
        if loss == "source_memory": db.delete(db.get(Memory, source["private"]["id"]))
        if loss in ("snapshot", "source_snapshot"):
            chosen = source["execution_id"] if loss == "source_snapshot" else saved_id
            db.query(ExecutionSnapshot).filter_by(execution_id=chosen).delete()
        if loss in ("evidence", "evidence_json"):
            log = db.query(ExecutionLog).filter(ExecutionLog.execution_id == saved_id,
                ExecutionLog.message.like("memory_retrieval_details:%")).one()
            if loss == "evidence": db.delete(log)
            else: log.message = "memory_retrieval_details: {invalid"
        if loss == "trace":
            log = db.query(ExecutionLog).filter(ExecutionLog.execution_id == saved_id,
                ExecutionLog.message.like("plan_started:%")).one()
            log.message += " changed"
        db.commit()
    before = database_rows(sessions)
    writes.clear()
    with pytest.raises((RuntimeError, ValueError, HTTPError)):
        acceptance.check_memory_evidence("http://demo", True, state_file, source_file)
    assert not writes and database_rows(sessions) == before


def test_missing_initial_semantic_fixtures_never_create_replacements(evidence_acceptance):
    _, _, sessions, source_file, state_file, writes, source = evidence_acceptance
    with sessions() as db:
        db.delete(db.get(Memory, source["private"]["id"])); db.commit()
    before = database_rows(sessions)
    with pytest.raises(RuntimeError, match="lost or changed"):
        acceptance.check_memory_evidence("http://demo", False, state_file, source_file)
    assert not writes and not state_file.exists() and database_rows(sessions) == before
