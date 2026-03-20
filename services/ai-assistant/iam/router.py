"""IAM API — staff management and permission resolution."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from iam import service
from iam.permissions import CATEGORIES, PERMISSIONS, ROLES

log = logging.getLogger(__name__)
router = APIRouter()


# -- Request/Response models --

class StaffCreateRequest(BaseModel):
    email: str
    display_name: str
    role: str = "staff"
    photo_url: str | None = None


class StaffUpdateRequest(BaseModel):
    display_name: str | None = None
    role: str | None = None
    photo_url: str | None = None


class DenyRulesRequest(BaseModel):
    permissions: list[str]


# -- Helpers --

def _get_caller_email(request: Request) -> str:
    """Extract caller email from X-User-Email header."""
    email = request.headers.get("X-User-Email")
    if not email:
        raise HTTPException(status_code=401, detail="Missing X-User-Email header")
    return email.lower().strip()


async def _require_staff_manage(request: Request) -> str:
    """Verify caller has staff.manage permission. Returns caller email."""
    email = _get_caller_email(request)
    resolved = await service.resolve_permissions(email)
    if "staff.manage" not in resolved["all_permissions"]:
        raise HTTPException(status_code=403, detail="Requires staff.manage permission")
    return email


# -- Endpoints --

@router.get("/me")
async def get_my_profile(request: Request):
    """Get current user's IAM profile and permissions."""
    email = _get_caller_email(request)
    resolved = await service.resolve_permissions(email)
    staff = await service.get_staff(email)
    return {
        "email": email,
        "staff": staff,
        **resolved,
    }


@router.get("/permissions")
async def list_permissions():
    """List all available permissions with labels."""
    result = []
    for perm_id, perm in PERMISSIONS.items():
        result.append({
            "id": perm_id,
            **perm,
            "category_labels": CATEGORIES.get(perm["category"], {}),
        })
    return {"permissions": result, "categories": CATEGORIES, "roles": list(ROLES)}


@router.get("/staff")
async def list_all_staff(request: Request):
    """List all registered staff members."""
    await _require_staff_manage(request)
    staff_list = await service.list_staff()
    return {"staff": staff_list}


@router.post("/staff", status_code=201)
async def create_staff(body: StaffCreateRequest, request: Request):
    """Register a new staff member."""
    await _require_staff_manage(request)
    try:
        staff = await service.register_staff(
            email=body.email,
            display_name=body.display_name,
            role=body.role,
            photo_url=body.photo_url,
        )
        return staff
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise HTTPException(status_code=409, detail=f"Staff {body.email} already exists")
        raise


@router.get("/staff/{email}")
async def get_staff_detail(email: str, request: Request):
    """Get staff member details with deny rules."""
    await _require_staff_manage(request)
    staff = await service.get_staff(email)
    if not staff:
        raise HTTPException(status_code=404, detail=f"Staff {email} not found")
    return staff


@router.put("/staff/{email}")
async def update_staff_member(email: str, body: StaffUpdateRequest, request: Request):
    """Update staff member's role or profile."""
    caller = await _require_staff_manage(request)

    # Prevent changing superuser's role
    existing = await service.get_staff(email)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Staff {email} not found")
    if existing["role"] == "superuser" and body.role and body.role != "superuser":
        raise HTTPException(status_code=403, detail="Cannot change superuser's role")
    # Only superuser can promote to superuser
    if body.role == "superuser":
        caller_info = await service.get_staff(caller)
        if not caller_info or caller_info["role"] != "superuser":
            raise HTTPException(status_code=403, detail="Only superuser can promote to superuser")

    try:
        result = await service.update_staff(
            email,
            display_name=body.display_name,
            role=body.role,
            photo_url=body.photo_url,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/staff/{email}")
async def delete_staff_member(email: str, request: Request):
    """Remove a staff member."""
    await _require_staff_manage(request)
    try:
        deleted = await service.delete_staff(email)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Staff {email} not found")
        return {"deleted": True, "email": email}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.put("/staff/{email}/deny-rules")
async def update_deny_rules(email: str, body: DenyRulesRequest, request: Request):
    """Set deny rules for a staff member (replaces existing rules)."""
    await _require_staff_manage(request)
    try:
        result = await service.set_deny_rules(email, body.permissions)
        if not result:
            raise HTTPException(status_code=404, detail=f"Staff {email} not found")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
