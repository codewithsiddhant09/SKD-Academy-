from fastapi import APIRouter

from app.api import deps
from app.core.config import get_settings
from app.models.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    knowledge = deps.assistant.knowledge if deps.assistant else None
    return HealthResponse(
        status="ok",
        app=get_settings().app_name,
        rag_ready=bool(knowledge and knowledge.is_ready()),
        categories_cached=deps.category_service.is_cached(),
    )
