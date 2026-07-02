"""Dynamic booking slot orchestration — priority-based missing-field detection."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.models.schemas import BookingPayload

BookingAction = Literal["ask", "discover", "confirm"]

# Priority order for collecting missing booking information.
BOOKING_SLOT_PRIORITY: tuple[str, ...] = (
    "service",
    "location",
    "salon",
    "date",
    "time",
)

# Phrases that must never be treated as salon names.
GENERIC_SALON_PHRASES: frozenset[str] = frozenset({
    "give me salon list",
    "salon list",
    "salons list",
    "show options",
    "show salons",
    "show me salons",
    "list of salons",
    "list salons",
    "recommend salon",
    "recommend salons",
    "recommend a salon",
    "nearby salons",
    "available salons",
    "which salons",
    "what salons",
    "any salons",
    "salon options",
    "give me list",
    "show me list",
    "show me options",
})


def normalize_phrase(text: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def is_generic_salon_phrase(text: str | None) -> bool:
    if not text or not str(text).strip():
        return False
    normalized = normalize_phrase(str(text))
    if normalized in GENERIC_SALON_PHRASES:
        return True
    generic_tokens = (
        "salon list",
        "list of salon",
        "show salon",
        "recommend salon",
        "give me salon",
        "nearby salon",
    )
    return any(p in normalized for p in generic_tokens)


@dataclass
class BookingEntityState:
    """Resolved booking entities available in the current turn."""

    service: str | None = None
    category: str | None = None
    location: str | None = None
    salon: str | None = None
    salon_id: str | None = None
    date: str | None = None
    time: str | None = None
    salon_verified: bool = False
    missing: list[str] = field(default_factory=list)
    action: BookingAction = "ask"
    next_slot: str | None = None

    def to_payload(self) -> BookingPayload:
        return BookingPayload(
            service=self.service,
            category=self.category,
            salon=self.salon,
            salon_id=self.salon_id,
            date=self.date,
            time=self.time,
        )


def compute_missing_slots(
    *,
    service: str | None,
    location: str | None,
    salon_verified: bool,
    date: str | None,
    time: str | None,
    service_valid: bool = True,
    date_valid: bool = True,
    time_valid: bool = True,
) -> list[str]:
    missing: list[str] = []
    if not service or not service_valid:
        missing.append("service")
    if not location:
        missing.append("location")
    if not salon_verified:
        missing.append("salon")
    if not date or not date_valid:
        missing.append("date")
    if not time or not time_valid:
        missing.append("time")
    return [slot for slot in BOOKING_SLOT_PRIORITY if slot in missing]


def decide_booking_action(missing: list[str]) -> tuple[BookingAction, str | None]:
    """Determine the next orchestration step from priority-ordered missing slots."""
    if not missing:
        return "confirm", None
    first = missing[0]
    if first == "salon":
        # Never ask for salon by text — show MongoDB cards when location is known.
        if "location" not in missing:
            return "discover", None
        return "ask", "location"
    return "ask", first
