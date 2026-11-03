from fastapi import APIRouter, HTTPException

from app.api import deps
from app.models.schemas import ChatRequest, ChatResponse, DebugRagRequest, DebugRagResponse

router = APIRouter()


def _assistant():
    if deps.assistant is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return deps.assistant


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    
    logger.info("=== CHAT REQUEST RECEIVED ===")
    logger.info("session_id: %s", payload.session_id)
    logger.info("platform: %s", payload.platform)
    logger.info("user_id: %s", payload.user_id)
    logger.info("auth_token present: %s", bool(payload.auth_token))
    logger.info("auth_token value: %s", payload.auth_token[:20] + "..." if payload.auth_token and len(payload.auth_token) > 20 else payload.auth_token)
    
    assistant = _assistant()
    session = assistant.sessions.get(payload.session_id)
    session.booking_platform = payload.platform
    session.whatsapp_phone = payload.user_id if payload.platform == "whatsapp" else None
    session.whatsapp_name = payload.user_name if payload.platform == "whatsapp" else None
    if payload.platform == "app" and payload.auth_token:
        session.jwt_token = payload.auth_token
        logger.info("Auth token saved to session.jwt_token")
    else:
        logger.warning("No auth_token provided! platform=%s, auth_token=%s", payload.platform, payload.auth_token)
    if payload.payment_option:
        session.payment_option = payload.payment_option
    return assistant.chat(session_id=payload.session_id, user_message=payload.message, user_id=payload.user_id if payload.platform == "app" else None)


@router.post("/debug-rag", response_model=DebugRagResponse)
def debug_rag(payload: DebugRagRequest) -> DebugRagResponse:
    """Show which knowledge-base passages a question retrieves."""
    knowledge = _assistant().knowledge
    if knowledge is None:
        raise HTTPException(status_code=503, detail="Knowledge base not configured")
    hits = knowledge.retrieve_with_scores(payload.question)
    return DebugRagResponse(
        question=payload.question,
        retrieved_chunks=[doc.page_content for doc, _ in hits],
        similarity_scores=[score for _, score in hits],
        sources=[(doc.metadata or {}).get("source") for doc, _ in hits],
    )
