"""Tools the assistant can call.

The LLM decides *what* the customer wants and *which* tool to call. The tools
own the data and the rules: they fetch real salons, categories and policy text,
and they refuse booking changes that are invalid (unknown salon, a service the
salon does not offer, a past date). This split is what keeps behaviour
consistent: understanding is done by the model, facts and rules by code.

Each tool is a Pydantic model (its fields are the arguments) plus a handler.
The model's docstring is sent to the LLM as the tool description, so it states
both WHAT the tool does and WHY/WHEN to use it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Literal
from zoneinfo import ZoneInfo

from bson import ObjectId
from pydantic import BaseModel, Field

from app.agent.session import Session
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import BookingPayload
from app.rag.vector_store import RagStore
from app.services.booking_service import BookingService
from app.services.category_service import CategoryService
from app.services.salon_service import SalonService

logger = get_logger(__name__)

MAX_SEARCH_RESULTS = 15  # salons the assistant sees (and can book)
MAX_CARDS = 5  # salons shown to the customer as cards
MIN_ADVANCE = timedelta(hours=2)  # appointments must be requested at least this far ahead
ADVANCE_HINT = "Bookings must be requested at least 2 hours before the appointment time."
MODIFIABLE_STATUSES = {"pending"}  # the salon has not responded yet
CANCELLABLE_STATUSES = {"pending", "payment_pending"}


@dataclass
class ToolContext:
    """Everything a tool may touch: the current session plus backing services."""

    session: Session
    categories: CategoryService
    salons: SalonService
    bookings: BookingService
    knowledge: RagStore | None
    # Filled by tools during a turn; returned to the API/socket caller.
    shown_salon_ids: list[str] | None = None
    # salon_id -> one-line availability shown on that salon's card.
    card_notes: dict[str, str] = field(default_factory=dict)
    booking_result: dict | None = None


# --------------------------------------------------------------------------- #
# Tool argument models (docstring = description the LLM sees)
# --------------------------------------------------------------------------- #
class list_service_categories(BaseModel):
    """WHAT: Returns the service categories currently offered on Bookly (e.g. Hair, Nails).
    WHY: Use when the customer asks what services/categories exist, or is unsure what to book.
    Never list categories from memory; they change and must come from this tool."""


class list_services(BaseModel):
    """WHAT: Lists the services offered in a category (e.g. 'Hair Removal'), with price range and how
    many salons offer each, optionally only in one location.
    WHY: Whenever the customer mentions a category instead of a specific service (e.g. "I want hair
    removal", "show me Lashes"), call this and ask which of these services they want. A category is
    never a bookable service."""

    category: str = Field(description="Category name exactly as returned by list_service_categories.")
    location: str | None = Field(description="City or area to limit to, e.g. 'Noida'. Null for all.")


class search_salons(BaseModel):
    """WHAT: Searches real, active Bookly salons by any combination of location, service,
    category and salon name. Returns up to 15 salons that match ALL given filters, each with id, name,
    address, rating, its services with price and category, and availability for the requested date:
    whether it can be booked that day (with its hours) and, if not, its next_available_date (null = no
    upcoming availability at all). Salons bookable that day come first. The first 5 are shown as
    salon cards; the customer may still pick any salon in the result.
    WHY: Use whenever the customer wants salons, names a salon or a service, asks which services
    a category includes (pass category), or changes service/location. Always pass the service or
    category the customer asked for, so only salons offering it are listed. A salon must come from
    this tool (or get_my_bookings) before update_booking can use it."""

    location: str | None = Field(description="City or area, e.g. 'Noida'. Null if unknown.")
    service: str | None = Field(
        description="Specific service, e.g. 'Hair Smoothing'. Null for any service. Never put a category here."
    )
    category: str | None = Field(
        description="Category when the customer named a category, e.g. 'Lashes' or 'Hair Removal'. Null for any."
    )
    salon_name: str | None = Field(description="Salon name if the customer named one. Null otherwise.")
    date: str | None = Field(description="Date the customer wants, YYYY-MM-DD. Null means today.")


class search_knowledge_base(BaseModel):
    """WHAT: Searches Bookly's FAQ and policy documents and returns the most relevant passages.
    WHY: Use for any question about Bookly itself, how it works, payments, cancellation,
    refunds, privacy or other policies. Answer ONLY from the returned passages; if they do
    not contain the answer, say you do not have that information."""

    query: str = Field(description="The customer's question, rephrased as a standalone search query.")


class update_booking(BaseModel):
    """WHAT: Sets or changes fields of the customer's booking draft and validates the result.
    It rejects the whole change if the salon is unknown, the salon does not offer the
    service, or the date/time is invalid or in the past, and explains why.
    Returns the current draft, which fields are still missing, and any problems.
    WHY: Call it as soon as the customer provides or changes the service, salon, date or
    time, including mid-conversation changes. Pass only the fields that changed.
    Never choose a service for the customer: set service only when the customer named that specific
    service or picked it from options you listed. If they only named a category, or only said they want
    to change the service, ask which service instead (use list_services to show the options).
    If the customer switches to a service their chosen salon does not offer, search for
    salons offering the new service and pass the new salon_id and service together."""

    service: str | None = Field(
        description="Service name. Once a salon is chosen, use the exact name from that salon's services list."
    )
    service_mentioned_as: Literal["specific_service", "category_only", "not_named"] | None = Field(
        description="Required when setting or changing service: how the CUSTOMER referred to it. "
        "'specific_service' = they named this exact service or picked it from options you listed; "
        "'category_only' = they only named a category such as 'Hair Removal'; "
        "'not_named' = they did not say which service (e.g. 'I want to change the service'). "
        "Null when service is null."
    )
    salon_id: str | None = Field(description="salon_id from search_salons or get_my_bookings.")
    date: str | None = Field(description="Appointment date as YYYY-MM-DD (resolve 'tomorrow' etc. using today's date).")
    time: str | None = Field(description="Appointment time as HH:MM in 24-hour format, e.g. '16:00' for 4 PM.")


class check_availability(BaseModel):
    """WHAT: Returns a salon's opening hours on a date and the window that can still be booked
    (appointments must be requested at least 2 hours ahead). available=false means it cannot be
    booked that day.
    WHY: Use before asking for or proposing a time, when the customer asks when a salon is open,
    free or next available (pass today's date; if not available it returns next_available_date), or
    when update_booking rejects a time. Present it as a range (e.g. "11:00 AM to 5:00 PM"),
    never as a list of slots, and mention the 2-hour advance rule."""

    salon_id: str = Field(description="salon_id from search_salons or get_my_bookings.")
    date: str = Field(description="Date as YYYY-MM-DD.")


class get_my_bookings(BaseModel):
    """WHAT: Returns the signed-in customer's previous bookings (salon, services, date, time,
    status, their own rating), their recent chatbot booking requests, and the salon to
    recommend from that history: the salon they rated highest, else the one they booked most,
    else the most recent. Salons returned become bookable with update_booking.
    WHY: Use when the customer asks about past bookings or requests, wants to rebook
    ('rebook my last facial'), or wants a service they have had before."""

    service: str | None = Field(description="Only bookings that include this service, e.g. 'haircut'. Null for all.")


class confirm_booking(BaseModel):
    """WHAT: Sends the booking draft to the salon as a booking request (status pending). When an existing
    request is being modified (modify_booking_request), it saves the changes on that same request ID instead.
    The salon accepts or rejects it; the customer is then notified in the Bookly app and
    pays there. The chatbot never handles payment.
    WHY: Call ONLY after you showed the customer the complete booking summary in a previous
    message and they explicitly agreed (e.g. 'yes', 'confirm'). It fails otherwise."""


class get_booking_request(BaseModel):
    """WHAT: Fetches an existing booking request by its ID (e.g. BKLY-09102026-004): salon, service,
    date, time, status, and whether it can still be modified or cancelled.
    WHY: Use whenever the customer gives a booking/request ID or asks about, wants to change,
    reschedule or cancel an existing request. Show its details before modifying or cancelling it."""

    request_id: str = Field(description="Booking request ID, e.g. 'BKLY-09102026-004'.")


class modify_booking_request(BaseModel):
    """WHAT: Starts changing an existing pending request: loads its service, salon, date and time into
    the booking draft. Then call update_booking with the customer's changes, show the updated summary,
    and after they confirm, confirm_booking saves the changes ON THE SAME request ID (no new request).
    WHY: Use when the customer wants to reschedule or change the service of an existing request.
    The salon cannot be changed; for another salon, cancel this request and make a new one."""

    request_id: str = Field(description="Booking request ID to modify.")


class cancel_booking_request(BaseModel):
    """WHAT: Cancels an existing booking request (its status becomes cancelled).
    WHY: Call ONLY after you showed the request's details (get_booking_request) in a previous message
    and the customer explicitly confirmed they want to cancel it. It fails otherwise."""

    request_id: str = Field(description="Booking request ID to cancel.")
    reason: str | None = Field(description="The customer's reason if they gave one, else null.")


class no_action(BaseModel):
    """WHAT: Does nothing.
    WHY: While a booking summary awaits confirmation you must pick an explicit action. Use this
    when the customer's message needs no booking change or lookup: they hesitate, ask you to
    wait, or say something unrelated. Then reply normally."""


class reset_booking(BaseModel):
    """WHAT: Clears the current booking draft.
    WHY: Use when the customer says they no longer want to book, or wants to start over."""


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #
def now_local() -> datetime:
    return datetime.now(ZoneInfo(get_settings().app_timezone))


def _draft_view(ctx: ToolContext) -> dict[str, Any]:
    d = ctx.session.draft
    missing = [f for f in ("service", "salon_id", "date", "time") if not getattr(d, f)]
    view = {
        "draft": {"service": d.service, "salon_id": d.salon_id, "salon": d.salon, "date": d.date, "time": d.time},
        "missing": missing,
        "ready_for_summary": not missing,
    }
    if ctx.session.editing_request:
        view["modifying_request_id"] = ctx.session.editing_request.get("request_id")
        view["saved"] = False
        view["note"] = "Changes are NOT saved yet. Say 'Here is the updated request' and ask the customer to confirm."
    if d.salon_id and not d.date:
        # Lets the assistant say straight away when the chosen salon is not taking bookings.
        view["salon_next_available_date"] = _availability(ctx, [d.salon_id], now_local().date())[d.salon_id][
            "next_available_date"
        ]
    return view


def _salon_view(salon, availability: dict[str, Any]) -> dict[str, Any]:
    return {
        "salon_id": salon.vendor_id,
        "name": salon.salon_name,
        "address": salon.location,
        "rating": salon.rating,
        "availability": {k: v for k, v in availability.items() if k != "summary"},
        "services": [{"name": o.name, "price": o.price, "category": o.category} for o in salon.offers]
        or salon.services,
    }


def run_list_service_categories(ctx: ToolContext, args: list_service_categories) -> dict:
    return {"categories": ctx.categories.get_category_names()}


def run_search_salons(ctx: ToolContext, args: search_salons) -> dict:
    if not (args.location or args.salon_name or args.service or args.category):
        return {"error": "Ask the customer for a location, service or salon name before searching."}
    if args.location:
        ctx.session.location = args.location
    try:
        day = date.fromisoformat(args.date) if args.date else now_local().date()
    except ValueError:
        return {"error": f"Date '{args.date}' is not YYYY-MM-DD."}
    found = ctx.salons.search(
        location=args.location, service=args.service, category=args.category, salon_name=args.salon_name
    )
    availability = _availability(ctx, [s.vendor_id for s in found], day)
    # Bookable on the requested day first, then soonest next date, then rating.
    found.sort(
        key=lambda s: (
            not availability[s.vendor_id]["available_on_date"],
            availability[s.vendor_id]["next_available_date"] or "9999",
            -(s.rating or 0),
        )
    )
    found = found[:MAX_SEARCH_RESULTS]
    for salon in found:
        ctx.session.known_salons[salon.vendor_id] = salon
        ctx.card_notes[salon.vendor_id] = availability[salon.vendor_id]["summary"]
    ctx.shown_salon_ids = [s.vendor_id for s in found[:MAX_CARDS]]
    return {
        "count": len(found),
        "date": day.isoformat(),
        "salons": [_salon_view(s, availability[s.vendor_id]) for s in found],
        "next": "When the customer picks one of these salons, call update_booking with its salon_id right away.",
    }


def run_list_services(ctx: ToolContext, args: list_services) -> dict:
    services = ctx.salons.list_services(args.category, args.location)
    if not services:
        return {"category": args.category, "services": [], "note": "No salon currently offers services in this category."}
    return {"category": args.category, "services": services}


def run_search_knowledge_base(ctx: ToolContext, args: search_knowledge_base) -> dict:
    if ctx.knowledge is None:
        return {"error": "Knowledge base unavailable. Tell the customer to contact Bookly support."}
    hits = ctx.knowledge.retrieve_with_scores(args.query)
    return {
        "passages": [
            {"source": (doc.metadata or {}).get("source"), "text": doc.page_content} for doc, _ in hits
        ]
    }


def _clock(minutes: int) -> str:
    return time(minutes // 60, minutes % 60).strftime("%I:%M %p").lstrip("0")


def _bookable_window(ctx: ToolContext, salon_id: str, day: date) -> tuple[int, int, int, int] | None:
    """(open, close, earliest, latest) minutes for `day`. earliest/latest bound the start times that
    can still be requested (opening hours, and at least MIN_ADVANCE from now). None if none left."""
    hours = ctx.bookings.working_hours(salon_id, day)
    if hours is None:
        return None
    opens, closes = hours
    cutoff = now_local().replace(tzinfo=None) + MIN_ADVANCE
    earliest = opens
    if day < cutoff.date():
        return None
    if day == cutoff.date():
        earliest = max(opens, cutoff.hour * 60 + cutoff.minute)
    if earliest >= closes:
        return None
    return opens, closes, earliest, closes - 1


def _day_label(day: date) -> str:
    today = now_local().date()
    if day == today:
        return "today"
    if day == today + timedelta(days=1):
        return "tomorrow"
    return day.strftime("%a %d %b")


def _next_bookable_dates(ctx: ToolContext, salon_ids: list[str], after: date) -> dict[str, str]:
    """First date AFTER `after` on which each salon has working hours."""
    return ctx.bookings.next_available_dates(salon_ids, after + timedelta(days=1)) if salon_ids else {}


def _availability(ctx: ToolContext, salon_ids: list[str], day: date) -> dict[str, dict[str, Any]]:
    """Per salon: can it be booked on `day` (hours and the 2-hour rule) and, if not, its next bookable date."""
    # ponytail: one working-hours lookup per salon (max 15 per search); batch it if searches get slow.
    windows = {sid: _bookable_window(ctx, sid, day) for sid in salon_ids}
    later = _next_bookable_dates(ctx, [sid for sid, w in windows.items() if w is None], day)
    result: dict[str, dict[str, Any]] = {}
    for sid, window in windows.items():
        if window:
            opens, closes, earliest, _ = window
            result[sid] = {
                "available_on_date": True,
                "open_hours": f"{_clock(opens)} to {_clock(closes)}",
                "bookable_from": _clock(earliest),
                "next_available_date": day.isoformat(),
                "summary": f"Available {_day_label(day)}, {_clock(earliest)} to {_clock(closes)}",
            }
        else:
            nxt = later.get(sid)
            result[sid] = {
                "available_on_date": False,
                "next_available_date": nxt,
                "summary": f"Not available {_day_label(day)} · next available {_day_label(date.fromisoformat(nxt))}"
                if nxt
                else "Not taking bookings at the moment",
            }
    return result


def run_check_availability(ctx: ToolContext, args: check_availability) -> dict:
    salon = ctx.session.known_salons.get(args.salon_id)
    if salon is None:
        return {"error": f"Unknown salon_id '{args.salon_id}'. Use search_salons first."}
    try:
        day = date.fromisoformat(args.date)
    except ValueError:
        return {"error": f"Date '{args.date}' is not YYYY-MM-DD."}
    if day < now_local().date():
        return {"error": f"{args.date} is in the past."}
    hours = ctx.bookings.working_hours(args.salon_id, day)
    window = _bookable_window(ctx, args.salon_id, day)
    if window is None:
        reason = "closed that day" if hours is None else "no time left that day that is at least 2 hours away"
        return {
            "salon": salon.salon_name,
            "date": args.date,
            "available": False,
            "reason": reason,
            "next_available_date": _next_bookable_dates(ctx, [args.salon_id], day).get(args.salon_id),
            "note": ADVANCE_HINT,
        }
    opens, closes, earliest, _ = window
    return {
        "salon": salon.salon_name,
        "date": args.date,
        "available": True,
        "open_hours": f"{_clock(opens)} to {_clock(closes)}",
        "bookable_from": _clock(earliest),
        "bookable_until": _clock(closes),
        "note": ADVANCE_HINT,
    }


def _validate(ctx: ToolContext, draft: BookingPayload) -> list[str]:
    problems: list[str] = []
    salon = ctx.session.known_salons.get(draft.salon_id) if draft.salon_id else None
    if draft.salon_id and salon is None:
        problems.append(f"Unknown salon_id '{draft.salon_id}'. Use search_salons first.")
    if salon and draft.service:
        offered = {s.lower(): s for s in salon.services}
        if draft.service.lower() not in offered:
            problems.append(
                f"{salon.salon_name} does not offer '{draft.service}'. It offers: {', '.join(salon.services) or 'nothing listed'}."
            )
    if draft.date:
        try:
            day = date.fromisoformat(draft.date)
        except ValueError:
            problems.append(f"Date '{draft.date}' is not YYYY-MM-DD.")
        else:
            if day < now_local().date():
                problems.append(f"{draft.date} is in the past.")
    if draft.time:
        try:
            slot = time.fromisoformat(draft.time)
        except ValueError:
            problems.append(f"Time '{draft.time}' is not HH:MM.")
        else:
            if draft.date and not problems:
                if datetime.combine(date.fromisoformat(draft.date), slot) < now_local().replace(tzinfo=None) + MIN_ADVANCE:
                    problems.append(f"{draft.date} {_clock(slot.hour * 60 + slot.minute)} is less than 2 hours away. {ADVANCE_HINT}")
    if salon and draft.date and draft.time and not problems:
        day, slot = date.fromisoformat(draft.date), time.fromisoformat(draft.time)
        window = _bookable_window(ctx, salon.vendor_id, day)
        minute = slot.hour * 60 + slot.minute
        if window is None:
            problems.append(f"{salon.salon_name} is not taking bookings on {draft.date}.")
        elif not window[2] <= minute <= window[3]:
            problems.append(
                f"{salon.salon_name} is open {_clock(window[0])} to {_clock(window[1])} on {draft.date}; "
                f"it can be booked from {_clock(window[2])} to {_clock(window[1])}. {ADVANCE_HINT}"
            )
    return problems


def run_update_booking(ctx: ToolContext, args: update_booking) -> dict:
    changes = {k: v for k, v in args.model_dump(exclude={"service_mentioned_as"}).items() if v}
    if ctx.session.editing_request and "salon_id" in changes:
        # The salon of an existing request is fixed: only a switch to another real salon is refused.
        requested = changes.pop("salon_id")
        if requested in ctx.session.known_salons and requested != ctx.session.draft.salon_id:
            return {
                "applied": False,
                "problems": ["The salon of an existing request cannot be changed. Cancel it and create a new request instead."],
                **_draft_view(ctx),
            }
    current = ctx.session.draft.service
    if "service" in changes and changes["service"].lower() != (current or "").lower():
        # The model's own judgement of what the customer said decides; code only enforces it.
        if args.service_mentioned_as != "specific_service":
            logger.info("SERVICE_NOT_CHOSEN_BY_CUSTOMER: %s (%s)", changes["service"], args.service_mentioned_as)
            ask = (
                "The customer named only a category. Call list_services for it and ask which service they want."
                if args.service_mentioned_as == "category_only"
                else "The customer has not said which service they want. Ask them; do not choose for them."
            )
            return {"applied": False, "problems": [ask], **_draft_view(ctx)}
    if "time" in changes:
        try:
            changes["time"] = time.fromisoformat(changes["time"]).strftime("%H:%M")
        except ValueError:
            pass  # reported by _validate
    candidate = ctx.session.draft.model_copy(update=changes)
    if candidate.salon_id in ctx.session.known_salons:
        salon = ctx.session.known_salons[candidate.salon_id]
        candidate.salon = salon.salon_name
        # Normalise to the salon's own spelling so the booking uses its real service name.
        match = next((s for s in salon.services if candidate.service and s.lower() == candidate.service.lower()), None)
        candidate.service = match or candidate.service

    problems = _validate(ctx, candidate)
    if problems:
        logger.info("BOOKING_UPDATE_REJECTED: %s", problems)
        return {"applied": False, "problems": problems, **_draft_view(ctx)}

    if candidate != ctx.session.draft:
        ctx.session.draft = candidate
        ctx.session.awaiting_confirmation = False  # any real change needs a fresh summary + confirmation
    logger.info("BOOKING_UPDATED: %s", candidate.model_dump(exclude_none=True))
    return {"applied": True, **_draft_view(ctx)}


def recommend_from_history(bookings: list[dict]) -> dict | None:
    """Scenario 1 priority over completed bookings: the salon the customer rated highest,
    else the one booked most often, else the most recently booked."""
    by_salon: dict[str, dict] = {}
    for b in bookings:
        if b["status"] != "Completed":
            continue
        s = by_salon.setdefault(b["salon_id"], {"salon_id": b["salon_id"], "salon": b["salon"], "bookings": 0, "my_best_rating": None, "last_date": ""})
        s["bookings"] += 1
        if b["my_rating"] is not None:
            s["my_best_rating"] = max(s["my_best_rating"] or 0, b["my_rating"])
        s["last_date"] = max(s["last_date"], b["date"] or "")
    if not by_salon:
        return None
    return max(by_salon.values(), key=lambda s: (s["my_best_rating"] or -1, s["bookings"], s["last_date"]))


def run_get_my_bookings(ctx: ToolContext, args: get_my_bookings) -> dict:
    user = ctx.session.user
    if not user or not user.user_id:
        return {"error": "The customer is not signed in, so booking history is unavailable."}
    history = ctx.bookings.history(user.user_id)
    bookings = history["bookings"]
    if args.service:
        wanted = args.service.lower()
        bookings = [b for b in bookings if any(wanted in s.lower() or s.lower() in wanted for s in b["services"])]
    bookable = {s.vendor_id: s for s in ctx.salons.get_by_ids(list({b["salon_id"] for b in bookings}))}
    ctx.session.known_salons.update(bookable)
    return {
        "bookings": bookings[:15],
        "pending_requests": history["requests"],
        # only salons that are still active and approved can be recommended
        "recommended_salon": recommend_from_history([b for b in bookings if b["salon_id"] in bookable]),
    }


def run_confirm_booking(ctx: ToolContext, args: confirm_booking) -> dict:
    session = ctx.session
    view = _draft_view(ctx)
    if not view["ready_for_summary"]:
        return {"error": f"Booking incomplete, missing: {', '.join(view['missing'])}.", **view}
    if not session.awaiting_confirmation:
        return {"error": "Show the customer the full booking summary and get their explicit confirmation first.", **view}
    problems = _validate(ctx, session.draft)  # re-check: e.g. the date may have passed meanwhile
    if problems:
        return {"error": "Booking is no longer valid.", "problems": problems, **view}

    d, user = session.draft, session.user
    salon = session.known_salons[d.salon_id]
    offer = next((o for o in salon.offers if o.name.lower() == d.service.lower()), None)
    if session.editing_request:
        return _save_modification(ctx, offer)
    if not user or not user.user_id:
        return {"error": "Booking requires a signed-in Bookly account. Sign in and try again."}
    contact = session.booking_contact or {}
    def value(key: str, profile_value: Any = None) -> Any:
        candidate = contact.get(key)
        return candidate if candidate is not None and candidate != "" else profile_value

    contact_name = value("contact_name", user.full_name)
    email = value("email", user.email)
    country_code = value("country_code", user.country_code)
    phone = value("phone_number", user.phone_number)
    address = value("address", user.address)
    city = value("city", user.city)
    zip_code = value("zip_code", user.zip_code)
    latitude = value("latitude", user.latitude)
    longitude = value("longitude", user.longitude)
    required = {
        "contact name": contact_name,
        "email": email,
        "country code": country_code,
        "phone number": phone,
        "address": address,
        "city": city,
        "zip code": zip_code,
        "latitude": latitude,
        "longitude": longitude,
    }
    missing_contact = [label for label, item in required.items() if item is None or item == ""]
    if missing_contact:
        return {"error": "Before submitting, please provide: " + ", ".join(missing_contact) + ". Save these using PATCH /session/{session_id}/booking-contact, then explicitly confirm the booking again."}
    if not offer or not offer.id or offer.id.startswith("mock-"):
        return {"error": "The selected service has no real Bookly service ID, so the booking cannot be submitted."}
    booking_payload = {
        "vendorId": salon.vendor_id,
        "serviceId": [offer.id],
        "bookingType": "Individual",
        "date": d.date,
        "slot": time.fromisoformat(d.time).strftime("%I:%M %p"),
        "BookingAppointment": contact.get("booking_appointment", "Home"),
        "contactName": contact_name,
        "email": email,
        "couponId": contact.get("coupon_id"),
        "discountAmount": contact.get("discount_amount"),
        "finalAmount": contact.get("final_amount"),
        "vatPercentage": ctx.bookings.vat_percentage(),
        "vat": contact.get("vat"),
        "countryCode": country_code,
        "phoneNumber": phone,
        "address": address,
        "city": city,
        "bookingcreatedBy": user.user_id,
        "zipCode": zip_code,
        "location": {"type": "Point", "coordinates": [float(longitude), float(latitude)]},
        "additionalNote": contact.get("additional_note"),
    }
    try:
        result = ctx.bookings.create_external_booking(booking_payload)
    except RuntimeError as exc:
        logger.warning("BOOKING_API_FAILED: %s", exc)
                return {"error": str(exc), "retry_safe": False}
    booking = result["results"]["booking"]

    logger.info("Booking created: %s", booking)

    request_id = booking["orderId"]
    booking_id = booking["_id"]
    ctx.booking_result = {
        "booking_id": booking_id,
        "order_id": request_id,

        "status": booking.get("bookingStatus", "Pending"),
        "payment_status": booking.get("paymentStatus", "Pending"),
        "salon": salon.salon_name,
        "service": d.service,
        "date": d.date,
        "time": d.time,
        "user_id": user.user_id,
    }
    session.last_booking_order_id = request_id
    session.draft = BookingPayload()
    session.awaiting_confirmation = False
        return {
        "submitted": True,
        "booking_id": booking_id,
        "order_id": request_id,


        "booking_status": booking.get("bookingStatus", "Pending"),
        "payment_status": booking.get("paymentStatus", "Pending"),
        "tell_customer": f"Your booking was created with order ID {request_id}. Its current status is {booking.get('bookingStatus', 'Pending')}; payment status is {booking.get('paymentStatus', 'Pending')}.",
    }



def _request_view(req: dict) -> dict[str, Any]:
    status = req.get("status")
    return {
        "request_id": req.get("request_id"),
        "salon": req.get("vendorName"),
        "service": req.get("serviceName"),
        "date": req.get("requestedDate"),
        "time": req.get("requestedTime"),
        "status": status,
        "can_modify": status in MODIFIABLE_STATUSES,
        "can_cancel": status in CANCELLABLE_STATUSES,
    }


def _may_manage(ctx: ToolContext, req: dict) -> bool:
    """A signed-in customer's requests are theirs only; anonymous (session) requests are
    manageable by whoever has the request ID."""
    owner = str(req.get("userId") or "")
    user = ctx.session.user
    if owner and owner in {ctx.session.session_id, user.user_id if user else None}:
        return True
    return not ObjectId.is_valid(owner)


def _load_request(ctx: ToolContext, request_id: str) -> tuple[dict | None, dict | None]:
    """(request, error)."""
    req = ctx.bookings.find_request(request_id)
    if req is None:
        return None, {"error": f"No booking request found with ID {request_id}."}
    if not _may_manage(ctx, req):
        return None, {"error": "This booking request belongs to another customer account."}
    return req, None


def run_get_booking_request(ctx: ToolContext, args: get_booking_request) -> dict:
    req, error = _load_request(ctx, args.request_id)
    if error:
        return error
    ctx.session.viewed_requests[req["request_id"]] = ctx.session.turn
    return _request_view(req)


def run_modify_booking_request(ctx: ToolContext, args: modify_booking_request) -> dict:
    req, error = _load_request(ctx, args.request_id)
    if error:
        return error
    if req.get("status") not in MODIFIABLE_STATUSES:
        return {"error": f"Request {req['request_id']} is {req.get('status')} and can no longer be modified.", **_request_view(req)}
    salons = ctx.salons.get_by_ids([str(req["vendorId"])])
    if not salons:
        return {"error": f"{req.get('vendorName')} is no longer taking bookings, so this request can only be cancelled."}
    ctx.session.known_salons[salons[0].vendor_id] = salons[0]
    ctx.session.viewed_requests[req["request_id"]] = ctx.session.turn
    ctx.session.editing_request = req
    ctx.session.draft = BookingPayload(
        service=req.get("serviceName"),
        salon_id=salons[0].vendor_id,
        salon=salons[0].salon_name,
        date=req.get("requestedDate"),
        time=req.get("requestedTime"),
    )
    ctx.session.awaiting_confirmation = False
    return {
        "editing_request_id": req["request_id"],
        **_draft_view(ctx),
        "next": "Ask what the customer wants to change (date, time or service), then call update_booking.",
    }


def draft_differs_from_request(session) -> bool:
    """While modifying, a summary only needs confirming once something actually changed."""
    req, d = session.editing_request, session.draft
    if req is None:
        return True
    return (d.date, d.time, (d.service or "").lower()) != (
        req.get("requestedDate"),
        req.get("requestedTime"),
        (req.get("serviceName") or "").lower(),
    )


def run_cancel_booking_request(ctx: ToolContext, args: cancel_booking_request) -> dict:
    req, error = _load_request(ctx, args.request_id)
    if error:
        return error
    rid, status = req["request_id"], req.get("status")
    if status not in CANCELLABLE_STATUSES:
        return {"error": f"Request {rid} is {status} and cannot be cancelled.", **_request_view(req)}
    shown = ctx.session.viewed_requests.get(rid)
    if shown is None or shown >= ctx.session.turn:
        return {"error": "Show the customer this request's details first and ask them to confirm the cancellation."}
    now = datetime.now(timezone.utc)
    ok = ctx.bookings.update_request(
        rid,
        status,
        {
            "status": "cancelled",
            "bookingStatus": "cancelled",
            "cancelReason": args.reason or "user requested via chatbot",
            "cancelledAt": now,
        },
    )
    if not ok:
        return {"error": f"Request {rid} changed meanwhile (the salon may have responded). Fetch it again."}
    if ctx.session.editing_request and ctx.session.editing_request.get("request_id") == rid:
        ctx.session.editing_request = None
        ctx.session.draft = BookingPayload()
    ctx.booking_result = {"request_id": rid, "status": "cancelled"}
    return {"cancelled": True, "request_id": rid}


def _save_modification(ctx: ToolContext, offer) -> dict:
    """Write the draft's changes onto the request being modified, keeping its request_id and
    recording the previous values the way the booking collection already does."""
    session, d = ctx.session, ctx.session.draft
    req = session.editing_request
    rid, now = req["request_id"], datetime.now(timezone.utc)
    fields: dict[str, Any] = {}
    if (d.date, d.time) != (req.get("requestedDate"), req.get("requestedTime")):
        fields.update(
            date=f"{d.date} 00:00:00",
            slot=time.fromisoformat(d.time).strftime("%I:%M %p"),
            requestedDate=d.date,
            requestedTime=d.time,
            previousRequestedDate=req.get("requestedDate"),
            previousRequestedTime=req.get("requestedTime"),
            rescheduledAt=now,
        )
    if d.service.lower() != (req.get("serviceName") or "").lower():
        fields.update(
            services=[offer.id] if offer else [],
            serviceName=d.service,
            categoryName=offer.category if offer else None,
            previousServiceId=(req.get("services") or [None])[0],
            previousServiceName=req.get("serviceName"),
            serviceModifiedAt=now,
        )
    if not fields:
        return {"error": "Nothing was changed on this request."}
    if not ctx.bookings.update_request(rid, "pending", fields):
        return {"error": f"Request {rid} is no longer pending (the salon may have responded), so it was not changed."}
    ctx.booking_result = {"request_id": rid, "status": "pending", "modified": True, "service": d.service, "date": d.date, "time": d.time}
    session.draft, session.editing_request, session.awaiting_confirmation = BookingPayload(), None, False
    return {
        "updated": True,
        "request_id": rid,
        "tell_customer": f"Confirm the change was saved on request {rid}.",
        "status": "pending",
        "next_steps": "The salon will review the updated request; the customer is notified in the Bookly app.",
    }


def run_no_action(ctx: ToolContext, args: no_action) -> dict:
    return {"ok": True}


def run_reset_booking(ctx: ToolContext, args: reset_booking) -> dict:
    ctx.session.editing_request = None
    ctx.session.draft = BookingPayload()
    ctx.session.awaiting_confirmation = False
    return {"cleared": True}


ToolHandler = Callable[[ToolContext, Any], dict]

TOOLS: dict[str, tuple[type[BaseModel], ToolHandler]] = {
    "list_service_categories": (list_service_categories, run_list_service_categories),
    "list_services": (list_services, run_list_services),
    "search_salons": (search_salons, run_search_salons),
    "search_knowledge_base": (search_knowledge_base, run_search_knowledge_base),
    "check_availability": (check_availability, run_check_availability),
    "get_my_bookings": (get_my_bookings, run_get_my_bookings),
    "update_booking": (update_booking, run_update_booking),
    "confirm_booking": (confirm_booking, run_confirm_booking),
    "get_booking_request": (get_booking_request, run_get_booking_request),
    "modify_booking_request": (modify_booking_request, run_modify_booking_request),
    "cancel_booking_request": (cancel_booking_request, run_cancel_booking_request),
    "reset_booking": (reset_booking, run_reset_booking),
    "no_action": (no_action, run_no_action),
}
