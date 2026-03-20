"""InvoicePrint Plugin - Generate shipping waybill PDFs via Browser Daemon."""

import logging

from django.urls import re_path
from django.http import JsonResponse

from plugin import InvenTreePlugin
from plugin.mixins import AppMixin, EventMixin, UrlsMixin, SettingsMixin
from plugin.base.ui.mixins import UserInterfaceMixin

import requests

logger = logging.getLogger("inventree")


class InvoicePrintPlugin(AppMixin, EventMixin, UrlsMixin, SettingsMixin, UserInterfaceMixin, InvenTreePlugin):
    """Generate 送り状 (shipping waybill) PDFs from Yamato and Sagawa via browser daemon."""

    NAME = "Invoice Print"
    SLUG = "invoice_print"
    TITLE = "Invoice Print"
    VERSION = "0.2.0"
    DESCRIPTION = "Generate shipping waybill PDFs from Yamato and Sagawa via browser daemon"
    MIN_VERSION = "0.13.0"

    SETTINGS = {
        "DAEMON_URL": {
            "name": "Browser Daemon URL",
            "description": "FastAPI endpoint of the browser daemon",
            "default": "http://127.0.0.1:8020",
        },
        "DEFAULT_CARRIER": {
            "name": "Default Carrier",
            "description": "Default shipping carrier (yamato or sagawa)",
            "default": "yamato",
        },
        "AUTO_GENERATE": {
            "name": "Auto Generate on Shipment",
            "description": "Automatically generate waybill PDF when shipment is created",
            "default": False,
            "validator": bool,
        },
        "ADMIN_EMAIL": {
            "name": "Admin Email",
            "description": "Email of the default portal admin user",
            "default": "admin@your-domain.com",
        },
        "DEFAULT_SENDER_COMPANY_ID": {
            "name": "Default Sender Company ID",
            "description": "Company ID for default sender address on waybills",
            "default": "",
        },
    }

    def setup_urls(self):
        """Register custom API endpoints."""
        from . import api, admin_page

        return [
            re_path(
                r"^generate/?$",
                self.api_generate_waybill,
                name="generate-waybill",
            ),
            re_path(
                r"^status/(?P<job_id>.+)/?$",
                self.api_job_status,
                name="job-status",
            ),
            re_path(
                r"^pdf/(?P<job_id>[^/]+)/?$",
                self.api_pdf_download,
                name="pdf-download",
            ),
            re_path(
                r"^printers/?$",
                api.handle_printers,
                name="printer-list",
            ),
            re_path(
                r"^printers/(?P<pk>\d+)/?$",
                api.handle_printer_detail,
                name="printer-detail",
            ),
            re_path(
                r"^printers/(?P<printer_pk>\d+)/trays/?$",
                api.handle_trays,
                name="tray-list",
            ),
            re_path(
                r"^printers/(?P<printer_pk>\d+)/trays/(?P<pk>\d+)/?$",
                api.handle_tray_detail,
                name="tray-detail",
            ),
            re_path(
                r"^printers/admin/?$",
                admin_page.printers_admin_page,
                name="printers-admin",
            ),
            re_path(
                r"^waybill-page/?$",
                admin_page.waybill_admin_page,
                name="waybill-page",
            ),
        ]

    def get_ui_dashboard_items(self, request, context):
        """Return dashboard widgets for waybill generation and address book."""
        return [
            {
                "key": "invoice-print-waybill",
                "title": "送り状発行",
                "description": "配送伝票を発行します",
                "source": self.plugin_static_file(
                    "invoice_plugin", "waybill_dashboard.js"
                ) + "?v=" + self.VERSION,
            },
            {
                "key": "address-book",
                "title": "住所録",
                "description": "会社住所の管理",
                "source": self.plugin_static_file(
                    "invoice_plugin", "address_dashboard.js"
                ) + "?v=" + self.VERSION,
            },
        ]

    def api_generate_waybill(self, request):
        """POST /api/plugin/invoice_print/generate/ - Submit a waybill generation job."""
        if request.method != "POST":
            return JsonResponse({"error": "Method not allowed"}, status=405)

        import json

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        shipment_id = body.get("shipment_id")
        carrier = body.get("carrier", self.get_setting("DEFAULT_CARRIER"))

        if not shipment_id:
            return JsonResponse({"error": "shipment_id is required"}, status=400)

        if carrier not in ("yamato", "sagawa"):
            return JsonResponse({"error": "carrier must be 'yamato' or 'sagawa'"}, status=400)

        # Look up shipment details from InvenTree
        try:
            from order.models import SalesOrderShipment

            shipment = SalesOrderShipment.objects.get(pk=shipment_id)
        except Exception as e:
            return JsonResponse({"error": f"Shipment not found: {e}"}, status=404)

        order = shipment.order
        params = self._extract_shipment_params(order, shipment)

        # Submit job to daemon
        daemon_url = self.get_setting("DAEMON_URL")
        try:
            resp = requests.post(
                f"{daemon_url}/jobs",
                json={
                    "type": "print_waybill",
                    "carrier": carrier,
                    "priority": 5,
                    "params": params,
                },
                timeout=10,
            )
            resp.raise_for_status()
            result = resp.json()
            return JsonResponse(result)
        except requests.RequestException as e:
            logger.error(f"[InvoicePrint] Daemon request failed: {e}")
            return JsonResponse({"error": f"Daemon unavailable: {e}"}, status=502)

    def api_job_status(self, request, job_id):
        """GET /api/plugin/invoice_print/status/{job_id}/ - Check job status."""
        if request.method != "GET":
            return JsonResponse({"error": "Method not allowed"}, status=405)

        daemon_url = self.get_setting("DAEMON_URL")
        try:
            resp = requests.get(f"{daemon_url}/jobs/{job_id}", timeout=10)
            resp.raise_for_status()
            return JsonResponse(resp.json())
        except requests.RequestException as e:
            logger.error(f"[InvoicePrint] Daemon status check failed: {e}")
            return JsonResponse({"error": f"Daemon unavailable: {e}"}, status=502)

    def api_pdf_download(self, request, job_id):
        """GET /api/plugin/invoice_print/pdf/{job_id}/ - Download waybill PDF."""
        if request.method != "GET":
            return JsonResponse({"error": "Method not allowed"}, status=405)

        from django.http import HttpResponse as DjHttpResponse

        daemon_url = self.get_setting("DAEMON_URL")
        try:
            resp = requests.get(f"{daemon_url}/pdfs/{job_id}", timeout=30, stream=True)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "application/pdf")
            response = DjHttpResponse(resp.content, content_type=content_type)
            response["Content-Disposition"] = f'attachment; filename="waybill-{job_id}.pdf"'
            return response
        except requests.RequestException as e:
            logger.error(f"[InvoicePrint] PDF download failed: {e}")
            return JsonResponse({"error": f"PDF download failed: {e}"}, status=502)

    def process_event(self, event, *args, **kwargs):
        """Handle InvenTree events."""
        if event != "salesordershipment.completed":
            return

        if not self.get_setting("AUTO_GENERATE"):
            return

        shipment = kwargs.get("model", None)
        if shipment is None:
            return

        order = shipment.order
        carrier = self.get_setting("DEFAULT_CARRIER")

        # Check if order metadata specifies a carrier
        if hasattr(order, "metadata") and order.metadata:
            meta_carrier = (order.metadata or {}).get("ecommerce_plugin", {}).get("carrier")
            if meta_carrier in ("yamato", "sagawa"):
                carrier = meta_carrier

        params = self._extract_shipment_params(order, shipment)

        daemon_url = self.get_setting("DAEMON_URL")
        try:
            resp = requests.post(
                f"{daemon_url}/jobs",
                json={
                    "type": "print_waybill",
                    "carrier": carrier,
                    "priority": 5,
                    "params": params,
                },
                timeout=10,
            )
            resp.raise_for_status()
            result = resp.json()
            logger.info(
                f"[InvoicePrint] Auto-generated waybill job {result.get('job_id')} "
                f"for shipment {shipment.pk} via {carrier}"
            )
        except requests.RequestException as e:
            logger.error(
                f"[InvoicePrint] Failed to auto-generate waybill for shipment "
                f"{shipment.pk}: {e}"
            )

    def _extract_shipment_params(self, order, shipment):
        """Extract recipient details from a SalesOrder for waybill generation."""
        params = {
            "sales_order_id": f"SO-{order.pk:04d}",
            "recipient_name": "",
            "recipient_address": "",
            "recipient_phone": "",
            "items_description": "",
        }

        # Try to get recipient info from order metadata or customer
        if hasattr(order, "customer") and order.customer:
            customer = order.customer
            params["recipient_name"] = str(customer.name) if customer.name else ""

            if hasattr(customer, "primary_address") and customer.primary_address:
                addr = customer.primary_address
                parts = [
                    str(getattr(addr, "line1", "") or ""),
                    str(getattr(addr, "line2", "") or ""),
                    str(getattr(addr, "postal_city", "") or ""),
                    str(getattr(addr, "province", "") or ""),
                    str(getattr(addr, "postal_code", "") or ""),
                ]
                params["recipient_address"] = " ".join(p for p in parts if p)
                params["recipient_phone"] = str(getattr(addr, "phone", "") or "")

        # Build items description from shipment allocations
        try:
            items = []
            for alloc in shipment.allocations.all():
                if hasattr(alloc, "line") and alloc.line:
                    part = alloc.line.part
                    items.append(str(part.name) if part else "")
            params["items_description"] = ", ".join(items[:5])
        except Exception:
            pass

        return params
