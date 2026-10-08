"""Expose synthetic order lookup over the official MCP stdio transport."""

from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from orders import DemoOrder, OrderId, OrderRepository


repository = OrderRepository(Path(__file__).with_name("fixtures.json"))
mcp = MCPServer(
    "AgentDesk demo orders",
    instructions="Read-only synthetic order examples. Results are demo data, not real customer orders.",
    log_level="WARNING",
)


@mcp.tool(annotations=ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False,
))
def get_order(order_id: OrderId) -> DemoOrder:
    """Look up a synthetic local order by its DEMO-1001-style id."""
    try:
        order = repository.get(order_id)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    if order is None:
        raise ToolError(f"Order {order_id} was not found in the demo dataset")
    return order


if __name__ == "__main__":
    # stdout is reserved for MCP messages; human-readable logging uses stderr.
    mcp.run(transport="stdio")
