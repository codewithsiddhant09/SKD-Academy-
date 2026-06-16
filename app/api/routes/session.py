from fastapi import APIRouter, HTTPException

from app.api import deps
from app.core.logging import get_logger
from app.models.schemas import SessionContext, SessionStartRequest, SessionStartResponse

logger = get_logger(__name__)
router = APIRouter()


@router.post("/session/start", response_model=SessionStartResponse)
def start_session(payload: SessionStartRequest) -> SessionStartResponse:
    """Initialize a session: load the user profile and return a greeting.

    This is additive and does not alter the existing chat or socket flows.
    """
    if deps.orchestrator_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    context = deps.orchestrator_service.ensure_user_context(payload.session_id, payload.user_id)
    context = context or SessionContext(user_id=payload.user_id)

    if context.full_name:
        greeting = f"Welcome back {context.full_name}.\n\nHow may I assist you today?"
    else:
        greeting = "Welcome to Bookly.\n\nHow may I assist you today?"

    logger.info("SESSION_START: session=%s user_id=%s personalized=%s", payload.session_id, payload.user_id, bool(context.full_name))

    return SessionStartResponse(session_id=payload.session_id, greeting=greeting, context=context)
