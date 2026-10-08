"""Typed, read-only synthetic shipment timelines for the MCP demo."""

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from orders import OrderId, OrderRepository


TRACKING_NO_PATTERN = r"^DEMO-TRACK-[0-9]{4}$"
TrackingNo = Annotated[str, Field(strict=True, pattern=TRACKING_NO_PATTERN)]


class TrackingEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    occurred_at: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
    status: Literal["label_created", "picked_up", "in_transit", "delivered"]
    location: str = Field(min_length=1)
    description: str = Field(min_length=1)

    @field_validator("occurred_at")
    @classmethod
    def valid_utc_timestamp(cls, value: str) -> str:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


class DemoTracking(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source: Literal["demo_fixture"] = "demo_fixture"
    tracking_no: TrackingNo
    order_id: OrderId
    carrier: str = Field(min_length=1)
    status: Literal["label_created", "in_transit", "delivered"]
    events: list[TrackingEvent] = Field(min_length=1)

    @model_validator(mode="after")
    def coherent_timeline(self):
        times = [event.occurred_at for event in self.events]
        if any(current <= previous for previous, current in zip(times, times[1:])):
            raise ValueError("Tracking events must have strictly increasing UTC timestamps")
        if self.events[-1].status != self.status:
            raise ValueError("Tracking status must match the final event")
        return self


class TrackingRepository:
    def __init__(self, path: Path, orders: OrderRepository | None = None):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != {"schema_version", "shipments"}:
            raise ValueError("Tracking fixtures require schema_version and shipments")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError("Tracking fixture schema_version must be the integer 1")
        rows = data["shipments"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("Tracking fixtures must contain a non-empty shipment list")
        self._shipments: dict[str, DemoTracking] = {}
        for row in rows:
            shipment = DemoTracking.model_validate(row)
            if shipment.tracking_no in self._shipments:
                raise ValueError(f"Duplicate demo tracking number: {shipment.tracking_no}")
            if orders is not None and orders.get(shipment.order_id) is None:
                raise ValueError(f"Tracking fixture refers to an unknown order: {shipment.order_id}")
            self._shipments[shipment.tracking_no] = shipment

    def get(self, tracking_no: str) -> DemoTracking | None:
        if not isinstance(tracking_no, str) or re.fullmatch(TRACKING_NO_PATTERN, tracking_no) is None:
            raise ValueError("tracking_no must use the format DEMO-TRACK-1001")
        shipment = self._shipments.get(tracking_no)
        return None if shipment is None else shipment.model_copy(deep=True)
