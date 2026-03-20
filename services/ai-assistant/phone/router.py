"""Phone admin API — LDAP user CRUD and device management."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter()


# -- Request/Response models --

class UserCreateRequest(BaseModel):
    uid: str
    cn: str
    password: str = "1234"


class UserUpdateRequest(BaseModel):
    cn: str | None = None
    password: str | None = None


class UserResponse(BaseModel):
    uid: str
    cn: str
    telephoneNumber: str = ""
    dn: str = ""


class AutoProvisionRequest(BaseModel):
    email: str
    display_name: str


class AutoProvisionResponse(BaseModel):
    accounts: list[dict]
    newly_created: bool
    extension: str


class DeviceResponse(BaseModel):
    mac: str
    type: str
    name: str = ""
    extension: str = ""


# -- Endpoints --

@router.get("/users")
async def list_users(request: Request) -> list[UserResponse]:
    """List all LDAP phonebook users."""
    phone = request.app.state.phone
    users = await phone.list_users()
    return [UserResponse(**u) for u in users]


@router.get("/users/{uid}")
async def get_user(uid: str, request: Request) -> UserResponse:
    """Get a single user by extension number."""
    phone = request.app.state.phone
    user = await phone.get_user(uid)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {uid} not found")
    return UserResponse(**user)


@router.post("/users", status_code=201)
async def create_user(body: UserCreateRequest, request: Request) -> UserResponse:
    """Create a new LDAP phonebook entry."""
    phone = request.app.state.phone
    result = await phone.create_user(uid=body.uid, cn=body.cn, password=body.password)
    if "error" in result:
        raise HTTPException(status_code=409, detail=result["error"])
    return UserResponse(**result)


@router.put("/users/{uid}")
async def update_user(uid: str, body: UserUpdateRequest, request: Request) -> UserResponse:
    """Update an existing LDAP user."""
    phone = request.app.state.phone
    result = await phone.update_user(uid, cn=body.cn, password=body.password)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return UserResponse(**result)


@router.delete("/users/{uid}")
async def delete_user(uid: str, request: Request):
    """Delete an LDAP user."""
    phone = request.app.state.phone
    deleted = await phone.delete_user(uid)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"User {uid} not found")
    return {"deleted": True, "uid": uid}


@router.post("/auto-provision")
async def auto_provision(body: AutoProvisionRequest, request: Request):
    """Auto-provision a phone extension for a user on first login."""
    phone = request.app.state.phone
    result = await phone.auto_provision(email=body.email, display_name=body.display_name)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/devices")
async def list_devices(request: Request) -> list[DeviceResponse]:
    """List all known phone devices."""
    phone = request.app.state.phone
    devices = await phone.list_devices()
    return [DeviceResponse(**d) for d in devices]
