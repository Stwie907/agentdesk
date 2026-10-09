"""Check same-user sharing, isolation, conditional edits, Runtime, and restart persistence."""

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
from app.config import DATABASE_URL, get_llm_settings


ORIGINAL = "AgentDeskSharedMemoryPython original."
EDITED = "AgentDeskSharedMemoryRust shared."
ISOLATED = "AgentDeskSharedIsolation private."


def context(base_url, agent_id):
    return request_json(base_url, f"/user-memories/for-agent/{agent_id}")


def save(base_url, agent_id, user_id, content, status=200):
    return memory_request(base_url, f"/user-memories/for-agent/{agent_id}",
                          {"user_id": user_id, "content": content}, status=status)


def item_path(row, agent_id):
    return f'/user-memories/item/{row["id"]}?agent_id={agent_id}&user_id={row["user_id"]}'


def patch(base_url, row, agent_id, content, *, expected=None, status=200):
    return memory_request(base_url, item_path(row, agent_id), {
        "content": content, "expected_content": row["content"] if expected is None else expected,
    }, method="PATCH", status=status)


def preview(base_url, agent_id, query):
    return request_json(base_url, f"/user-memories/for-agent/{agent_id}/search?" + urlencode({"query": query, "limit": 5}))


def default_state_file():
    database = make_url(DATABASE_URL).database
    require(bool(database) and database != ":memory:", "Use a persistent SQLite database for this check")
    return Path(database).resolve().parent / "user-memory-acceptance.json"


def inspection(base_url, execution_id):
    return {suffix: request_json(base_url, f"/executions/{execution_id}" + suffix) for suffix in ("", "/trace", "/snapshot")}


def validate_checkpoint(base_url, state, own, peer, agents):
    require(isinstance(state, dict) and state.get("version") == 1,
            "Shared memory persistence checkpoint is invalid")
    for key in ("agent_id", "peer_agent_id", "user_id", "isolation_agent_id", "isolation_user_id", "execution_id"):
        require(type(state.get(key)) is int and state[key] > 0, "Shared memory persistence checkpoint has invalid IDs")
    require(state["agent_id"] == own["agent_id"] and state["peer_agent_id"] == peer["agent_id"]
            and state["user_id"] == own["user_id"] == peer["user_id"], "Shared memory checkpoint owner or Agents changed")
    require(state["isolation_user_id"] != state["user_id"]
            and any(row["id"] == state["isolation_agent_id"] for row in agents), "Shared memory isolation fixture was lost or changed")
    other = context(base_url, state["isolation_agent_id"])
    require(other["user_id"] == state["isolation_user_id"], "Shared memory isolation owner changed")
    for key, owner, current, content in (("memory", own["user_id"], own["memories"], EDITED),
                                       ("isolation_memory", other["user_id"], other["memories"], ISOLATED)):
        saved = state.get(key)
        require(isinstance(saved, dict) and saved.get("user_id") == owner and saved.get("content") == content
                and type(saved.get("id")) is int and saved["id"] > 0 and isinstance(saved.get("created_at"), str),
                "Shared memory persistence checkpoint contains an invalid record")
        require(saved in current, "Shared memory was lost or changed before restart verification")
    require(state["memory"] in peer["memories"] and state["memory"] not in other["memories"]
            and state["isolation_memory"] not in own["memories"], "Shared memory persistence crossed owner scope")
    message = "Shared memory Runtime execution, trace, or snapshot was lost or changed"
    require(isinstance(state.get("inspection"), dict), message)
    try:
        current_inspection = inspection(base_url, state["execution_id"])
    except HTTPError as error:
        if error.code != 404:
            raise
        raise RuntimeError(message) from error
    require(current_inspection == state["inspection"], message)
    return other


def protected_agent_data(base_url, agent_ids):
    protected = {}
    for agent_id in agent_ids:
        conversations = request_json(base_url, f"/conversations?agent_id={agent_id}")
        protected[agent_id] = {
            "memories": request_json(base_url, f"/memories/{agent_id}"),
            "executions": request_json(base_url, f"/executions?agent_id={agent_id}&limit=100"),
            "conversations": conversations,
            "messages": {row["id"]: request_json(base_url, f'/conversations/{row["id"]}/messages') for row in conversations},
        }
    return protected


def check_user_memory(base_url: str, verify_persistence: bool = False, state_file: Path | None = None) -> dict:
    state_file = default_state_file() if state_file is None else Path(state_file)
    agents = request_json(base_url, "/agents")
    demos = [row for row in agents if row["name"] == "Demo Agent"]
    peers = [row for row in agents if row["name"] == "MCP Order Agent"]
    require(len(demos) == len(peers) == 1, "Run the demo initializer first")
    agent_id, peer_id = demos[0]["id"], peers[0]["id"]
    own, peer = context(base_url, agent_id), context(base_url, peer_id)
    require(own["user_id"] == peer["user_id"], "Demo Agents must belong to the same user")
    state = None
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        other = validate_checkpoint(base_url, state, own, peer, agents)
    else:
        require(not verify_persistence, "Shared memory persistence checkpoint is missing; run the initial check first")
    # No write, including replacement fixture creation, occurs before the above checks.
    protected = protected_agent_data(base_url, (agent_id, peer_id))
    owner = own["user_id"]
    if state is None:
        token = uuid4().hex[:12]
        user = request_json(base_url, "/users", {"username": "shared-check-" + token, "email": token + "@agentdesk.local"})
        project = request_json(base_url, "/projects", {"name": "Shared memory isolation fixture", "owner_id": user["id"]})
        isolation_agent = request_json(base_url, "/agents", {
            "name": "Shared memory isolation " + token, "project_id": project["id"],
            "model": "qwen2.5:7b", "allowed_tools": ["calculator"],
        })
        other = context(base_url, isolation_agent["id"])
        saved_matches = [row for row in own["memories"] if row["content"] == EDITED]
        require(len(saved_matches) <= 1, "Duplicate shared acceptance records exist")
        if saved_matches:
            saved = saved_matches[0]
        else:
            original = save(base_url, agent_id, owner, ORIGINAL)
            saved = patch(base_url, original, peer_id, "  " + EDITED + "  ")
            require(saved == {**original, "content": EDITED}, "Shared edit changed ID, owner, or creation time")
        isolated = save(base_url, other["agent_id"], other["user_id"], ISOLATED)
        other = context(base_url, other["agent_id"])
    else:
        saved, isolated = state["memory"], state["isolation_memory"]
    require(save(base_url, peer_id, owner, "  " + EDITED + "  ") == saved, "Same-user duplicate did not retain identity")
    require(patch(base_url, saved, agent_id, EDITED) == saved, "Unchanged shared edit changed identity")
    require(saved in context(base_url, peer_id)["memories"], "Same-user Agents do not share the record")
    require(saved not in other["memories"] and isolated not in context(base_url, agent_id)["memories"], "Shared lists crossed users")
    patch(base_url, saved, other["agent_id"], "Wrong user", status=404)
    memory_request(base_url, item_path(saved, other["agent_id"]), method="DELETE", status=404)
    save(base_url, other["agent_id"], owner, "Wrong expected owner", status=404)

    transient = save(base_url, agent_id, owner, "Shared temporary " + uuid4().hex)
    try:
        patch(base_url, saved, peer_id, transient["content"], status=409)
        patch(base_url, saved, peer_id, "Do not overwrite", expected=ORIGINAL, status=409)
        for content in (" \n\t", "x" * 2001):
            save(base_url, agent_id, owner, content, status=422)
        memory_request(base_url, f'/user-memories/item/{saved["id"]}?agent_id={agent_id}',
                       {"content": "New", "expected_content": EDITED}, method="PATCH", status=422)
        require(saved in context(base_url, agent_id)["memories"], "Rejected writes changed shared records")
    finally:
        memory_request(base_url, item_path(transient, peer_id), method="DELETE")
    require(transient not in context(base_url, agent_id)["memories"], "Same-user delete did not propagate")
    require(context(base_url, other["agent_id"])["memories"] == other["memories"], "Other user's records changed")
    require(protected_agent_data(base_url, (agent_id, peer_id)) == protected,
            "Shared CRUD changed Agent memory, conversations, messages, or executions")
    for chosen in (agent_id, peer_id):
        results = preview(base_url, chosen, "AgentDeskSharedMemoryRust")["results"]
        require(len(results) == 1 and results[0]["memory"] == saved, "Preview did not retrieve the shared edit")
        require(preview(base_url, chosen, "AgentDeskSharedMemoryPython")["results"] == [], "Preview still uses original content")
    require(preview(base_url, other["agent_id"], "AgentDeskSharedMemoryRust")["results"] == [], "Preview crossed users")

    runtime_ids = []
    for chosen, marker, expected in ((agent_id, "AgentDeskSharedMemoryRust", "Relevant memory loaded"),
                                    (peer_id, "AgentDeskSharedMemoryRust", "Relevant memory loaded"),
                                    (other["agent_id"], "AgentDeskSharedMemoryRust", "No relevant memory found"),
                                    (other["agent_id"], "AgentDeskSharedIsolation", "Relevant memory loaded")):
        chat = request_json(base_url, f"/agents/{chosen}/chat", {"message": marker})
        require(chat["status"] == "completed" and chat["response"].startswith("[MOCK]"), "Expected a fixed Mock reply")
        logs = request_json(base_url, f'/execution-logs/{chat["execution_id"]}')
        require(any(row["message"] == "memory_retrieved: " + expected for row in logs), "Runtime retrieval did not respect user scope")
        verify_snapshot(base_url, chat["execution_id"], chat["response"])
        runtime_ids.append(chat["execution_id"])
    if state is None:
        checkpoint = {"version": 1, "agent_id": agent_id, "peer_agent_id": peer_id, "user_id": owner,
                      "isolation_agent_id": other["agent_id"], "isolation_user_id": other["user_id"],
                      "memory": saved, "isolation_memory": isolated, "execution_id": runtime_ids[0],
                      "inspection": inspection(base_url, runtime_ids[0])}
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=state_file.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(checkpoint, handle, ensure_ascii=False); handle.write("\n")
            handle.flush(); os.fsync(handle.fileno())
        try:
            os.replace(temporary, state_file)
        finally:
            temporary.unlink(missing_ok=True)
    return {"agent_id": agent_id, "peer_agent_id": peer_id, "user_id": owner, "memory_id": saved["id"],
            "isolation_agent_id": other["agent_id"], "execution_ids": runtime_ids, "checks_passed": 8,
            "persistence_verified": verify_persistence, "reply_mode": "fixed_mock_reply"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--verify-persistence", action="store_true")
    parser.add_argument("--state-file", type=Path, help="Checkpoint stored beside the SQLite database by default")
    args = parser.parse_args()
    try:
        require(get_llm_settings().provider == "mock", "Run this check from the Mock backend container")
        result = check_user_memory(args.base_url, args.verify_persistence, args.state_file)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Shared user memory check failed: {error}\n")
    print(json.dumps({"status": "passed", **result}))


if __name__ == "__main__":
    main()
