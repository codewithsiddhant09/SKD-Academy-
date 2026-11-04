"""Per-session conversation state, kept in process memory."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock

from app.models.schemas import BookingPayload, Salon, SessionContext

# Keep this many past user/assistant messages as LLM context.
HISTORY_LIMIT = 20
# Sessions idle longer than this are dropped.
SESSION_TTL_SECONDS = 2 * 60 * 60


@dataclass
class Session:
    session_id: str
    history: list[dict[str, str]] = field(default_factory=list)
    user: SessionContext | None = None
    auth_token: str | None = field(default=None, repr=False)
    jwt_token: str | None = field(default=None, repr=False)
    booking_platform: str = "app"
    whatsapp_phone: str | None = None
    whatsapp_name: str | None = None
    # Every salon the assistant has seen via search_salons, by vendor id.
    # Booking may only reference these, so the salon's service list is always known.
    known_salons: dict[str, Salon] = field(default_factory=dict)
    draft: BookingPayload = field(default_factory=BookingPayload)
    # Last location the customer searched in; stored on the booking request.
    location: str | None = None
    booking_contact: dict | None = None
    last_booking_order_id: str | None = None
    last_booking_id: str | None = None  # For payment verification
    pending_payment_check: bool = False  # True after PayNow booking, cleared after verification
    # True once a complete draft was summarised and awaits payment choice or modification confirmation.
    awaiting_confirmation: bool = False
    # Set only from a customer's explicit choice after they saw the summary.
    payment_option: str | None = None
    # Booking type: "Individual" (default) or "Group"
    booking_type: str | None = None
    # For group bookings: number of people
    group_size: int | None = None
    booking_channel: str = "app"
    cancellation_quote: dict | None = None
    # Counts customer messages; used to require that a request was shown before it is cancelled.
    turn: int = 0
    # request_id -> turn in which its details were shown to the customer.
    viewed_requests: dict[str, int] = field(default_factory=dict)
    # Set while an existing request is being modified: confirm_booking then updates this request
    # (same request_id) instead of creating a new one. Holds the request as it was when loaded.
    editing_request: dict | None = None
    last_seen: float = field(default_factory=time.time)

    def __repr__(self) -> str:
        return f"Session(session_id={self.session_id!r}, user_id={self.user.user_id if self.user else None!r})"

    def add_message(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})
        del self.history[:-HISTORY_LIMIT]


class SessionStore:
    # ponytail: in-process dict, so sessions are lost on restart and not shared
    # across workers; move to Redis/Mongo when running more than one process.
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()

    def get(self, session_id: str) -> Session:
        now = time.time()
        with self._lock:
            for sid in [s for s, v in self._sessions.items() if now - v.last_seen > SESSION_TTL_SECONDS]:
                del self._sessions[sid]
            session = self._sessions.setdefault(session_id, Session(session_id))
            session.last_seen = now
            return session
