from __future__ import annotations

from collections import defaultdict
from threading import Lock

from app.models.schemas import BookingPayload, Message, SessionContext


class ConversationStore:
    def __init__(self) -> None:
        self._messages: dict[str, list[Message]] = defaultdict(list)
        self._booking_drafts: dict[str, BookingPayload] = defaultdict(BookingPayload)
        self._booking_stages: dict[str, str] = {}
        self._active_booking_sessions: set[str] = set()
        self._user_contexts: dict[str, SessionContext] = {}
        self._salon_lookup: dict[str, dict[str, str]] = {}
        self._lock = Lock()

    def add_message(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            self._messages[session_id].append(Message(role=role, content=content))

    def get_history(self, session_id: str, limit: int = 12) -> list[dict[str, str]]:
        with self._lock:
            items = self._messages.get(session_id, [])[-limit:]
            return [{"role": m.role, "content": m.content} for m in items]

    def get_booking_draft(self, session_id: str) -> BookingPayload:
        with self._lock:
            return self._booking_drafts[session_id]

    def set_booking_draft(self, session_id: str, payload: BookingPayload) -> None:
        with self._lock:
            self._booking_drafts[session_id] = payload

    def clear_booking_draft(self, session_id: str) -> None:
        with self._lock:
            self._booking_drafts[session_id] = BookingPayload()
            self._booking_stages.pop(session_id, None)
            self._active_booking_sessions.discard(session_id)

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
