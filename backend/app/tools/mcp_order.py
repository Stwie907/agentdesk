"""A registered order tool backed by an isolated, real MCP SDK client."""

import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

from app.tools.base import BaseTool, ToolArgumentsError


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ORDER_CLIENT = PROJECT_ROOT / "mcp-server" / "client.py"
ORDER_ID_PATTERN = r"^DEMO-[0-9]{4}$"


def mcp_python() -> str:
    configured = os.environ.get("MCP_PYTHON")
    if configured is not None:
        if not configured.strip():
            raise RuntimeError("MCP_PYTHON must be a Python executable path")
        return configured.strip()
    environment = PROJECT_ROOT / "mcp-server" / ".venv"
    candidate = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(candidate) if candidate.is_file() else sys.executable


def mcp_timeout() -> float:
    try:
        timeout = float(os.getenv("MCP_TIMEOUT_SECONDS", "30"))
    except ValueError as exc:
        raise RuntimeError("MCP_TIMEOUT_SECONDS must be a positive finite number") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise RuntimeError("MCP_TIMEOUT_SECONDS must be a positive finite number")
    return timeout


class MCPOrderTool(BaseTool):
    name = "get_order"
    description = "Look up a synthetic, read-only demo order by its DEMO-1001-style id through MCP."
    return_direct = True
    transport = "mcp_stdio"
    input_schema = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "pattern": ORDER_ID_PATTERN, "examples": ["DEMO-1001"],
                         "description": "A synthetic order id such as DEMO-1001 or DEMO-1002."},
        },
        "required": ["order_id"],
        "additionalProperties": False,
    }

    def validate_arguments(self, arguments) -> None:
        if not isinstance(arguments, dict):
            raise ToolArgumentsError("get_order requires an object containing order_id")
        super().validate_arguments(arguments)
        if re.fullmatch(ORDER_ID_PATTERN, arguments["order_id"]) is None:
            raise ToolArgumentsError("order_id must match DEMO-1001-style demo ids")

    def run(self, arguments: dict) -> str:
        if not ORDER_CLIENT.is_file():
            raise RuntimeError("The MCP order client is missing from mcp-server/client.py")
        timeout = mcp_timeout()
        try:
            completed = subprocess.run(
                [mcp_python(), "-u", str(ORDER_CLIENT), "--timeout", str(timeout)],
                input=json.dumps(arguments), capture_output=True,
                text=True, encoding="utf-8", timeout=timeout + 15,
                cwd=str(ORDER_CLIENT.parent),
                env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except OSError as exc:
            raise RuntimeError("Cannot start the MCP client; check MCP_PYTHON and the separate MCP environment") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("The MCP order client exceeded its timeout") from exc
        try:
            response = json.loads(completed.stdout)
        except (json.JSONDecodeError, TypeError) as exc:
            diagnostic = completed.stderr.strip()[-500:]
            raise RuntimeError(
                "The MCP client returned no valid JSON. Install mcp-server/requirements.txt "
                f"in its separate environment and check MCP_PYTHON. {diagnostic}"
            ) from exc
        if not isinstance(response, dict):
            raise RuntimeError("The MCP client returned an invalid response envelope")
        if completed.returncode != 0 or response.get("status") != "ok":
            raise RuntimeError(str(response.get("error") or "The MCP order call failed"))
        order = response.get("order")
        if (response.get("tool") != self.name or response.get("transport") != "stdio"
                or not isinstance(response.get("protocol_version"), str)
                or not response["protocol_version"]
                or not isinstance(order, dict)
                or order.get("order_id") != arguments["order_id"]
                or order.get("source") != "demo_fixture"):
            raise RuntimeError("The MCP client returned an incompatible order response")
        return json.dumps(order, ensure_ascii=False, sort_keys=True)
