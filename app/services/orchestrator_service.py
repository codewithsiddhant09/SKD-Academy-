from __future__ import annotations

from app.agents.booking_agent import BookingAgent
from app.agents.category_agent import CategoryAgent
from app.agents.faq_agent import FaqAgent
from app.agents.intent_agent import IntentAgent
from app.agents.location_agent import LocationAgent
from app.agents.salon_discovery_agent import SalonDiscoveryAgent
from app.agents.salon_ranking_agent import SalonRankingAgent
from app.core.logging import get_logger
from app.graph.workflow import OrchestratorWorkflow
from app.memory.conversation_store import ConversationStore
from app.models.schemas import ChatResponse, SessionContext
from app.models.state import GraphState
from app.services.booking_service import BookingService
from app.services.category_service import CategoryService
from app.services.user_service import UserService

logger = get_logger(__name__)


class OrchestratorService:
    def __init__(
        self,
        categories: list[str],
        user_service: UserService | None = None,
        category_service: CategoryService | None = None,
    ) -> None:
        self.memory = ConversationStore()
        self.user_service = user_service or UserService()
        self.workflow = OrchestratorWorkflow(
            memory=self.memory,
            categories=categories,
            intent_agent=IntentAgent(),
            category_agent=CategoryAgent(),
            location_agent=LocationAgent(),
            discovery_agent=SalonDiscoveryAgent(),
            ranking_agent=SalonRankingAgent(),
            faq_agent=FaqAgent(),
            booking_agent=BookingAgent(),
            booking_service=BookingService(),
            category_service=category_service,
        )

    def ensure_user_context(self, session_id: str, user_id: str | None) -> SessionContext | None:
        """Load and cache the user's session context once per session."""
        if not user_id:
            return self.memory.get_user_context(session_id)

        existing = self.memory.get_user_context(session_id)
        if existing and existing.user_id == user_id:
            return existing

        # User enrichment must never break chat/socket: degrade to a generic
        # context if anything goes wrong loading the profile.
        try:
            profile = self.user_service.get_user_profile(user_id)
            context = self.user_service.build_session_context(user_id, profile)
        except Exception:  # pragma: no cover - defensive
            logger.exception("USER_CONTEXT_FAILED: session=%s user_id=%s", session_id, user_id)
            context = SessionContext(user_id=user_id)

        self.memory.set_user_context(session_id, context)
        logger.info(
            "USER_CONTEXT_SET: session=%s user_id=%s fullName=%s",
            session_id,
            context.user_id,
            context.full_name,
        )
        return context

    def chat(self, session_id: str, user_message: str, user_id: str | None = None) -> ChatResponse:
        self.ensure_user_context(session_id, user_id)
        self.memory.add_message(session_id, "user", user_message)
        state: GraphState = {"session_id": session_id, "user_message": user_message}
        result = self.workflow.run(state)

        reply = result.get(
            "reply",
            (
                "I am here to assist you. Please let me know which service "
                "you are looking for or how I can help."
            ),
        )
        self.memory.add_message(session_id, "assistant", reply)

        intent_analysis = result.get("intent_analysis")
        user_context = self.memory.get_user_context(session_id)
        booking_response = result.get("booking_response")
        session_memory = self.memory.get_session_memory_api(session_id)
        return ChatResponse(
            session_id=session_id,
            reply=reply,
            intent=intent_analysis.intent if intent_analysis else "general_conversation",
            structured={
                "intent": intent_analysis.intent if intent_analysis else "general_conversation",
                "category": result.get("category"),
                "service": result.get("service"),
                "location": result.get("location_analysis").model_dump() if result.get("location_analysis") else None,
                "booking_payload": result.get("booking_payload").model_dump() if result.get("booking_payload") else None,
                "booking_response": booking_response,
                "user_context": user_context.model_dump() if user_context else None,
                "session_memory": session_memory,
            },
            recommendations=result.get("recommendations", []),
        )
