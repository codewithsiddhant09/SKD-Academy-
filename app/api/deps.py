from __future__ import annotations

from app.agent.assistant import BookingAssistant
from app.core.config import get_settings
from app.core.logging import get_logger
from app.rag.ingest import DOCUMENTS_DIR
from app.rag.vector_store import create_rag_store, load_docs_from_directory
from app.services.booking_service import BookingService
from app.services.category_service import CategoryService
from app.services.user_service import UserService

logger = get_logger(__name__)

category_service = CategoryService()
user_service = UserService()
booking_service = BookingService()
assistant: BookingAssistant | None = None


def initialize_dependencies() -> None:
    global assistant

    category_service.warmup()
    logger.info("CATEGORIES_LOADED: %s", category_service.get_category_names())

    knowledge = create_rag_store() if get_settings().openai_api_key else None
    if knowledge is not None and knowledge.count() == 0:
        knowledge.upsert_documents(load_docs_from_directory(DOCUMENTS_DIR))
        logger.info("RAG documents ingested into empty collection")

    assistant = BookingAssistant(categories=category_service, users=user_service, knowledge=knowledge)
    logger.info("Dependencies initialized successfully")
