"""Yahoo Shopping provider for the Multi-Channel E-Commerce Plugin."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

import requests

from schema import OrderStatus, UnifiedItem, UnifiedOrder

from .base import BaseProvider

_TOKEN_URL = "https://auth.login.yahoo.co.jp/yconnect/v2/token"
_API_BASE = "https://circus.shopping.yahooapis.jp/ShoppingWebService/V1"

_STATUS_MAP: dict[int, OrderStatus] = {
    1: OrderStatus.marked,
    2: OrderStatus.marked,
    3: OrderStatus.marked,
    4: OrderStatus.sent,
    5: OrderStatus.sent,
    8: OrderStatus.cancelled,
    9: OrderStatus.cancelled,
}


class YahooProvider(BaseProvider):
    """Yahoo Shopping integration using OAuth2 refresh-token flow."""

    PLATFORM = "yahoo"

    def __init__(
        self,
        get_setting: Callable[[str], str],
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(get_setting, logger)
        self._access_token: str = ""
        self._seller_id: str = ""

    def is_configured(self) -> bool:
        return bool(
            self.get_setting("YAHOO_CLIENT_ID")
            and self.get_setting("YAHOO_CLIENT_SECRET")
            and self.get_setting("YAHOO_REFRESH_TOKEN")
            and self.get_setting("YAHOO_SELLER_ID")
        )

    def authenticate(self) -> None:
        resp = requests.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self.get_setting("YAHOO_CLIENT_ID"),
                "client_secret": self.get_setting("YAHOO_CLIENT_SECRET"),
                "refresh_token": self.get_setting("YAHOO_REFRESH_TOKEN"),
            },
            timeout=30,
        )
        resp.raise_for_status()
        token_data = resp.json()
        self._access_token = token_data["access_token"]
        self._seller_id = self.get_setting("YAHOO_SELLER_ID")

        # Yahoo YConnect v2 uses rotating refresh tokens — persist the new one
        new_refresh = token_data.get("refresh_token")
        if new_refresh:
            self.set_setting("YAHOO_REFRESH_TOKEN", new_refresh)

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def fetch_orders(self) -> list[UnifiedOrder]:
        if not self._access_token:
            self.authenticate()

        since = datetime.now(timezone.utc) - timedelta(days=7)

        # Step 1: orderList
        params = {
            "sellerId": self._seller_id,
            "Condition.OrderTimeFrom": since.strftime("%Y%m%d%H%M%S"),
            "Condition.OrderTimeTo": datetime.now(timezone.utc).strftime(
                "%Y%m%d%H%M%S"
            ),
            "Condition.OrderStatus": "1,2,3",  # marked statuses
            "Result": "1000",
            "output": "json",
        }
        try:
            resp = requests.get(
                f"{_API_BASE}/orderList",
                params=params,
                headers=self._auth_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            self.logger.exception("Yahoo: orderList failed")
            return []

        search_result = data.get("ResultSet", {}).get("Result", {})
        order_list = search_result.get("OrderInfo", [])
        if isinstance(order_list, dict):
            order_list = [order_list]

        results: list[UnifiedOrder] = []
        for order_info in order_list:
            yahoo_order_id = order_info.get("OrderId", "")
            if not yahoo_order_id:
                continue

            # Step 2: orderInfo
            try:
                detail_params = {
                    "sellerId": self._seller_id,
                    "Target.OrderId": yahoo_order_id,
                    "output": "json",
                }
                detail_resp = requests.get(
                    f"{_API_BASE}/orderInfo",
                    params=detail_params,
                    headers=self._auth_headers(),
                    timeout=30,
                )
                detail_resp.raise_for_status()
                detail = detail_resp.json()
            except Exception:
                self.logger.exception(
                    "Yahoo: orderInfo failed for %s", yahoo_order_id
                )
                continue

            order_detail = (
                detail.get("ResultSet", {}).get("Result", {}).get("OrderInfo", {})
            )
            raw_status = int(order_detail.get("OrderStatus", 0))
            status = _STATUS_MAP.get(raw_status, OrderStatus.created)

            items: list[UnifiedItem] = []
            item_list = order_detail.get("Item", [])
            if isinstance(item_list, dict):
                item_list = [item_list]
            for it in item_list:
                items.append(
                    UnifiedItem(
                        sku=it.get("ItemId", ""),
                        quantity=int(it.get("Quantity", 1)),
                        price=float(it.get("UnitPrice", 0)),
                        title=it.get("Title", ""),
                    )
                )

            ship = order_detail.get("Ship", {})
            address_str = " ".join(
                filter(
                    None,
                    [
                        ship.get("ShipZipCode", ""),
                        ship.get("ShipPrefecture", ""),
                        ship.get("ShipCity", ""),
                        ship.get("ShipAddress1", ""),
                        ship.get("ShipAddress2", ""),
                    ],
                )
            )

            order_date = None
            raw_date = order_detail.get("OrderTime")
            if raw_date:
                try:
                    order_date = datetime.strptime(raw_date, "%Y%m%d%H%M%S").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    pass

            results.append(
                UnifiedOrder(
                    platform="yahoo",
                    order_id=yahoo_order_id,
                    status=status,
                    customer_name=ship.get("ShipName", ""),
                    address=address_str,
                    items=items,
                    order_date=order_date,
                )
            )

        return results

    def push_tracking(self, order_id: str, tracking_number: str) -> bool:
        if not self._access_token:
            self.authenticate()

        params = {
            "sellerId": self._seller_id,
            "Target.OrderId": order_id,
            "Target.IsPointFix": "true",
            "Order.Operate": "ship",
            "Order.ShipInquiryNumber1": tracking_number,
            "output": "json",
        }
        try:
            resp = requests.post(
                f"{_API_BASE}/orderStatusChange",
                data=params,
                headers=self._auth_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            self.logger.info(
                "Yahoo: pushed tracking %s for %s", tracking_number, order_id
            )
            return True
        except Exception:
            self.logger.exception(
                "Yahoo: failed to push tracking for %s", order_id
            )
            return False

    def get_inventory(self, sku: str) -> int | None:
        return None

    def update_inventory(self, sku: str, qty: int) -> bool:
        if not self._access_token:
            self.authenticate()

        params = {
            "sellerId": self._seller_id,
            "itemCode": sku,
            "quantity": str(qty),
            "output": "json",
        }
        try:
            resp = requests.post(
                f"{_API_BASE}/setStock",
                data=params,
                headers=self._auth_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            return True
        except Exception:
            self.logger.exception(
                "Yahoo: failed to update inventory for %s", sku
            )
            return False
