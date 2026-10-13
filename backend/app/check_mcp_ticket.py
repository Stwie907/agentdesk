"""Check local ticket writes, deduplication, replay, permissions, and persistence."""

import argparse
import json
import re
from urllib.error import HTTPError, URLError

from app.check_demo import request_json, require, verify_snapshot
from app.config import get_llm_settings
from app.seed_demo import TICKET_AGENT_NAME, TRACKING_AGENT_NAME


FIRST_PROBLEM = "Demo parcel is delayed."
SECOND_PROBLEM = "示例订单需要帮助。"


def verify_ticket_trace(base_url: str, execution_id: int, problem: str, output: str) -> None:
    trace = request_json(base_url, f"/executions/{execution_id}/trace")
    require([event["event"] for event in trace] == ["plan_started", "step_started", "step_completed", "plan_completed"],
            "Unexpected ticket trace order")
    require(trace[1]["tool"] == "create_ticket" and "transport=mcp_stdio" in trace[1]["message"]
            and json.dumps({"problem": problem}, ensure_ascii=False) in trace[1]["message"], "Ticket trace arguments differ")
    require("result=" + output in trace[2]["message"], "Ticket result is missing from the trace")
    verify_snapshot(base_url, execution_id, output)
    snapshot = request_json(base_url, f"/executions/{execution_id}/snapshot")
    steps = json.loads(snapshot["plan_snapshot"])["steps"]
    require(len(steps) == 1 and steps[0]["tool"] == "create_ticket" and steps[0]["arguments"] == {"problem": problem},
            "Ticket plan snapshot differs")


def check_mcp_ticket(base_url: str, verify_persistence: bool = False) -> dict:
    agents = request_json(base_url, "/agents")
    matches = [agent for agent in agents if agent["name"] == TICKET_AGENT_NAME]
    require(len(matches) == 1, "Expected one MCP Ticket Agent; rerun the demo initializer")
    agent_id = matches[0]["id"]
    require("create_ticket" in matches[0]["allowed_tools"], "MCP Ticket Agent must allow create_ticket")
    previous = {}
    if verify_persistence:
        history = request_json(base_url, f"/executions?agent_id={agent_id}&limit=100")
        for execution in history:
            if execution["status"] == "completed" and execution["output"]:
                try:
                    ticket = json.loads(execution["output"])
                except (ValueError, TypeError):
                    continue
                if isinstance(ticket, dict) and ticket.get("source") == "demo_ticket_store":
                    previous.setdefault(ticket.get("problem"), execution["output"])
        require(FIRST_PROBLEM in previous and SECOND_PROBLEM in previous,
                "Ticket execution history was lost; run the initial ticket check before persistence verification")

    sources = []
    for message, problem in (("Create ticket " + FIRST_PROBLEM, FIRST_PROBLEM),
                             ("创建工单" + SECOND_PROBLEM, SECOND_PROBLEM)):
        reply = request_json(base_url, f"/agents/{agent_id}/chat", {"message": message})
        require(reply["status"] == "completed", "Ticket creation did not complete")
        ticket = json.loads(reply["response"])
        require(ticket.get("source") == "demo_ticket_store" and ticket.get("problem") == problem
                and ticket.get("status") == "open"
                and re.fullmatch(r"DEMO-TICKET-[a-f0-9]{32}", ticket.get("ticket_id", ""))
                and bool(ticket.get("created_at")), "Ticket output is incompatible")
        if verify_persistence:
            require(reply["response"] == previous[problem], "The MCP ticket store was lost after service recreation")
        verify_ticket_trace(base_url, reply["execution_id"], problem, reply["response"])
        sources.append(reply)
    require(json.loads(sources[0]["response"])["ticket_id"] != json.loads(sources[1]["response"])["ticket_id"],
            "Distinct problems reused one ticket")

    source = sources[0]
    repeated = request_json(base_url, f"/agents/{agent_id}/chat", {"message": "Create ticket   " + FIRST_PROBLEM + "  "})
    require(repeated["status"] == "completed" and repeated["response"] == source["response"], "Duplicate ticket was created")
    verify_ticket_trace(base_url, repeated["execution_id"], FIRST_PROBLEM, repeated["response"])
    replay = request_json(base_url, f'/executions/{source["execution_id"]}/replay', {})
    require(replay["status"] == "completed" and replay["output"] == source["response"]
            and replay["replay_of_execution_id"] == source["execution_id"], "Ticket replay differs")
    verify_ticket_trace(base_url, replay["id"], FIRST_PROBLEM, replay["output"])
    history = request_json(base_url, f'/executions/{source["execution_id"]}/replays')
    require(any(row["id"] == replay["id"] for row in history), "Ticket replay is missing from history")

    readers = [agent for agent in agents if agent["name"] == TRACKING_AGENT_NAME]
    require(len(readers) == 1 and "create_ticket" not in readers[0]["allowed_tools"],
            "Permission check requires MCP Logistics Agent without ticket write permission")
    denied = request_json(base_url, f'/agents/{readers[0]["id"]}/chat', {"message": "Create ticket Permission demo problem"})
    require(denied["status"] == "completed" and denied["response"].startswith("[MOCK]"), "Disallowed write selected a tool")
    trace = request_json(base_url, f'/executions/{denied["execution_id"]}/trace')
    require(all(event["tool"] is None for event in trace), "A disallowed write was traced")
    return {"agent_id": agent_id, "ticket_execution_ids": [reply["execution_id"] for reply in sources],
            "ticket_ids": [json.loads(reply["response"])["ticket_id"] for reply in sources],
            "duplicate_execution_id": repeated["execution_id"], "replay_id": replay["id"],
            "permission_execution_id": denied["execution_id"], "checks_passed": 5,
            "persistence_verified": verify_persistence}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--verify-persistence", action="store_true")
    args = parser.parse_args()
    try:
        require(get_llm_settings().provider == "mock", "Run this check from the Mock backend container")
        result = check_mcp_ticket(args.base_url, args.verify_persistence)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"MCP ticket check failed: {exc}\n")
    print(json.dumps({"status": "passed", "transport": "stdio", **result}))


if __name__ == "__main__":
    main()
