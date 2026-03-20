"""Multi-Channel E-Commerce Plugin for InvenTree.

Syncs orders from Amazon JP, Rakuten, Yahoo Shopping and Qoo10 into
InvenTree as SalesOrders, auto-allocates stock, and pushes tracking
numbers back to the respective platforms.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import Q

from company.models import Company
from InvenTree.helpers import str2bool
from order.models import (
    SalesOrder,
    SalesOrderAllocation,
    SalesOrderLineItem,
    SalesOrderShipment,
)
from part.models import Part
from plugin import InvenTreePlugin
from plugin.mixins import EventMixin, ScheduleMixin, SettingsMixin
from stock.models import StockItem, StockLocation

from schema import OrderStatus, UnifiedOrder

from providers import (
    AmazonProvider,
    Qoo10Provider,
    RakutenProvider,
    YahooProvider,
)

logger = logging.getLogger("inventree.ecommerce")

# Maps platform key → (Provider class, display name used for Company)
_PROVIDERS: dict[str, tuple[type, str]] = {
    "amazon": (AmazonProvider, "Amazon JP"),
    "rakuten": (RakutenProvider, "Rakuten"),
    "yahoo": (YahooProvider, "Yahoo Shopping"),
    "qoo10": (Qoo10Provider, "Qoo10"),
}


class MultiChannelEcommercePlugin(
    EventMixin, ScheduleMixin, SettingsMixin, InvenTreePlugin
):
    """InvenTree plugin for multi-channel Japanese e-commerce integration."""

    NAME = "Multi-Channel E-Commerce Integration"
    SLUG = "ecommerce"
    TITLE = "Multi-Channel E-Commerce Integration"
    DESCRIPTION = (
        "Syncs orders from Amazon JP, Rakuten, Yahoo Shopping and Qoo10 "
        "into InvenTree SalesOrders with automatic stock allocation and "
        "tracking-number push-back."
    )
    VERSION = "0.1.0"
    AUTHOR = "Shinbee Japan"
    MIN_VERSION = "0.13.0"

    # -----------------------------------------------------------------
    # Settings
    # -----------------------------------------------------------------

    SETTINGS: dict[str, dict[str, Any]] = {
        # --- Global ---
        "FULFILLMENT_LOCATION": {
            "name": "Fulfillment Location",
            "description": "StockLocation name used for allocation",
            "default": "Online Fulfillment",
        },
        "ENABLED_PLATFORMS": {
            "name": "Enabled Platforms",
            "description": "Comma-separated list: amazon,rakuten,yahoo,qoo10",
            "default": "amazon,rakuten,yahoo,qoo10",
        },
        # --- Amazon ---
        "AMAZON_REFRESH_TOKEN": {
            "name": "Amazon Refresh Token",
            "description": "LWA refresh token for SP-API",
            "default": "",
            "protected": True,
        },
        "AMAZON_LWA_CLIENT_ID": {
            "name": "Amazon LWA Client ID",
            "default": "",
            "protected": True,
        },
        "AMAZON_LWA_CLIENT_SECRET": {
            "name": "Amazon LWA Client Secret",
            "default": "",
            "protected": True,
        },
        "AMAZON_AWS_ACCESS_KEY": {
            "name": "Amazon AWS Access Key",
            "default": "",
            "protected": True,
        },
        "AMAZON_AWS_SECRET_KEY": {
            "name": "Amazon AWS Secret Key",
            "default": "",
            "protected": True,
        },
        "AMAZON_ROLE_ARN": {
            "name": "Amazon Role ARN",
            "default": "",
            "protected": True,
        },
        "AMAZON_MARKETPLACE": {
            "name": "Amazon Marketplace",
            "description": "Marketplace code (default: JP)",
            "default": "JP",
        },
        # --- Rakuten ---
        "RAKUTEN_SERVICE_SECRET": {
            "name": "Rakuten Service Secret",
            "default": "",
            "protected": True,
        },
        "RAKUTEN_LICENSE_KEY": {
            "name": "Rakuten License Key",
            "default": "",
            "protected": True,
        },
        # --- Yahoo ---
        "YAHOO_CLIENT_ID": {
            "name": "Yahoo Client ID",
            "default": "",
            "protected": True,
        },
        "YAHOO_CLIENT_SECRET": {
            "name": "Yahoo Client Secret",
            "default": "",
            "protected": True,
        },
        "YAHOO_REFRESH_TOKEN": {
            "name": "Yahoo Refresh Token",
            "default": "",
            "protected": True,
        },
        "YAHOO_SELLER_ID": {
            "name": "Yahoo Seller ID",
            "default": "",
            "protected": True,
        },
        # --- Qoo10 ---
        "QOO10_API_KEY": {
            "name": "Qoo10 API Key",
            "default": "",
            "protected": True,
        },
        "QOO10_SELLER_AUTH_KEY": {
            "name": "Qoo10 Seller Auth Key",
            "default": "",
            "protected": True,
        },
    }

    # -----------------------------------------------------------------
    # Scheduled tasks (every 15 min)
    # -----------------------------------------------------------------

    SCHEDULED_TASKS = {
        "fetch_orders": {
            "func": "fetch_orders_task",
            "schedule": "I",
            "minutes": 15,
        },
        "sync_inventory": {
            "func": "sync_inventory_task",
            "schedule": "I",
            "minutes": 15,
        },
    }

    # =================================================================
    #  Scheduled task: Fetch orders
    # =================================================================

    def fetch_orders_task(self) -> None:
        """Fetch orders from all enabled platforms, deduplicate, create SOs."""
        enabled = self._enabled_platforms()
        for platform_key in enabled:
            provider_cls, display_name = _PROVIDERS.get(
                platform_key, (None, None)
            )
            if provider_cls is None:
                continue
            provider = provider_cls(self.get_setting, logger, self.set_setting)
            if not provider.is_configured():
                logger.debug(
                    "Skipping %s — not configured", display_name
                )
                continue
            try:
                provider.authenticate()
                orders = provider.fetch_orders()
            except Exception:
                logger.exception("Failed to fetch orders from %s", display_name)
                continue

            for order in orders:
                try:
                    self._process_order(order, display_name)
                except Exception:
                    logger.exception(
                        "Failed to process order %s from %s",
                        order.order_id,
                        display_name,
                    )

    # =================================================================
    #  Scheduled task: Sync inventory
    # =================================================================

    def sync_inventory_task(self) -> None:
        """Push InvenTree stock levels to all enabled platforms."""
        enabled = self._enabled_platforms()
        location = self._fulfillment_location()
        if location is None:
            logger.warning("Fulfillment location not found — skipping inventory sync")
            return

        for platform_key in enabled:
            provider_cls, display_name = _PROVIDERS.get(
                platform_key, (None, None)
            )
            if provider_cls is None:
                continue
            provider = provider_cls(self.get_setting, logger, self.set_setting)
            if not provider.is_configured():
                continue
            try:
                provider.authenticate()
            except Exception:
                logger.exception("Auth failed for %s inventory sync", display_name)
                continue

            # Push stock for every Part that has an IPN
            for item in StockItem.objects.filter(
                location=location, part__IPN__isnull=False
            ).select_related("part"):
                sku = item.part.IPN
                if not sku:
                    continue
                try:
                    provider.update_inventory(sku, int(item.quantity))
                except Exception:
                    logger.exception(
                        "%s: failed to update inventory for %s",
                        display_name,
                        sku,
                    )

    # =================================================================
    #  Event handler: push tracking on shipment completion
    # =================================================================

    def wants_process_event(self, event: str) -> bool:
        return event in (
            "salesordershipment.completed",
            "order_salesordershipment.saved",
        )

    def process_event(self, event: str, *args, **kwargs) -> None:
        shipment_id = kwargs.get("id")
        if not shipment_id:
            return
        try:
            shipment = SalesOrderShipment.objects.select_related("order").get(
                pk=shipment_id
            )
        except SalesOrderShipment.DoesNotExist:
            return

        so = shipment.order
        meta = (so.metadata or {}).get("ecommerce_plugin", {})
        platform_key = meta.get("platform")
        platform_order_id = meta.get("platform_order_id")
        tracking = shipment.tracking_number or meta.get("tracking_no", "")

        if not platform_key or not platform_order_id or not tracking:
            return

        provider_cls, display_name = _PROVIDERS.get(
            platform_key, (None, None)
        )
        if provider_cls is None:
            return

        provider = provider_cls(self.get_setting, logger, self.set_setting)
        if not provider.is_configured():
            return

        try:
            provider.authenticate()
            ok = provider.push_tracking(platform_order_id, tracking)
            if ok:
                logger.info(
                    "Pushed tracking %s to %s for order %s",
                    tracking,
                    display_name,
                    platform_order_id,
                )
        except Exception:
            logger.exception(
                "Failed to push tracking to %s for order %s",
                display_name,
                platform_order_id,
            )

    # =================================================================
    #  Internal helpers
    # =================================================================

    def _enabled_platforms(self) -> list[str]:
        raw = self.get_setting("ENABLED_PLATFORMS") or ""
        return [p.strip().lower() for p in raw.split(",") if p.strip()]

    def _fulfillment_location(self) -> StockLocation | None:
        name = self.get_setting("FULFILLMENT_LOCATION") or "Online Fulfillment"
        return StockLocation.objects.filter(name=name).first()

    # ----- order processing -----

    def _process_order(
        self, order: UnifiedOrder, display_name: str
    ) -> None:
        if order.status != OrderStatus.marked:
            return
        if self._order_exists(order.platform, order.order_id):
            return
        customer = self._get_or_create_customer(display_name)
        so = self._create_sales_order(order, customer)
        self._allocate_stock(so, order)

    def _order_exists(self, platform: str, order_id: str) -> bool:
        return SalesOrder.objects.filter(
            metadata__ecommerce_plugin__platform=platform,
            metadata__ecommerce_plugin__platform_order_id=order_id,
        ).exists()

    def _get_or_create_customer(self, display_name: str) -> Company:
        company, _ = Company.objects.get_or_create(
            name=display_name,
            defaults={"is_customer": True, "is_supplier": False},
        )
        if not company.is_customer:
            company.is_customer = True
            company.save()
        return company

    def _create_sales_order(
        self, order: UnifiedOrder, customer: Company
    ) -> SalesOrder:
        so = SalesOrder.objects.create(
            customer=customer,
            customer_reference=order.order_id,
            description=f"{order.platform.title()} order {order.order_id}",
            target_date=order.order_date,
        )
        so.metadata = so.metadata or {}
        so.metadata["ecommerce_plugin"] = {
            "platform": order.platform,
            "platform_order_id": order.order_id,
            "customer_name": order.customer_name,
            "address": order.address,
            "tracking_no": order.tracking_no,
            "currency": order.currency,
        }
        so.save()

        # Create line items
        for item in order.items:
            part = self._resolve_part(item.sku)
            if part is None:
                logger.warning(
                    "SKU %s not found — skipping line item", item.sku
                )
                continue
            SalesOrderLineItem.objects.create(
                order=so,
                part=part,
                quantity=item.quantity,
                sale_price=item.price,
                sale_price_currency=order.currency,
            )

        # Issue the order (move from Draft → Pending)
        try:
            so.issue_order()
        except Exception:
            logger.exception("Could not issue SO %s", so.pk)

        return so

    @staticmethod
    def _resolve_part(sku: str) -> Part | None:
        """Resolve a marketplace SKU to an InvenTree Part.

        Tries Part.IPN first, then falls back to SupplierPart.SKU.
        """
        from company.models import SupplierPart

        part = Part.objects.filter(IPN=sku).first()
        if part:
            return part
        sp = SupplierPart.objects.filter(SKU=sku).select_related("part").first()
        if sp:
            return sp.part
        return None

    def _allocate_stock(self, so: SalesOrder, order: UnifiedOrder) -> None:
        location = self._fulfillment_location()
        if location is None:
            logger.warning("Fulfillment location not found — cannot allocate")
            return

        shipment, _ = SalesOrderShipment.objects.get_or_create(
            order=so,
            reference="1",
            defaults={"tracking_number": order.tracking_no or ""},
        )

        for line in so.lines.all():
            stock = StockItem.objects.filter(
                part=line.part,
                location=location,
                quantity__gte=line.quantity,
            ).first()

            if stock is None:
                logger.warning(
                    "No stock for %s at %s — skipping allocation",
                    line.part.IPN,
                    location.name,
                )
                continue

            SalesOrderAllocation.objects.create(
                line=line,
                shipment=shipment,
                item=stock,
                quantity=line.quantity,
            )
