"""Call get_order through MCP and emit one JSON envelope for the backend."""

import argparse
import asyncio
import json
import math
from pathlib import Path
import re
import sys

from mcp import Client, StdioServerParameters

from orders import DemoOrder, ORDER_ID_PATTERN


class OrderCallError(RuntimeError):
    pass


def describe_error(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(describe_error(child) for child in exc.exceptions)
    return str(exc) or type(exc).__name__


async def lookup_order(server_path: Path, order_id: str, timeout: float = 30) -> dict:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-u", str(server_path.resolve())],
        cwd=str(server_path.resolve().parent),
        env={"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    async with asyncio.timeout(timeout):
        async with Client(parameters, read_timeout_seconds=timeout) as client:
            listing = await client.list_tools()
            matches = [tool for tool in listing.tools if tool.name == "get_order"]
            if len(matches) != 1:
                raise OrderCallError("MCP discovery did not expose exactly one get_order tool")
            tool = matches[0]
            field = tool.input_schema.get("properties", {}).get("order_id", {})
            if (tool.input_schema.get("required") != ["order_id"]
                    or field.get("type") != "string"
                    or field.get("pattern") != ORDER_ID_PATTERN
                    or not tool.output_schema
                    or tool.annotations is None
                    or tool.annotations.read_only_hint is not True):
                raise OrderCallError("The MCP order tool contract is incompatible")
            result = await client.call_tool("get_order", {"order_id": order_id})
            if result.is_error:
                message = " ".join(block.text for block in result.content if block.type == "text")
                raise OrderCallError(message or "The MCP order tool returned an error")
            if not isinstance(result.structured_content, dict):
                raise OrderCallError("The MCP order tool returned no structured order")
            order = DemoOrder.model_validate(result.structured_content)
            if order.order_id != order_id or not client.protocol_version:
                raise OrderCallError("The MCP response does not match the requested order")
            return {
                "status": "ok", "tool": "get_order", "transport": "stdio",
                "protocol_version": client.protocol_version,
                "order": order.model_dump(mode="json"),
            }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, default=Path(__file__).with_name("server.py"))
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args(argv)
    try:
        if not args.server.is_file():
            raise ValueError("The MCP server script does not exist")
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be a positive finite number")
        raw = sys.stdin.read(1025)
        if len(raw) > 1024:
            raise ValueError("The MCP request is too large")
        request = json.loads(raw)
        if not isinstance(request, dict) or set(request) != {"order_id"}:
            raise ValueError("The MCP request must contain only order_id")
        order_id = request["order_id"]
        if not isinstance(order_id, str) or re.fullmatch(ORDER_ID_PATTERN, order_id) is None:
            raise ValueError("order_id must match DEMO-1001-style demo ids")
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 2
    try:
        response = asyncio.run(lookup_order(args.server, order_id, args.timeout))
    except Exception as exc:
        print(json.dumps({"status": "error", "error": describe_error(exc)}))
        return 1
    print(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
