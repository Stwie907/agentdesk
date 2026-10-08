"""Check scoring and failures independently of a running backend."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from evaluation.run import (
    API, EvaluationError, evaluate, latency_summary,
    load_dataset, main, markdown_report, write_reports,
)


DATASET_PATH = Path(__file__).parents[1] / "dataset.json"
DATASET = load_dataset(DATASET_PATH)


class FakeAPI:
    base_url = "http://test"

    def __init__(self):
        self.agents = [{"id": 1, "name": "Demo Agent", "allowed_tools": ["calculator"]}]
        self.records = {}
        self.inputs = {case.message: case for case in DATASET.cases if not case.replay_of}
        self.calls = []
        self.overrides = {}
        self.error_path = None

    def request(self, path, payload=None):
        self.calls.append((path, payload))
        if path == self.error_path:
            raise EvaluationError("Injected request failure")
        if path == "/health":
            return {"status": "ok"}
        if path == "/agents":
            return self.agents
        if path.endswith("/chat"):
            case = self.inputs[payload["message"]]
            record = self.create(case, None)
            return {"execution_id": record["id"], "status": record["status"],
                    "response": record["output"]}
        parts = path.strip("/").split("/")
        current_id = int(parts[1])
        if parts[-1] == "replay":
            case = self.inputs[self.records[current_id]["input"]]
            return self.create(case, current_id)
        record = self.records[current_id]
        case = self.inputs[record["input"]]
        if len(parts) == 2:
            return dict(record)
        if parts[-1] == "trace":
            events = self.overrides.get("events", [
                "plan_started", "step_started", "step_completed", "plan_completed",
            ])
            provider = self.overrides.get("provider", "mock")
            return [{"execution_id": current_id, "event": event,
                     "step_index": 0 if event.startswith("step_") else None,
                     "tool": case.expected_tool if event.startswith("step_") else None,
                     "message": f"plan_started: provider={provider}; planner=demo_rules"}
                    for event in events]
        if parts[-1] == "snapshot":
            tool = self.overrides.get("snapshot_tool", case.expected_tool)
            arguments = {"expression": case.expected_expression} if case.expected_tool else {}
            return {"execution_id": current_id, "snapshot_version": 1,
                    "input_snapshot": case.message,
                    "output_snapshot": self.overrides.get("snapshot_output", record["output"]),
                    "plan_snapshot": json.dumps({"steps": [{"input": case.message,
                                                            "tool": tool, "arguments": arguments}]})}
        if parts[-1] == "replays":
            return [] if self.overrides.get("missing_replay") else [
                dict(row) for row in self.records.values()
                if row["replay_of_execution_id"] == current_id
            ]
        raise AssertionError(f"Unexpected request: {path}")

    def create(self, case, source_id):
        current_id = len(self.records) + 1
        record = {"id": current_id, "agent_id": 1, "input": case.message,
                  "output": self.overrides.get("output", case.expected_output),
                  "status": self.overrides.get("status", "completed"),
                  "replay_of_execution_id": source_id}
        self.records[current_id] = record
        return dict(record)


class DatasetTests(unittest.TestCase):
    def load_mutation(self, mutate):
        data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        mutate(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return load_dataset(path)

    def test_rejects_duplicate_ids(self):
        with self.assertRaisesRegex(EvaluationError, "Duplicate"):
            self.load_mutation(lambda data: data["cases"].append(data["cases"][0]))

    def test_rejects_forward_replay_reference(self):
        with self.assertRaisesRegex(EvaluationError, "earlier chat"):
            self.load_mutation(lambda data: data["cases"].reverse())

    def test_rejects_non_mock_provider(self):
        with self.assertRaisesRegex(EvaluationError, "provider mock"):
            self.load_mutation(lambda data: data.update(provider="ollama"))

    def test_rejects_ambiguous_case_operation(self):
        with self.assertRaisesRegex(EvaluationError, "exactly one"):
            self.load_mutation(lambda data: data["cases"][-1].update(message="Hello"))

    def test_rejects_misspelled_case_field(self):
        with self.assertRaisesRegex(EvaluationError, "supported fields"):
            self.load_mutation(lambda data: data["cases"][0].update(expected_ouput="42"))

    def test_rejects_empty_dataset(self):
        with self.assertRaisesRegex(EvaluationError, "at least one"):
            self.load_mutation(lambda data: data.update(cases=[]))


class ScoringTests(unittest.TestCase):
    def test_all_cases_and_replay_pass(self):
        api = FakeAPI()
        report = evaluate(DATASET, api)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["summary"]["passed_cases"], 8)
        source, replay = report["cases"][0], report["cases"][-1]
        self.assertEqual(replay["source_execution_id"], source["execution_id"])
        self.assertNotEqual(replay["execution_id"], source["execution_id"])
        self.assertTrue(replay["checks"]["replay_history"])

    def test_completed_wrong_answer_is_not_a_pass(self):
        api = FakeAPI()
        api.overrides["output"] = "wrong"
        report = evaluate(DATASET, api)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["summary"]["completed_cases"], 7)
        self.assertEqual(report["summary"]["execution_success_rate"], 7 / 8)
        self.assertEqual(report["summary"]["output_accuracy"], 0)
        self.assertEqual(report["summary"]["skipped_cases"], 1)
        self.assertIn("output", report["cases"][0]["failures"])
        self.assertFalse(any(path.endswith("/replay") for path, _ in api.calls))

    def test_missing_or_wrong_snapshot_fails_correct_output(self):
        for change in ({"snapshot_output": "corrupted"}, {"snapshot_tool": None}):
            with self.subTest(change=change):
                api = FakeAPI()
                api.overrides.update(change)
                report = evaluate(DATASET, api)
                self.assertTrue(report["cases"][0]["checks"]["output"])
                self.assertFalse(report["cases"][0]["checks"]["snapshot"])
                self.assertEqual(report["status"], "failed")

    def test_reordered_trace_is_rejected(self):
        api = FakeAPI()
        api.overrides["events"] = ["plan_started", "step_completed", "step_started", "plan_completed"]
        report = evaluate(DATASET, api)
        self.assertIn("trace", report["cases"][0]["failures"])

    def test_non_mock_provider_stops_remaining_submissions(self):
        for provider in ("ollama", "mocked"):
            with self.subTest(provider=provider):
                api = FakeAPI()
                api.overrides["provider"] = provider
                report = evaluate(DATASET, api)
                self.assertEqual(report["summary"]["skipped_cases"], 7)
                self.assertEqual(len(api.records), 1)
                self.assertIn("Mock provider", report["run_error"])

    def test_replay_missing_from_history_fails(self):
        api = FakeAPI()
        api.overrides["missing_replay"] = True
        report = evaluate(DATASET, api)
        self.assertEqual(report["summary"]["passed_cases"], 7)
        self.assertIn("replay_history", report["cases"][-1]["failures"])

    def test_transport_failure_still_reports_every_case(self):
        api = FakeAPI()
        api.error_path = "/agents/1/chat"
        report = evaluate(DATASET, api)
        self.assertEqual(len(report["cases"]), 8)
        self.assertEqual(report["summary"]["failed_cases"], 7)
        self.assertEqual(report["summary"]["latency_ms"]["samples"], 7)
        self.assertEqual(report["summary"]["skipped_cases"], 1)

    def test_preflight_error_makes_no_submissions(self):
        api = FakeAPI()
        api.error_path = "/health"
        report = evaluate(DATASET, api)
        self.assertEqual(report["summary"]["skipped_cases"], 8)
        self.assertEqual(report["summary"]["pass_rate"], 0)
        self.assertEqual(report["summary"]["latency_ms"]["samples"], 0)
        self.assertEqual(len(api.records), 0)

    def test_duplicate_agent_names_require_explicit_id(self):
        api = FakeAPI()
        api.agents.append({"id": 2, "name": "Demo Agent", "allowed_tools": ["calculator"]})
        self.assertEqual(evaluate(DATASET, api)["status"], "failed")
        self.assertEqual(evaluate(DATASET, api, agent_id=1)["status"], "passed")

    def test_latency_uses_nearest_rank_and_ignores_skipped_cases(self):
        values = [{"latency_ms": value} for value in range(1, 21)] + [{"latency_ms": None}]
        summary = latency_summary(values)
        self.assertEqual(summary, {"samples": 20, "mean": 10.5, "median": 10.5, "p95": 19})

    def test_failed_cli_run_saves_reports_and_exits_nonzero(self):
        api = FakeAPI()
        api.error_path = "/health"
        with tempfile.TemporaryDirectory() as directory, patch("evaluation.run.API", return_value=api):
            with patch("builtins.print"):
                self.assertEqual(main(["--output-dir", directory]), 1)
            report = json.loads((Path(directory) / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertTrue((Path(directory) / "report.md").exists())

    def test_report_preserves_json_and_escapes_markdown_diagnostics(self):
        api = FakeAPI()
        api.overrides["output"] = "wrong | value\n<details>"
        report = evaluate(DATASET, api)
        text = markdown_report(report)
        self.assertIn("wrong &#124; value &lt;details&gt;", text)
        with tempfile.TemporaryDirectory() as directory:
            write_reports(report, Path(directory))
            saved = json.loads((Path(directory) / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["cases"][0]["actual_output"], "wrong | value\n<details>")


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(404 if self.path == "/missing" else 200)
                self.send_header("Content-Type", "text/html" if self.path == "/html" else "application/json")
                self.end_headers()
                self.wfile.write(b"<html>fallback</html>" if self.path == "/html" else b'{"status":"ok"}')

            def log_message(self, *_):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.api = API(f"http://127.0.0.1:{cls.server.server_port}")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_rejects_spa_html_as_api_json(self):
        with self.assertRaisesRegex(EvaluationError, "expected JSON"):
            self.api.request("/html")

    def test_preserves_http_status_in_error(self):
        with self.assertRaisesRegex(EvaluationError, "HTTP 404"):
            self.api.request("/missing")

    def test_local_requests_bypass_environment_proxy(self):
        with patch.dict("os.environ", {"HTTP_PROXY": "http://127.0.0.1:1", "NO_PROXY": ""}):
            api = API(self.api.base_url)
            self.assertEqual(api.request("/health"), {"status": "ok"})

    def test_rejects_non_finite_or_non_positive_timeout(self):
        for timeout in (0, -1, float("inf"), float("nan")):
            with self.subTest(timeout=timeout), self.assertRaises(EvaluationError):
                API(self.api.base_url, timeout)


if __name__ == "__main__":
    unittest.main()
