import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from mcp import Client
from pydantic import ValidationError

from client import call_read_only_tool, OrderCallError
from server import mcp
from tickets import DemoTicket, TicketStore, ticket_db_path


ROOT = Path(__file__).resolve().parents[1]


def count_tickets(path):
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT COUNT(*) FROM demo_tickets").fetchone()[0]


class TicketStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "nested" / "tickets.db"

    def test_repeated_trimmed_problems_reuse_the_persisted_record(self):
        first = TicketStore(self.path).create("  Demo parcel is delayed.  ")
        second = TicketStore(self.path).create("Demo parcel is delayed.")
        self.assertEqual(first, second)
        self.assertEqual(first.problem, "Demo parcel is delayed.")
        self.assertEqual(first.source, "demo_ticket_store")
        self.assertEqual(first.status, "open")
        self.assertEqual(count_tickets(self.path), 1)

    def test_different_problems_create_distinct_tickets(self):
        first = TicketStore(self.path).create("First demo problem")
        second = TicketStore(self.path).create("Second demo problem")
        self.assertNotEqual(first.ticket_id, second.ticket_id)
        self.assertEqual(count_tickets(self.path), 2)

    def test_concurrent_servers_create_one_ticket_for_the_same_problem(self):
        with ThreadPoolExecutor(max_workers=8) as workers:
            tickets = list(workers.map(lambda _: TicketStore(self.path).create("Concurrent demo problem"), range(16)))
        self.assertEqual(len({ticket.ticket_id for ticket in tickets}), 1)
        self.assertEqual(count_tickets(self.path), 1)

    def test_invalid_problems_do_not_create_a_database(self):
        for problem in (None, True, 42, "", " \n\t", "x" * 2001):
            with self.subTest(problem=str(problem)[:20]), self.assertRaises(ValueError):
                TicketStore(self.path).create(problem)
        self.assertFalse(self.path.parent.exists())

    def test_sql_metacharacters_are_stored_as_problem_text(self):
        problem = "Demo issue'); DROP TABLE demo_tickets; --"
        first = TicketStore(self.path).create(problem)
        self.assertEqual(TicketStore(self.path).create(problem), first)
        self.assertEqual(count_tickets(self.path), 1)

    def test_unknown_schema_version_is_rejected_without_changing_it(self):
        self.path.parent.mkdir()
        with sqlite3.connect(self.path) as connection:
            connection.execute("PRAGMA user_version = 2")
        with self.assertRaisesRegex(ValueError, "schema version"):
            TicketStore(self.path).create("Demo problem")
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0], 0)

    def test_an_unrelated_database_is_not_modified(self):
        self.path.parent.mkdir()
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE unrelated(value TEXT)")
            connection.execute("INSERT INTO unrelated VALUES ('keep')")
        with self.assertRaisesRegex(ValueError, "dedicated database"):
            TicketStore(self.path).create("Demo problem")
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute("SELECT value FROM unrelated").fetchone()[0], "keep")
            self.assertEqual(connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall(), [("unrelated",)])

    def test_corrupted_saved_ticket_is_rejected_without_inserting_a_duplicate(self):
        TicketStore(self.path).create("Demo problem")
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE demo_tickets SET created_at = '2026-02-30T08:00:00Z'")
        with self.assertRaises(ValidationError):
            TicketStore(self.path).create("Demo problem")
        self.assertEqual(count_tickets(self.path), 1)

    def test_configured_store_must_be_an_absolute_file_path(self):
        for value in ("", "relative.db", ":memory:"):
            with self.subTest(value=value), patch.dict(os.environ, {"MCP_TICKET_DB": value}):
                with self.assertRaisesRegex(ValueError, "absolute path"):
                    ticket_db_path()


class TicketProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_arguments_and_read_only_calls_do_not_create_the_ticket_store(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tickets.db"
            with patch.dict(os.environ, {"MCP_TICKET_DB": str(path)}):
                async with Client(mcp) as client:
                    listing = await client.list_tools()
                    tool = next(tool for tool in listing.tools if tool.name == "create_ticket")
                    self.assertFalse(tool.annotations.read_only_hint)
                    self.assertTrue(tool.annotations.idempotent_hint)
                    for arguments in ({}, {"problem": 1}, {"problem": "   "}, {"problem": "x" * 2001}):
                        result = await client.call_tool("create_ticket", arguments)
                        self.assertTrue(result.is_error)
                        self.assertIsNone(result.structured_content)
                    await client.call_tool("get_order", {"order_id": "DEMO-1001"})
                    await client.call_tool("track_order", {"tracking_no": "DEMO-TRACK-1001"})
                    self.assertFalse(path.exists())
                    ticket = await client.call_tool("create_ticket", {"problem": "Demo problem"})
                    self.assertFalse(ticket.is_error)
                    self.assertEqual(count_tickets(path), 1)

    async def test_database_failure_is_a_tool_error_and_the_session_remains_usable(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"MCP_TICKET_DB": directory}):
                async with Client(mcp) as client:
                    failed = await client.call_tool("create_ticket", {"problem": "Demo problem"})
                    self.assertTrue(failed.is_error)
                    self.assertIsNone(failed.structured_content)
                    order = await client.call_tool("get_order", {"order_id": "DEMO-1001"})
                    self.assertFalse(order.is_error)

    async def test_read_only_client_api_cannot_launch_ticket_creation(self):
        with self.assertRaisesRegex(OrderCallError, "read-only"):
            await call_read_only_tool(ROOT / "server.py", "create_ticket", {"problem": "Demo problem"})


class TicketClientTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "tickets.db"

    def call(self, request, path=None):
        return subprocess.run(
            [sys.executable, str(ROOT / "client.py"), "--tool", "create_ticket"],
            input=json.dumps(request), capture_output=True, text=True, encoding="utf-8", timeout=12,
            env={**os.environ, "MCP_TICKET_DB": str(path or self.path)},
        )

    def test_real_subprocess_reconnections_reuse_the_ticket(self):
        first = self.call({"problem": "Demo parcel is delayed."})
        second = self.call({"problem": "  Demo parcel is delayed.  "})
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        response = json.loads(first.stdout)
        self.assertEqual(response, json.loads(second.stdout))
        self.assertEqual(response["tool"], "create_ticket")
        self.assertEqual(response["transport"], "stdio")
        self.assertTrue(response["protocol_version"])
        DemoTicket.model_validate(response["ticket"])
        self.assertEqual(count_tickets(self.path), 1)

    def test_full_length_chinese_problem_fits_the_json_request_limit(self):
        result = self.call({"problem": "示" * 2000})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["ticket"]["problem"], "示" * 2000)

    def test_invalid_requests_are_rejected_without_writing(self):
        for request in ({}, {"problem": False}, {"problem": ""}, {"problem": " \n"},
                        {"problem": "x" * 2001}, {"problem": "Demo", "command": "anything"}):
            with self.subTest(request=str(request)[:40]):
                result = self.call(request)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["status"], "error")
                self.assertFalse(self.path.exists())

    def test_write_failure_returns_only_an_error_envelope(self):
        result = self.call({"problem": "Demo problem"}, Path(self.directory.name))
        self.assertEqual(result.returncode, 1)
        response = json.loads(result.stdout)
        self.assertEqual(response["status"], "error")
        self.assertNotIn("ticket", response)


if __name__ == "__main__":
    unittest.main()
