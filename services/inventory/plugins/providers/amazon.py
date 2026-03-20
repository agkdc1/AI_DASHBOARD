"""Amazon SP-API provider for the Multi-Channel E-Commerce Plugin."""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Callable

from schema import OrderStatus, UnifiedItem, UnifiedOrder

from .base import BaseProvider

# Status mapping: Amazon → unified
_STATUS_MAP: dict[str, OrderStatus] = {
    "Unshipped": OrderStatus.marked,
    "PartiallyShipped": OrderStatus.marked,
    "Shipped": OrderStatus.sent,
    "Canceled": OrderStatus.cancelled,
}


class AmazonProvider(BaseProvider):
    """Amazon Japan SP-API integration using *python-amazon-sp-api*."""

    PLATFORM = "amazon"

    def __init__(
        self,
        get_setting: Callable[[str], str],
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(get_setting, logger)
        self._orders_api = None
        self._feeds_api = None

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        required = [
            "AMAZON_REFRESH_TOKEN",
            "AMAZON_LWA_CLIENT_ID",
            "AMAZON_LWA_CLIENT_SECRET",
            "AMAZON_AWS_ACCESS_KEY",
            "AMAZON_AWS_SECRET_KEY",
            "AMAZON_ROLE_ARN",
        ]
        return all(self.get_setting(k) for k in required)

    def _credentials(self) -> dict:
        return {
            "refresh_token": self.get_setting("AMAZON_REFRESH_TOKEN"),
            "lwa_app_id": self.get_setting("AMAZON_LWA_CLIENT_ID"),
            "lwa_client_secret": self.get_setting("AMAZON_LWA_CLIENT_SECRET"),
            "aws_access_key": self.get_setting("AMAZON_AWS_ACCESS_KEY"),
            "aws_secret_key": self.get_setting("AMAZON_AWS_SECRET_KEY"),
            "role_arn": self.get_setting("AMAZON_ROLE_ARN"),
        }

    def _marketplace(self):
        from sp_api.base import Marketplaces

        raw = self.get_setting("AMAZON_MARKETPLACE") or "JP"
        return getattr(Marketplaces, raw, Marketplaces.JP)

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------

    def authenticate(self) -> None:
        from sp_api.api import Feeds, Orders

        creds = self._credentials()
        mp = self._marketplace()
        self._orders_api = Orders(credentials=creds, marketplace=mp)
        self._feeds_api = Feeds(credentials=creds, marketplace=mp)

    def fetch_orders(self) -> list[UnifiedOrder]:
        if self._orders_api is None:
            self.authenticate()

        since = datetime.now(timezone.utc) - timedelta(days=7)
        results: list[UnifiedOrder] = []

        try:
            resp = self._orders_api.get_orders(
                CreatedAfter=since.isoformat(),
                OrderStatuses=["Unshipped", "PartiallyShipped"],
                MarketplaceIds=[self._marketplace().marketplace_id],
            )
            orders = resp.payload.get("Orders", [])
        except Exception:
            self.logger.exception("Amazon: failed to fetch orders")
            return results

        for order in orders:
            amazon_id = order.get("AmazonOrderId", "")
            raw_status = order.get("OrderStatus", "")
            status = _STATUS_MAP.get(raw_status, OrderStatus.created)

            # Fetch line items
            items: list[UnifiedItem] = []
            try:
                time.sleep(0.5)  # rate-limit
                items_resp = self._orders_api.get_order_items(amazon_id)
                for it in items_resp.payload.get("OrderItems", []):
                    items.append(
                        UnifiedItem(
                            sku=it.get("SellerSKU", ""),
                            quantity=it.get("QuantityOrdered", 1),
                            price=float(
                                it.get("ItemPrice", {}).get("Amount", 0)
                            ),
                            title=it.get("Title", ""),
                        )
                    )
            except Exception:
                self.logger.exception(
                    "Amazon: failed to fetch items for %s", amazon_id
                )

            addr = order.get("ShippingAddress", {})
            address_parts = [
                addr.get("PostalCode", ""),
                addr.get("StateOrRegion", ""),
                addr.get("City", ""),
                addr.get("AddressLine1", ""),
                addr.get("AddressLine2", ""),
            ]
            address_str = " ".join(p for p in address_parts if p)

            order_date = None
            if order.get("PurchaseDate"):
                try:
                    order_date = datetime.fromisoformat(
                        order["PurchaseDate"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            results.append(
                UnifiedOrder(
                    platform="amazon",
                    order_id=amazon_id,
                    status=status,
                    customer_name=addr.get("Name", ""),
                    address=address_str,
                    items=items,
                    currency=order.get("OrderTotal", {}).get(
                        "CurrencyCode", "JPY"
                    ),
                    order_date=order_date,
                )
            )

        return results

    def push_tracking(self, order_id: str, tracking_number: str) -> bool:
        if self._feeds_api is None:
            self.authenticate()

        xml_body = self._build_fulfillment_xml(order_id, tracking_number)

        try:
            resp = self._feeds_api.submit_feed(
                feed_type="POST_ORDER_FULFILLMENT_DATA",
                input_feed_document=xml_body,
                content_type="text/xml; charset=UTF-8",
            )
            self.logger.info(
                "Amazon: submitted tracking feed for %s – feedId=%s",
                order_id,
                resp.payload.get("feedId"),
            )
            return True
        except Exception:
            self.logger.exception(
                "Amazon: failed to push tracking for %s", order_id
            )
            return False

    def get_inventory(self, sku: str) -> int | None:
        """Not yet implemented — requires FBA Inventory API."""
        return None

    def update_inventory(self, sku: str, qty: int) -> bool:
        """Not yet implemented — requires Feeds API inventory update."""
        return False

    # ------------------------------------------------------------------
    # XML helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_fulfillment_xml(order_id: str, tracking: str) -> str:
        root = ET.Element(
            "AmazonEnvelope",
            attrib={
                "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                "xsi:noNamespaceSchemaLocation": "amzn-envelope.xsd",
            },
        )
        header = ET.SubElement(root, "Header")
        ET.SubElement(header, "DocumentVersion").text = "1.01"
        ET.SubElement(header, "MerchantIdentifier").text = "default"
        ET.SubElement(root, "MessageType").text = "OrderFulfillment"

        message = ET.SubElement(root, "Message")
        ET.SubElement(message, "MessageID").text = "1"
        fulfillment = ET.SubElement(message, "OrderFulfillment")
        ET.SubElement(fulfillment, "AmazonOrderID").text = order_id
        ET.SubElement(
            fulfillment, "FulfillmentDate"
        ).text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        fulfillment_data = ET.SubElement(fulfillment, "FulfillmentData")
        ET.SubElement(fulfillment_data, "CarrierName").text = "Other"
        ET.SubElement(
            fulfillment_data, "ShippingMethod"
        ).text = "Standard"
        ET.SubElement(
            fulfillment_data, "ShipperTrackingNumber"
        ).text = tracking

        return ET.tostring(root, encoding="unicode", xml_declaration=True)
