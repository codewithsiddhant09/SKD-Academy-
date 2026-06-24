from __future__ import annotations

from collections import defaultdict
from threading import Lock

from app.models.schemas import BookingPayload, Message, SessionContext, SessionMemory


class ConversationStore:
    def __init__(self) -> None:
        self._messages: dict[str, list[Message]] = defaultdict(list)
        self._booking_drafts: dict[str, BookingPayload] = defaultdict(BookingPayload)
        self._booking_stages: dict[str, str] = {}
        self._active_booking_sessions: set[str] = set()
        self._user_contexts: dict[str, SessionContext] = {}
        self._salon_lookup: dict[str, dict[str, str]] = {}
        self._session_memory: dict[str, SessionMemory] = defaultdict(SessionMemory)
        self._lock = Lock()

    def add_message(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            self._messages[session_id].append(Message(role=role, content=content))

    def get_history(self, session_id: str, limit: int = 12) -> list[dict[str, str]]:
        with self._lock:
            items = self._messages.get(session_id, [])[-limit:]
            return [{"role": m.role, "content": m.content} for m in items]

    def get_session_memory(self, session_id: str) -> SessionMemory:
        with self._lock:
            return self._session_memory[session_id].model_copy(deep=True)

    def update_session_memory(self, session_id: str, **fields: str | bool | None) -> SessionMemory:
        with self._lock:
            current = self._session_memory[session_id]
            data = current.model_dump()
            for key, value in fields.items():
                if key in SessionMemory.model_fields:
                    data[key] = value
            updated = SessionMemory.model_validate(data)
            self._session_memory[session_id] = updated
            return updated.model_copy(deep=True)

    def sync_session_from_draft(
        self,
        session_id: str,
        draft: BookingPayload,
        *,
        last_intent: str | None = None,
        preferred_location: str | None = None,
        selected_category: str | None = None,
    ) -> SessionMemory:
        fields: dict[str, str | None] = {
            "appointment_date": draft.date,
            "appointment_time": draft.time,
        }
        if draft.salon:
            fields["selected_salon"] = draft.salon
        if draft.salon_id:
            fields["salon_id"] = draft.salon_id
        if draft.service:
            fields["selected_service"] = draft.service
        if selected_category:
            fields["selected_category"] = selected_category
        elif draft.category:
            fields["selected_category"] = draft.category
        if preferred_location:
            fields["preferred_location"] = preferred_location
        if last_intent:
            fields["last_intent"] = last_intent
        return self.update_session_memory(session_id, **fields)

    def merge_session_into_draft(self, session_id: str) -> BookingPayload:
        with self._lock:
            draft = self._booking_drafts[session_id].model_copy(deep=True)
            memory = self._session_memory[session_id]
            if memory.selected_service and not draft.service:
                draft.service = memory.selected_service
            if memory.selected_category and not draft.category:
                draft.category = memory.selected_category
            if memory.selected_salon and not draft.salon:
                draft.salon = memory.selected_salon
            if memory.salon_id and not draft.salon_id:
                draft.salon_id = memory.salon_id
            if memory.appointment_date and not draft.date:
                draft.date = memory.appointment_date
            if memory.appointment_time and not draft.time:
                draft.time = memory.appointment_time
            return draft

    def get_session_memory_api(self, session_id: str) -> dict:
        with self._lock:
            memory = self._session_memory[session_id]
            history = [{"role": m.role, "content": m.content} for m in self._messages.get(session_id, [])]
            return memory.to_api_dict(conversation_history=history)

    def clear_booking_appointment_memory(self, session_id: str) -> None:
        with self._lock:
            current = self._session_memory[session_id]
            self._session_memory[session_id] = current.model_copy(
                update={"appointment_date": None, "appointment_time": None}
            )

    def get_booking_draft(self, session_id: str) -> BookingPayload:
        return self.merge_session_into_draft(session_id)

    def set_booking_draft(self, session_id: str, payload: BookingPayload) -> None:
        with self._lock:
            self._booking_drafts[session_id] = payload
        self.sync_session_from_draft(session_id, payload)

    def clear_booking_draft(self, session_id: str) -> None:
        with self._lock:
            self._booking_drafts[session_id] = BookingPayload()
            self._booking_stages.pop(session_id, None)
            self._active_booking_sessions.discard(session_id)
        self.clear_booking_appointment_memory(session_id)
        self.update_session_memory(
            session_id,
            booking_summary_shown=False,
            awaiting_confirmation=False,
        )

    def end_booking_session(self, session_id: str) -> None:
        with self._lock:
            self._booking_stages.pop(session_id, None)
            self._active_booking_sessions.discard(session_id)

    def set_booking_stage(self, session_id: str, stage: str) -> None:
        with self._lock:
            self._booking_stages[session_id] = stage

    def get_booking_stage(self, session_id: str) -> str | None:
        with self._lock:
            return self._booking_stages.get(session_id)

    def start_booking_session(self, session_id: str) -> None:
        with self._lock:
            self._active_booking_sessions.add(session_id)

    def has_active_booking_session(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._active_booking_sessions

    def set_user_context(self, session_id: str, context: SessionContext) -> None:
        with self._lock:
            self._user_contexts[session_id] = context

    def get_user_context(self, session_id: str) -> SessionContext | None:
        with self._lock:
            return self._user_contexts.get(session_id)

    def set_salon_lookup(self, session_id: str, lookup: dict[str, str]) -> None:
        with self._lock:
            self._salon_lookup[session_id] = lookup

    def get_salon_lookup(self, session_id: str) -> dict[str, str]:
        with self._lock:
            return dict(self._salon_lookup.get(session_id, {}))
