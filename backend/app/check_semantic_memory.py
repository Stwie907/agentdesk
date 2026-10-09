"""Verify offline semantic fixtures, scoped Runtime retrieval, and persistence."""

import argparse
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from uuid import uuid4

from sqlalchemy.engine import make_url

from app.check_demo import request_json, require, verify_snapshot
from app.check_memory import memory_request
from app.check_user_memory import inspection, protected_agent_data
from app.config import DATABASE_URL, get_llm_settings


PRIVATE = "I prefer concise answers."
SHARED = "我喜欢简洁的回答。"
QUERY = "Keep it brief."
CHINESE_QUERY = "请用简短的方式解释。"


def preview(base_url, agent_id, query=QUERY, *, shared=False, semantic=True, limit=5, minimum=0.35):
    prefix = f"/user-memories/for-agent/{agent_id}" if shared else f"/memories/{agent_id}"
    params = {"query": query, "limit": limit}
    if semantic: params["min_similarity"] = minimum
    path = prefix + ("/semantic-search?" if semantic else "/search?") + urlencode(params)
    return request_json(base_url, path)


def default_state_file():
    database = make_url(DATABASE_URL).database
    require(bool(database) and database != ":memory:", "Use persistent SQLite for this check")
    return Path(database).resolve().parent / "semantic-memory-acceptance.json"


def validate_checkpoint(base_url, state, agent_id, peer_id, owner, agents):
    require(isinstance(state, dict) and state.get("version") == 1, "Semantic memory checkpoint is invalid")
    for key in ("agent_id", "peer_agent_id", "user_id", "isolation_agent_id", "isolation_user_id"):
        require(type(state.get(key)) is int and state[key] > 0, "Semantic memory checkpoint has invalid IDs")
    require(state.get("agent_id") == agent_id and state.get("peer_agent_id") == peer_id and state.get("user_id") == owner,
            "Semantic memory checkpoint owner or Agents changed")
    require(type(state.get("isolation_agent_id")) is int and type(state.get("isolation_user_id")) is int
            and state["isolation_user_id"] != owner and any(row["id"] == state["isolation_agent_id"] for row in agents),
            "Semantic memory isolation fixture was lost or changed")
    other = request_json(base_url, f'/user-memories/for-agent/{state["isolation_agent_id"]}')
    require(other["user_id"] == state["isolation_user_id"], "Semantic memory isolation owner changed")
    scopes = (
        ("private", "agent_id", agent_id, PRIVATE, request_json(base_url, f"/memories/{agent_id}")),
        ("shared", "user_id", owner, SHARED, request_json(base_url, f"/user-memories/for-agent/{agent_id}")["memories"]),
        ("isolated", "user_id", other["user_id"], PRIVATE, other["memories"]),
    )
    for key, scope_key, scope, content, rows in scopes:
        saved = state.get(key)
        require(isinstance(saved, dict) and type(saved.get("id")) is int and saved["id"] > 0
                and type(saved.get(scope_key)) is int and saved[scope_key] == scope and saved.get("content") == content
                and isinstance(saved.get("created_at"), str), "Semantic memory checkpoint has an invalid record")
        require(saved in rows, "Semantic memory was lost or changed before restart verification")
    require(state["shared"] in request_json(base_url, f"/user-memories/for-agent/{peer_id}")["memories"],
            "Semantic memory same-user fixture was lost or changed")
    message = "Semantic Runtime execution, trace, or snapshot was lost or changed"
    require(type(state.get("execution_id")) is int and state["execution_id"] > 0
            and isinstance(state.get("inspection"), dict), "Semantic memory checkpoint has invalid Runtime data")
    try:
        require(inspection(base_url, state["execution_id"]) == state["inspection"], message)
    except HTTPError as error:
        if error.code != 404: raise
        raise RuntimeError(message) from error
    return other


def check_semantic_memory(base_url, verify_persistence=False, state_file=None):
    state_file = default_state_file() if state_file is None else Path(state_file)
    agents = request_json(base_url, "/agents")
    demos = [row for row in agents if row["name"] == "Demo Agent"]
    peers = [row for row in agents if row["name"] == "MCP Order Agent"]
    require(len(demos) == len(peers) == 1, "Run the demo initializer first")
    agent_id, peer_id = demos[0]["id"], peers[0]["id"]
    context = request_json(base_url, f"/user-memories/for-agent/{agent_id}")
    owner = context["user_id"]
    require(request_json(base_url, f"/user-memories/for-agent/{peer_id}")["user_id"] == owner,
            "Demo Agents must share one owner")
    state = None
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        other = validate_checkpoint(base_url, state, agent_id, peer_id, owner, agents)
    else:
        require(not verify_persistence, "Semantic memory checkpoint is missing; run the initial check first")
    probe = preview(base_url, agent_id)
    require(probe["provider"] == "mock" and probe["model"] == "mock-fixtures-v1", "Use offline Mock vector fixtures for this check")
    require(probe["runtime_mode"] == "semantic", "Enable MEMORY_RETRIEVAL_MODE=semantic on the running Mock backend first")
    # Persistence and running-backend mode checks precede all fixture writes.
    if state is None:
        private = memory_request(base_url, "/memories", {"agent_id": agent_id, "content": PRIVATE})
        shared = memory_request(base_url, f"/user-memories/for-agent/{agent_id}", {"user_id": owner, "content": SHARED})
        token = uuid4().hex[:12]
        user = request_json(base_url, "/users", {"username": "semantic-check-" + token, "email": token + "@agentdesk.local"})
        project = request_json(base_url, "/projects", {"name": "Semantic isolation fixture", "owner_id": user["id"]})
        outsider = request_json(base_url, "/agents", {"name": "Semantic isolation " + token, "project_id": project["id"],
                                                     "model": "qwen2.5:7b", "allowed_tools": ["calculator"]})
        other = request_json(base_url, f'/user-memories/for-agent/{outsider["id"]}')
        isolated = memory_request(base_url, f'/user-memories/for-agent/{other["agent_id"]}', {"user_id": other["user_id"], "content": PRIVATE})
    else:
        private, shared, isolated = state["private"], state["shared"], state["isolated"]
    protected = protected_agent_data(base_url, (agent_id, peer_id, other["agent_id"]))
    shared_before = request_json(base_url, f"/user-memories/for-agent/{agent_id}")["memories"]
    other_before = request_json(base_url, f'/user-memories/for-agent/{other["agent_id"]}')["memories"]
    own_preview = preview(base_url, agent_id)
    require(any(row["memory"] == private and row["similarity"] == 0.96 for row in own_preview["results"]), "Semantic fixture ranking failed")
    require(all(row["memory"] != private for row in preview(base_url, agent_id, semantic=False)["results"]), "Fixture must demonstrate a query without keyword overlap")
    require(all(row["memory"] != private for row in preview(base_url, agent_id, minimum=0.97)["results"]), "Minimum similarity did not exclude weak matches")
    require(len(preview(base_url, agent_id, limit=1)["results"]) <= 1, "Semantic limit was ignored")
    require(all(row["memory"] != private for row in preview(base_url, agent_id, "Unrelated semantic fixture.")["results"]), "Unrelated fixture matched")
    require(all(row["memory"] != private for row in preview(base_url, peer_id)["results"]), "Agent memory leaked into another Agent")
    for chosen in (agent_id, peer_id):
        require(any(row["memory"] == shared for row in preview(base_url, chosen, CHINESE_QUERY, shared=True)["results"]),
                "Same-user bilingual shared retrieval failed")
    foreign = preview(base_url, other["agent_id"], shared=True)["results"]
    require(any(row["memory"] == isolated for row in foreign) and all(row["memory"] != shared for row in foreign),
            "Semantic retrieval crossed user scope")
    require(protected_agent_data(base_url, (agent_id, peer_id, other["agent_id"])) == protected
            and request_json(base_url, f"/user-memories/for-agent/{agent_id}")["memories"] == shared_before
            and request_json(base_url, f'/user-memories/for-agent/{other["agent_id"]}')["memories"] == other_before,
            "Semantic previews changed SQLite records")

    temporary_prefix = "AgentDeskSemanticTemporary " + uuid4().hex + " | "
    transient = memory_request(base_url, "/memories", {"agent_id": agent_id, "content": temporary_prefix + "SQLite records survive restarts."})
    try:
        require(any(row["memory"] == transient for row in preview(base_url, agent_id, "Can saved information stay after reboot?")["results"]), "Initial edit fixture did not match")
        changed = memory_request(base_url, f'/memories/item/{transient["id"]}?agent_id={agent_id}',
            {"content": temporary_prefix + "Unrelated semantic fixture.", "expected_content": transient["content"]}, method="PATCH")
        require(changed == {**transient, "content": temporary_prefix + "Unrelated semantic fixture."}, "Semantic edit fixture changed identity")
        require(all(row["memory"]["id"] != changed["id"] for row in preview(base_url, agent_id, "Can saved information stay after reboot?")["results"]), "Edited memory used stale vectors")
        require(any(row["memory"] == changed for row in preview(base_url, agent_id, "Unrelated semantic fixture.")["results"]), "Edited memory did not receive fresh vectors")
    finally:
        memory_request(base_url, f'/memories/item/{transient["id"]}?agent_id={agent_id}', method="DELETE")
    require(all(row["memory"]["id"] != transient["id"] for row in preview(base_url, agent_id, "Unrelated semantic fixture.")["results"]), "Deleted memory was still retrieved")
    for path in (f"/memories/{agent_id}", f"/user-memories/for-agent/{agent_id}"):
        memory_request(base_url, path + "/semantic-search?" + urlencode({"query": " "}), status=422)
        memory_request(base_url, path + "/semantic-search?" + urlencode({"query": "Unsupported Mock query"}), status=503)
    require(protected_agent_data(base_url, (agent_id, peer_id, other["agent_id"])) == protected, "Edit/delete checks changed protected data")
    execution_ids = []
    for chosen in (agent_id, peer_id):
        chat = request_json(base_url, f"/agents/{chosen}/chat", {"message": QUERY})
        require(chat["status"] == "completed" and chat["response"].startswith("[MOCK]"), "Expected a fixed Mock reply")
        logs = request_json(base_url, f'/execution-logs/{chat["execution_id"]}')
        require(any(row["message"] == "memory_retrieved: Relevant memory loaded" for row in logs)
                and not any(row["message"].startswith("memory_retrieval_fallback:") for row in logs), "Runtime did not use semantic retrieval")
        verify_snapshot(base_url, chat["execution_id"], chat["response"])
        execution_ids.append(chat["execution_id"])
    if state is None:
        checkpoint = {"version": 1, "agent_id": agent_id, "peer_agent_id": peer_id, "user_id": owner,
                      "isolation_agent_id": other["agent_id"], "isolation_user_id": other["user_id"],
                      "private": private, "shared": shared, "isolated": isolated, "execution_id": execution_ids[0],
                      "inspection": inspection(base_url, execution_ids[0])}
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=state_file.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(checkpoint, handle, ensure_ascii=False); handle.write("\n")
            handle.flush(); os.fsync(handle.fileno())
        try: os.replace(temporary, state_file)
        finally: temporary.unlink(missing_ok=True)
    return {"agent_id": agent_id, "memory_id": private["id"], "shared_memory_id": shared["id"],
            "execution_ids": execution_ids, "checks_passed": 8, "persistence_verified": verify_persistence,
            "embedding_provider": "mock", "runtime_mode": "semantic", "reply_mode": "fixed_mock_reply"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--verify-persistence", action="store_true")
    parser.add_argument("--state-file", type=Path)
    args = parser.parse_args()
    try:
        require(get_llm_settings().provider == "mock", "Run this check from the Mock backend")
        result = check_semantic_memory(args.base_url, args.verify_persistence, args.state_file)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Semantic memory check failed: {error}\n")
    print(json.dumps({"status": "passed", **result}))


if __name__ == "__main__": main()
