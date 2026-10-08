"""Call an allowlisted demo MCP business tool and emit a backend JSON envelope."""

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import re
import sys

from mcp import Client, StdioServerParameters

from orders import DemoOrder, ORDER_ID_PATTERN
from tracking import DemoTracking, TRACKING_NO_PATTERN
from tickets import DemoTicket, MAX_PROBLEM_LENGTH, normalize_problem


TOOL_CONTRACTS = {
    "get_order": ("order_id", ORDER_ID_PATTERN, "order", DemoOrder, True),
    "track_order": ("tracking_no", TRACKING_NO_PATTERN, "tracking", DemoTracking, True),
    "create_ticket": ("problem", None, "ticket", DemoTicket, False),
}


class OrderCallError(RuntimeError):
    pass


def describe_error(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(describe_error(child) for child in exc.exceptions)
    return str(exc) or type(exc).__name__


def validate_request(tool_name: str, arguments) -> dict:
    if tool_name not in TOOL_CONTRACTS:
        raise OrderCallError("Unsupported MCP tool")
    argument_name, pattern, _, _, _ = TOOL_CONTRACTS[tool_name]
    if not isinstance(arguments, dict) or set(arguments) != {argument_name}:
        raise ValueError(f"The MCP request must contain only {argument_name}")
    value = arguments[argument_name]
    if tool_name == "create_ticket":
        return {argument_name: normalize_problem(value)}
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise ValueError(f"{argument_name} does not match its demo id format")
    return arguments


async def call_business_tool(server_path: Path, tool_name: str, arguments: dict, timeout: float = 30) -> dict:
    arguments = validate_request(tool_name, arguments)
    argument_name, pattern, response_key, model, read_only = TOOL_CONTRACTS[tool_name]
    environment = {"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    if "MCP_TICKET_DB" in os.environ:
        environment["MCP_TICKET_DB"] = os.environ["MCP_TICKET_DB"]
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-u", str(server_path.resolve())],
        cwd=str(server_path.resolve().parent),
        env=environment,
    )
    async with asyncio.timeout(timeout):
        async with Client(parameters, read_timeout_seconds=timeout) as client:
            listing = await client.list_tools()
            matches = [tool for tool in listing.tools if tool.name == tool_name]
            if len(matches) != 1:
                raise OrderCallError(f"MCP discovery did not expose exactly one {tool_name} tool")
            tool = matches[0]
            field = tool.input_schema.get("properties", {}).get(argument_name, {})
            if (tool.input_schema.get("required") != [argument_name]
                    or field.get("type") != "string"
                    or field.get("pattern") != pattern
                    or not tool.output_schema
                    or tool.annotations is None
                    or tool.annotations.read_only_hint is not read_only):
                raise OrderCallError(f"The MCP {tool_name} tool contract is incompatible")
            if not read_only and (field.get("minLength") != 1 or field.get("maxLength") != MAX_PROBLEM_LENGTH
                                  or tool.annotations.idempotent_hint is not True
                                  or tool.annotations.destructive_hint is not False
                                  or tool.annotations.open_world_hint is not False):
                raise OrderCallError("The MCP create_ticket write contract is incompatible")
            result = await client.call_tool(tool_name, arguments)
            if result.is_error:
                message = " ".join(block.text for block in result.content if block.type == "text")
                raise OrderCallError(message or f"The MCP {tool_name} tool returned an error")
            if not isinstance(result.structured_content, dict):
                raise OrderCallError(f"The MCP {tool_name} tool returned no structured data")
            record = model.model_validate(result.structured_content)
            if getattr(record, argument_name) != arguments[argument_name] or not client.protocol_version:
                raise OrderCallError("The MCP response does not match the requested business arguments")
            return {
                "status": "ok", "tool": tool_name, "transport": "stdio",
                "protocol_version": client.protocol_version,
                response_key: record.model_dump(mode="json"),
            }


async def call_read_only_tool(server_path: Path, tool_name: str, arguments: dict, timeout: float = 30) -> dict:
    """Preserve the read-only API and prevent it from launching a write tool."""
    if tool_name not in TOOL_CONTRACTS or not TOOL_CONTRACTS[tool_name][4]:
        raise OrderCallError("Unsupported read-only MCP tool")
    return await call_business_tool(server_path, tool_name, arguments, timeout)


async def lookup_order(server_path: Path, order_id: str, timeout: float = 30) -> dict:
    """Keep the original order client API and response envelope compatible."""
    return await call_read_only_tool(server_path, "get_order", {"order_id": order_id}, timeout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, default=Path(__file__).with_name("server.py"))
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--tool", default="get_order", help="get_order, track_order, or create_ticket")
    args = parser.parse_args(argv)
    try:
        if args.tool not in TOOL_CONTRACTS:
            raise ValueError("Unsupported MCP tool; use get_order, track_order, or create_ticket")
        if not args.server.is_file():
            raise ValueError("The MCP server script does not exist")
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be a positive finite number")
        limit = 16384 if args.tool == "create_ticket" else 1024
        raw = sys.stdin.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("The MCP request is too large")
        request = validate_request(args.tool, json.loads(raw))
    except (ValueError, OSError, OrderCallError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 2
    try:
        response = asyncio.run(call_business_tool(args.server, args.tool, request, args.timeout))
    except Exception as exc:
        print(json.dumps({"status": "error", "error": describe_error(exc)}))
        return 1
    print(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
