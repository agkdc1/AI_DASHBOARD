"""Qoo10 provider for the Multi-Channel E-Commerce Plugin."""

from __future__ import annotations

import logging
from typing import Callable

import requests

from schema import OrderStatus, UnifiedItem, UnifiedOrder

from .base import BaseProvider

_API_BASE = (
    "https://api.qoo10.jp/GMKT.INC.Front.QAPIService/ebayjapan.qapi"
)

_STATUS_MAP: dict[int, OrderStatus] = {
    2: OrderStatus.marked,
    3: OrderStatus.marked,
    4: OrderStatus.sent,
    5: OrderStatus.sent,
    6: OrderStatus.sent,
    9: OrderStatus.cancelled,
}


class Qoo10Provider(BaseProvider):
    """Qoo10 Japan integration using API Key + SellerAuthKey."""

    PLATFORM = "qoo10"

    def __init__(
        self,
        get_setting: Callable[[str], str],
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(get_setting, logger)
        self._api_key: str = ""
        self._seller_auth_key: str = ""

    def is_configured(self) -> bool:
        return bool(
            self.get_setting("QOO10_API_KEY")
            and self.get_setting("QOO10_SELLER_AUTH_KEY")
        )

    def authenticate(self) -> None:
        self._api_key = self.get_setting("QOO10_API_KEY")
        self._seller_auth_key = self.get_setting("QOO10_SELLER_AUTH_KEY")

    def _base_params(self) -> dict[str, str]:
        return {
            "v": "1.0",
            "returnType": "json",
            "key": self._api_key,
            "SellerAuthKey": self._seller_auth_key,
        }

    def fetch_orders(self) -> list[UnifiedOrder]:
        if not self._api_key:
            self.authenticate()

        params = {
            **self._base_params(),
            "method": "ShippingBasic.GetShippingInfo_v2",
            "ShippingStat": "2,3",  # marked statuses
        }

        try:
            resp = requests.get(_API_BASE, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            self.logger.exception("Qoo10: GetShippingInfo_v2 failed")
            return []

        result_object = data.get("ResultObject", [])
        if not isinstance(result_object, list):
            result_object = [result_object] if result_object else []

        results: list[UnifiedOrder] = []
        for order in result_object:
            raw_status = int(order.get("shippingStat", 0))
            status = _STATUS_MAP.get(raw_status, OrderStatus.created)

            items = [
                UnifiedItem(
                    sku=order.get("sellerItemCode", ""),
                    quantity=int(order.get("orderQty", 1)),
                    price=float(order.get("orderPrice", 0)),
                    title=order.get("itemTitle", ""),
                )
            ]

            address_str = " ".join(
                filter(
                    None,
                    [
                        order.get("zipCode", ""),
                        order.get("shippingAddr", ""),
                    ],
                )
            )

            results.append(
                UnifiedOrder(
                    platform="qoo10",
                    order_id=order.get("orderNo", ""),
                    status=status,
                    customer_name=order.get("receiver", ""),
                    address=address_str,
                    items=items,
                )
            )

        return results

    def push_tracking(self, order_id: str, tracking_number: str) -> bool:
        if not self._api_key:
            self.authenticate()

        params = {
            **self._base_params(),
            "method": "ShippingBasic.SetSendingInfo",
            "OrderNo": order_id,
            "ShippingCorp": "ETC",
            "TrackingNo": tracking_number,
        }
        try:
            resp = requests.get(_API_BASE, params=params, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            if result.get("ResultCode") == 0:
                self.logger.info(
                    "Qoo10: pushed tracking %s for %s",
                    tracking_number,
                    order_id,
                )
                return True
            self.logger.warning(
                "Qoo10: tracking push returned code %s for %s",
                result.get("ResultCode"),
                order_id,
            )
            return False
        except Exception:
            self.logger.exception(
                "Qoo10: failed to push tracking for %s", order_id
            )
            return False

    def get_inventory(self, sku: str) -> int | None:
        return None

    def update_inventory(self, sku: str, qty: int) -> bool:
        if not self._api_key:
            self.authenticate()

        params = {
            **self._base_params(),
            "method": "ItemsBasic.SetSellerItemStockQty",
            "ItemCode": sku,
            "StockQty": str(qty),
        }
        try:
            resp = requests.get(_API_BASE, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json().get("ResultCode") == 0
        except Exception:
            self.logger.exception(
                "Qoo10: failed to update inventory for %s", sku
            )
            return False
