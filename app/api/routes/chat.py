from fastapi import APIRouter, HTTPException

from app.api import deps
from app.core.logging import get_logger
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    DebugIntentRequest,
    DebugIntentResponse,
    DebugRagRequest,
    DebugRagResponse,
)

logger = get_logger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    if deps.orchestrator_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return deps.orchestrator_service.chat(
        session_id=payload.session_id,
        user_message=payload.message,
        user_id=payload.user_id,
    )


@router.post("/debug-rag", response_model=DebugRagResponse)
def debug_rag(payload: DebugRagRequest) -> DebugRagResponse:
    if deps.orchestrator_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    faq_agent = deps.orchestrator_service.workflow.faq_agent
    return faq_agent.debug_answer(payload.question)


@router.post("/debug-intent", response_model=DebugIntentResponse)
def debug_intent(payload: DebugIntentRequest) -> DebugIntentResponse:
    """Debug endpoint to test intent classification.
    
    Returns the detected intent for a user message along with
    category and service information if available.
    """
    if deps.orchestrator_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    intent_agent = deps.orchestrator_service.workflow.intent_agent
    session_id = "debug_session"
    history = deps.orchestrator_service.memory.get_history(session_id)
    
    analysis = intent_agent.analyze(
        message=payload.message,
        categories=deps.orchestrator_service.workflow.categories,
        history=history,
    )
    
    logger.info(
        "DEBUG_INTENT: message='%s', intent='%s', category='%s', service='%s'",
        payload.message,
        analysis.intent,
        analysis.category,
        analysis.service,
    )
    
    # Determine if this would trigger RAG
    rag_keywords = ["faq", "policy", "cancellation", "what", "why", "how", "bookly", "mission", "vision", "payment", "refund"]
    text = payload.message.lower()
    would_trigger_rag = analysis.intent in ["faq", "policy", "appointment_cancellation"]
    
    explanation = (
        f"Intent detected: {analysis.intent}. "
        f"Will route to: "
        f"{'faq_agent (RAG pipeline)' if would_trigger_rag else 'other agent (no RAG)'}."
    )
    
    return DebugIntentResponse(
        message=payload.message,
        intent=analysis.intent,
        category=analysis.category,
        service=analysis.service,
        explanation=explanation,
    )
