"""Check conversation rename, scoped deletion, and retained Agent data over HTTP."""

import argparse
import json
from urllib.error import HTTPError, URLError
from uuid import uuid4

from app.check_demo import request_json, require, verify_snapshot
from app.check_memory import memory_request
from app.config import get_llm_settings


TITLE = "AgentDesk conversation management keeper"
INITIAL_TITLE = TITLE + " draft"
TEMPORARY_TITLE = "AgentDesk disposable conversation "
FIRST_MESSAGE = "I like AgentDeskConversationManagementDemo"
MEMORY_CONTENT = "User likes AgentDeskConversationManagementDemo."


def find_keeper_execution(base_url, agent_id):
    offset = 0
    while True:
        rows = request_json(base_url, f"/executions?agent_id={agent_id}&limit=100&offset={offset}")
        matches = [row for row in rows if row["input"] == FIRST_MESSAGE and row["status"] == "completed"]
        if matches:
            return matches[0]
        require(len(rows) == 100, "Keeper execution was lost")
        offset += len(rows)


def check_conversation_management(base_url: str, verify_persistence: bool = False) -> dict:
    agents = request_json(base_url, "/agents")
    demos = [row for row in agents if row["name"] == "Demo Agent"]
    others = [row for row in agents if row["name"] == "MCP Order Agent"]
    require(len(demos) == len(others) == 1, "Run the demo initializer first")
    agent_id, other_id = demos[0]["id"], others[0]["id"]
    rows = request_json(base_url, f"/conversations?agent_id={agent_id}")
    matches = [row for row in rows if row["title"] in (TITLE, INITIAL_TITLE)]
    require(len(matches) <= 1, "Multiple keeper conversations exist")
    if verify_persistence:
        # All persistence evidence is checked before any repair or test write.
        require(len(matches) == 1 and matches[0]["title"] == TITLE, "Renamed keeper conversation was lost")
        old_messages = request_json(base_url, f'/conversations/{matches[0]["id"]}/messages?agent_id={agent_id}')
        require(any(row["role"] == "user" and row["content"] == FIRST_MESSAGE for row in old_messages)
                and any(row["role"] == "assistant" and row["content"].startswith("[MOCK]") for row in old_messages),
                "Keeper transcript was lost")
        require(any(row["content"] == MEMORY_CONTENT for row in request_json(base_url, f"/memories/{agent_id}")),
                "Keeper memory was lost")
        require(not any(row["title"].startswith(TEMPORARY_TITLE) for row in rows), "A deleted temporary conversation remains")
        previous_execution = find_keeper_execution(base_url, agent_id)
        verify_snapshot(base_url, previous_execution["id"], previous_execution["output"])

    keeper = matches[0] if matches else request_json(base_url, "/conversations", {"agent_id": agent_id, "title": INITIAL_TITLE})
    keeper_path = f'/conversations/{keeper["id"]}'
    keeper_messages = request_json(base_url, keeper_path + f"/messages?agent_id={agent_id}")
    if not any(row["role"] == "user" and row["content"] == FIRST_MESSAGE for row in keeper_messages):
        reply = request_json(base_url, keeper_path + f"/chat?agent_id={agent_id}", {"message": FIRST_MESSAGE})
        require(reply["status"] == "completed" and reply["response"].startswith("[MOCK]"), "Expected a Mock keeper turn")
        keeper_messages = request_json(base_url, keeper_path + f"/messages?agent_id={agent_id}")
    keeper_execution = find_keeper_execution(base_url, agent_id)
    verify_snapshot(base_url, keeper_execution["id"], keeper_execution["output"])
    before_rename = memory_request(base_url, keeper_path + f"?agent_id={agent_id}", {"title": INITIAL_TITLE}, method="PATCH")
    renamed = memory_request(base_url, keeper_path + f"?agent_id={agent_id}", {"title": "  " + TITLE + "  "}, method="PATCH")
    require(renamed == {**before_rename, "title": TITLE}, "Rename changed identity, Agent, or creation time")
    require(request_json(base_url, keeper_path + f"/messages?agent_id={agent_id}") == keeper_messages, "Rename changed the transcript")

    other_conversations = request_json(base_url, f"/conversations?agent_id={other_id}")
    other_memories = request_json(base_url, f"/memories/{other_id}")
    temporary = request_json(base_url, "/conversations", {"agent_id": agent_id, "title": TEMPORARY_TITLE + uuid4().hex})
    temporary_path = f'/conversations/{temporary["id"]}'
    try:
        reply = request_json(base_url, temporary_path + f"/chat?agent_id={agent_id}",
                             {"message": "Temporary conversation management acceptance turn."})
        require(reply["status"] == "completed" and reply["response"].startswith("[MOCK]"), "Expected a Mock temporary turn")
        transcript = request_json(base_url, temporary_path + f"/messages?agent_id={agent_id}")
        require(len(transcript) == 2, "Temporary conversation has no saved turn")
        for payload in ({"title": " "}, {"title": "x" * 201}, {"title": "New", "agent_id": other_id}):
            memory_request(base_url, temporary_path + f"?agent_id={agent_id}", payload, method="PATCH", status=422)
        memory_request(base_url, temporary_path + f"?agent_id={other_id}", {"title": "Wrong Agent"}, method="PATCH", status=404)
        memory_request(base_url, temporary_path + f"?agent_id={other_id}", method="DELETE", status=404)
        require(request_json(base_url, temporary_path + f"?agent_id={agent_id}") == temporary, "Rejected write changed conversation")
        require(request_json(base_url, temporary_path + f"/messages?agent_id={agent_id}") == transcript, "Rejected write changed messages")
        protected = [row for row in request_json(base_url, f"/conversations?agent_id={agent_id}") if row["id"] != temporary["id"]]
        memories = request_json(base_url, f"/memories/{agent_id}")
        require(any(row["content"] == MEMORY_CONTENT for row in memories), "Keeper preference is missing")
        execution_path = f'/executions/{reply["execution_id"]}'
        inspection = {suffix: request_json(base_url, execution_path + suffix) for suffix in ("", "/trace", "/snapshot")}
    finally:
        deleted = memory_request(base_url, temporary_path + f"?agent_id={agent_id}", method="DELETE")
        require(deleted == {"message": "deleted"}, "Unexpected deletion response")

    for suffix in ("", "/messages"):
        memory_request(base_url, temporary_path + suffix + f"?agent_id={agent_id}", status=404)
    memory_request(base_url, temporary_path + f"?agent_id={agent_id}", {"title": "Gone"}, method="PATCH", status=404)
    memory_request(base_url, temporary_path + f"?agent_id={agent_id}", method="DELETE", status=404)
    memory_request(base_url, temporary_path + f"/chat?agent_id={agent_id}", {"message": "Gone"}, status=404)
    require(request_json(base_url, f"/conversations?agent_id={agent_id}") == protected, "Deletion changed another conversation")
    require(request_json(base_url, keeper_path + f"/messages?agent_id={agent_id}") == keeper_messages, "Deletion changed keeper messages")
    require(request_json(base_url, f"/memories/{agent_id}") == memories, "Deletion changed Agent memory")
    require({suffix: request_json(base_url, execution_path + suffix) for suffix in inspection} == inspection,
            "Deletion changed execution, trace, or snapshot")
    require(request_json(base_url, f"/conversations?agent_id={other_id}") == other_conversations
            and request_json(base_url, f"/memories/{other_id}") == other_memories, "Another Agent's data changed")
    return {"agent_id": agent_id, "keeper_conversation_id": keeper["id"], "deleted_conversation_id": temporary["id"],
            "preserved_execution_id": reply["execution_id"], "checks_passed": 6, "persistence_verified": verify_persistence}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--verify-persistence", action="store_true")
    args = parser.parse_args()
    try:
        require(get_llm_settings().provider == "mock", "Run this check from the Mock backend container")
        result = check_conversation_management(args.base_url, args.verify_persistence)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Conversation management check failed: {exc}\n")
    print(json.dumps({"status": "passed", **result}))


if __name__ == "__main__":
    main()
