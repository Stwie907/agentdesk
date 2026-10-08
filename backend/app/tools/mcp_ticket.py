"""Permission-controlled creation of persistent synthetic MCP support tickets."""

from app.tools.base import BaseTool, ToolArgumentsError
from app.tools.mcp_order import call_mcp_tool


class MCPTicketTool(BaseTool):
    name = "create_ticket"
    description = "Create a synthetic local support ticket for a problem. Repeated identical trimmed problems reuse the existing ticket. This tool writes to the local demo store."
    return_direct = True
    transport = "mcp_stdio"
    input_schema = {
        "type": "object",
        "properties": {
            "problem": {"type": "string", "minLength": 1, "maxLength": 2000,
                        "examples": ["Demo parcel is delayed."],
                        "description": "A non-blank demo support problem, up to 2000 characters."},
        },
        "required": ["problem"],
        "additionalProperties": False,
    }

    def validate_arguments(self, arguments) -> None:
        if not isinstance(arguments, dict):
            raise ToolArgumentsError("create_ticket requires an object containing problem")
        super().validate_arguments(arguments)
        problem = arguments["problem"]
        if not 1 <= len(problem) <= 2000 or not problem.strip():
            raise ToolArgumentsError("problem must be a non-blank string of at most 2000 characters")

    def run(self, arguments: dict) -> str:
        normalized = {"problem": arguments["problem"].strip()}
        return call_mcp_tool(self.name, normalized, "ticket", "problem", source="demo_ticket_store")
