"""Expose local demo order, shipment, and support-ticket tools over MCP."""

from pathlib import Path
import sqlite3

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from orders import DemoOrder, OrderId, OrderRepository
from tracking import DemoTracking, TrackingNo, TrackingRepository
from tickets import DemoTicket, Problem, TicketStore, ticket_db_path


repository = OrderRepository(Path(__file__).with_name("fixtures.json"))
tracking_repository = TrackingRepository(Path(__file__).with_name("tracking-fixtures.json"), repository)
mcp = MCPServer(
    "AgentDesk demo business tools",
    instructions="Synthetic order/shipment lookups and local demo ticket creation. No real customer, carrier, or support service is contacted. Repeated trimmed ticket problems return the existing local ticket.",
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


@mcp.tool(annotations=ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False,
))
def create_ticket(problem: Problem) -> DemoTicket:
    """Create a synthetic local support ticket, or reuse the same trimmed problem."""
    try:
        return TicketStore(ticket_db_path()).create(problem)
    except (ValueError, OSError, sqlite3.Error) as exc:
        raise ToolError(f"Cannot create a demo ticket: {exc}") from exc


if __name__ == "__main__":
    # stdout is reserved for MCP messages; human-readable logging uses stderr.
    mcp.run(transport="stdio")
