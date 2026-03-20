"""Printer & Tray CRUD API views (staff-only, JSON responses)."""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect

from .models import Printer, Tray

logger = logging.getLogger("inventree")


def _require_staff(request):
    """Return a 403 JsonResponse if user is not staff, else None."""
    if not request.user or not request.user.is_staff:
        return JsonResponse({"error": "Forbidden"}, status=403)
    return None


def _parse_json(request):
    """Parse JSON body, return (dict, None) or (None, JsonResponse)."""
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, ValueError):
        return None, JsonResponse({"error": "Invalid JSON body"}, status=400)


def _printer_to_dict(printer):
    """Serialize a Printer instance (with nested trays) to dict."""
    return {
        "id": printer.id,
        "name": printer.name,
        "ip": str(printer.ip),
        "platform": printer.platform,
        "has_multiple_trays": printer.has_multiple_trays,
        "trays": [
            {
                "id": tray.id,
                "name": tray.name,
                "paper_size": tray.paper_size,
                "label_type": tray.label_type,
            }
            for tray in printer.trays.all()
        ],
    }


def _tray_to_dict(tray):
    """Serialize a Tray instance to dict."""
    return {
        "id": tray.id,
        "name": tray.name,
        "paper_size": tray.paper_size,
        "label_type": tray.label_type,
        "printer_id": tray.printer_id,
    }


def handle_printers(request):
    """GET: list all printers with trays. POST: create a printer."""
    err = _require_staff(request)
    if err:
        return err

    if request.method == "GET":
        printers = Printer.objects.prefetch_related("trays").all()
        return JsonResponse([_printer_to_dict(p) for p in printers], safe=False)

    if request.method == "POST":
        body, err = _parse_json(request)
        if err:
            return err

        name = body.get("name", "").strip()
        ip = body.get("ip", "").strip()
        platform = body.get("platform", "").strip()
        has_multiple_trays = bool(body.get("has_multiple_trays", False))

        if not name or not ip or not platform:
            return JsonResponse(
                {"error": "name, ip, and platform are required"}, status=400
            )
        if platform not in ("yamato", "sagawa"):
            return JsonResponse(
                {"error": "platform must be 'yamato' or 'sagawa'"}, status=400
            )

        printer = Printer.objects.create(
            name=name, ip=ip, platform=platform,
            has_multiple_trays=has_multiple_trays,
        )

        # Optionally create trays inline
        for tray_data in body.get("trays", []):
            Tray.objects.create(
                printer=printer,
                name=tray_data.get("name", "").strip(),
                paper_size=tray_data.get("paper_size", "").strip(),
                label_type=tray_data.get("label_type", "").strip(),
            )

        printer.refresh_from_db()
        return JsonResponse(_printer_to_dict(printer), status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def handle_printer_detail(request, pk):
    """GET/PUT/DELETE a single printer."""
    err = _require_staff(request)
    if err:
        return err

    try:
        printer = Printer.objects.prefetch_related("trays").get(pk=pk)
    except Printer.DoesNotExist:
        return JsonResponse({"error": "Printer not found"}, status=404)

    if request.method == "GET":
        return JsonResponse(_printer_to_dict(printer))

    if request.method == "PUT":
        body, err = _parse_json(request)
        if err:
            return err

        if "name" in body:
            printer.name = body["name"].strip()
        if "ip" in body:
            printer.ip = body["ip"].strip()
        if "platform" in body:
            if body["platform"] not in ("yamato", "sagawa"):
                return JsonResponse(
                    {"error": "platform must be 'yamato' or 'sagawa'"}, status=400
                )
            printer.platform = body["platform"]
        if "has_multiple_trays" in body:
            printer.has_multiple_trays = bool(body["has_multiple_trays"])

        printer.save()
        printer.refresh_from_db()
        return JsonResponse(_printer_to_dict(printer))

    if request.method == "DELETE":
        printer.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def handle_trays(request, printer_pk):
    """GET: list trays for a printer. POST: add a tray."""
    err = _require_staff(request)
    if err:
        return err

    try:
        printer = Printer.objects.get(pk=printer_pk)
    except Printer.DoesNotExist:
        return JsonResponse({"error": "Printer not found"}, status=404)

    if request.method == "GET":
        trays = printer.trays.all()
        return JsonResponse([_tray_to_dict(t) for t in trays], safe=False)

    if request.method == "POST":
        body, err = _parse_json(request)
        if err:
            return err

        name = body.get("name", "").strip()
        paper_size = body.get("paper_size", "").strip()
        label_type = body.get("label_type", "").strip()

        if not name or not paper_size or not label_type:
            return JsonResponse(
                {"error": "name, paper_size, and label_type are required"}, status=400
            )

        tray = Tray.objects.create(
            printer=printer,
            name=name,
            paper_size=paper_size,
            label_type=label_type,
        )
        return JsonResponse(_tray_to_dict(tray), status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def handle_tray_detail(request, printer_pk, pk):
    """PUT/DELETE a single tray."""
    err = _require_staff(request)
    if err:
        return err

    try:
        tray = Tray.objects.get(pk=pk, printer_id=printer_pk)
    except Tray.DoesNotExist:
        return JsonResponse({"error": "Tray not found"}, status=404)

    if request.method == "GET":
        return JsonResponse(_tray_to_dict(tray))

    if request.method == "PUT":
        body, err = _parse_json(request)
        if err:
            return err

        if "name" in body:
            tray.name = body["name"].strip()
        if "paper_size" in body:
            tray.paper_size = body["paper_size"].strip()
        if "label_type" in body:
            tray.label_type = body["label_type"].strip()

        tray.save()
        return JsonResponse(_tray_to_dict(tray))

    if request.method == "DELETE":
        tray.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"error": "Method not allowed"}, status=405)
