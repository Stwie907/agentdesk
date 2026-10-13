"""Smoke-check a running Mock demo using only Python's standard library."""

import argparse
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from app.config import get_llm_settings


# Compose service traffic should stay on the local Docker network.
HTTP = build_opener(ProxyHandler({}))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def request_json(base_url: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    with HTTP.open(request, timeout=30) as response:
        require(response.headers.get_content_type() == "application/json",
                f"{path} returned HTML or another non-JSON response; check the API proxy")
        return json.load(response)


def verify_snapshot(base_url: str, execution_id: int, expected_output: str) -> None:
    snapshot = request_json(base_url, f"/executions/{execution_id}/snapshot")
    require(snapshot["snapshot_version"] == 1, "Unexpected snapshot version")
    require(snapshot["output_snapshot"] == expected_output, "Snapshot output differs")


def verify_persisted_history(base_url: str, agent_id: int) -> None:
    history = request_json(base_url, f"/executions?agent_id={agent_id}&limit=100")
    sources = [
        row for row in history
        if row["status"] == "completed" and row["output"] == "42"
        and row["replay_of_execution_id"] is None
    ]
    require(bool(sources), "Calculator history was lost after recreating containers")
    source_ids = {row["id"] for row in sources}
    replays = [
        row for row in history
        if row["status"] == "completed" and row["output"] == "42"
        and row["replay_of_execution_id"] in source_ids
    ]
    require(bool(replays), "Replay history was lost after recreating containers")
    replies = [
        row for row in history
        if row["status"] == "completed" and (row["output"] or "").startswith("[MOCK]")
    ]
    require(bool(replies), "Mock chat history was lost after recreating containers")
    for row in (sources[0], replays[0], replies[0]):
        verify_snapshot(base_url, row["id"], row["output"])


def check_demo(base_url: str, verify_persistence: bool = False) -> dict[str, int]:
    with HTTP.open(base_url.rstrip("/") + "/", timeout=10) as response:
        html = response.read().decode("utf-8")
    require('id="root"' in html, "The built React workbench was not served")
    assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
    require(bool(assets), "The workbench contains no production build assets")
    for asset in assets:
        with HTTP.open(base_url.rstrip("/") + asset, timeout=10) as response:
            require(response.headers.get_content_type() != "text/html",
                    f"Build asset {asset} returned the HTML fallback")
            require(bool(response.read()), f"Build asset {asset} is empty")

    require(request_json(base_url, "/health") == {"status": "ok"}, "API health failed")
    agents = request_json(base_url, "/agents")
    demos = [agent for agent in agents if agent["name"] == "Demo Agent"]
    require(len(demos) == 1, "Expected exactly one Demo Agent")
    agent_id = demos[0]["id"]
    require("calculator" in demos[0]["allowed_tools"], "Demo Agent does not allow Calculator")

    if verify_persistence:
        verify_persisted_history(base_url, agent_id)

    calculator = request_json(
        base_url, f"/agents/{agent_id}/chat", {"message": "Calculate 40 + 2"},
    )
    require(calculator["status"] == "completed" and calculator["response"] == "42",
            "The Calculator task did not complete with 42")
    execution_id = calculator["execution_id"]
    trace = request_json(base_url, f"/executions/{execution_id}/trace")
    require(bool(trace) and "provider=mock" in trace[0]["message"], "The server is not in Mock mode")
    require(any(event["tool"] == "calculator" and event["event"] == "step_completed"
                for event in trace), "The Calculator tool did not complete")
    verify_snapshot(base_url, execution_id, "42")

    chat = request_json(base_url, f"/agents/{agent_id}/chat", {"message": "Hello AgentDesk"})
    require(chat["status"] == "completed" and chat["response"].startswith("[MOCK]"),
            "The demo chat reply is not explicitly marked as Mock")
    verify_snapshot(base_url, chat["execution_id"], chat["response"])

    replay = request_json(base_url, f"/executions/{execution_id}/replay", {})
    require(replay["id"] != execution_id and replay["replay_of_execution_id"] == execution_id,
            "Replay is not linked to its source execution")
    require(replay["status"] == "completed" and replay["output"] == "42", "Calculator replay failed")
    verify_snapshot(base_url, replay["id"], "42")
    history = request_json(base_url, f"/executions/{execution_id}/replays")
    require(any(row["id"] == replay["id"] for row in history), "Replay is missing from history")
    return {"agent_id": agent_id, "execution_id": execution_id, "replay_id": replay["id"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--verify-persistence", action="store_true")
    args = parser.parse_args()
    try:
        require(get_llm_settings().provider == "mock", "Run this check from the Mock backend container")
        result = check_demo(args.base_url, args.verify_persistence)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError) as exc:
        parser.exit(1, f"Demo smoke check failed: {exc}\n")
    print(json.dumps({"status": "passed", **result}))


if __name__ == "__main__":
    main()
