"""Check real MCP order calls, Agent permissions, traces, snapshots, and replay."""

import argparse
import json
from urllib.error import HTTPError, URLError

from app.check_demo import request_json, require, verify_snapshot
from app.config import get_llm_settings
from app.seed_demo import DEMO_AGENT_NAME, MCP_AGENT_NAME


def verify_order_trace(base_url: str, execution_id: int, order_id: str, failed=False) -> None:
    trace = request_json(base_url, f"/executions/{execution_id}/trace")
    expected = ["plan_started", "step_started", "step_failed" if failed else "step_completed",
                "plan_failed" if failed else "plan_completed"]
    require([event["event"] for event in trace] == expected, "Unexpected MCP trace order")
    started = trace[1]
    require(started["tool"] == "get_order" and "transport=mcp_stdio" in started["message"]
            and f'"order_id": "{order_id}"' in started["message"], "MCP trace arguments are missing")
    result = trace[2]
    if failed:
        require(bool(result["error"]) and "not found" in result["error"], "MCP failure detail is missing")
    else:
        require("result=" in result["message"] and '"source": "demo_fixture"' in result["message"],
                "MCP result is missing from the step trace")


def check_mcp_runtime(base_url: str) -> dict:
    agents = request_json(base_url, "/agents")
    matches = [agent for agent in agents if agent["name"] == MCP_AGENT_NAME]
    require(len(matches) == 1, "Expected exactly one MCP Order Agent; rerun the demo initializer")
    agent_id = matches[0]["id"]
    require("get_order" in matches[0]["allowed_tools"], "MCP Order Agent must allow get_order")
    sources = []
    for order_id, status, total in (("DEMO-1001", "shipped", "129.00"),
                                   ("DEMO-1002", "processing", "59.00")):
        reply = request_json(base_url, f"/agents/{agent_id}/chat", {"message": f"Get order {order_id}"})
        require(reply["status"] == "completed", f"{order_id} did not complete")
        order = json.loads(reply["response"])
        require(order.get("order_id") == order_id and order.get("status") == status
                and order.get("total") == total and order.get("currency") == "CNY"
                and order.get("source") == "demo_fixture", "MCP order differs from its demo fixture")
        execution_id = reply["execution_id"]
        verify_order_trace(base_url, execution_id, order_id)
        verify_snapshot(base_url, execution_id, reply["response"])
        snapshot = request_json(base_url, f"/executions/{execution_id}/snapshot")
        steps = json.loads(snapshot["plan_snapshot"])["steps"]
        require(len(steps) == 1 and steps[0]["tool"] == "get_order"
                and steps[0]["arguments"] == {"order_id": order_id}, "MCP plan snapshot differs")
        sources.append(reply)

    source = sources[0]
    replay = request_json(base_url, f'/executions/{source["execution_id"]}/replay', {})
    require(replay["status"] == "completed" and replay["output"] == source["response"]
            and replay["replay_of_execution_id"] == source["execution_id"], "MCP replay differs from its source")
    verify_order_trace(base_url, replay["id"], "DEMO-1001")
    verify_snapshot(base_url, replay["id"], replay["output"])
    history = request_json(base_url, f'/executions/{source["execution_id"]}/replays')
    require(any(row["id"] == replay["id"] for row in history), "MCP replay is missing from history")

    missing = request_json(base_url, f"/agents/{agent_id}/chat", {"message": "Get order DEMO-9999"})
    require(missing["status"] == "failed" and "not found" in missing["response"], "Unknown order must fail")
    record = request_json(base_url, f'/executions/{missing["execution_id"]}')
    require(record["failure_type"] == "tool_execution_error" and record["retry_count"] == 0,
            "MCP failure metadata differs")
    verify_order_trace(base_url, missing["execution_id"], "DEMO-9999", failed=True)

    demos = [agent for agent in agents if agent["name"] == DEMO_AGENT_NAME]
    require(len(demos) == 1 and "get_order" not in demos[0]["allowed_tools"],
            "Permission check requires Demo Agent without get_order permission")
    denied = request_json(base_url, f'/agents/{demos[0]["id"]}/chat', {"message": "Get order DEMO-1001"})
    require(denied["status"] == "completed" and denied["response"].startswith("[MOCK]"),
            "Planner should use a no-tool response without permission")
    denied_trace = request_json(base_url, f'/executions/{denied["execution_id"]}/trace')
    require(all(event["tool"] is None for event in denied_trace), "A disallowed MCP tool was selected")
    return {"agent_id": agent_id, "order_execution_ids": [row["execution_id"] for row in sources],
            "replay_id": replay["id"], "failed_execution_id": missing["execution_id"],
            "permission_execution_id": denied["execution_id"], "checks_passed": 5}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    args = parser.parse_args()
    try:
        require(get_llm_settings().provider == "mock", "Run this check from the Mock backend container")
        result = check_mcp_runtime(args.base_url)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"MCP runtime check failed: {exc}\n")
    print(json.dumps({"status": "passed", "transport": "stdio", **result}))


if __name__ == "__main__":
    main()
