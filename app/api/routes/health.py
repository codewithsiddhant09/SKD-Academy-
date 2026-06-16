from fastapi import APIRouter

from app.api.deps import category_service
from app.core.config import get_settings
from app.models.schemas import HealthResponse
from app.rag.vector_store import RagStore

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    rag_ready = False
    if settings.openai_api_key:
        try:
            rag_ready = RagStore().is_ready()
        except Exception:
            rag_ready = False

    return HealthResponse(
        status="ok",
        app=settings.app_name,
        rag_ready=rag_ready,
        categories_cached=category_service.is_cached(),
    )
