"""Seating business logic — CRUD, check-in/out, CFU management, wall extraction."""

import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from config import settings
from seating.db import get_db
from seating.models import (
    AssignmentResponse,
    DeskCreate,
    DeskResponse,
    DeskUpdate,
    DeskWithStatus,
    FloorCreate,
    FloorMap,
    FloorResponse,
    OfficeCreate,
    OfficeResponse,
    RoomCreate,
    RoomResponse,
)

log = logging.getLogger(__name__)


def _faxapi_headers() -> dict:
    """Build faxapi request headers with API key if available."""
    headers: dict[str, str] = {}
    if hasattr(settings, "faxapi_key") and settings.faxapi_key:
        headers["X-API-Key"] = settings.faxapi_key
    return headers


def _compute_extension(floor_number: int, room_number: int, desk_number: int) -> str:
    """Compute desk extension from floor/room/desk: FRDD format."""
    return f"{floor_number}{room_number}{desk_number:02d}"


# ---------------------------------------------------------------------------
# Office CRUD
# ---------------------------------------------------------------------------


async def list_offices() -> list[OfficeResponse]:
    db = await get_db()
    try:
        rows = await db.execute_fetchall("SELECT * FROM offices ORDER BY id")
        return [OfficeResponse(**dict(r)) for r in rows]
    finally:
        await db.close()


async def create_office(data: OfficeCreate) -> OfficeResponse:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO offices (name, address) VALUES (?, ?)",
            (data.name, data.address),
        )
        await db.commit()
        row = await db.execute_fetchall(
            "SELECT * FROM offices WHERE id = ?", (cursor.lastrowid,)
        )
        return OfficeResponse(**dict(row[0]))
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Floor CRUD
# ---------------------------------------------------------------------------


async def list_floors(office_id: int) -> list[FloorResponse]:
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT * FROM floors WHERE office_id = ? ORDER BY floor_number",
            (office_id,),
        )
        return [FloorResponse(**dict(r)) for r in rows]
    finally:
        await db.close()


async def create_floor(data: FloorCreate) -> FloorResponse:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO floors (office_id, floor_number, name) VALUES (?, ?, ?)",
            (data.office_id, data.floor_number, data.name),
        )
        await db.commit()
        row = await db.execute_fetchall(
            "SELECT * FROM floors WHERE id = ?", (cursor.lastrowid,)
        )
        return FloorResponse(**dict(row[0]))
    finally:
        await db.close()


async def upload_floorplan(floor_id: int, image_bytes: bytes, filename: str) -> str:
    """Save floor plan image and update DB. Returns saved filename."""
    db = await get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT id FROM floors WHERE id = ?", (floor_id,)
        )
        if not row:
            raise ValueError(f"Floor {floor_id} not found")

        ext = Path(filename).suffix or ".png"
        saved_name = f"floor_{floor_id}{ext}"
        save_path = Path(settings.floorplan_dir) / saved_name
        save_path.write_bytes(image_bytes)

        await db.execute(
            "UPDATE floors SET floorplan_image = ? WHERE id = ?",
            (saved_name, floor_id),
        )
        await db.commit()
        log.info("Saved floorplan: %s (%d bytes)", saved_name, len(image_bytes))
        return saved_name
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Room CRUD
# ---------------------------------------------------------------------------


async def list_rooms(floor_id: int) -> list[RoomResponse]:
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT * FROM rooms WHERE floor_id = ? ORDER BY room_number",
            (floor_id,),
        )
        return [RoomResponse(**dict(r)) for r in rows]
    finally:
        await db.close()


async def create_room(data: RoomCreate) -> RoomResponse:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO rooms (floor_id, room_number, name) VALUES (?, ?, ?)",
            (data.floor_id, data.room_number, data.name),
        )
        await db.commit()
        row = await db.execute_fetchall(
            "SELECT * FROM rooms WHERE id = ?", (cursor.lastrowid,)
        )
        return RoomResponse(**dict(row[0]))
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Desk CRUD
# ---------------------------------------------------------------------------


async def _get_desk_context(db, room_id: int) -> tuple[int, int]:
    """Get floor_number and room_number for extension computation."""
    row = await db.execute_fetchall(
        """SELECT f.floor_number, r.room_number
           FROM rooms r JOIN floors f ON r.floor_id = f.id
           WHERE r.id = ?""",
        (room_id,),
    )
    if not row:
        raise ValueError(f"Room {room_id} not found")
    return row[0]["floor_number"], row[0]["room_number"]


async def create_desk(data: DeskCreate) -> DeskResponse:
    """Create a desk, compute its extension, and register in Asterisk."""
    db = await get_db()
    try:
        floor_num, room_num = await _get_desk_context(db, data.room_id)
        extension = _compute_extension(floor_num, room_num, data.desk_number)

        cursor = await db.execute(
            """INSERT INTO desks
               (room_id, desk_number, desk_extension, phone_mac, phone_model,
                desk_type, designated_email, pos_x, pos_y)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.room_id,
                data.desk_number,
                extension,
                data.phone_mac,
                data.phone_model,
                data.desk_type,
                data.designated_email,
                data.pos_x,
                data.pos_y,
            ),
        )
        await db.commit()
        row = await db.execute_fetchall(
            "SELECT * FROM desks WHERE id = ?", (cursor.lastrowid,)
        )
        desk = DeskResponse(**dict(row[0]))
    finally:
        await db.close()

    # Create Asterisk extension via faxapi
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(
                f"{settings.faxapi_url}/extensions",
                json={
                    "extension": extension,
                    "name": f"Desk {extension}",
                    "password": f"desk{extension}",
                },
                headers=_faxapi_headers(),
            )
            log.info("Created Asterisk extension for desk %s", extension)
    except Exception as exc:
        log.warning("Asterisk extension creation for desk %s failed: %s", extension, exc)

    return desk


async def update_desk(desk_id: int, data: DeskUpdate) -> DeskResponse:
    db = await get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT * FROM desks WHERE id = ?", (desk_id,)
        )
        if not row:
            raise ValueError(f"Desk {desk_id} not found")

        current = dict(row[0])
        updates = data.model_dump(exclude_unset=True)
        if not updates:
            return DeskResponse(**current)

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [desk_id]
        await db.execute(
            f"UPDATE desks SET {set_clauses} WHERE id = ?", values
        )
        await db.commit()

        row = await db.execute_fetchall(
            "SELECT * FROM desks WHERE id = ?", (desk_id,)
        )
        return DeskResponse(**dict(row[0]))
    finally:
        await db.close()


async def delete_desk(desk_id: int) -> bool:
    db = await get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT desk_extension FROM desks WHERE id = ?", (desk_id,)
        )
        if not row:
            return False

        extension = row[0]["desk_extension"]
        await db.execute("DELETE FROM desks WHERE id = ?", (desk_id,))
        await db.commit()
    finally:
        await db.close()

    # Delete Asterisk extension
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.delete(
                f"{settings.faxapi_url}/extensions/{extension}",
                headers=_faxapi_headers(),
            )
            log.info("Deleted Asterisk extension %s", extension)
    except Exception as exc:
        log.warning("Asterisk extension deletion for %s failed: %s", extension, exc)

    return True


# ---------------------------------------------------------------------------
# Floor Map (desks + assignments)
# ---------------------------------------------------------------------------


async def get_floor_map(floor_id: int) -> FloorMap:
    db = await get_db()
    try:
        # Get floor
        floor_rows = await db.execute_fetchall(
            "SELECT * FROM floors WHERE id = ?", (floor_id,)
        )
        if not floor_rows:
            raise ValueError(f"Floor {floor_id} not found")
        floor = FloorResponse(**dict(floor_rows[0]))

        # Get all desks on this floor (across all rooms)
        desk_rows = await db.execute_fetchall(
            """SELECT d.* FROM desks d
               JOIN rooms r ON d.room_id = r.id
               WHERE r.floor_id = ?
               ORDER BY d.desk_extension""",
            (floor_id,),
        )

        desks_with_status = []
        for dr in desk_rows:
            desk = DeskResponse(**dict(dr))

            # Current assignment (not checked out)
            assign_rows = await db.execute_fetchall(
                """SELECT * FROM seat_assignments
                   WHERE desk_id = ? AND checked_out_at IS NULL
                   LIMIT 1""",
                (desk.id,),
            )
            assignment = None
            if assign_rows:
                assignment = AssignmentResponse(**dict(assign_rows[0]))

            desks_with_status.append(
                DeskWithStatus(desk=desk, current_assignment=assignment)
            )

        return FloorMap(floor=floor, desks=desks_with_status)
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Check-in / Check-out
# ---------------------------------------------------------------------------


async def check_in(email: str, display_name: str, desk_id: int) -> AssignmentResponse:
    """Check in an employee to a desk.

    1. Look up employee extension from AD (via PhoneService)
    2. Verify desk is available
    3. Auto-checkout from any previous desk
    4. Insert assignment
    5. Set CFU: employee_ext → desk_ext
    6. Push display name to phone
    """
    from phone.service import PhoneService

    phone_svc = PhoneService()

    # Look up employee SIP extension (retry once on LDAP failure)
    user = await phone_svc.find_by_email(email)
    if not user:
        # Retry with a fresh connection — LDAP may have timed out
        log.warning("LDAP lookup failed for %s, retrying with reconnect", email)
        phone_svc._reconnect()
        user = await phone_svc.find_by_email(email)
    if not user:
        raise ValueError(f"No SIP extension found for {email}. Check AD account has mail attribute set.")
    employee_ext = user["telephoneNumber"]
    if not employee_ext:
        raise ValueError(f"AD account for {email} has no telephoneNumber attribute")

    # Use AD display name (cn) as authoritative source, fall back to header
    ad_name = (user.get("cn") or "").strip()
    effective_name = ad_name if ad_name else display_name

    db = await get_db()
    try:
        # Verify desk exists and is available
        desk_rows = await db.execute_fetchall(
            "SELECT * FROM desks WHERE id = ?", (desk_id,)
        )
        if not desk_rows:
            raise ValueError(f"Desk {desk_id} not found")
        desk = dict(desk_rows[0])

        # Check designated desk restrictions
        if desk["desk_type"] == "designated" and desk["designated_email"] != email:
            raise ValueError("This desk is designated for another employee")

        # Check if desk is already occupied
        occupied = await db.execute_fetchall(
            """SELECT * FROM seat_assignments
               WHERE desk_id = ? AND checked_out_at IS NULL""",
            (desk_id,),
        )
        if occupied:
            raise ValueError("Desk is already occupied")

        # Auto-checkout from any previous desk
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        prev = await db.execute_fetchall(
            """SELECT sa.*, d.desk_extension, d.phone_ip
               FROM seat_assignments sa
               JOIN desks d ON sa.desk_id = d.id
               WHERE sa.employee_email = ? AND sa.checked_out_at IS NULL""",
            (email,),
        )
        for p in prev:
            await db.execute(
                "UPDATE seat_assignments SET checked_out_at = ? WHERE id = ?",
                (now, p["id"]),
            )
            # Clear CFU for old desk
            await _clear_cfu(employee_ext)
            # Reset old phone display
            if p["phone_ip"]:
                await _set_phone_display(p["phone_ip"], f"Desk {p['desk_extension']}")

        # Insert new assignment
        cursor = await db.execute(
            """INSERT INTO seat_assignments
               (desk_id, employee_email, employee_name, employee_extension)
               VALUES (?, ?, ?, ?)""",
            (desk_id, email, effective_name, employee_ext),
        )
        await db.commit()

        row = await db.execute_fetchall(
            "SELECT * FROM seat_assignments WHERE id = ?", (cursor.lastrowid,)
        )
        assignment = AssignmentResponse(**dict(row[0]))
    finally:
        await db.close()

    # Set CFU: employee ext → desk ext
    await _set_cfu(employee_ext, desk["desk_extension"])

    # Push display name to phone
    if desk["phone_ip"]:
        await _set_phone_display(desk["phone_ip"], display_name)

    log.info(
        "Check-in: %s (%s) → desk %s (ext %s)",
        email, employee_ext, desk_id, desk["desk_extension"],
    )
    return assignment


async def check_out(email: str, desk_id: int | None = None) -> AssignmentResponse:
    """Check out an employee. Clears CFU and resets phone display."""
    db = await get_db()
    try:
        if desk_id:
            rows = await db.execute_fetchall(
                """SELECT sa.*, d.desk_extension, d.phone_ip
                   FROM seat_assignments sa
                   JOIN desks d ON sa.desk_id = d.id
                   WHERE sa.desk_id = ? AND sa.employee_email = ?
                     AND sa.checked_out_at IS NULL""",
                (desk_id, email),
            )
        else:
            rows = await db.execute_fetchall(
                """SELECT sa.*, d.desk_extension, d.phone_ip
                   FROM seat_assignments sa
                   JOIN desks d ON sa.desk_id = d.id
                   WHERE sa.employee_email = ? AND sa.checked_out_at IS NULL""",
                (email,),
            )

        if not rows:
            raise ValueError("No active assignment found")

        row = dict(rows[0])
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        await db.execute(
            "UPDATE seat_assignments SET checked_out_at = ? WHERE id = ?",
            (now, row["id"]),
        )
        await db.commit()

        updated = await db.execute_fetchall(
            "SELECT * FROM seat_assignments WHERE id = ?", (row["id"],)
        )
        assignment = AssignmentResponse(**dict(updated[0]))
    finally:
        await db.close()

    # Clear CFU
    await _clear_cfu(row["employee_extension"])

    # Reset phone display name
    if row["phone_ip"]:
        await _set_phone_display(row["phone_ip"], f"Desk {row['desk_extension']}")

    log.info("Check-out: %s from desk ext %s", email, row["desk_extension"])
    return assignment


async def get_my_assignment(email: str) -> AssignmentResponse | None:
    """Get current active assignment for an employee."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT * FROM seat_assignments
               WHERE employee_email = ? AND checked_out_at IS NULL
               LIMIT 1""",
            (email,),
        )
        if not rows:
            return None
        return AssignmentResponse(**dict(rows[0]))
    finally:
        await db.close()


async def get_history(email: str, limit: int = 20) -> list[AssignmentResponse]:
    """Get past assignments for an employee."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT * FROM seat_assignments
               WHERE employee_email = ?
               ORDER BY checked_in_at DESC
               LIMIT ?""",
            (email, limit),
        )
        return [AssignmentResponse(**dict(r)) for r in rows]
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Helpers — faxapi calls for CFU and phone display
# ---------------------------------------------------------------------------


async def _set_cfu(extension: str, forward_to: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{settings.faxapi_url}/pbx/cfu",
                json={"extension": extension, "forward_to": forward_to},
                headers=_faxapi_headers(),
            )
    except Exception as exc:
        log.error("Failed to set CFU %s → %s: %s", extension, forward_to, exc)


async def _clear_cfu(extension: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.delete(
                f"{settings.faxapi_url}/pbx/cfu/{extension}",
                headers=_faxapi_headers(),
            )
    except Exception as exc:
        log.error("Failed to clear CFU %s: %s", extension, exc)


async def _set_phone_display(phone_ip: str, display_name: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{settings.faxapi_url}/phone/display-name",
                json={"phone_ip": phone_ip, "display_name": display_name},
                headers=_faxapi_headers(),
            )
    except Exception as exc:
        log.warning("Failed to set phone display %s → %s: %s", phone_ip, display_name, exc)


# ---------------------------------------------------------------------------
# Wall extraction — Gemini image generation
# ---------------------------------------------------------------------------

_WALL_EXTRACTION_PROMPT = """\
You are an architectural floor plan processor.

TASK: Extract ONLY the wall outlines from the floor plan in this image.

If the image is a screenshot from a phone/tablet app, CROP OUT any app UI
(header bars, toolbars, buttons, file info) and process only the floor plan.

REMOVE everything except walls:
- ALL text: labels, dimensions, measurements, annotations, area values
- ALL colored/red markup, handwritten annotations, circles, arrows
- ALL dimension lines with arrows and numbers
- Door swing arcs (quarter-circle lines showing door opening direction)
- Staircase internal step lines and grid patterns
- Window detail lines, door symbols
- Plumbing, electrical, HVAC symbols
- Grid reference markers (circled numbers)
- Title blocks, borders, scale bars
- Furniture, fixtures, appliances

KEEP only:
- Exterior walls (thick solid lines forming the building outline)
- Interior partition walls (dividing rooms)
- Columns and structural pillars
- Wall openings shown as gaps (where doors/windows are)
- Outer walls of stairwells (not internal step lines)

OUTPUT: Clean black walls on pure white background. Same wall thickness as
original. The output should contain ONLY the floor plan walls — no UI, no
text, no annotations. Fill the entire output image with the wall drawing."""

_genai_client: Any = None


def _get_genai_client() -> Any:
    """Lazy-init google-genai client for Vertex AI (us-central1 for image model)."""
    global _genai_client
    if _genai_client is None:
        from google import genai

        _genai_client = genai.Client(
            vertexai=True,
            project=settings.gcp_project,
            location="us-central1",
        )
    return _genai_client


async def extract_walls(image_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
    """Extract wall outlines from a blueprint image using Gemini.

    Args:
        image_bytes: Raw image data (JPEG/PNG/WebP).
        mime_type: MIME type of the input image.

    Returns:
        Tuple of (output_image_bytes, output_mime_type).

    Raises:
        ValueError: If extraction fails or no image is returned.
    """
    import asyncio

    from google.genai import types

    client = _get_genai_client()

    def _call_gemini() -> tuple[bytes, str]:
        response = client.models.generate_content(
            model=settings.gemini_image_model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                _WALL_EXTRACTION_PROMPT,
            ],
            config=types.GenerateContentConfig(
                response_modalities=[types.Modality.TEXT, types.Modality.IMAGE],
                temperature=0.2,
            ),
        )

        # Extract image from response parts
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                return part.inline_data.data, part.inline_data.mime_type

        raise ValueError(
            "Gemini did not return an image. "
            "Ensure the input is a floor plan or blueprint."
        )

    # Run synchronous Gemini call in thread pool
    result = await asyncio.get_event_loop().run_in_executor(None, _call_gemini)

    # Validate output is a valid image
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(result[0]))
        img.verify()
    except Exception as exc:
        raise ValueError(f"Gemini returned invalid image data: {exc}")

    log.info(
        "Wall extraction: %d bytes in → %d bytes out (%s)",
        len(image_bytes),
        len(result[0]),
        result[1],
    )
    return result
