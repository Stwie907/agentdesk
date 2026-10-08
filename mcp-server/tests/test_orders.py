"""Validate demo data and MCP behavior with the actual SDK and transport."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest

from mcp import Client
from pydantic import ValidationError

from check import check_server, main
from orders import OrderRepository
from server import mcp


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures.json"


class RepositoryTests(unittest.TestCase):
    def modified_repository(self, mutate):
        data = json.loads(FIXTURES.read_text(encoding="utf-8"))
        mutate(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixtures.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return OrderRepository(path)

    def test_rejects_duplicate_order_ids(self):
        with self.assertRaisesRegex(ValueError, "Duplicate demo order"):
            self.modified_repository(lambda data: data["orders"].append(data["orders"][0]))

    def test_rejects_incorrect_fixture_version(self):
        for version in (True, 2, "1"):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "schema_version"):
                self.modified_repository(lambda data: data.update(schema_version=version))

    def test_rejects_invalid_order_contract(self):
        for field, value in (("currency", "USD"), ("total", "free"), ("items", []),
                             ("source", "production"), ("order_id", "real-order-123")):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.modified_repository(lambda data: data["orders"][0].update({field: value}))

    def test_rejects_invalid_item_quantity(self):
        for quantity in (0, -1, True, "1"):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                self.modified_repository(lambda data: data["orders"][0]["items"][0].update(quantity=quantity))

    def test_callers_cannot_modify_cached_order_items(self):
        repository = OrderRepository(FIXTURES)
        order = repository.get("DEMO-1001")
        order.items.clear()
        self.assertEqual(len(repository.get("DEMO-1001").items), 1)

    def test_missing_order_does_not_create_fixture_data(self):
        original = FIXTURES.read_bytes()
        repository = OrderRepository(FIXTURES)
        self.assertIsNone(repository.get("DEMO-9999"))
        self.assertEqual(FIXTURES.read_bytes(), original)

    def test_rejects_ids_outside_demo_format(self):
        repository = OrderRepository(FIXTURES)
        for order_id in ("", " DEMO-1001", "../fixtures.json", None, 1001):
            with self.subTest(order_id=order_id), self.assertRaises(ValueError):
                repository.get(order_id)


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_error_does_not_end_the_client_session(self):
        async with Client(mcp) as client:
            missing = await client.call_tool("get_order", {"order_id": "DEMO-9999"})
            self.assertTrue(missing.is_error)
            self.assertIsNone(missing.structured_content)
            order = await client.call_tool("get_order", {"order_id": "DEMO-1001"})
            self.assertFalse(order.is_error)
            self.assertEqual(order.structured_content["source"], "demo_fixture")

    async def test_schema_rejects_invalid_arguments_before_lookup(self):
        async with Client(mcp) as client:
            for arguments in ({}, {"order_id": 1001}, {"order_id": "../fixtures.json"}):
                with self.subTest(arguments=arguments):
                    result = await client.call_tool("get_order", arguments)
                    self.assertTrue(result.is_error)
                    self.assertIsNone(result.structured_content)
            valid = await client.call_tool("get_order", {"order_id": "DEMO-1002"})
            self.assertEqual(valid.structured_content["status"], "processing")

    async def test_real_stdio_process_passes_all_protocol_checks(self):
        report = await check_server(ROOT / "server.py")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["transport"], "stdio")
        self.assertEqual(report["checks_passed"], 16)
        self.assertEqual(report["tool_names"], ["get_order", "track_order"])

    async def test_reconnection_uses_unchanged_fixture_data(self):
        async with Client(mcp) as first:
            result = await first.call_tool("get_order", {"order_id": "DEMO-1001"})
            result.structured_content["items"].clear()
        async with Client(mcp) as second:
            result = await second.call_tool("get_order", {"order_id": "DEMO-1001"})
            self.assertEqual(len(result.structured_content["items"]), 1)


class CommandTests(unittest.TestCase):
    def test_checker_reports_broken_server_and_returns_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            server_path = Path(directory) / "broken.py"
            server_path.write_text("print('not a JSON-RPC message')\n", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output), self.assertLogs("mcp.client.stdio", level="ERROR"):
                code = main(["--server", str(server_path), "--timeout", "2"])
            self.assertEqual(code, 1)
            report = json.loads(output.getvalue())
            self.assertEqual(report["status"], "failed")
            self.assertTrue(report["error"])

    def test_checker_times_out_without_reporting_success(self):
        with tempfile.TemporaryDirectory() as directory:
            server_path = Path(directory) / "unresponsive.py"
            server_path.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
            output = io.StringIO()
            started = time.monotonic()
            with contextlib.redirect_stdout(output):
                code = main(["--server", str(server_path), "--timeout", "0.1"])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.getvalue())["status"], "failed")
            self.assertLess(time.monotonic() - started, 5)

    def test_invalid_timeout_is_a_configuration_error(self):
        for timeout in ("0", "-1", "nan", "inf"):
            with self.subTest(timeout=timeout), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(["--timeout", timeout])
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
