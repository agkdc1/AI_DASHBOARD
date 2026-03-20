"""Fax review API endpoints."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class ApproveRequest(BaseModel):
    doc_id: str | None = None
    pdf_id: str | None = None


@router.get("/pending")
async def list_pending(request: Request):
    """List fax PDF+Doc pairs pending review."""
    try:
        service = request.app.state.fax_review
        return await service.list_pending()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/approve")
async def approve(body: ApproveRequest, request: Request):
    """Move reviewed fax files to the 'reviewed' folder."""
    if not body.doc_id and not body.pdf_id:
        raise HTTPException(status_code=400, detail="At least one of doc_id or pdf_id is required")
    try:
        service = request.app.state.fax_review
        return await service.approve(body.doc_id, body.pdf_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
