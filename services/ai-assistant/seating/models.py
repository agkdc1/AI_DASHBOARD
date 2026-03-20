"""Pydantic request/response models for the seating module."""

from pydantic import BaseModel


class OfficeCreate(BaseModel):
    name: str
    address: str | None = None


class OfficeResponse(BaseModel):
    id: int
    name: str
    address: str | None
    created_at: str


class FloorCreate(BaseModel):
    office_id: int
    floor_number: int
    name: str | None = None


class FloorResponse(BaseModel):
    id: int
    office_id: int
    floor_number: int
    name: str | None
    floorplan_image: str | None
    created_at: str


class RoomCreate(BaseModel):
    floor_id: int
    room_number: int
    name: str | None = None


class RoomResponse(BaseModel):
    id: int
    floor_id: int
    room_number: int
    name: str | None
    created_at: str


class DeskCreate(BaseModel):
    room_id: int
    desk_number: int
    phone_mac: str | None = None
    phone_model: str = "GXP1760W"
    desk_type: str = "open"
    designated_email: str | None = None
    pos_x: float | None = None
    pos_y: float | None = None


class DeskUpdate(BaseModel):
    phone_mac: str | None = None
    phone_model: str | None = None
    phone_ip: str | None = None
    desk_type: str | None = None
    designated_email: str | None = None
    pos_x: float | None = None
    pos_y: float | None = None


class DeskResponse(BaseModel):
    id: int
    room_id: int
    desk_number: int
    desk_extension: str
    phone_mac: str | None
    phone_model: str | None
    phone_ip: str | None
    desk_type: str
    designated_email: str | None
    pos_x: float | None
    pos_y: float | None
    created_at: str


class AssignmentResponse(BaseModel):
    id: int
    desk_id: int
    employee_email: str
    employee_name: str
    employee_extension: str
    checked_in_at: str
    checked_out_at: str | None


class DeskWithStatus(BaseModel):
    desk: DeskResponse
    current_assignment: AssignmentResponse | None = None


class FloorMap(BaseModel):
    floor: FloorResponse
    desks: list[DeskWithStatus]


class CheckInRequest(BaseModel):
    desk_id: int


class CheckOutRequest(BaseModel):
    desk_id: int | None = None
