"""Check shared keyword retrieval, scoped previews, and saved memory persistence."""

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from uuid import uuid4

from app.check_demo import request_json, require, verify_snapshot
from app.check_memory import memory_request
from app.config import get_llm_settings


MARKER = "AgentDeskRetrievalPreview"
QUERY = MARKER + "Python " + MARKER + "SQLite"
CONTENTS = [QUERY + " guide.", MARKER + "Python notes.", MARKER + "中文：机器学习。"]


def preview(base_url, agent_id, query, limit=5, status=200):
    return memory_request(base_url, f"/memories/{agent_id}/search?" + urlencode({"query": query, "limit": limit}), status=status)


def check_memory_search(base_url: str, verify_persistence: bool = False) -> dict:
    agents = request_json(base_url, "/agents")
    demos = [row for row in agents if row["name"] == "Demo Agent"]
    others = [row for row in agents if row["name"] == "MCP Order Agent"]
    require(len(demos) == len(others) == 1, "Run the demo initializer first")
    agent_id, other_id = demos[0]["id"], others[0]["id"]
    before = request_json(base_url, f"/memories/{agent_id}")
    existing = [[row for row in before if row["content"] == content] for content in CONTENTS]
    require(all(len(rows) <= 1 for rows in existing), "Duplicate retrieval demo memories exist")
    if verify_persistence:
        require(all(len(rows) == 1 for rows in existing), "Retrieval demo memory was lost; run the initial check before restart")
    saved = [memory_request(base_url, "/memories", {"agent_id": agent_id, "content": "  " + content + "  "}) for content in CONTENTS]
    if verify_persistence:
        require(saved == [rows[0] for rows in existing], "Persisted memory identity or timestamp changed")
    for row in saved:
        require(memory_request(base_url, "/memories", {"agent_id": agent_id, "content": row["content"]}) == row,
                "Exact duplicate policy changed")
    transient = memory_request(base_url, "/memories", {"agent_id": other_id, "content": QUERY + " scope " + uuid4().hex})
    try:
        own_before = request_json(base_url, f"/memories/{agent_id}")
        other_before = request_json(base_url, f"/memories/{other_id}")
        history_before = request_json(base_url, f"/executions?agent_id={agent_id}&limit=100")
        conversations_before = request_json(base_url, f"/conversations?agent_id={agent_id}")
        ranked = preview(base_url, agent_id, QUERY)
        require(ranked["agent_id"] == agent_id and ranked["query"] == QUERY and ranked["limit"] == 5,
                "Preview metadata changed scope, query, or default limit")
        require([row["memory"]["id"] for row in ranked["results"]] == [saved[0]["id"], saved[1]["id"]],
                "Keyword ranking or unrelated-memory filtering failed")
        require([row["score"] for row in ranked["results"]] == [2, 1], "Wrong overlap scores")
        require(all(row["score"] == len(row["matched_terms"]) for row in ranked["results"]), "Match evidence differs from score")
        require(preview(base_url, agent_id, QUERY, 1)["results"] == ranked["results"][:1], "Preview limit was ignored")
        require(preview(base_url, agent_id, QUERY + " " + MARKER + "Python")["results"] == ranked["results"],
                "Repeated query terms inflated scores")
        full_width = "ＡｇｅｎｔＤｅｓｋＲｅｔｒｉｅｖａｌＰｒｅｖｉｅｗＰｙｔｈｏｎ"
        require({row["memory"]["id"] for row in preview(base_url, agent_id, full_width)["results"]}
                == {saved[0]["id"], saved[1]["id"]}, "Full-width matching failed")
        chinese = preview(base_url, agent_id, MARKER + "机器学习")["results"]
        require(chinese and chinese[0]["memory"] == saved[2] and "机器" in chinese[0]["matched_terms"],
                "Chinese/mixed keyword matching failed")
        require(preview(base_url, agent_id, "AgentDeskUnrelated" + uuid4().hex)["results"] == [], "Unrelated query matched a memory")
        scoped = preview(base_url, other_id, QUERY)["results"]
        require(any(row["memory"] == transient for row in scoped)
                and all(row["memory"]["agent_id"] == other_id for row in scoped), "Preview crossed Agent boundaries")
        for query in ("", " \n\t", "x" * 501):
            preview(base_url, agent_id, query, status=422)
        for limit in (0, 21):
            preview(base_url, agent_id, QUERY, limit, status=422)
        preview(base_url, max(row["id"] for row in agents) + 100000, QUERY, status=404)
        require(len(preview(base_url, agent_id, "字" * 500, 20)["query"]) == 500, "Maximum Unicode query did not reach the API")
        require(request_json(base_url, f"/memories/{agent_id}") == own_before
                and request_json(base_url, f"/memories/{other_id}") == other_before, "Preview changed saved memory")
        require(request_json(base_url, f"/executions?agent_id={agent_id}&limit=100") == history_before
                and request_json(base_url, f"/conversations?agent_id={agent_id}") == conversations_before,
                "Preview created or changed a chat/execution")
    finally:
        memory_request(base_url, f'/memories/item/{transient["id"]}?agent_id={other_id}', method="DELETE")

    # This explicit Runtime probe is separate from the read-only preview checks.
    reply = request_json(base_url, f"/agents/{agent_id}/chat", {"message": QUERY})
    require(reply["status"] == "completed" and reply["response"].startswith("[MOCK]"), "Expected a marked Mock response")
    logs = request_json(base_url, f'/execution-logs/{reply["execution_id"]}')
    require(any(row["message"] == "memory_retrieved: Relevant memory loaded" for row in logs), "Runtime did not load previewed keywords")
    verify_snapshot(base_url, reply["execution_id"], reply["response"])
    require(request_json(base_url, f"/memories/{agent_id}") == own_before, "Runtime probe changed saved memories")
    return {"agent_id": agent_id, "memory_ids": [row["id"] for row in saved], "execution_id": reply["execution_id"],
            "checks_passed": 6, "persistence_verified": verify_persistence, "reply_mode": "fixed_mock_reply"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--verify-persistence", action="store_true")
    args = parser.parse_args()
    try:
        require(get_llm_settings().provider == "mock", "Run this check from the Mock backend container")
        result = check_memory_search(args.base_url, args.verify_persistence)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Memory search check failed: {exc}\n")
    print(json.dumps({"status": "passed", **result}))


if __name__ == "__main__":
    main()
