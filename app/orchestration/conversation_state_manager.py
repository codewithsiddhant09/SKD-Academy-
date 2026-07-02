from __future__ import annotations

from app.models.schemas import BookingPayload, IntentAnalysis
from app.orchestration.models import ExtractedEntities, PendingQuestion
from app.orchestration.session_manager import SessionManager


class ConversationStateManager:
    """Track selected slots and pending questions — avoid duplicate asks."""

    def __init__(self, session: SessionManager) -> None:
        self.session = session

    def apply_entities(
        self,
        session_id: str,
        intent: IntentAnalysis,
        entities: ExtractedEntities,
    ) -> PendingQuestion:
        memory_updates: dict[str, str | bool | None] = {"last_intent": intent.intent.value}
        if entities.service:
            memory_updates["selected_service"] = entities.service
        if entities.category:
            memory_updates["selected_category"] = entities.category
        if entities.location:
            memory_updates["preferred_location"] = entities.location
        if entities.salon:
            memory_updates["selected_salon"] = entities.salon
        if entities.salon_id:
            memory_updates["salon_id"] = entities.salon_id
        if entities.date:
            memory_updates["appointment_date"] = entities.date
        if entities.time:
            memory_updates["appointment_time"] = entities.time
        if memory_updates:
            self.session.update_memory(session_id, **memory_updates)

        draft = self.session.get_booking_draft(session_id)
        changed = False
        if entities.service and not draft.service:
            draft.service = entities.service
            changed = True
        if entities.category and not draft.category:
            draft.category = entities.category
            changed = True
        if entities.salon and not draft.salon:
            draft.salon = entities.salon
            changed = True
        if entities.salon_id and not draft.salon_id:
            draft.salon_id = entities.salon_id
            changed = True
        if entities.date and not draft.date:
            draft.date = entities.date
            changed = True
        if entities.time and not draft.time:
            draft.time = entities.time
            changed = True
        if changed:
            self.session.set_booking_draft(session_id, draft)

        return self.pending_question(session_id)

    def pending_question(self, session_id: str) -> PendingQuestion:
        memory = self.session.get_memory(session_id)
        stage = self.session.get_booking_stage(session_id)

        if memory.awaiting_confirmation or stage == "awaiting_confirmation":
            return PendingQuestion.CONFIRMATION
        if stage == "awaiting_salon":
            return PendingQuestion.SALON
        if stage == "awaiting_date":
            return PendingQuestion.DATE
        if stage == "awaiting_time":
            return PendingQuestion.TIME

        if self._awaiting_location(session_id):
            return PendingQuestion.LOCATION

        draft = self.session.get_booking_draft(session_id)
        if self.session.has_active_booking(session_id) or any(
            getattr(draft, field) for field in ("service", "salon", "date", "time")
        ):
            missing = self._first_missing(draft)
            if missing == "service":
                return PendingQuestion.SERVICE
            if missing == "salon":
                return PendingQuestion.SALON
            if missing == "date":
                return PendingQuestion.DATE
            if missing == "time":
                return PendingQuestion.TIME

        if draft.service and not draft.salon and not memory.preferred_location:
            return PendingQuestion.LOCATION
        if draft.service and memory.preferred_location and not draft.salon:
            return PendingQuestion.SALON

        return PendingQuestion.NONE

    def _awaiting_location(self, session_id: str) -> bool:
        history = self.session.get_history(session_id)
        for msg in reversed(history):
            if msg["role"] == "assistant":
                lower = msg["content"].lower()
                return "preferred location" in lower or "recommend nearby salons" in lower
        return False

    @staticmethod
    def _first_missing(draft: BookingPayload) -> str | None:
        for field in ("service", "salon", "date", "time"):
            if not getattr(draft, field):
                return field
        return None

    def booking_fields_complete(self, session_id: str) -> bool:
        draft = self.session.get_booking_draft(session_id)
        return all(getattr(draft, field) for field in ("service", "salon", "date", "time"))
