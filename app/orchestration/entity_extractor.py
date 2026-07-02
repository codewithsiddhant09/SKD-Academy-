from __future__ import annotations

from app.agents.booking_agent import BookingAgent
from app.agents.category_agent import CategoryAgent
from app.models.enums import IntentType
from app.models.schemas import BookingPayload, IntentAnalysis
from app.orchestration.models import ExtractedEntities
from app.orchestration.session_manager import SessionManager
from app.utils.location import sanitize_location


class EntityExtractor:
    """Extract entities only — never generate responses."""

    def __init__(
        self,
        session: SessionManager,
        categories: list[str],
        booking_agent: BookingAgent | None = None,
        category_agent: CategoryAgent | None = None,
    ) -> None:
        self.session = session
        self.categories = categories
        self.booking_agent = booking_agent or BookingAgent(
            categories=categories,
            category_agent=category_agent or CategoryAgent(),
        )
        self.category_agent = category_agent or CategoryAgent()

    def extract(
        self,
        message: str,
        intent: IntentAnalysis,
        session_id: str,
    ) -> ExtractedEntities:
        memory = self.session.get_memory(session_id)
        draft = self.session.get_booking_draft(session_id)
        lookup = self.session.get_salon_lookup(session_id)
        salon_search = intent.intent in {
            IntentType.SALON_SEARCH,
            IntentType.LOCATION_SEARCH,
        }

        entities = ExtractedEntities(salon_search=salon_search)

        if salon_search:
            if intent.location:
                entities.location = sanitize_location(intent.location) or intent.location
            elif memory.preferred_location:
                entities.location = memory.preferred_location
            return entities

        preview = self.booking_agent.extract_booking_fields(message, draft, lookup)
        entities.service = preview.service or intent.service or memory.selected_service
        entities.category = (
            preview.category
            or intent.category
            or memory.selected_category
            or (
                self.category_agent.map_category(entities.service, self.categories)
                if entities.service
                else None
            )
        )
        entities.salon = preview.salon or memory.selected_salon
        entities.salon_id = preview.salon_id or memory.salon_id
        entities.date = preview.date or memory.appointment_date
        entities.time = preview.time or memory.appointment_time

        location = intent.location
        if not location and entities.service:
            location = self._extract_location_clause(message)
        if not location:
            location = memory.preferred_location
        if location:
            entities.location = sanitize_location(location) or location.strip()

        return entities

    @staticmethod
    def _extract_location_clause(message: str) -> str | None:
        import re

        match = re.search(
            r"\b(?:in|at|near|around|within|located in)\s+(.+)",
            message,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        words = match.group(1).strip(" .?!").split()
        if not words or len(words) > 5:
            return None
        return " ".join(words)
