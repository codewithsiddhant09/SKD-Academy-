from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api import deps

router = APIRouter()


@router.post("/auth/session/{session_id}", include_in_schema=False)
def set_booking_token(session_id: str) -> dict:
    """Enable the configured server-side Bookly API token for a chat session."""
    if deps.assistant is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    if not deps.assistant.settings.bookly_api_token:
        raise HTTPException(status_code=503, detail="Bookly API token is not configured on the server")
    deps.assistant.sessions.get(session_id).auth_token = deps.assistant.settings.bookly_api_token
    return {"configured": True}


@router.delete("/auth/session/{session_id}", include_in_schema=False)
def clear_booking_token(session_id: str) -> dict:
    if deps.assistant is not None:
        session = deps.assistant.sessions.get(session_id)
        session.auth_token = None
        session.user = None
        session.booking_contact = None
    return {"configured": False}
