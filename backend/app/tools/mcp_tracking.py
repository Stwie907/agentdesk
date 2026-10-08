"""Permission-controlled shipment lookup through the shared MCP client."""

import re

from app.tools.base import BaseTool, ToolArgumentsError
from app.tools.mcp_order import call_mcp_tool


TRACKING_NO_PATTERN = r"^DEMO-TRACK-[0-9]{4}$"


class MCPTrackingTool(BaseTool):
    name = "track_order"
    description = "Look up a synthetic, read-only shipment timeline using its DEMO-TRACK-1001-style tracking number through MCP."
    return_direct = True
    transport = "mcp_stdio"
    input_schema = {
        "type": "object",
        "properties": {
            "tracking_no": {"type": "string", "pattern": TRACKING_NO_PATTERN,
                            "examples": ["DEMO-TRACK-1001"],
                            "description": "A synthetic tracking number, not an order id."},
        },
        "required": ["tracking_no"],
        "additionalProperties": False,
    }

    def validate_arguments(self, arguments) -> None:
        if not isinstance(arguments, dict):
            raise ToolArgumentsError("track_order requires an object containing tracking_no")
        super().validate_arguments(arguments)
        if re.fullmatch(TRACKING_NO_PATTERN, arguments["tracking_no"]) is None:
            raise ToolArgumentsError("tracking_no must match DEMO-TRACK-1001-style demo numbers")

    def run(self, arguments: dict) -> str:
        return call_mcp_tool(self.name, arguments, "tracking", "tracking_no")
