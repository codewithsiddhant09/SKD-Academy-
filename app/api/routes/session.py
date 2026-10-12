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
    if deps.assistant is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # When a userId is explicitly provided and the DB is reachable, a missing
    # user is a 404 (not a 500). If the DB is unreachable we degrade gracefully.
    if payload.user_id:
        user_service = deps.assistant.users
        if user_service.is_available():
            profile = user_service.get_user_profile(payload.user_id)
            if profile is None:
                logger.info("SESSION_START: user not found user_id=%s -> 404", payload.user_id)
                raise HTTPException(status_code=404, detail=f"User not found: {payload.user_id}")

    context = deps.assistant.ensure_user_context(payload.session_id, payload.user_id)
    context = context or SessionContext(user_id=payload.user_id)

    if context.full_name:
        greeting = f"Welcome back {context.full_name}.\n\nHow may I assist you today?"
    else:
        greeting = "Welcome to Bookly.\n\nHow may I assist you today?"

    logger.info("SESSION_START: session=%s user_id=%s personalized=%s", payload.session_id, payload.user_id, bool(context.full_name))

    return SessionStartResponse(session_id=payload.session_id, greeting=greeting, context=context)
