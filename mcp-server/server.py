"""Expose synthetic order and shipment lookups over MCP stdio."""

from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from orders import DemoOrder, OrderId, OrderRepository
from tracking import DemoTracking, TrackingNo, TrackingRepository


repository = OrderRepository(Path(__file__).with_name("fixtures.json"))
tracking_repository = TrackingRepository(Path(__file__).with_name("tracking-fixtures.json"), repository)
mcp = MCPServer(
    "AgentDesk demo orders",
    instructions="Read-only synthetic order and shipment examples. Results are demo data, not real customer orders or live logistics.",
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


@mcp.tool(annotations=ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False,
))
def track_order(tracking_no: TrackingNo) -> DemoTracking:
    """Look up a synthetic shipment timeline by its DEMO-TRACK-1001-style number."""
    try:
        shipment = tracking_repository.get(tracking_no)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    if shipment is None:
        raise ToolError(f"Tracking number {tracking_no} was not found in the demo dataset")
    return shipment


if __name__ == "__main__":
    # stdout is reserved for MCP messages; human-readable logging uses stderr.
    mcp.run(transport="stdio")
