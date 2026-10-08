"""Launch the MCP server and verify discovery, structured output, and errors."""

import argparse
import asyncio
import json
import math
from pathlib import Path
import sys
import tempfile

from mcp import Client, StdioServerParameters
from tracking import DemoTracking, TRACKING_NO_PATTERN
from tickets import DemoTicket, MAX_PROBLEM_LENGTH


class CheckError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


def error_text(result) -> str:
    return " ".join(block.text for block in result.content if block.type == "text")


async def check_server(server_path: Path, timeout: float = 30) -> dict:
    # Protocol checks must never write to a user's persistent ticket store.
    with tempfile.TemporaryDirectory(prefix="agentdesk-mcp-check-") as directory:
        return await check_demo_server(server_path, timeout, Path(directory) / "tickets.db")


async def check_demo_server(server_path: Path, timeout: float, ticket_path: Path) -> dict:
    parameters = StdioServerParameters(
        command=sys.executable, args=["-u", str(server_path.resolve())],
        cwd=str(server_path.resolve().parent),
        env={"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "MCP_TICKET_DB": str(ticket_path)},
    )
    checks = []
    async with asyncio.timeout(timeout):
        async with Client(parameters, read_timeout_seconds=timeout) as client:
            listing = await client.list_tools()
            names = [tool.name for tool in listing.tools]
            matches = [tool for tool in listing.tools if tool.name == "get_order"]
            require(len(matches) == 1, "Discovery must include exactly one get_order tool")
            tool = matches[0]
            schema = tool.input_schema
            require(schema.get("type") == "object" and schema.get("required") == ["order_id"],
                    "get_order must require order_id")
            field = schema.get("properties", {}).get("order_id", {})
            require(field.get("type") == "string" and field.get("pattern") == r"^DEMO-[0-9]{4}$",
                    "get_order must declare its demo id format")
            require(bool(tool.output_schema) and bool(client.protocol_version),
                    "Structured output schema and a negotiated protocol version are required")
            checks.append("discovery_and_schemas")

            hints = tool.annotations
            require(hints is not None and hints.read_only_hint is True
                    and hints.destructive_hint is False and hints.idempotent_hint is True
                    and hints.open_world_hint is False, "Order lookup metadata must describe a local read-only tool")
            checks.append("read_only_metadata")

            samples = []
            for order_id, status, total, sku in (
                ("DEMO-1001", "shipped", "129.00", "DEMO-NOTEBOOK"),
                ("DEMO-1002", "processing", "59.00", "DEMO-PEN"),
            ):
                result = await client.call_tool("get_order", {"order_id": order_id})
                order = result.structured_content
                require(not result.is_error and isinstance(order, dict), f"{order_id} returned no structured order")
                require(order.get("source") == "demo_fixture" and order.get("order_id") == order_id
                        and order.get("status") == status and order.get("currency") == "CNY"
                        and order.get("total") == total, f"{order_id} differs from its fixed fixture")
                items = order.get("items")
                require(isinstance(items, list) and len(items) == 1 and items[0].get("sku") == sku
                        and items[0].get("quantity") == 1, f"{order_id} item data differs")
                samples.append({key: order[key] for key in ("order_id", "status", "source")})
                checks.append("lookup_" + order_id.lower().replace("-", "_"))

            missing = await client.call_tool("get_order", {"order_id": "DEMO-9999"})
            require(missing.is_error and missing.structured_content is None
                    and "not found" in error_text(missing), "Unknown orders must return a tool error")
            checks.append("unknown_order_error")

            for label, arguments in (
                ("invalid_id_error", {"order_id": "../private-file"}),
                ("missing_argument_error", {}),
                ("wrong_type_error", {"order_id": 1001}),
            ):
                result = await client.call_tool("get_order", arguments)
                require(result.is_error and result.structured_content is None and bool(error_text(result)),
                        f"{label} must return a tool error, not successful order data")
                checks.append(label)

            matches = [tool for tool in listing.tools if tool.name == "track_order"]
            require(len(matches) == 1, "Discovery must include exactly one track_order tool")
            tracking_tool = matches[0]
            schema = tracking_tool.input_schema
            field = schema.get("properties", {}).get("tracking_no", {})
            require(schema.get("type") == "object" and schema.get("required") == ["tracking_no"]
                    and field.get("type") == "string" and field.get("pattern") == TRACKING_NO_PATTERN
                    and bool(tracking_tool.output_schema), "track_order schemas are incompatible")
            checks.append("tracking_discovery_and_schemas")
            hints = tracking_tool.annotations
            require(hints is not None and hints.read_only_hint is True
                    and hints.destructive_hint is False and hints.idempotent_hint is True
                    and hints.open_world_hint is False, "Tracking must be a local read-only tool")
            checks.append("tracking_read_only_metadata")

            tracking_samples = []
            for tracking_no, order_id, status, event_count in (
                ("DEMO-TRACK-1001", "DEMO-1001", "in_transit", 3),
                ("DEMO-TRACK-1002", "DEMO-1002", "label_created", 1),
            ):
                result = await client.call_tool("track_order", {"tracking_no": tracking_no})
                require(not result.is_error and isinstance(result.structured_content, dict),
                        f"{tracking_no} returned no structured shipment")
                shipment = DemoTracking.model_validate(result.structured_content)
                require(shipment.tracking_no == tracking_no and shipment.order_id == order_id
                        and shipment.status == status and shipment.carrier == "Demo Courier"
                        and len(shipment.events) == event_count, "Tracking differs from its fixed fixture")
                tracking_samples.append({"tracking_no": tracking_no, "status": status, "source": shipment.source})
                checks.append("lookup_" + tracking_no.lower().replace("-", "_"))

            missing = await client.call_tool("track_order", {"tracking_no": "DEMO-TRACK-9999"})
            require(missing.is_error and missing.structured_content is None
                    and "not found" in error_text(missing), "Unknown tracking numbers must return a tool error")
            checks.append("unknown_tracking_error")
            for label, arguments in (
                ("invalid_tracking_error", {"tracking_no": "DEMO-1001"}),
                ("missing_tracking_argument_error", {}),
                ("wrong_tracking_type_error", {"tracking_no": 1001}),
            ):
                result = await client.call_tool("track_order", arguments)
                require(result.is_error and result.structured_content is None and bool(error_text(result)),
                        f"{label} must be a tool error")
                checks.append(label)

            matches = [tool for tool in listing.tools if tool.name == "create_ticket"]
            require(len(matches) == 1, "Discovery must include exactly one create_ticket tool")
            ticket_tool = matches[0]
            schema = ticket_tool.input_schema
            field = schema.get("properties", {}).get("problem", {})
            require(schema.get("required") == ["problem"] and field.get("type") == "string"
                    and field.get("minLength") == 1 and field.get("maxLength") == MAX_PROBLEM_LENGTH
                    and bool(ticket_tool.output_schema), "create_ticket schemas are incompatible")
            checks.append("ticket_discovery_and_schemas")
            hints = ticket_tool.annotations
            require(hints is not None and hints.read_only_hint is False and hints.destructive_hint is False
                    and hints.idempotent_hint is True and hints.open_world_hint is False,
                    "Ticket creation must advertise local, idempotent write behavior")
            checks.append("ticket_write_metadata")

            created = await client.call_tool("create_ticket", {"problem": "Protocol demo problem"})
            require(not created.is_error and isinstance(created.structured_content, dict), "Ticket creation failed")
            ticket = DemoTicket.model_validate(created.structured_content)
            require(ticket.problem == "Protocol demo problem" and ticket.status == "open", "Ticket content differs")
            checks.append("ticket_creation")
            repeated = await client.call_tool("create_ticket", {"problem": "  Protocol demo problem  "})
            require(not repeated.is_error and repeated.structured_content == created.structured_content,
                    "Repeated trimmed problems must return the original ticket")
            checks.append("ticket_idempotency")
            other = await client.call_tool("create_ticket", {"problem": "Second protocol demo problem"})
            require(not other.is_error and isinstance(other.structured_content, dict), "Second ticket failed")
            other_ticket = DemoTicket.model_validate(other.structured_content)
            require(other_ticket.ticket_id != ticket.ticket_id, "Different problems must receive different tickets")
            checks.append("distinct_ticket_creation")
            for label, arguments in (
                ("blank_ticket_problem_error", {"problem": "   "}),
                ("missing_ticket_problem_error", {}),
                ("wrong_ticket_problem_type_error", {"problem": True}),
                ("oversized_ticket_problem_error", {"problem": "x" * (MAX_PROBLEM_LENGTH + 1)}),
            ):
                result = await client.call_tool("create_ticket", arguments)
                require(result.is_error and result.structured_content is None and bool(error_text(result)),
                        f"{label} must be a tool error")
                checks.append(label)

            return {"status": "passed", "transport": "stdio", "protocol_version": client.protocol_version,
                    "tool_names": names, "checks_passed": len(checks), "checks": checks,
                    "sample_orders": samples, "sample_shipments": tracking_samples,
                    "sample_tickets": [{"ticket_id": item.ticket_id, "status": item.status, "source": item.source}
                                       for item in (ticket, other_ticket)]}


def describe_error(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(describe_error(child) for child in exc.exceptions)
    return str(exc) or type(exc).__name__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, default=Path(__file__).with_name("server.py"))
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args(argv)
    if not args.server.is_file():
        parser.error("The MCP server script does not exist")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be a positive finite number")
    try:
        report = asyncio.run(check_server(args.server, args.timeout))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": describe_error(exc)}))
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
