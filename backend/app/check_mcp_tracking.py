"""Check shipment tasks, permissions, errors, snapshots, and real MCP replay."""

import argparse
import json
from urllib.error import HTTPError, URLError

from app.check_demo import request_json, require, verify_snapshot
from app.config import get_llm_settings
from app.seed_demo import MCP_AGENT_NAME, TRACKING_AGENT_NAME


def verify_tracking_trace(base_url: str, execution_id: int, tracking_no: str, failed=False) -> None:
    trace = request_json(base_url, f"/executions/{execution_id}/trace")
    expected = ["plan_started", "step_started", "step_failed" if failed else "step_completed",
                "plan_failed" if failed else "plan_completed"]
    require([event["event"] for event in trace] == expected, "Unexpected tracking trace order")
    require(trace[1]["tool"] == "track_order" and "transport=mcp_stdio" in trace[1]["message"]
            and f'"tracking_no": "{tracking_no}"' in trace[1]["message"], "Tracking trace arguments are missing")
    if failed:
        require(bool(trace[2]["error"]) and "not found" in trace[2]["error"], "Tracking error detail is missing")
    else:
        require("result=" in trace[2]["message"] and '"source": "demo_fixture"' in trace[2]["message"],
                "Tracking result is missing from the step trace")


def check_mcp_tracking(base_url: str) -> dict:
    agents = request_json(base_url, "/agents")
    matches = [agent for agent in agents if agent["name"] == TRACKING_AGENT_NAME]
    require(len(matches) == 1, "Expected exactly one MCP Logistics Agent; rerun the demo initializer")
    agent_id = matches[0]["id"]
    require("track_order" in matches[0]["allowed_tools"], "MCP Logistics Agent must allow track_order")
    sources = []
    for message, tracking_no, order_id, status, event_count in (
        ("Track order DEMO-TRACK-1001", "DEMO-TRACK-1001", "DEMO-1001", "in_transit", 3),
        ("查询物流DEMO-TRACK-1002", "DEMO-TRACK-1002", "DEMO-1002", "label_created", 1),
    ):
        reply = request_json(base_url, f"/agents/{agent_id}/chat", {"message": message})
        require(reply["status"] == "completed", f"{tracking_no} did not complete")
        shipment = json.loads(reply["response"])
        events = shipment.get("events")
        require(shipment.get("tracking_no") == tracking_no and shipment.get("order_id") == order_id
                and shipment.get("status") == status and shipment.get("carrier") == "Demo Courier"
                and shipment.get("source") == "demo_fixture" and isinstance(events, list)
                and len(events) == event_count and events[-1].get("status") == status,
                "Tracking differs from its demo fixture")
        execution_id = reply["execution_id"]
        verify_tracking_trace(base_url, execution_id, tracking_no)
        verify_snapshot(base_url, execution_id, reply["response"])
        snapshot = request_json(base_url, f"/executions/{execution_id}/snapshot")
        steps = json.loads(snapshot["plan_snapshot"])["steps"]
        require(len(steps) == 1 and steps[0]["tool"] == "track_order"
                and steps[0]["arguments"] == {"tracking_no": tracking_no}, "Tracking plan snapshot differs")
        sources.append(reply)

    source = sources[0]
    replay = request_json(base_url, f'/executions/{source["execution_id"]}/replay', {})
    require(replay["status"] == "completed" and replay["output"] == source["response"]
            and replay["replay_of_execution_id"] == source["execution_id"], "Tracking replay differs")
    verify_tracking_trace(base_url, replay["id"], "DEMO-TRACK-1001")
    verify_snapshot(base_url, replay["id"], replay["output"])
    history = request_json(base_url, f'/executions/{source["execution_id"]}/replays')
    require(any(row["id"] == replay["id"] for row in history), "Tracking replay is missing from history")

    missing = request_json(base_url, f"/agents/{agent_id}/chat", {"message": "Track order DEMO-TRACK-9999"})
    require(missing["status"] == "failed" and "not found" in missing["response"], "Unknown tracking must fail")
    record = request_json(base_url, f'/executions/{missing["execution_id"]}')
    require(record["failure_type"] == "tool_execution_error" and record["retry_count"] == 0,
            "Tracking failure metadata differs")
    verify_tracking_trace(base_url, missing["execution_id"], "DEMO-TRACK-9999", failed=True)

    order_agents = [agent for agent in agents if agent["name"] == MCP_AGENT_NAME]
    require(len(order_agents) == 1 and "track_order" not in order_agents[0]["allowed_tools"],
            "Permission check requires MCP Order Agent without track_order permission")
    denied = request_json(base_url, f'/agents/{order_agents[0]["id"]}/chat',
                          {"message": "Track order DEMO-TRACK-1001"})
    require(denied["status"] == "completed" and denied["response"].startswith("[MOCK]"),
            "Tracking without permission must use a no-tool response")
    trace = request_json(base_url, f'/executions/{denied["execution_id"]}/trace')
    require(all(event["tool"] is None for event in trace), "A disallowed tracking tool was selected")
    return {"agent_id": agent_id, "tracking_execution_ids": [row["execution_id"] for row in sources],
            "replay_id": replay["id"], "failed_execution_id": missing["execution_id"],
            "permission_execution_id": denied["execution_id"], "checks_passed": 5}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    args = parser.parse_args()
    try:
        require(get_llm_settings().provider == "mock", "Run this check from the Mock backend container")
        result = check_mcp_tracking(args.base_url)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"MCP tracking check failed: {exc}\n")
    print(json.dumps({"status": "passed", "transport": "stdio", **result}))


if __name__ == "__main__":
    main()
