from __future__ import annotations

from app.agents.location_agent import LocationAgent
from app.agents.salon_discovery_agent import SalonDiscoveryAgent
from app.agents.salon_ranking_agent import SalonRankingAgent
from app.core.logging import get_logger
from app.models.enums import IntentType
from app.models.schemas import BookingPayload
from app.orchestration.models import HandlerResult, OrchestrationContext, PendingQuestion
from app.orchestration.response_generator import ResponseGenerator
from app.orchestration.session_manager import SessionManager
from app.services.category_service import CategoryService
from app.utils.text import title_case_safe

logger = get_logger(__name__)


class SalonHandler:
    """Salon discovery — uses live APIs/Mongo; never auto-selects a salon."""

    def __init__(
        self,
        session: SessionManager,
        categories: list[str],
        category_service: CategoryService | None,
        location_agent: LocationAgent,
        discovery_agent: SalonDiscoveryAgent,
        ranking_agent: SalonRankingAgent,
    ) -> None:
        self.session = session
        self.categories = categories
        self.category_service = category_service
        self.location_agent = location_agent
        self.discovery_agent = discovery_agent
        self.ranking_agent = ranking_agent

    def _category_names(self) -> list[str]:
        if self.category_service is not None:
            try:
                return [c.name for c in self.category_service.get_categories(force_refresh=False)]
            except Exception:
                pass
        return list(self.categories)

    def handle(self, ctx: OrchestrationContext) -> HandlerResult:
        entities = ctx.entities
        service = entities.service
        category = entities.category
        location = entities.location
        salon_search = entities.salon_search

        if not salon_search and not service:
            names = self._category_names()
            return HandlerResult(
                intent=IntentType.SERVICE_SEARCH,
                reply=ResponseGenerator.service_prompt(names),
            )

        if not location:
            self.session.update_memory(ctx.session_id, last_intent=ctx.intent.intent.value)
            return HandlerResult(
                intent=ctx.intent.intent,
                service=service,
                category=category,
                reply=ResponseGenerator.location_prompt(),
            )

        location_analysis = self.location_agent.analyze(location)
        salons = self.discovery_agent.discover(
            category=category or "",
            service=service or "",
            location=location_analysis.normalized_location,
            radius_km=location_analysis.radius_km,
        )
        recommendations = self.ranking_agent.rank(
            salons=salons,
            service=service or "",
            radius_km=location_analysis.radius_km,
        )[:5]

        logger.info("SALON_HANDLER: found %s salons in %s", len(recommendations), location)

        if not recommendations:
            return HandlerResult(
                intent=ctx.intent.intent,
                service=service,
                category=category,
                location=location,
                location_analysis=location_analysis,
                reply=ResponseGenerator.no_salons(location, service),
            )

        lookup = {
            title_case_safe(r.salon_name).lower(): (r.vendor_id or "")
            for r in recommendations
        }
        self.session.set_salon_lookup(ctx.session_id, lookup)

        draft = self.session.get_booking_draft(ctx.session_id)
        if service:
            draft.service = service
        if category:
            draft.category = category
        self.session.set_booking_draft(ctx.session_id, draft)
        self.session.sync_from_draft(
            ctx.session_id,
            draft,
            last_intent="discovery",
            preferred_location=location,
            selected_category=category,
        )
        self.session.set_booking_stage(ctx.session_id, "awaiting_salon")

        return HandlerResult(
            intent=ctx.intent.intent,
            service=service,
            category=category,
            location=location,
            location_analysis=location_analysis,
            recommendations=recommendations,
            booking_stage="awaiting_salon",
            reply=ResponseGenerator.salon_results(
                location,
                service,
                salon_search=salon_search,
            ),
        )
