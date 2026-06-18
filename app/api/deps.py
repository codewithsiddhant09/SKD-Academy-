from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger
from app.rag.ingest import ingest_rag_documents
from app.services.category_service import CategoryService
from app.services.orchestrator_service import OrchestratorService
from app.services.user_service import UserService

logger = get_logger(__name__)

category_service = CategoryService()
user_service = UserService()
orchestrator_service: OrchestratorService | None = None


def initialize_dependencies() -> None:
    global orchestrator_service

    category_service.warmup()
    categories = category_service.get_category_names()
    logger.info("CATEGORIES_LOADED: %s categories from Categories API -> %s", len(categories), categories)
    orchestrator_service = OrchestratorService(
        categories=categories,
        user_service=user_service,
        category_service=category_service,
    )

    # Skip RAG ingestion for now - will load on-demand
    # settings = get_settings()
    # if settings.openai_api_key:
    #     try:
    #         ingest_rag_documents()
    #         logger.info("RAG documents ingested")
    #     except Exception as exc:
    #         logger.warning("RAG ingestion skipped: %s", exc)
    logger.info("Dependencies initialized successfully")
