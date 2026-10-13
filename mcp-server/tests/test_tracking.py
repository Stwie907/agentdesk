import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mcp import Client
from pydantic import ValidationError

from orders import OrderRepository
from server import mcp
from tracking import TrackingRepository


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tracking-fixtures.json"


class TrackingRepositoryTests(unittest.TestCase):
    def changed(self, mutate, orders=None):
        data = json.loads(FIXTURES.read_text(encoding="utf-8"))
        mutate(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tracking.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return TrackingRepository(path, orders)

    def test_duplicate_tracking_numbers_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate demo tracking"):
            self.changed(lambda data: data["shipments"].append(data["shipments"][0]))

    def test_fixture_version_is_an_integer_one(self):
        for version in (True, "1", 2):
            with self.subTest(version=version), self.assertRaises(ValueError):
                self.changed(lambda data: data.update(schema_version=version))

    def test_invalid_shipment_fields_are_rejected(self):
        for field, value in (("tracking_no", "DEMO-1001"), ("order_id", "real-order"),
                             ("carrier", ""), ("events", []), ("status", "unknown"), ("source", "production")):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.changed(lambda data: data["shipments"][0].update({field: value}))

    def test_impossible_utc_dates_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.changed(lambda data: data["shipments"][0]["events"][0].update(occurred_at="2026-02-30T08:00:00Z"))

    def test_event_order_and_summary_must_be_coherent(self):
        with self.assertRaises(ValidationError):
            self.changed(lambda data: data["shipments"][0]["events"].reverse())
        with self.assertRaises(ValidationError):
            self.changed(lambda data: data["shipments"][0].update(status="delivered"))

    def test_unknown_order_links_are_rejected_at_startup(self):
        with self.assertRaisesRegex(ValueError, "unknown order"):
            self.changed(lambda data: data["shipments"][0].update(order_id="DEMO-9999"), OrderRepository(ROOT / "fixtures.json"))

    def test_returned_events_do_not_mutate_cached_fixtures(self):
        repository = TrackingRepository(FIXTURES)
        repository.get("DEMO-TRACK-1001").events.clear()
        self.assertEqual(len(repository.get("DEMO-TRACK-1001").events), 3)

    def test_unknown_tracking_does_not_create_data(self):
        original = FIXTURES.read_bytes()
        self.assertIsNone(TrackingRepository(FIXTURES).get("DEMO-TRACK-9999"))
        self.assertEqual(FIXTURES.read_bytes(), original)

    def test_malformed_tracking_identifiers_are_rejected(self):
        repository = TrackingRepository(FIXTURES)
        for value in ("DEMO-1001", "../tracking.json", 1001, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                repository.get(value)


class TrackingProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_errors_do_not_end_a_session_with_both_business_tools(self):
        async with Client(mcp) as client:
            missing = await client.call_tool("track_order", {"tracking_no": "DEMO-TRACK-9999"})
            self.assertTrue(missing.is_error)
            self.assertIsNone(missing.structured_content)
            tracking = await client.call_tool("track_order", {"tracking_no": "DEMO-TRACK-1001"})
            order = await client.call_tool("get_order", {"order_id": "DEMO-1001"})
            self.assertEqual(tracking.structured_content["order_id"], order.structured_content["order_id"])
            self.assertEqual(tracking.structured_content["events"][-1]["status"], "in_transit")

    async def test_schema_rejects_wrong_argument_shapes(self):
        async with Client(mcp) as client:
            for arguments in ({}, {"tracking_no": 1001}, {"tracking_no": "DEMO-1001"}):
                with self.subTest(arguments=arguments):
                    response = await client.call_tool("track_order", arguments)
                    self.assertTrue(response.is_error)
                    self.assertIsNone(response.structured_content)


class TrackingClientTests(unittest.TestCase):
    def call(self, arguments, tool="track_order"):
        return subprocess.run([sys.executable, str(ROOT / "client.py"), "--tool", tool],
                              input=json.dumps(arguments), capture_output=True, text=True, encoding="utf-8", timeout=12)

    def test_real_tracking_client_returns_a_typed_envelope(self):
        result = self.call({"tracking_no": "DEMO-TRACK-1001"})
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(response["tool"], "track_order")
        self.assertEqual(response["transport"], "stdio")
        self.assertTrue(response["protocol_version"])
        self.assertEqual(response["tracking"]["source"], "demo_fixture")
        self.assertEqual(response["tracking"]["tracking_no"], "DEMO-TRACK-1001")
        self.assertEqual(len(response["tracking"]["events"]), 3)
        self.assertNotIn("order", response)

    def test_unknown_tracking_client_returns_an_error(self):
        result = self.call({"tracking_no": "DEMO-TRACK-9999"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("not found", json.loads(result.stdout)["error"])
        self.assertNotIn("tracking", json.loads(result.stdout))

    def test_client_rejects_unlisted_tools_and_wrong_argument_names(self):
        for tool, arguments in (("delete_order", {"order_id": "DEMO-1001"}),
                                ("track_order", {"order_id": "DEMO-1001"}),
                                ("track_order", {"tracking_no": "DEMO-1001"})):
            with self.subTest(tool=tool, arguments=arguments):
                result = self.call(arguments, tool)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["status"], "error")


if __name__ == "__main__":
    unittest.main()
