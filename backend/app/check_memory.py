"""Check Agent-scoped memory storage, retrieval, and restart persistence over HTTP."""

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request
from uuid import uuid4

from app.check_demo import HTTP, request_json, require, verify_snapshot
from app.config import get_llm_settings


DEMO_CONTENT = "AgentDesk memory demo: Python."


def memory_request(base_url, path, payload=None, *, method=None, status=200):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(base_url.rstrip("/") + path, data=data, method=method,
                      headers={"Accept": "application/json", "Content-Type": "application/json"})
    try:
        response = HTTP.open(request, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        require(response.status == status, f"{path}: expected HTTP {status}, got {response.status}")
        require(response.headers.get_content_type() == "application/json", f"{path} did not return JSON")
        return json.load(response)


def check_memory(base_url: str, verify_persistence: bool = False) -> dict:
    agents = request_json(base_url, "/agents")
    demos = [row for row in agents if row["name"] == "Demo Agent"]
    others = [row for row in agents if row["name"] == "MCP Order Agent"]
    require(len(demos) == len(others) == 1, "Run the demo initializer first")
    agent_id, other_id = demos[0]["id"], others[0]["id"]
    before = request_json(base_url, f"/memories/{agent_id}")
    previous = [row for row in before if row["content"] == DEMO_CONTENT]
    if verify_persistence:
        # Check before POST: recreating a missing record would hide data loss.
        require(len(previous) == 1, "Demo memory was lost; run the initial check before restart verification")
    saved = memory_request(base_url, "/memories", {"agent_id": agent_id, "content": "  " + DEMO_CONTENT + "  "})
    require(saved["agent_id"] == agent_id and saved["content"] == DEMO_CONTENT, "Memory was not trimmed or scoped")
    if verify_persistence:
        require(saved == previous[0], "Persisted memory ID, content, or timestamp changed")
    repeated = memory_request(base_url, "/memories", {"agent_id": agent_id, "content": DEMO_CONTENT})
    require(repeated == saved, "Duplicate memory did not reuse its original ID and timestamp")
    rows = request_json(base_url, f"/memories/{agent_id}")
    require(sum(row["content"] == DEMO_CONTENT for row in rows) == 1, "Duplicate memory rows exist")
    require(all(row["agent_id"] == agent_id for row in rows), "Agent list contains another Agent's memory")

    transient = memory_request(base_url, "/memories", {
        "agent_id": other_id, "content": "AgentDesk scope check " + uuid4().hex,
    })
    try:
        own = request_json(base_url, f"/memories/{agent_id}")
        other = request_json(base_url, f"/memories/{other_id}")
        require(transient not in own and saved not in other and transient in other,
                "Memory lists crossed Agent boundaries")
        memory_request(base_url, f'/memories/item/{transient["id"]}?agent_id={agent_id}', method="DELETE", status=404)
        require(transient in request_json(base_url, f"/memories/{other_id}"), "Wrong Agent deleted the memory")
    finally:
        memory_request(base_url, f'/memories/item/{transient["id"]}?agent_id={other_id}', method="DELETE")
    require(transient not in request_json(base_url, f"/memories/{other_id}"), "Scoped delete did not remove memory")
    memory_request(base_url, f'/memories/item/{transient["id"]}?agent_id={other_id}', method="DELETE", status=404)

    for content in (" \n\t", "x" * 2001):
        memory_request(base_url, "/memories", {"agent_id": agent_id, "content": content}, status=422)
    missing_id = max(row["id"] for row in agents) + 100000
    memory_request(base_url, "/memories", {"agent_id": missing_id, "content": DEMO_CONTENT}, status=404)
    memory_request(base_url, f"/memories/{missing_id}", status=404)
    require(request_json(base_url, f"/memories/{agent_id}") == rows, "Invalid writes changed saved memories")

    chat = request_json(base_url, f"/agents/{agent_id}/chat", {
        "message": "What is in my AgentDesk memory about Python?",
    })
    require(chat["status"] == "completed" and chat["response"].startswith("[MOCK]"), "Expected a marked Mock response")
    logs = request_json(base_url, f'/execution-logs/{chat["execution_id"]}')
    require(any(row["message"] == "memory_retrieved: Relevant memory loaded" for row in logs),
            "Runtime did not load relevant saved memory")
    verify_snapshot(base_url, chat["execution_id"], chat["response"])
    return {"agent_id": agent_id, "memory_id": saved["id"], "execution_id": chat["execution_id"],
            "checks_passed": 6, "persistence_verified": verify_persistence,
            "reply_mode": "fixed_mock_reply"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--verify-persistence", action="store_true")
    args = parser.parse_args()
    try:
        require(get_llm_settings().provider == "mock", "Run this check from the Mock backend container")
        result = check_memory(args.base_url, args.verify_persistence)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Memory check failed: {exc}\n")
    print(json.dumps({"status": "passed", **result}))


if __name__ == "__main__":
    main()
