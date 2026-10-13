"""Check persistent multi-turn conversation chat and automatic Agent memory."""

import argparse
import json
from urllib.error import HTTPError, URLError

from app.check_demo import request_json, require, verify_snapshot
from app.check_memory import memory_request
from app.config import get_llm_settings


TITLE = "AgentDesk conversation memory demo"
PREFERENCE = "AgentDeskConversationMemoryDemo"
FIRST_MESSAGE = "I like " + PREFERENCE
SECOND_MESSAGE = "What do I like about " + PREFERENCE + "?"
MEMORY_CONTENT = "User likes " + PREFERENCE + "."


def check_conversation(base_url: str, verify_persistence: bool = False) -> dict:
    agents = request_json(base_url, "/agents")
    demos = [row for row in agents if row["name"] == "Demo Agent"]
    others = [row for row in agents if row["name"] == "MCP Order Agent"]
    require(len(demos) == len(others) == 1, "Run the demo initializer first")
    agent_id, other_id = demos[0]["id"], others[0]["id"]
    conversations = request_json(base_url, f"/conversations?agent_id={agent_id}")
    require(all(row["agent_id"] == agent_id for row in conversations), "Conversation list crossed Agent scope")
    matches = [row for row in conversations if row["title"] == TITLE]
    require(len(matches) <= 1, "Multiple conversation demo records exist")
    require(not verify_persistence or len(matches) == 1,
            "Demo conversation was lost; run the initial check before restart verification")
    if matches:
        conversation = matches[0]
    else:
        conversation = request_json(base_url, "/conversations", {"agent_id": agent_id, "title": "  " + TITLE + "  "})
    require(conversation["agent_id"] == agent_id and conversation["title"] == TITLE, "Conversation was not trimmed or scoped")
    conversation_id = conversation["id"]
    prefix = f"/conversations/{conversation_id}"
    before = request_json(base_url, prefix + f"/messages?agent_id={agent_id}")
    if verify_persistence:
        require(len(before) >= 4 and any(row["role"] == "user" and row["content"] == FIRST_MESSAGE for row in before)
                and any(row["role"] == "user" and row["content"] == SECOND_MESSAGE for row in before),
                "Conversation history was lost after restart")
        require(any(row["content"] == MEMORY_CONTENT for row in request_json(base_url, f"/memories/{agent_id}")),
                "Extracted memory was lost after restart")

    other_before = request_json(base_url, f"/memories/{other_id}")
    require(conversation not in request_json(base_url, f"/conversations?agent_id={other_id}"), "Another Agent sees this conversation")
    memory_request(base_url, prefix + f"/messages?agent_id={other_id}", status=404)
    memory_request(base_url, prefix + f"/chat?agent_id={other_id}", {"message": FIRST_MESSAGE}, status=404)
    for message in (" \n\t", "x" * 4001):
        memory_request(base_url, prefix + f"/chat?agent_id={agent_id}", {"message": message}, status=422)
    require(request_json(base_url, prefix + f"/messages?agent_id={agent_id}") == before, "Rejected chat changed transcript")
    require(request_json(base_url, f"/memories/{other_id}") == other_before, "Rejected chat wrote another Agent's memory")

    replies = []
    after_statement = None
    for index, message in enumerate((FIRST_MESSAGE, SECOND_MESSAGE)):
        reply = request_json(base_url, prefix + f"/chat?agent_id={agent_id}", {"message": "  " + message + "  "})
        require(reply["status"] == "completed" and reply["response"].startswith("[MOCK]"), "Expected a marked Mock response")
        verify_snapshot(base_url, reply["execution_id"], reply["response"])
        replies.append(reply)
        if index == 0:
            after_statement = request_json(base_url, f"/memories/{agent_id}")
    after = request_json(base_url, prefix + f"/messages?agent_id={agent_id}")
    require(after[:len(before)] == before and len(after) == len(before) + 4, "Earlier transcript changed or new turns are missing")
    require([row["role"] for row in after[-4:]] == ["user", "assistant", "user", "assistant"], "Transcript roles are out of order")
    require([row["content"] for row in after[-4:]] == [FIRST_MESSAGE, replies[0]["response"], SECOND_MESSAGE, replies[1]["response"]],
            "Transcript content differs from submitted turns")
    memories = request_json(base_url, f"/memories/{agent_id}")
    extracted = [row for row in memories if row["content"] == MEMORY_CONTENT]
    require(len(extracted) == 1, "Preference was not extracted once or was duplicated")
    require(memories == after_statement, "Question changed stored preferences")
    logs = request_json(base_url, f'/execution-logs/{replies[1]["execution_id"]}')
    require(any(row["message"] == "conversation_history_loaded" for row in logs), "Previous-turn history did not reach Runtime")
    require(any(row["message"] == "memory_retrieved: Relevant memory loaded" for row in logs), "Relevant memory did not reach Runtime")
    return {"agent_id": agent_id, "conversation_id": conversation_id, "memory_id": extracted[0]["id"],
            "execution_ids": [row["execution_id"] for row in replies], "message_count": len(after),
            "checks_passed": 6, "persistence_verified": verify_persistence, "reply_mode": "fixed_mock_reply"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--verify-persistence", action="store_true")
    args = parser.parse_args()
    try:
        require(get_llm_settings().provider == "mock", "Run this check from the Mock backend container")
        result = check_conversation(args.base_url, args.verify_persistence)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Conversation check failed: {exc}\n")
    print(json.dumps({"status": "passed", **result}))


if __name__ == "__main__":
    main()
