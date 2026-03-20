"""Rakuten RMS 2.0 provider for the Multi-Channel E-Commerce Plugin."""

from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Callable

import requests

from schema import OrderStatus, UnifiedItem, UnifiedOrder

from .base import BaseProvider

_BASE_URL = "https://api.rms.rakuten.co.jp/es/2.0"

# Rakuten API proxy — set RAKUTEN_PROXY to route requests through a static IP.
# Format: http://host:port (e.g. http://100.64.0.1:3128)
# The requests library also respects HTTPS_PROXY env var automatically.
_PROXY = os.environ.get("RAKUTEN_PROXY", "")
_PROXIES = {"https": _PROXY} if _PROXY else None

# Rakuten order status ranges → unified status
_STATUS_RANGES: list[tuple[range, OrderStatus]] = [
    (range(100, 400), OrderStatus.marked),
    (range(400, 600), OrderStatus.sent),
    (range(800, 1000), OrderStatus.cancelled),
]


def _map_status(code: int) -> OrderStatus:
    for rng, status in _STATUS_RANGES:
        if code in rng:
            return status
    return OrderStatus.created


class RakutenProvider(BaseProvider):
    """Rakuten RMS 2.0 integration using ESA authentication."""

    PLATFORM = "rakuten"

    def __init__(
        self,
        get_setting: Callable[[str], str],
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(get_setting, logger)
        self._headers: dict[str, str] = {}

    def is_configured(self) -> bool:
        return bool(
            self.get_setting("RAKUTEN_SERVICE_SECRET")
            and self.get_setting("RAKUTEN_LICENSE_KEY")
        )

    def authenticate(self) -> None:
        secret = self.get_setting("RAKUTEN_SERVICE_SECRET")
        license_key = self.get_setting("RAKUTEN_LICENSE_KEY")
        token = base64.b64encode(
            f"{secret}:{license_key}".encode()
        ).decode()
        self._headers = {
            "Authorization": f"ESA {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def fetch_orders(self) -> list[UnifiedOrder]:
        if not self._headers:
            self.authenticate()

        since = datetime.now(timezone.utc) - timedelta(days=7)
        date_str = since.strftime("%Y-%m-%dT%H:%M:%S+0900")

        # Step 1: searchOrder → get order numbers
        search_body = {
            "dateType": 1,
            "startDatetime": date_str,
            "endDatetime": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S+0900"
            ),
            "PaginationRequestModel": {"requestRecordsAmount": 100, "requestPage": 1},
            "orderProgressList": [100, 200, 300],  # marked statuses
        }

        try:
            resp = requests.post(
                f"{_BASE_URL}/order/searchOrder/",
                json=search_body,
                headers=self._headers,
                timeout=30,
                proxies=_PROXIES,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            self.logger.exception("Rakuten: searchOrder failed")
            return []

        order_numbers = []
        for item in data.get("orderNumberList", []):
            if isinstance(item, str):
                order_numbers.append(item)
            elif isinstance(item, dict):
                order_numbers.append(item.get("orderNumber", ""))

        if not order_numbers:
            return []

        # Step 2: getOrder → full order details (batches of 100)
        results: list[UnifiedOrder] = []
        for i in range(0, len(order_numbers), 100):
            batch = order_numbers[i : i + 100]
            try:
                resp = requests.post(
                    f"{_BASE_URL}/order/getOrder/",
                    json={"orderNumberList": batch, "version": 7},
                    headers=self._headers,
                    timeout=30,
                    proxies=_PROXIES,
                )
                resp.raise_for_status()
                order_data = resp.json()
            except Exception:
                self.logger.exception("Rakuten: getOrder failed for batch")
                continue

            for om in order_data.get("OrderModelList", []):
                status_code = om.get("orderProgress", 0)
                status = _map_status(status_code)
                items: list[UnifiedItem] = []
                for pkg in om.get("PackageModelList", []):
                    for it in pkg.get("ItemModelList", []):
                        items.append(
                            UnifiedItem(
                                sku=it.get("itemNumber", ""),
                                quantity=it.get("units", 1),
                                price=float(it.get("price", 0)),
                                title=it.get("itemName", ""),
                            )
                        )
                addr = om.get("OrdererModel", {})
                address_str = " ".join(
                    filter(
                        None,
                        [
                            addr.get("zipCode1", ""),
                            addr.get("zipCode2", ""),
                            addr.get("prefecture", ""),
                            addr.get("city", ""),
                            addr.get("subAddress", ""),
                        ],
                    )
                )

                order_date = None
                raw_date = om.get("orderDatetime")
                if raw_date:
                    try:
                        order_date = datetime.fromisoformat(raw_date)
                    except ValueError:
                        pass

                results.append(
                    UnifiedOrder(
                        platform="rakuten",
                        order_id=om.get("orderNumber", ""),
                        status=status,
                        customer_name=addr.get("familyName", "")
                        + " "
                        + addr.get("firstName", ""),
                        address=address_str,
                        items=items,
                        order_date=order_date,
                    )
                )

        return results

    def push_tracking(self, order_id: str, tracking_number: str) -> bool:
        if not self._headers:
            self.authenticate()

        body = {
            "orderNumber": order_id,
            "BasketidModelList": [
                {
                    "basketId": 1,
                    "ShippingModelList": [
                        {
                            "shippingCompany": "9999",  # Other
                            "shippingNumber": tracking_number,
                        }
                    ],
                }
            ],
        }
        try:
            resp = requests.post(
                f"{_BASE_URL}/order/updateOrderShipping/",
                json=body,
                headers=self._headers,
                timeout=30,
                proxies=_PROXIES,
            )
            resp.raise_for_status()
            self.logger.info(
                "Rakuten: pushed tracking %s for %s",
                tracking_number,
                order_id,
            )
            return True
        except Exception:
            self.logger.exception(
                "Rakuten: failed to push tracking for %s", order_id
            )
            return False

    def get_inventory(self, sku: str) -> int | None:
        return None

    def update_inventory(self, sku: str, qty: int) -> bool:
        if not self._headers:
            self.authenticate()

        body = {
            "ItemInventoryUpdateModel": {
                "item": {
                    "itemUrl": sku,
                    "inventoryType": 1,
                    "inventory": {"inventoryCount": qty},
                }
            }
        }
        try:
            resp = requests.post(
                f"{_BASE_URL}/inventory/updateInventoryExternal/",
                json=body,
                headers=self._headers,
                timeout=30,
                proxies=_PROXIES,
            )
            resp.raise_for_status()
            return True
        except Exception:
            self.logger.exception(
                "Rakuten: failed to update inventory for %s", sku
            )
            return False
