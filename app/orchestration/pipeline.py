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
from app.models.state import GraphState
from app.orchestration.conversation_state_manager import ConversationStateManager
from app.orchestration.entity_extractor import EntityExtractor
from app.orchestration.handlers.booking_handler import BookingHandler
from app.orchestration.handlers.category_handler import CategoryHandler
from app.orchestration.handlers.fallback_handler import FallbackHandler
from app.orchestration.handlers.faq_handler import FaqHandler
from app.orchestration.handlers.greeting_handler import GreetingHandler
from app.orchestration.handlers.platform_handler import PlatformHandler
from app.orchestration.handlers.registry import HandlerRegistry
from app.orchestration.handlers.salon_handler import SalonHandler
from app.orchestration.intent_classifier import IntentClassifier
from app.orchestration.models import OrchestrationContext, PendingQuestion, RouteTarget
from app.orchestration.router import Router
from app.orchestration.session_manager import SessionManager
from app.services.booking_service import BookingService
from app.services.category_service import CategoryService

logger = get_logger(__name__)


class OrchestrationPipeline:
    """Production orchestration entry point — classify, extract, route, handle, respond."""

    def __init__(
        self,
        memory: ConversationStore,
        categories: list[str],
        category_service: CategoryService | None = None,
    ) -> None:
        self.session = SessionManager(memory)
        self.categories = categories
        self.category_service = category_service

        category_agent = CategoryAgent()
        booking_agent = BookingAgent(categories=categories, category_agent=category_agent)

        self.workflow = OrchestratorWorkflow(
            memory=memory,
            categories=categories,
            intent_agent=IntentAgent(),
            category_agent=category_agent,
            location_agent=LocationAgent(),
            discovery_agent=SalonDiscoveryAgent(),
            ranking_agent=SalonRankingAgent(),
            faq_agent=FaqAgent(),
            booking_agent=booking_agent,
            booking_service=BookingService(),
            category_service=category_service,
        )

        self.intent_classifier = IntentClassifier(categories)
        self.entity_extractor = EntityExtractor(self.session, categories, booking_agent, category_agent)
        self.state_manager = ConversationStateManager(self.session)
        self.router = Router()

        faq_agent = FaqAgent()
        self.handlers = HandlerRegistry(
            greeting=GreetingHandler(),
            platform=PlatformHandler(),
            category=CategoryHandler(category_service, categories),
            salon=SalonHandler(
                self.session,
                categories,
                category_service,
                LocationAgent(),
                SalonDiscoveryAgent(),
                SalonRankingAgent(),
            ),
            booking=BookingHandler(self.workflow, self.session),
            faq=FaqHandler(faq_agent, self.session),
            fallback=FallbackHandler(self.session),
        )

    def run(self, state: GraphState) -> GraphState:
        session_id = state["session_id"]
        message = state["user_message"]
        history = self.session.get_history(session_id)

        category_names = self.categories
        if self.category_service is not None:
            try:
                category_names = [c.name for c in self.category_service.get_categories()]
            except Exception:
                pass

        intent = self.intent_classifier.classify(message, history, category_names=category_names)
        entities = self.entity_extractor.extract(message, intent, session_id)
        pending = self.state_manager.apply_entities(session_id, intent, entities)

        ctx = OrchestrationContext(
            session_id=session_id,
            user_message=message,
            history=history,
            intent=intent,
            entities=entities,
            pending_question=pending,
        )

        target = self.router.route_with_session(ctx, self.session)
        logger.info("PIPELINE: route=%s intent=%s pending=%s", target, intent.intent, pending)

        if ctx.resume_booking_after_faq and target == RouteTarget.FAQ:
            self.session.update_memory(session_id, booking_status="paused")

        result = self.handlers.dispatch(target, ctx)

        out: GraphState = {
            "session_id": session_id,
            "user_message": message,
            "history": history,
            "intent_analysis": intent,
            "reply": result.reply,
            "service": result.service or entities.service,
            "category": result.category or entities.category,
            "location": result.location or entities.location,
            "location_analysis": result.location_analysis,
            "recommendations": result.recommendations,
            "booking_payload": result.booking_payload,
            "booking_response": result.booking_response,
            "booking_stage": result.booking_stage,
        }
        return out
