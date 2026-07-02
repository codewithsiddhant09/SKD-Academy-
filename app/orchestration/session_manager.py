from __future__ import annotations

from app.memory.conversation_store import ConversationStore
from app.models.schemas import BookingPayload, SessionContext, SessionMemory


class SessionManager:
    """Session, history, booking draft, and memory — no business routing."""

    def __init__(self, store: ConversationStore) -> None:
        self._store = store

    @property
    def store(self) -> ConversationStore:
        return self._store

    def add_message(self, session_id: str, role: str, content: str) -> None:
        self._store.add_message(session_id, role, content)

    def get_history(self, session_id: str, limit: int = 12) -> list[dict[str, str]]:
        return self._store.get_history(session_id, limit=limit)

    def get_memory(self, session_id: str) -> SessionMemory:
        return self._store.get_session_memory(session_id)

    def update_memory(self, session_id: str, **fields: str | bool | None) -> SessionMemory:
        return self._store.update_session_memory(session_id, **fields)

    def get_booking_draft(self, session_id: str) -> BookingPayload:
        return self._store.get_booking_draft(session_id)

    def set_booking_draft(self, session_id: str, payload: BookingPayload) -> None:
        self._store.set_booking_draft(session_id, payload)

    def clear_booking_draft(self, session_id: str) -> None:
        self._store.clear_booking_draft(session_id)

    def get_booking_stage(self, session_id: str) -> str | None:
        return self._store.get_booking_stage(session_id)

    def set_booking_stage(self, session_id: str, stage: str) -> None:
        self._store.set_booking_stage(session_id, stage)

    def start_booking_session(self, session_id: str) -> None:
        self._store.start_booking_session(session_id)

    def end_booking_session(self, session_id: str) -> None:
        self._store.end_booking_session(session_id)

    def has_active_booking(self, session_id: str) -> bool:
        return self._store.has_active_booking_session(session_id)

    def get_salon_lookup(self, session_id: str) -> dict[str, str]:
        return self._store.get_salon_lookup(session_id)

    def set_salon_lookup(self, session_id: str, lookup: dict[str, str]) -> None:
        self._store.set_salon_lookup(session_id, lookup)

    def get_user_context(self, session_id: str) -> SessionContext | None:
        return self._store.get_user_context(session_id)

    def set_user_context(self, session_id: str, context: SessionContext) -> None:
        self._store.set_user_context(session_id, context)

    def get_memory_api(self, session_id: str) -> dict:
        return self._store.get_session_memory_api(session_id)

    def sync_from_draft(
        self,
        session_id: str,
        draft: BookingPayload,
        *,
        last_intent: str | None = None,
        preferred_location: str | None = None,
        selected_category: str | None = None,
    ) -> SessionMemory:
        return self._store.sync_session_from_draft(
            session_id,
            draft,
            last_intent=last_intent,
            preferred_location=preferred_location,
            selected_category=selected_category,
        )
