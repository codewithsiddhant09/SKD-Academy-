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
    return _assistant().chat(session_id=payload.session_id, user_message=payload.message, user_id=payload.user_id)


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
