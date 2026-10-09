"""Shared memory is user-scoped, conditional, persistent, and used by Runtime."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.agent import Agent
from app.models.project import Project
from app.models.user import User
from app.models.user_memory import UserMemory
from app.services.user_memory_service import (
    UserMemoryConflict, save_user_memory, update_user_memory,
)
from app.workers import execution_worker
from test_mcp_runtime_api import demo_api  # noqa: F401


def add_agent(sessions, owner_id=None):
    with sessions() as db:
        if owner_id is None:
            owner = User(username="another-user", email="another@agentdesk.local")
            db.add(owner)
            db.flush()
            owner_id = owner.id
        project = Project(name="Another Project", owner_id=owner_id)
        db.add(project)
        db.flush()
        agent = Agent(name="Another Agent", project_id=project.id, model="qwen2.5:7b", allowed_tools='["calculator"]')
        db.add(agent)
        db.commit()
        return agent.id, owner_id


def rows(client, agent_id):
    response = client.get(f"/user-memories/for-agent/{agent_id}")
    assert response.status_code == 200
    return response.json()


def save(client, agent_id, user_id, content):
    response = client.post(f"/user-memories/for-agent/{agent_id}", json={"user_id": user_id, "content": content})
    assert response.status_code == 200, response.text
    return response.json()


def edit(client, agent_id, memory, content, expected=None):
    return client.patch(f'/user-memories/item/{memory["id"]}?agent_id={agent_id}&user_id={memory["user_id"]}',
        json={"content": content, "expected_content": memory["content"] if expected is None else expected})


def remove(client, agent_id, memory):
    return client.delete(f'/user-memories/item/{memory["id"]}?agent_id={agent_id}&user_id={memory["user_id"]}')


def test_same_owner_shares_across_projects_but_different_owner_cannot_write(demo_api):
    client, ids, sessions = demo_api
    other_project_agent, owner = add_agent(sessions, ids["user_id"])
    outsider, outsider_owner = add_agent(sessions)
    memory = save(client, ids["agent_id"], owner, "  Shared Python preference. \n")
    assert set(memory) == {"id", "user_id", "content", "created_at"}
    assert memory["content"] == "Shared Python preference."
    for agent in (ids["agent_id"], ids["mcp_agent_id"], other_project_agent):
        assert rows(client, agent)["memories"] == [memory]
        assert save(client, agent, owner, memory["content"]) == memory
    assert rows(client, outsider)["memories"] == []
    assert edit(client, outsider, memory, "Intrusion").status_code == 404
    assert remove(client, outsider, memory).status_code == 404
    assert client.post(f"/user-memories/for-agent/{outsider}", json={"user_id": owner, "content": "Intrusion"}).status_code == 404
    foreign = save(client, outsider, outsider_owner, memory["content"])
    assert foreign["id"] != memory["id"] and foreign["user_id"] == outsider_owner
    changed = edit(client, other_project_agent, memory, "Rust shared preference.")
    assert changed.status_code == 200
    assert changed.json() == {**memory, "content": "Rust shared preference."}
    assert rows(client, ids["agent_id"])["memories"] == [changed.json()]
    assert rows(client, outsider)["memories"] == [foreign]
    assert remove(client, ids["mcp_agent_id"], changed.json()).status_code == 200
    assert rows(client, other_project_agent)["memories"] == []
    assert rows(client, outsider)["memories"] == [foreign]


def test_stale_owner_guard_rejects_writes_after_project_reassignment(demo_api):
    client, ids, sessions = demo_api
    outsider, new_owner = add_agent(sessions)
    memory = save(client, ids["agent_id"], ids["user_id"], "Original owner memory")
    with sessions() as db:
        project = db.get(Project, db.get(Agent, ids["agent_id"]).project_id)
        project.owner_id = new_owner
        db.commit()
    assert rows(client, ids["agent_id"])["user_id"] == new_owner
    assert client.post(f'/user-memories/for-agent/{ids["agent_id"]}',
        json={"user_id": ids["user_id"], "content": "Stale user draft"}).status_code == 404
    assert edit(client, ids["agent_id"], memory, "Stale edit").status_code == 404
    assert remove(client, ids["agent_id"], memory).status_code == 404
    assert rows(client, outsider)["memories"] == []
    with sessions() as db:
        assert db.get(UserMemory, memory["id"]).content == memory["content"]


@pytest.mark.parametrize("changes", [
    {"content": ""}, {"content": " \n\t"}, {"content": "x" * 2001},
    {"content": None}, {"content": 3}, {"content": True},
    {"user_id": 0}, {"user_id": "1"}, {"user_id": True}, {"user_id": None},
    {"created_at": "changed"}, {"agent_id": 1},
])
def test_invalid_create_is_read_only(demo_api, changes):
    client, ids, _ = demo_api
    payload = {"user_id": ids["user_id"], "content": "Original", **changes}
    assert client.post(f'/user-memories/for-agent/{ids["agent_id"]}', json=payload).status_code == 422
    assert rows(client, ids["agent_id"])["memories"] == []


@pytest.mark.parametrize("payload", [
    {}, {"content": "New"}, {"content": "New", "expected_content": None},
    {"content": "New", "expected_content": 1}, {"content": "", "expected_content": "Old"},
    {"content": "x" * 2001, "expected_content": "Old"},
    {"content": "New", "expected_content": "Old", "user_id": 1},
])
def test_invalid_edit_is_read_only(demo_api, payload):
    client, ids, _ = demo_api
    memory = save(client, ids["agent_id"], ids["user_id"], "Old")
    path = f'/user-memories/item/{memory["id"]}?agent_id={ids["agent_id"]}&user_id={ids["user_id"]}'
    assert client.patch(path, json=payload).status_code == 422
    assert rows(client, ids["agent_id"])["memories"] == [memory]


@pytest.mark.parametrize("scope", ["", "?agent_id=1", "?user_id=1", "?agent_id=0&user_id=1", "?agent_id=1&user_id=-1"])
def test_mutations_require_both_positive_scopes(demo_api, scope):
    client, ids, _ = demo_api
    memory = save(client, ids["agent_id"], ids["user_id"], "Old")
    path = f'/user-memories/item/{memory["id"]}' + scope
    assert client.patch(path, json={"content": "New", "expected_content": "Old"}).status_code == 422
    assert client.delete(path).status_code == 422
    assert rows(client, ids["agent_id"])["memories"] == [memory]


def test_duplicate_name_and_stale_edit_conflicts_preserve_identity(demo_api):
    client, ids, _ = demo_api
    agent, owner = ids["agent_id"], ids["user_id"]
    name = save(client, agent, owner, "User's name is Tom.")
    memory = save(client, agent, owner, "Python.")
    assert client.post(f"/user-memories/for-agent/{agent}", json={"user_id": owner, "content": "User's name is Jane."}).status_code == 409
    assert edit(client, agent, memory, "User's name is Jane.").status_code == 409
    assert edit(client, agent, memory, name["content"]).status_code == 409
    changed = edit(client, ids["mcp_agent_id"], memory, "  Rust.  ").json()
    assert changed == {**memory, "content": "Rust."}
    assert edit(client, agent, memory, "Do not overwrite").status_code == 409
    assert edit(client, agent, changed, changed["content"]).json() == changed
    assert edit(client, agent, changed, "机" * 2000).status_code == 200
    assert rows(client, agent)["memories"][0] == name


def test_conditional_sql_catches_change_after_read_and_commit_failure_rolls_back(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    memory = save(client, ids["agent_id"], ids["user_id"], "Old")
    with sessions() as editing, sessions() as other:
        cached = editing.get(UserMemory, memory["id"])
        update_user_memory(other, other.get(UserMemory, memory["id"]), "Changed elsewhere", "Old")
        with pytest.raises(UserMemoryConflict, match="changed since"):
            update_user_memory(editing, cached, "Do not overwrite", "Old")
    with sessions() as editing:
        cached = editing.get(UserMemory, memory["id"])
        monkeypatch.setattr(editing, "commit", lambda: (_ for _ in ()).throw(RuntimeError("Commit failed")))
        with pytest.raises(RuntimeError, match="Commit failed"):
            update_user_memory(editing, cached, "Do not persist", "Changed elsewhere")
        assert editing.get(UserMemory, memory["id"]).content == "Changed elsewhere"
    assert rows(client, ids["agent_id"])["memories"] == [{**memory, "content": "Changed elsewhere"}]


def test_concurrent_identical_saves_reuse_database_identity(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        owner = User(username="parallel", email="parallel@agentdesk.local")
        db.add(owner); db.commit()
        owner_id = owner.id
    barrier = Barrier(2)
    def save_parallel(_):
        with sessions() as db:
            commit = db.commit
            def synchronize():
                barrier.wait(timeout=10)
                commit()
            db.commit = synchronize
            memory = save_user_memory(db, owner_id, "Shared concurrent preference")
            return memory.id, memory.content, memory.created_at
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(save_parallel, range(2)))
        assert first == second
        with sessions() as db:
            assert db.query(UserMemory).count() == 1
    finally:
        engine.dispose()


def test_preview_unicode_ranking_scope_and_runtime_source_labels(demo_api, monkeypatch):
    client, ids, sessions = demo_api
    agent, owner = ids["agent_id"], ids["user_id"]
    outsider, foreign_owner = add_agent(sessions)
    first = save(client, agent, owner, "Python SQLite 中文记忆")
    newest = save(client, agent, owner, "Python SQLite shared")
    foreign = save(client, outsider, foreign_owner, "Python SQLite foreign secret")
    preview = client.get(f"/user-memories/for-agent/{agent}/search", params={"query": "  ＰＹＴＨＯＮ sqlite  ", "limit": 2}).json()
    assert preview["query"] == "ＰＹＴＨＯＮ sqlite"
    assert [row["memory"] for row in preview["results"]] == [newest, first]
    assert all(row["score"] == 2 and row["matched_terms"] == ["python", "sqlite"] for row in preview["results"])
    chinese = client.get(f"/user-memories/for-agent/{agent}/search", params={"query": "中文记忆"}).json()
    assert chinese["results"][0]["memory"] == first
    local = client.post("/memories", json={"agent_id": agent, "content": "Python private Agent memory"}).json()
    captured = []
    original = execution_worker.run_agent
    def run(*args, **kwargs):
        captured.append(args[2])
        return original(*args, **kwargs)
    monkeypatch.setattr(execution_worker, "run_agent", run)
    for chosen in (agent, ids["mcp_agent_id"], outsider):
        chat = client.post(f"/agents/{chosen}/chat", json={"message": "Explain Python SQLite"}).json()
        assert chat["status"] == "completed" and chat["response"].startswith("[MOCK]")
    assert captured[0] == f'Shared user memory:\n{newest["content"]}\n{first["content"]}\nAgent memory:\n{local["content"]}'
    assert captured[1] == f'Shared user memory:\n{newest["content"]}\n{first["content"]}'
    assert captured[2] == f'Shared user memory:\n{foreign["content"]}'


@pytest.mark.parametrize("params", [{}, {"query": " "}, {"query": "x" * 501}, {"query": "Python", "limit": 0}, {"query": "Python", "limit": 21}])
def test_search_validation_and_missing_agent(demo_api, params):
    client, ids, _ = demo_api
    assert client.get(f'/user-memories/for-agent/{ids["agent_id"]}/search', params=params).status_code == 422
    assert client.get("/user-memories/for-agent/99999").status_code == 404
    assert client.get("/user-memories/for-agent/99999/search", params={"query": "Python"}).status_code == 404


def test_shared_crud_preserves_transcript_execution_and_automatic_agent_memories(demo_api):
    client, ids, _ = demo_api
    agent, owner = ids["agent_id"], ids["user_id"]
    conversation = client.post("/conversations", json={"agent_id": agent, "title": "Keep transcript"}).json()
    chat = client.post(f'/conversations/{conversation["id"]}/chat', json={"message": "My name is Tom. I like Python."}).json()
    local = client.get(f"/memories/{agent}").json()
    assert local and rows(client, agent)["memories"] == []
    transcript = client.get(f'/conversations/{conversation["id"]}/messages').json()
    execution = f'/executions/{chat["execution_id"]}'
    inspections = {suffix: client.get(execution + suffix).json() for suffix in ("", "/trace", "/snapshot")}
    history = client.get(f"/executions?agent_id={agent}").json()
    memory = save(client, agent, owner, "Python shared preference")
    changed = edit(client, ids["mcp_agent_id"], memory, "Rust shared preference").json()
    assert remove(client, agent, changed).status_code == 200
    assert client.get(f"/memories/{agent}").json() == local
    assert client.get(f'/conversations/{conversation["id"]}/messages').json() == transcript
    assert client.get(f"/executions?agent_id={agent}").json() == history
    assert {suffix: client.get(execution + suffix).json() for suffix in inspections} == inspections


@pytest.mark.parametrize("loss", ["checkpoint", "invalid_checkpoint", "memory", "identity", "timestamp", "isolation_agent", "isolation_memory", "owner", "execution", "missing_snapshot"])
def test_restart_check_rejects_data_loss_before_any_write(tmp_path, monkeypatch, loss):
    import json
    from app import check_user_memory as acceptance
    primary = {"id": 10, "user_id": 1, "content": acceptance.EDITED, "created_at": "2026-10-09T08:00:00"}
    isolated = {"id": 20, "user_id": 2, "content": acceptance.ISOLATED, "created_at": "2026-10-09T08:00:00"}
    own = {"agent_id": 1, "user_id": 1, "username": "demo", "memories": [dict(primary)]}
    peer = {**own, "agent_id": 2}
    other = {"agent_id": 3, "user_id": 2, "username": "other", "memories": [dict(isolated)]}
    agents = [{"name": "Demo Agent", "id": 1}, {"name": "MCP Order Agent", "id": 2}, {"name": "Isolated", "id": 3}]
    state = {"version": 1, "agent_id": 1, "peer_agent_id": 2, "user_id": 1, "isolation_agent_id": 3,
             "isolation_user_id": 2, "memory": primary, "isolation_memory": isolated, "execution_id": 7,
             "inspection": {"": {"id": 7}, "/trace": [], "/snapshot": {"execution_id": 7}}}
    path = tmp_path / "user-memory-acceptance.json"
    if loss != "checkpoint":
        path.write_text(json.dumps({} if loss == "invalid_checkpoint" else state), encoding="utf-8")
    if loss == "memory": own["memories"] = []
    if loss == "identity": own["memories"][0]["id"] += 1
    if loss == "timestamp": own["memories"][0]["created_at"] = "changed"
    if loss == "isolation_agent": agents.pop()
    if loss == "isolation_memory": other["memories"] = []
    if loss == "owner": other["user_id"] = 1
    responses = {"/agents": agents, "/user-memories/for-agent/1": own,
                 "/user-memories/for-agent/2": peer, "/user-memories/for-agent/3": other}
    for suffix, value in state["inspection"].items(): responses["/executions/7" + suffix] = value
    if loss == "execution": responses["/executions/7"] = {"id": 8}
    def read(base, requested, payload=None):
        assert payload is None, "Restart verification attempted a fixture creation"
        if loss == "missing_snapshot" and requested == "/executions/7/snapshot":
            from urllib.error import HTTPError
            raise HTTPError(requested, 404, "Not Found", {}, None)
        return responses[requested]
    monkeypatch.setattr(acceptance, "request_json", read)
    monkeypatch.setattr(acceptance, "memory_request", lambda *args, **kwargs: pytest.fail("Restart verification attempted a replacement write"))
    with pytest.raises(RuntimeError, match="checkpoint|lost or changed|owner changed"):
        acceptance.check_user_memory("http://demo", True, path)


def test_http_acceptance_initial_repeat_and_restart_reuse_checkpoint(demo_api, tmp_path, monkeypatch):
    import json
    from app import check_demo, check_user_memory as acceptance
    client, _, _ = demo_api
    def read(base, path, payload=None):
        response = client.get(path) if payload is None else client.post(path, json=payload)
        assert response.status_code == 200, response.text
        return response.json()
    def request(base, path, payload=None, *, method=None, status=200):
        response = client.request(method or ("POST" if payload is not None else "GET"), path, json=payload)
        assert response.status_code == status, response.text
        return response.json()
    monkeypatch.setattr(acceptance, "request_json", read)
    monkeypatch.setattr(acceptance, "memory_request", request)
    monkeypatch.setattr(check_demo, "request_json", read)
    path = tmp_path / "user-memory-acceptance.json"
    first = acceptance.check_user_memory("http://demo", state_file=path)
    original = path.read_bytes()
    state = json.loads(original)
    for persistence in (False, True):
        result = acceptance.check_user_memory("http://demo", persistence, path)
        assert result["checks_passed"] == 8 and result["persistence_verified"] is persistence
        assert result["memory_id"] == first["memory_id"] == state["memory"]["id"]
        assert result["isolation_agent_id"] == first["isolation_agent_id"]
        assert path.read_bytes() == original
