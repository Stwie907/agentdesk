"""Evaluate a running Mock backend through its public Runtime V4 APIs."""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


class EvaluationError(RuntimeError):
    """A dataset, setup, or HTTP contract could not be evaluated."""


@dataclass(frozen=True)
class Case:
    id: str
    message: str
    expected_output: str
    expected_tool: str | None
    expected_expression: str | None = None
    replay_of: str | None = None


@dataclass(frozen=True)
class Dataset:
    name: str
    sha256: str
    cases: tuple[Case, ...]


def load_dataset(path: Path) -> Dataset:
    raw = path.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int:
        raise EvaluationError("Dataset schema_version must be the integer 1")
    if data["schema_version"] != 1 or data.get("provider") != "mock":
        raise EvaluationError("Only schema version 1 and provider mock are supported")
    name = data.get("name")
    rows = data.get("cases")
    if not isinstance(name, str) or not name.strip():
        raise EvaluationError("Dataset name must be a non-empty string")
    if not isinstance(rows, list) or not rows:
        raise EvaluationError("Dataset must contain at least one case")
    cases = {}
    allowed = {"id", "message", "replay_of", "expected_output",
               "expected_tool", "expected_expression"}
    for row in rows:
        if not isinstance(row, dict) or set(row) - allowed:
            raise EvaluationError("Case must be an object with supported fields")
        case_id = row.get("id")
        if not isinstance(case_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", case_id):
            raise EvaluationError("Case id must use lowercase letters, digits, or underscores")
        if case_id in cases:
            raise EvaluationError(f"Duplicate case id: {case_id}")
        output = row.get("expected_output")
        tool = row.get("expected_tool")
        expression = row.get("expected_expression")
        if not isinstance(output, str) or "expected_tool" not in row:
            raise EvaluationError(f"{case_id}: expected_output and expected_tool are required")
        if tool not in (None, "calculator"):
            raise EvaluationError(f"{case_id}: expected_tool must be calculator or null")
        if tool == "calculator" and (not isinstance(expression, str) or not expression):
            raise EvaluationError(f"{case_id}: calculator cases require expected_expression")
        if tool is None and expression is not None:
            raise EvaluationError(f"{case_id}: a reply case cannot expect a tool expression")
        if ("message" in row) == ("replay_of" in row):
            raise EvaluationError(f"{case_id}: provide exactly one of message or replay_of")
        source = row.get("replay_of")
        if source is not None:
            if not isinstance(source, str) or source not in cases or cases[source].replay_of:
                raise EvaluationError(f"{case_id}: replay_of must reference an earlier chat case")
            message = cases[source].message
        else:
            message = row.get("message")
        if not isinstance(message, str) or not message.strip():
            raise EvaluationError(f"{case_id}: message must be a non-empty string")
        cases[case_id] = Case(case_id, message, output, tool, expression, source)
    return Dataset(name, hashlib.sha256(raw).hexdigest(), tuple(cases.values()))


class API:
    def __init__(self, base_url: str, timeout: float = 30):
        parsed = urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise EvaluationError("base-url must be an HTTP or HTTPS URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise EvaluationError("base-url cannot contain credentials, query, or fragment")
        if not math.isfinite(timeout) or timeout <= 0:
            raise EvaluationError("timeout must be a positive finite number")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Local Compose traffic must not be routed through a host proxy.
        self.http = build_opener(ProxyHandler({}))

    def request(self, path: str, payload: dict | None = None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(self.base_url + path, data=data, headers={
            "Accept": "application/json", "Content-Type": "application/json",
        })
        try:
            with self.http.open(request, timeout=self.timeout) as response:
                if response.headers.get_content_type() != "application/json":
                    raise EvaluationError(f"{path}: expected JSON; check the frontend API proxy")
                return json.load(response)
        except HTTPError as exc:
            detail = exc.read(1000).decode("utf-8", errors="replace")
            raise EvaluationError(f"{path}: HTTP {exc.code}: {detail}") from exc
        except (URLError, OSError, ValueError) as exc:
            raise EvaluationError(f"{path}: {exc}") from exc


def object_response(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise EvaluationError(f"{label}: expected a JSON object")
    return value


def execution_id(value) -> int:
    if type(value) is not int or value <= 0:
        raise EvaluationError("Execution response has no positive integer id")
    return value


def select_agent(api: API, agent_id: int | None, agent_name: str) -> dict:
    if api.request("/health") != {"status": "ok"}:
        raise EvaluationError("Backend health check failed")
    agents = api.request("/agents")
    if not isinstance(agents, list) or any(not isinstance(row, dict) for row in agents):
        raise EvaluationError("/agents: expected a JSON array of agents")
    matches = [row for row in agents if (
        row.get("id") == agent_id if agent_id is not None else row.get("name") == agent_name
    )]
    if len(matches) != 1:
        raise EvaluationError("Expected one selected agent; start and seed the Mock demo, "
                              "or select an existing agent with --agent-id")
    agent = matches[0]
    execution_id(agent.get("id"))
    tools = agent.get("allowed_tools")
    if not isinstance(tools, list) or "calculator" not in tools:
        raise EvaluationError("The selected agent must allow the calculator tool")
    return agent


def empty_result(case: Case, reason: str | None = None) -> dict:
    return {
        "case_id": case.id, "operation": "replay" if case.replay_of else "chat",
        "input": case.message, "expected_output": case.expected_output,
        "actual_output": None, "execution_id": None, "source_execution_id": None,
        "execution_status": None, "latency_ms": None, "passed": False,
        "skipped": reason is not None, "checks": {}, "failures": [], "error": reason,
    }


def evaluate_case(case: Case, api: API, agent_id: int, source: dict | None) -> dict:
    result = empty_result(case)
    checks = result["checks"]
    if case.replay_of:
        if source is None or not source["passed"]:
            return empty_result(case, f"Source case {case.replay_of} did not pass")
        result["source_execution_id"] = source["execution_id"]
        path = f"/executions/{source['execution_id']}/replay"
        payload = {}
    else:
        path = f"/agents/{agent_id}/chat"
        payload = {"message": case.message}
    try:
        started = time.perf_counter()
        try:
            response = object_response(api.request(path, payload), path)
        finally:
            result["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        current_id = execution_id(response.get("id" if case.replay_of else "execution_id"))
        result["execution_id"] = current_id
        result["execution_status"] = response.get("status")
        output = response.get("output" if case.replay_of else "response")
        result["actual_output"] = output
        checks["completed"] = result["execution_status"] == "completed"
        checks["output"] = output == case.expected_output

        execution = object_response(api.request(f"/executions/{current_id}"), "execution")
        checks["execution_record"] = (
            execution.get("id") == current_id and execution.get("agent_id") == agent_id
            and execution.get("input") == case.message and execution.get("output") == output
            and execution.get("status") == result["execution_status"]
            and execution.get("replay_of_execution_id") == result["source_execution_id"]
        )
        trace = api.request(f"/executions/{current_id}/trace")
        if not isinstance(trace, list) or any(not isinstance(row, dict) for row in trace):
            raise EvaluationError("Trace must be a JSON array of events")
        checks["trace"] = (
            [row.get("event") for row in trace]
            == ["plan_started", "step_started", "step_completed", "plan_completed"]
            and all(row.get("execution_id") == current_id for row in trace)
            and all(row.get("tool") == case.expected_tool and row.get("step_index") == 0
                    for row in trace if row.get("event") in ("step_started", "step_completed"))
        )
        if not case.replay_of:
            checks["provider"] = bool(trace and re.search(
                r"(?:^|[;:\s])provider=mock(?:[;\s]|$)", str(trace[0].get("message", "")),
            ))

        snapshot = object_response(api.request(f"/executions/{current_id}/snapshot"), "snapshot")
        plan = json.loads(snapshot.get("plan_snapshot") or "null")
        steps = plan.get("steps") if isinstance(plan, dict) else None
        arguments = {"expression": case.expected_expression} if case.expected_tool else {}
        checks["snapshot"] = (
            snapshot.get("execution_id") == current_id
            and type(snapshot.get("snapshot_version")) is int
            and snapshot["snapshot_version"] == 1
            and snapshot.get("input_snapshot") == case.message
            and snapshot.get("output_snapshot") == output
            and isinstance(steps, list) and len(steps) == 1 and isinstance(steps[0], dict)
            and steps[0].get("tool") == case.expected_tool
            and steps[0].get("arguments") == arguments
            and steps[0].get("input") == case.message
        )
        if case.replay_of:
            checks["replay_link"] = current_id != source["execution_id"]
            history = api.request(f"/executions/{source['execution_id']}/replays")
            checks["replay_history"] = isinstance(history, list) and any(
                isinstance(row, dict) and row.get("id") == current_id
                and row.get("replay_of_execution_id") == source["execution_id"]
                for row in history
            )
    except (EvaluationError, ValueError, TypeError) as exc:
        result["error"] = str(exc)
    result["failures"] = [name for name, passed in checks.items() if not passed]
    result["passed"] = result["error"] is None and bool(checks) and all(checks.values())
    return result


def latency_summary(results: list[dict]) -> dict:
    values = sorted(row["latency_ms"] for row in results if row["latency_ms"] is not None)
    if not values:
        return {"samples": 0, "mean": None, "median": None, "p95": None}
    return {"samples": len(values), "mean": round(statistics.fmean(values), 3),
            "median": round(statistics.median(values), 3),
            "p95": values[math.ceil(0.95 * len(values)) - 1]}


def build_summary(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(row["passed"] for row in results)
    skipped = sum(row["skipped"] for row in results)
    completed = sum(row["execution_status"] == "completed" for row in results)
    correct = sum(row["checks"].get("output", False) for row in results)
    return {
        "total_cases": total, "passed_cases": passed,
        "failed_cases": total - passed - skipped, "skipped_cases": skipped,
        "completed_cases": completed, "correct_outputs": correct,
        "pass_rate": passed / total, "execution_success_rate": completed / total,
        "output_accuracy": correct / total, "latency_ms": latency_summary(results),
    }


def evaluate(dataset: Dataset, api: API, agent_id: int | None = None,
             agent_name: str = "Demo Agent", revision: str = "unknown") -> dict:
    results = []
    previous = {}
    agent = None
    run_error = None
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        agent = select_agent(api, agent_id, agent_name)
    except EvaluationError as exc:
        run_error = str(exc)
    for case in dataset.cases:
        if run_error:
            result = empty_result(case, run_error)
        else:
            result = evaluate_case(case, api, agent["id"], previous.get(case.replay_of))
            if result["checks"].get("provider") is False:
                run_error = "Mock provider could not be verified. Start the explicit Mock demo."
        results.append(result)
        previous[case.id] = result
    return {
        "report_version": 1, "status": "passed" if all(row["passed"] for row in results) else "failed",
        "started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(),
        "revision": revision, "dataset": {"name": dataset.name, "sha256": dataset.sha256},
        "expected_provider": "mock", "base_url": api.base_url,
        "agent": agent, "run_error": run_error, "summary": build_summary(results), "cases": results,
    }


def markdown_cell(value) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(
        ">", "&gt;").replace("|", "&#124;").replace("\r", " ").replace("\n", " ")


def markdown_report(report: dict) -> str:
    summary = report["summary"]
    latency = summary["latency_ms"]
    lines = [
        "# AgentDesk Runtime V4 evaluation", "",
        f"Status: **{report['status']}**", "",
        f"Dataset: `{report['dataset']['name']}`", "",
        f"Dataset SHA-256: `{report['dataset']['sha256']}`", "",
        f"Started: {report['started_at']}", "", f"Revision: {markdown_cell(report['revision'])}", "",
        "| Metric | Result |", "| --- | --- |",
        f"| Passed cases | {summary['passed_cases']}/{summary['total_cases']} |",
        f"| Failed / skipped cases | {summary['failed_cases']} / {summary['skipped_cases']} |",
        f"| Overall pass rate | {summary['pass_rate']:.1%} |",
        f"| Execution success rate | {summary['execution_success_rate']:.1%} |",
        f"| Exact output accuracy | {summary['output_accuracy']:.1%} |",
        f"| POST latency samples | {latency['samples']} |",
        f"| Mean / median / p95 latency (ms) | {latency['mean']} / {latency['median']} / {latency['p95']} |", "",
        "Latency covers chat/replay POST requests, including failed requests. "
        "Follow-up inspection GET requests are excluded.", "",
        "| Case | Operation | Result | Execution | Latency (ms) | Expected | Actual | Diagnostics |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["cases"]:
        status = "skipped" if row["skipped"] else "passed" if row["passed"] else "failed"
        diagnostics = row["error"] or ", ".join(row["failures"]) or "-"
        cells = [row["case_id"], row["operation"], status, row["execution_id"],
                 row["latency_ms"], row["expected_output"], row["actual_output"], diagnostics]
        lines.append("| " + " | ".join(markdown_cell(cell) for cell in cells) + " |")
    lines += ["", "This is a deterministic Runtime regression suite. It does not measure "
              "general language-model quality, Router/RAG accuracy, hallucinations, or tokens.", ""]
    return "\n".join(lines)


def write_reports(report: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8",
    )
    (output_dir / "report.md").write_text(markdown_report(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(__file__).with_name("dataset.json"))
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).with_name("reports"))
    parser.add_argument("--timeout", type=float, default=30)
    agent = parser.add_mutually_exclusive_group()
    agent.add_argument("--agent-id", type=int)
    agent.add_argument("--agent-name", default="Demo Agent")
    parser.add_argument("--revision", default=os.environ.get("EVALUATION_REVISION", "unknown"))
    args = parser.parse_args(argv)
    try:
        if args.agent_id is not None and args.agent_id <= 0:
            raise EvaluationError("agent-id must be positive")
        dataset = load_dataset(args.dataset)
        api = API(args.base_url, args.timeout)
        report = evaluate(dataset, api, args.agent_id, args.agent_name, args.revision)
        write_reports(report, args.output_dir)
    except (EvaluationError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": report["status"], **report["summary"]}, ensure_ascii=False))
    print(f"Reports: {args.output_dir / 'report.json'} and {args.output_dir / 'report.md'}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
