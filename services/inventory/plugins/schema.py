"""Unified data models for the Multi-Channel E-Commerce Plugin."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    """Normalised order status across all platforms."""

    created = "created"
    marked = "marked"
    sent = "sent"
    cancelled = "cancelled"


class UnifiedItem(BaseModel):
    """A single line-item inside an order."""

    sku: str
    quantity: int
    price: float
    title: str = ""


class UnifiedOrder(BaseModel):
    """Platform-agnostic order representation."""

    platform: str
    order_id: str
    status: OrderStatus
    customer_name: str = ""
    address: str = ""
    items: list[UnifiedItem] = Field(default_factory=list)
    tracking_no: str = ""
    currency: str = "JPY"
    order_date: datetime | None = None
