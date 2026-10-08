import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OrderClientTests(unittest.TestCase):
    def call(self, request, *arguments):
        return subprocess.run(
            [sys.executable, str(ROOT / "client.py"), *arguments],
            input=json.dumps(request), text=True, encoding="utf-8", capture_output=True, timeout=12,
        )

    def test_real_order_call_returns_a_negotiated_mcp_envelope(self):
        result = self.call({"order_id": "DEMO-1001"})
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["transport"], "stdio")
        self.assertTrue(response["protocol_version"])
        self.assertEqual(response["order"]["order_id"], "DEMO-1001")
        self.assertEqual(response["order"]["source"], "demo_fixture")

    def test_unknown_order_is_a_failed_call(self):
        result = self.call({"order_id": "DEMO-9999"})
        self.assertEqual(result.returncode, 1)
        response = json.loads(result.stdout)
        self.assertEqual(response["status"], "error")
        self.assertIn("not found", response["error"])
        self.assertNotIn("order", response)

    def test_invalid_requests_are_rejected_before_connection(self):
        for request in ([], {}, {"order_id": 1001}, {"order_id": "../private-file"},
                        {"order_id": "DEMO-1001", "command": "anything"}):
            with self.subTest(request=request):
                result = self.call(request)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["status"], "error")

    def test_broken_server_cannot_be_a_successful_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            server = Path(directory) / "broken.py"
            server.write_text('print("not JSON", flush=True)\n', encoding="utf-8")
            result = self.call({"order_id": "DEMO-1001"}, "--server", str(server))
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["status"], "error")

    def test_timeout_closes_the_server_process(self):
        with tempfile.TemporaryDirectory() as directory:
            server = Path(directory) / "slow.py"
            pid_file = Path(directory) / "server.pid"
            server.write_text(
                f"import os, time\nfrom pathlib import Path\nPath({str(pid_file)!r}).write_text(str(os.getpid()))\n"
                "time.sleep(30)\n", encoding="utf-8",
            )
            started = time.monotonic()
            result = self.call({"order_id": "DEMO-1001"}, "--server", str(server), "--timeout", "0.3")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["status"], "error")
            self.assertLess(time.monotonic() - started, 10)
            self.assertTrue(pid_file.is_file())
            if os.name == "posix":
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(pid_file.read_text()), 0)

    def test_invalid_configuration_returns_a_json_error(self):
        for timeout in ("0", "nan", "inf"):
            with self.subTest(timeout=timeout):
                result = self.call({"order_id": "DEMO-1001"}, "--timeout", timeout)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["status"], "error")

    def test_incompatible_discovery_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            server = Path(directory) / "incompatible.py"
            server.write_text(
                'from mcp.server import MCPServer\nmcp = MCPServer("wrong contract")\n'
                '@mcp.tool()\ndef get_order(order_id: str) -> dict:\n    return {"order_id": order_id}\n'
                'mcp.run(transport="stdio")\n', encoding="utf-8",
            )
            result = self.call({"order_id": "DEMO-1001"}, "--server", str(server))
            self.assertEqual(result.returncode, 1)
            self.assertIn("incompatible", json.loads(result.stdout)["error"])

    def test_response_for_a_different_order_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            server = Path(directory) / "wrong_order.py"
            server.write_text(
                f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n"
                'from mcp.server import MCPServer\nfrom mcp.types import ToolAnnotations\n'
                'from orders import DemoOrder, OrderId, OrderRepository\nfrom pathlib import Path\n'
                f'repository = OrderRepository(Path({str(ROOT / "fixtures.json")!r}))\n'
                'mcp = MCPServer("wrong order")\n'
                '@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))\n'
                'def get_order(order_id: OrderId) -> DemoOrder:\n    return repository.get("DEMO-1002")\n'
                'mcp.run(transport="stdio")\n', encoding="utf-8",
            )
            result = self.call({"order_id": "DEMO-1001"}, "--server", str(server))
            self.assertEqual(result.returncode, 1)
            self.assertIn("does not match", json.loads(result.stdout)["error"])


if __name__ == "__main__":
    unittest.main()
