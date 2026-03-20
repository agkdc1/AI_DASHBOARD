"""FastAPI router for seating / hot-desking endpoints."""

import base64
import logging
from pathlib import Path

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response

from config import settings
from seating import service


def _resolve_email(
    request: Request,
    header_email: str,
) -> str:
    """Return a non-empty email or raise 401.

    Priority: X-User-Email header → X-Authentik-Email header (forward-auth).
    """
    email = (header_email or "").strip()
    if not email:
        # Fallback: check if forward-auth set the email
        email = (request.headers.get("X-Authentik-Email") or "").strip()
    if not email:
        raise HTTPException(
            status_code=401,
            detail="Authentication required: no email found. Please re-login.",
        )
    return email


def _decode_display_name(raw: str) -> str:
    """Decode Base64-encoded display name from X-User-Name header.

    Flutter Web cannot send non-ISO-8859-1 characters in HTTP headers,
    so Japanese/Korean names are Base64-encoded on the client side.
    Falls back to the raw value if decoding fails (plain ASCII names).
    """
    if not raw:
        return raw
    try:
        return base64.b64decode(raw).decode("utf-8")
    except Exception:
        return raw


from seating.models import (
    CheckInRequest,
    CheckOutRequest,
    DeskCreate,
    DeskUpdate,
    FloorCreate,
    OfficeCreate,
    RoomCreate,
)

log = logging.getLogger(__name__)

router = APIRouter()


def _get_email(x_user_email: str = Header(...)) -> str:
    """Extract user email from header (set by auth proxy)."""
    return x_user_email


# ---------------------------------------------------------------------------
# Admin: Offices
# ---------------------------------------------------------------------------


@router.get("/offices")
async def list_offices():
    return {"offices": await service.list_offices()}


@router.post("/offices")
async def create_office(data: OfficeCreate):
    office = await service.create_office(data)
    return office


# ---------------------------------------------------------------------------
# Admin: Floors
# ---------------------------------------------------------------------------


@router.get("/floors")
async def list_floors(office_id: int):
    return {"floors": await service.list_floors(office_id)}


@router.post("/floors")
async def create_floor(data: FloorCreate):
    floor = await service.create_floor(data)
    return floor


@router.post("/floors/{floor_id}/floorplan")
async def upload_floorplan(floor_id: int, file: UploadFile = File(...)):
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")
    filename = file.filename or "floorplan.png"
    try:
        saved = await service.upload_floorplan(floor_id, content, filename)
        return {"status": "ok", "filename": saved}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/floors/extract-walls")
async def extract_walls(file: UploadFile = File(...)):
    """Extract wall outlines from a blueprint image using Gemini.

    Accepts JPEG, PNG, or WebP. Returns a cleaned image with only walls.
    """
    ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
    content_type = file.content_type or ""
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}. Use JPEG, PNG, or WebP.",
        )

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    try:
        image_bytes, mime_type = await service.extract_walls(content, content_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        log.exception("Wall extraction failed")
        raise HTTPException(status_code=502, detail=f"Gemini API error: {exc}")

    return Response(
        content=image_bytes,
        media_type=mime_type,
        headers={"Content-Disposition": "inline; filename=walls.png"},
    )


@router.get("/floors/{floor_id}/floorplan")
async def get_floorplan(floor_id: int):
    from seating.db import get_db

    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT floorplan_image FROM floors WHERE id = ?", (floor_id,)
        )
        if not rows or not rows[0]["floorplan_image"]:
            raise HTTPException(status_code=404, detail="No floorplan uploaded")
        image_file = rows[0]["floorplan_image"]
    finally:
        await db.close()

    file_path = Path(settings.floorplan_dir) / image_file
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Floorplan file not found")
    return FileResponse(file_path)


# ---------------------------------------------------------------------------
# Admin: Rooms
# ---------------------------------------------------------------------------


@router.get("/rooms")
async def list_rooms(floor_id: int):
    return {"rooms": await service.list_rooms(floor_id)}


@router.post("/rooms")
async def create_room(data: RoomCreate):
    room = await service.create_room(data)
    return room


# ---------------------------------------------------------------------------
# Admin: Desks
# ---------------------------------------------------------------------------


@router.post("/desks")
async def create_desk(data: DeskCreate):
    try:
        desk = await service.create_desk(data)
        return desk
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/desks/{desk_id}")
async def update_desk(desk_id: int, data: DeskUpdate):
    try:
        desk = await service.update_desk(desk_id, data)
        return desk
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/desks/{desk_id}")
async def delete_desk(desk_id: int):
    deleted = await service.delete_desk(desk_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Desk {desk_id} not found")
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# User: Floor Map
# ---------------------------------------------------------------------------


@router.get("/floors/{floor_id}/map")
async def get_floor_map(floor_id: int):
    try:
        floor_map = await service.get_floor_map(floor_id)
        return floor_map
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# User: Check-in / Check-out
# ---------------------------------------------------------------------------


@router.get("/my-seat")
async def get_my_seat(
    request: Request,
    email: str = Header(alias="X-User-Email", default=""),
):
    resolved = _resolve_email(request, email)
    assignment = await service.get_my_assignment(resolved)
    if not assignment:
        return {"assignment": None}
    return {"assignment": assignment}


@router.post("/check-in")
async def check_in(
    data: CheckInRequest,
    request: Request,
    email: str = Header(alias="X-User-Email", default=""),
    display_name: str = Header(alias="X-User-Name", default=""),
):
    resolved = _resolve_email(request, email)
    name = _decode_display_name(display_name)
    try:
        assignment = await service.check_in(resolved, name or resolved, data.desk_id)
        return assignment
    except ValueError as exc:
        log.warning("Check-in failed for %s desk=%s: %s", resolved, data.desk_id, exc)
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/check-out")
async def check_out(
    data: CheckOutRequest,
    request: Request,
    email: str = Header(alias="X-User-Email", default=""),
):
    resolved = _resolve_email(request, email)
    try:
        assignment = await service.check_out(resolved, data.desk_id)
        return assignment
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# User: History
# ---------------------------------------------------------------------------


@router.get("/history")
async def get_history(
    request: Request,
    email: str = Header(alias="X-User-Email", default=""),
    limit: int = 20,
):
    resolved = _resolve_email(request, email)
    history = await service.get_history(resolved, limit)
    return {"history": history}
