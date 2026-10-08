"""Read-only synthetic order data for the first AgentDesk MCP milestone."""

import json
from pathlib import Path
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


ORDER_ID_PATTERN = r"^DEMO-[0-9]{4}$"
OrderId = Annotated[str, Field(strict=True, pattern=ORDER_ID_PATTERN)]


class OrderItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    sku: str = Field(min_length=1)
    name: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class DemoOrder(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source: Literal["demo_fixture"] = "demo_fixture"
    order_id: OrderId
    status: Literal["processing", "shipped", "delivered"]
    currency: Literal["CNY"]
    total: str = Field(pattern=r"^[0-9]+\.[0-9]{2}$")
    items: list[OrderItem] = Field(min_length=1)


class OrderRepository:
    def __init__(self, path: Path):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != {"schema_version", "orders"}:
            raise ValueError("Order fixtures require schema_version and orders")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError("Order fixture schema_version must be the integer 1")
        rows = data["orders"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("Order fixtures must contain a non-empty order list")
        self._orders: dict[str, DemoOrder] = {}
        for row in rows:
            order = DemoOrder.model_validate(row)
            if order.order_id in self._orders:
                raise ValueError(f"Duplicate demo order id: {order.order_id}")
            self._orders[order.order_id] = order

    def get(self, order_id: str) -> DemoOrder | None:
        if not isinstance(order_id, str) or re.fullmatch(ORDER_ID_PATTERN, order_id) is None:
            raise ValueError("order_id must use the format DEMO-1001")
        order = self._orders.get(order_id)
        # A caller can mutate its copy's item list without changing fixture data.
        return None if order is None else order.model_copy(deep=True)
