"""Memory editing preserves identity and rejects stale or conflicting writes."""

import pytest

from app.models.memory import Memory
from app.services.memory_service import MemoryEditConflict, save_agent_memory, update_agent_memory
from app.workers import execution_worker
from test_mcp_runtime_api import demo_api  # noqa: F401


def save(client, agent_id, content):
    response = client.post("/memories", json={"agent_id": agent_id, "content": content})
    assert response.status_code == 200
    return response.json()


def edit(client, memory, content, **changes):
    return client.patch(f'/memories/item/{memory["id"]}?agent_id={memory["agent_id"]}',
                        json={"content": content, "expected_content": memory["content"], **changes})


def test_edit_preserves_identity_other_records_transcript_and_inspection(demo_api):
    client, ids, _ = demo_api
    agent = ids["agent_id"]
    memory = save(client, agent, "Python original.")
    protected = save(client, agent, "Keep this record.")
    other = save(client, ids["mcp_agent_id"], "Python other Agent.")
    conversation = client.post("/conversations", json={"agent_id": agent, "title": "Keep transcript"}).json()
    chat = client.post(f'/conversations/{conversation["id"]}/chat', json={"message": "Hello"}).json()
    transcript = client.get(f'/conversations/{conversation["id"]}/messages').json()
    execution = f'/executions/{chat["execution_id"]}'
    inspection = {suffix: client.get(execution + suffix).json() for suffix in ("", "/trace", "/snapshot")}
    history = client.get(f"/executions?agent_id={agent}").json()
    response = edit(client, memory, "  Rust updated. \n")
    assert response.status_code == 200
    assert response.json() == {**memory, "content": "Rust updated."}
    assert client.get(f"/memories/{agent}").json() == [response.json(), protected]
    assert client.get(f'/memories/{other["agent_id"]}').json() == [other]
    assert client.get(f'/conversations/{conversation["id"]}').json() == conversation
    assert client.get(f'/conversations/{conversation["id"]}/messages').json() == transcript
    assert client.get(f"/executions?agent_id={agent}").json() == history
    assert {suffix: client.get(execution + suffix).json() for suffix in inspection} == inspection


def test_preview_and_runtime_receive_edited_content(demo_api, monkeypatch):
    client, ids, _ = demo_api
    memory = save(client, ids["agent_id"], "Python original.")
    assert edit(client, memory, "Rust updated.").status_code == 200
    assert client.get(f'/memories/{memory["agent_id"]}/search', params={"query": "Python"}).json()["results"] == []
    preview = client.get(f'/memories/{memory["agent_id"]}/search', params={"query": "Rust"}).json()
    assert preview["results"][0]["memory"] == {**memory, "content": "Rust updated."}
    captured = []
    original = execution_worker.run_agent
    def run(*args, **kwargs):
        captured.append(args[2])
        return original(*args, **kwargs)
    monkeypatch.setattr(execution_worker, "run_agent", run)
    assert client.post(f'/agents/{memory["agent_id"]}/chat', json={"message": "What about Rust?"}).status_code == 200
    assert captured == ["Rust updated."]


@pytest.mark.parametrize("payload", [
    {}, {"content": "New"}, {"expected_content": "Old"},
    {"content": "", "expected_content": "Old"},
    {"content": " \n\t", "expected_content": "Old"},
    {"content": "x" * 2001, "expected_content": "Old"},
    {"content": None, "expected_content": "Old"},
    {"content": 123, "expected_content": "Old"},
    {"content": "New", "expected_content": None},
    {"content": "New", "expected_content": 123},
    {"content": "New", "expected_content": "Old", "agent_id": 7},
    {"content": "New", "expected_content": "Old", "created_at": "changed"},
])
def test_invalid_payload_never_changes_saved_memory(demo_api, payload):
    client, ids, _ = demo_api
    memory = save(client, ids["agent_id"], "Old")
    response = client.patch(f'/memories/item/{memory["id"]}?agent_id={memory["agent_id"]}', json=payload)
    assert response.status_code == 422
    assert client.get(f'/memories/{memory["agent_id"]}').json() == [memory]


@pytest.mark.parametrize("suffix", ["", "?agent_id=0", "?agent_id=-1", "?agent_id=bad"])
def test_edit_requires_positive_agent_scope(demo_api, suffix):
    client, ids, _ = demo_api
    memory = save(client, ids["agent_id"], "Old")
    assert client.patch(f'/memories/item/{memory["id"]}' + suffix,
                        json={"content": "New", "expected_content": "Old"}).status_code == 422
    assert client.get(f'/memories/{memory["agent_id"]}').json() == [memory]


def test_wrong_agent_and_missing_memory_return_404(demo_api):
    client, ids, _ = demo_api
    memory = save(client, ids["agent_id"], "Old")
    payload = {"content": "New", "expected_content": "Old"}
    assert client.patch(f'/memories/item/{memory["id"]}?agent_id={ids["mcp_agent_id"]}', json=payload).status_code == 404
    assert client.patch(f'/memories/item/100000?agent_id={ids["agent_id"]}', json=payload).status_code == 404
    assert client.patch(f'/memories/item/0?agent_id={ids["agent_id"]}', json=payload).status_code == 422
    assert client.get(f'/memories/{memory["agent_id"]}').json() == [memory]


def test_duplicate_is_conflict_but_other_agents_do_not_block_edit(demo_api):
    client, ids, _ = demo_api
    memory = save(client, ids["agent_id"], "Old")
    duplicate = save(client, ids["agent_id"], "New")
    assert edit(client, memory, "  New  ").status_code == 409
    assert client.get(f'/memories/{memory["agent_id"]}').json() == [memory, duplicate]
    save(client, ids["mcp_agent_id"], "Other content")
    assert edit(client, memory, "Other content").status_code == 200


def test_name_policy_and_automatic_replacement_detect_stale_edits(demo_api):
    client, ids, sessions = demo_api
    agent = ids["agent_id"]
    name = save(client, agent, "User's name is Tom.")
    preference = save(client, agent, "User likes Python.")
    assert edit(client, preference, "User's name is Jane.").status_code == 409
    changed = edit(client, name, "User's name is Jane.").json()
    assert changed == {**name, "content": "User's name is Jane."}
    with sessions() as db:
        save_agent_memory(db, agent, "User's name is Alex.")
    assert edit(client, changed, "User's name is Bob.").status_code == 409
    assert client.get(f"/memories/{agent}").json() == [{**name, "content": "User's name is Alex."}, preference]


def test_stale_retry_noop_maximum_and_legacy_original(demo_api):
    client, ids, sessions = demo_api
    memory = save(client, ids["agent_id"], "Old")
    assert edit(client, memory, "Old").json() == memory
    updated = edit(client, memory, "  " + "机" * 2000 + "  ").json()
    assert updated == {**memory, "content": "机" * 2000}
    assert edit(client, memory, "Do not overwrite").status_code == 409
    assert client.get(f'/memories/{memory["agent_id"]}').json() == [updated]
    with sessions() as db:
        legacy = save_agent_memory(db, ids["agent_id"], " " + "x" * 2100 + " ")
        legacy_id = legacy.id
    original = next(row for row in client.get(f'/memories/{memory["agent_id"]}').json() if row["id"] == legacy_id)
    assert edit(client, original, "Shorter legacy record.").status_code == 200


def test_commit_failure_rolls_back_edit(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    memory = save(client, ids["agent_id"], "Old")
    with sessions() as db:
        saved = db.get(Memory, memory["id"])
        def fail():
            raise RuntimeError("Commit failed")
        monkeypatch.setattr(db, "commit", fail)
        with pytest.raises(RuntimeError, match="Commit failed"):
            update_agent_memory(db, saved, "New", "Old")
        assert db.get(Memory, saved.id).content == "Old"
    assert client.get(f'/memories/{memory["agent_id"]}').json() == [memory]


def test_conditional_write_catches_change_after_initial_read(demo_api):
    client, ids, sessions = demo_api
    memory = save(client, ids["agent_id"], "Old")
    with sessions() as editing, sessions() as other:
        cached = editing.get(Memory, memory["id"])
        other.query(Memory).filter(Memory.id == memory["id"]).update({Memory.content: "Changed elsewhere"})
        other.commit()
        with pytest.raises(MemoryEditConflict, match="changed since"):
            update_agent_memory(editing, cached, "Do not overwrite", "Old")
    assert client.get(f'/memories/{memory["agent_id"]}').json() == [{**memory, "content": "Changed elsewhere"}]


@pytest.mark.parametrize("loss", ["checkpoint", "memory", "id", "timestamp", "invalid_checkpoint"])
def test_persistence_check_rejects_lost_or_changed_fixture_before_any_write(tmp_path, monkeypatch, loss):
    import json
    from app import check_memory_editing as acceptance
    original = {"id": 10, "agent_id": 1, "content": acceptance.EDITED, "created_at": "2026-10-09T08:00:00"}
    path = tmp_path / "memory-edit-acceptance.json"
    if loss != "checkpoint":
        path.write_text(json.dumps({"version": 1, "memory": original}) if loss != "invalid_checkpoint" else "{}")
    current = {**original}
    if loss == "id":
        current["id"] = 11
    if loss == "timestamp":
        current["created_at"] = "2026-10-10T08:00:00"
    responses = iter([[{"name": "Demo Agent", "id": 1}, {"name": "MCP Order Agent", "id": 2}],
                      [] if loss == "memory" else [current]])
    monkeypatch.setattr(acceptance, "request_json", lambda *args: next(responses))
    def no_write(*args, **kwargs):
        pytest.fail("Persistence validation attempted a replacement write")
    monkeypatch.setattr(acceptance, "memory_request", no_write)
    with pytest.raises(RuntimeError, match="checkpoint|lost or changed"):
        acceptance.check_memory_editing("http://demo", True, path)
