"""Bookly assistant: one LLM tool-calling loop per customer message.

Flow for every message:
  1. Build the system prompt (rules + today's date + live session state).
  2. Send prompt + recent history + the new message to the LLM with the tools.
  3. Execute any tool calls the LLM makes, feed results back, repeat
     until the LLM answers in plain text (or MAX_TOOL_ROUNDS is hit).
  4. Store the reply and return it with salon cards / booking result.

There is no keyword or regex intent detection: the LLM reads the whole message
in context and decides what to do. Rules that must never be broken (salon
offers the service, no past dates, explicit confirmation) are enforced in tools.
"""
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI, OpenAIError, pydantic_function_tool

from app.agent.session import Session, SessionStore
from app.agent.tools import TOOLS, ToolContext, draft_differs_from_request, now_local
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.enums import IntentType
from app.models.schemas import ChatResponse, SalonRecommendation, SessionContext
from app.rag.vector_store import RagStore
from app.services.booking_service import BookingService
from app.services.category_service import CategoryService
from app.services.salon_service import SalonService
from app.services.user_service import UserService

logger = get_logger(__name__)

MAX_TOOL_ROUNDS = 6
FALLBACK_REPLY = "I apologize, I could not process that just now. Please try again in a moment."

SYSTEM_PROMPT = """You are Bookly's AI assistant. Bookly is a salon and wellness appointment booking platform.
You help customers discover salons and services, book appointments, and answer questions about Bookly.

How to work:
- Understand what the customer means from the whole conversation, not from keywords. They may ask
  questions, change their mind, or switch topics in the middle of a booking: handle what they said,
  then guide them back to any unfinished booking.
- Use tools for every fact. Never invent salons, services, categories, prices, availability or policies.
  For any question about Bookly itself (what it is, how it works, payments, cancellation, refunds,
  privacy), call search_knowledge_base even if you think you know the answer.
- Ask one short question at a time when something is missing.

Booking rules:
- A booking needs: service, salon (from search_salons or get_my_bookings), date and time.
- Use search_salons for salons, services and categories. Call it in the same turn as soon as you know
  any of: location, service, category or salon name (e.g. "I want Hulk service" -> service="Hulk";
  "what services are in Lashes" -> category="Lashes"). Never say you will search without calling it,
  and do not ask optional questions first. Ask for a location to narrow results when it helps.
  If the customer names a salon that is not in salons_seen, call search_salons with salon_name before
  answering; never say a salon does not exist without searching for it.
  Salon cards are shown automatically: introduce them briefly, do not repeat every detail.
- Only present salons returned by search_salons for the service/category the customer asked for;
  never mention salons that do not offer it. For each salon, say whether it can be booked on the
  requested day (with its hours) and, if not, its next available day. If a salon has no next
  available day, say it is not taking bookings at the moment.
- When the customer asks when a salon is next available, call check_availability for today and
  answer with the next available day (and its hours if they ask).
- If the customer wants a service they had before, wants to rebook, or asks about past bookings,
  call get_my_bookings and suggest its recommended_salon (explain why: their rating, how often
  or how recently they booked it). Never assume the previous time: ask whether they want the
  same time or a different one.
- Services vs categories: if the customer mentions a category (e.g. "Hair Removal", "Lashes") rather
  than a specific service, call list_services for it, show the services in that category and ask
  which one they want. Never treat a category as the service.
- Never choose or assume a service. If the customer says they want to change the service without
  naming the new one, ask which service they want before changing it. When a salon is already chosen,
  offer only that salon's own services (from salons_seen), not services of other salons.
- Times: use check_availability and describe availability as a range ("open 11:00 AM to 5:00 PM"),
  never as a list of slots. Appointments must be requested at least 2 hours in advance: mention this
  when asking for a time, and when a time is too soon, give the earliest time that can be booked.
- Call update_booking immediately whenever the customer gives or changes service, salon, date or
  time, in that same turn and before asking your next question. This includes picking a salon
  from the cards (e.g. "Proceed with X", "Book X for Y"): call it with that salon_id and the service,
  so the choice is saved and checked right away. Never choose a service for the customer: if they
  only named a category (e.g. Lashes) and the salon offers several services in it, ask which one.
  If it reports problems (service not offered, time not available, past date), explain them
  plainly and offer options: another service or time at this salon, or other salons.
- When update_booking says ready_for_summary, show the summary and ask for appointment location FIRST.
  Ask: "Would you like to visit the salon or have the service at your home?"
  Options:
  - "Visit Salon" / "Walk-In" → set_appointment_location with "Salon"
  - "Home Visit" / "At Home" → set_appointment_location with "Home"
  
  After appointment location is set, ask for booking type selection.
  Ask: "Would you like to book for yourself (Individual) or for a group (Group Booking)?"
  - For Individual: Continue to payment option selection
  - For Group: Ask "How many people will be in your group?" and store the number
  
  After booking type is confirmed, ask for payment option selection.
  Offer "Pay Now" (online payment before appointment) or "Pay at Store" (pay at salon after service).
  
  After payment option is selected, collect contact information:
  - For BOTH Salon Visit and Home Service, ALWAYS ask for and save:
    * Full name
    * Email address
    * Phone number with country code (e.g., +971 for UAE)
    * Address
  - For Home Service ONLY, also ask for:
    * City
    * Location coordinates (latitude/longitude) - can be obtained from address
  
  NOTE: Do NOT ask for zip code / postal code - it is not required.
  
  When customer provides contact details in the conversation:
  1. Parse all information from their message (name, email, phone, country code, address, city, zip)
  2. Immediately call save_booking_contact with ALL provided information
  3. Check which fields are still missing
  4. Ask for any missing required fields
  5. Only call confirm_booking after ALL required fields are collected
  
  IMPORTANT: Do NOT assume contact info from user profile. Always ask explicitly if not provided.
  
  IMPORTANT: Always create the booking immediately after payment selection - there is NO salon approval step.
  PayAtStore bookings are APPROVED immediately. PayNow bookings require payment within 10 minutes.
- Call confirm_booking after explicit confirmation and payment choice.
  The booking is created immediately via Bookly API - do NOT say "salon will review" or "waiting for approval".
- For PayNow: The response includes a payment link. Tell customer to complete payment within 10 minutes
  or the booking will be automatically cancelled. Show the payment link clearly.
- After PayNow payment: When customer returns or asks about payment status, use check_payment_status tool
  to verify if payment is complete. If payment is confirmed (status: Paid), congratulate them and confirm
  their booking is approved. Never assume payment is complete without checking.
- For PayAtStore: The booking is APPROVED immediately. Tell customer their appointment is confirmed and
  they will pay at the salon after the service is complete.
- For cancellation, retrieve and show the Bookly cancellation quote (including any fees) before asking 
  for confirmation. Only cancel after explicit confirmation. Mention the refund amount if applicable.
- WhatsApp bookings: Use PayAtStore as default. PayNow is available if explicitly requested.

Existing booking requests (IDs like BKLY-09102026-004):
- When the customer gives a request ID or asks about an existing request, call get_booking_request and
  show its salon, service, date, time and status.
- To change its date, time or service, call modify_booking_request, then update_booking with the
  changes, show the updated summary as a proposed change ("Here is the updated request: ... Shall I
  save this change?"), never as already done, and call confirm_booking only after the customer confirms.
  The changes are saved on the SAME request ID; never create a new request for a modification. Only
  pending requests can be changed, and the salon cannot be changed (cancel and book anew instead).
- To cancel, show the request's details first and ask the customer to confirm; only after they
  explicitly confirm, call cancel_booking_request.

Style: reply in the customer's language (e.g. Hinglish to Hinglish, Arabic to Arabic). Professional, warm, concise. No filler words such as Awesome, Great, Cool, Amazing, Perfect.
Use short paragraphs. Do not mention tools, JSON or internal ids to the customer."""


def _intent_from_tools(called: list[str]) -> IntentType:
    """Report what the assistant did this turn (for analytics/debug panels)."""
    if {
        "update_booking", "confirm_booking", "reset_booking", "check_availability", "get_my_bookings",
        "get_booking_request", "modify_booking_request", "cancel_booking_request", "quote_booking_cancellation",
        "cancel_bookly_booking",
    } & set(called):
        return IntentType.APPOINTMENT_BOOKING
    if "search_salons" in called:
        return IntentType.SALON_SEARCH
    if "search_knowledge_base" in called:
        return IntentType.FAQ
    if "list_service_categories" in called:
        return IntentType.CATEGORY_LIST
    return IntentType.GENERAL_CONVERSATION


class BookingAssistant:
    def __init__(
        self,
        categories: CategoryService,
        users: UserService,
        salons: SalonService | None = None,
        bookings: BookingService | None = None,
        knowledge: RagStore | None = None,
        client: Any | None = None,
    ) -> None:
        self.settings = get_settings()
        self.sessions = SessionStore()
        self.categories = categories
        self.users = users
        self.salons = salons or SalonService()
        self.bookings = bookings or BookingService()
        self.knowledge = knowledge
        self.client = client or (OpenAI(api_key=self.settings.openai_api_key) if self.settings.openai_api_key else None)
        self.tool_specs = [pydantic_function_tool(model) for model, _ in TOOLS.values()]

    # ------------------------------------------------------------------ #
    def ensure_user_context(self, session_id: str, user_id: str | None) -> SessionContext | None:
        """Load the user's profile once per session (never fails the chat)."""
        session = self.sessions.get(session_id)
        if not user_id or (session.user and session.user.user_id == user_id):
            return session.user
        try:
            session.user = self.users.build_session_context(user_id, self.users.get_user_profile(user_id))
        except Exception:
            logger.exception("USER_CONTEXT_FAILED: session=%s user_id=%s", session_id, user_id)
            session.user = SessionContext(user_id=user_id)
        return session.user

    def _system_prompt(self, session: Session) -> str:
        now = now_local()
        state = {
            "today": now.strftime("%A %Y-%m-%d"),
            "current_time": now.strftime("%H:%M"),
            "customer_name": session.user.full_name if session.user else None,
            "booking_draft": session.draft.model_dump(include={"service", "salon", "salon_id", "date", "time"}),
            "booking_summary_awaiting_payment_choice": session.awaiting_confirmation and not session.editing_request,
            "summary_shown_awaiting_confirmation": session.awaiting_confirmation,
            "selected_payment_option": session.payment_option,
            "modifying_request_id": session.editing_request.get("request_id") if session.editing_request else None,
            "salons_seen": [
                {"salon_id": s.vendor_id, "name": s.salon_name, "services": s.services}
                for s in list(session.known_salons.values())[-20:]
            ],
        }
        return f"{SYSTEM_PROMPT}\n\nCurrent session state (JSON):\n{json.dumps(state, default=str)}"

    def _run_tool(self, ctx: ToolContext, name: str, arguments: str) -> dict:
        if name not in TOOLS:
            return {"error": f"Unknown tool {name}"}
        model, handler = TOOLS[name]
        try:
            result = handler(ctx, model.model_validate_json(arguments or "{}"))
        except Exception as exc:
            logger.exception("TOOL_FAILED: %s(%s)", name, arguments)
            result = {"error": f"{name} failed: {exc}"}
        logger.info("TOOL: %s(%s) -> %s", name, arguments, json.dumps(result, default=str)[:500])
        return result

    # ------------------------------------------------------------------ #
    def chat(self, session_id: str, user_message: str, user_id: str | None = None) -> ChatResponse:
        self.ensure_user_context(session_id, user_id)
        session = self.sessions.get(session_id)
        session.turn += 1
        ctx = ToolContext(
            session=session,
            categories=self.categories,
            salons=self.salons,
            bookings=self.bookings,
            knowledge=self.knowledge,
        )
        payment_choice_required = session.awaiting_confirmation and not session.editing_request
        if payment_choice_required:
            choice = self._payment_choice(user_message)
            if session.booking_platform == "whatsapp":
                session.payment_option = choice or "Pay Later"
            elif choice:
                session.payment_option = choice
        called: list[str] = []
        reply = self._converse(session, ctx, user_message, called)
        rid = (ctx.booking_result or {}).get("request_id")
        if reply and rid and rid not in reply:
            # The booking ID must always be shown when a request is created, changed or cancelled.
            reply = f"{reply}\n\nBooking ID: {rid}"
        if reply is None:
            # The turn failed, so the customer never saw a summary: do not arm confirmation.
            reply = FALLBACK_REPLY
        else:
            # The summary is shown in the turn the draft became complete; confirmation
            # is only accepted from a later turn (see confirm_booking).
            d = session.draft
            session.awaiting_confirmation = all([d.service, d.salon_id, d.date, d.time]) and draft_differs_from_request(
                session
            )
            if not session.awaiting_confirmation:
                session.payment_option = None
        session.add_message("user", user_message)
        session.add_message("assistant", reply)

        intent = _intent_from_tools(called)
        logger.info("CHAT: session=%s tools=%s intent=%s", session_id, called, intent.value)
        return ChatResponse(
            session_id=session_id,
            reply=reply,
            intent=intent,
            structured={
                "intent": intent.value,
                "tools_called": called,
                "booking_payload": session.draft.model_dump(),
                "awaiting_confirmation": session.awaiting_confirmation,
                "payment_option": session.payment_option,
                "booking_response": ctx.booking_result,
                "booking_contact_required": bool(session.awaiting_confirmation and session.user and session.user.user_id and not session.last_booking_order_id),
                "user_context": session.user.model_dump(include={"user_id", "full_name"}) if session.user else None,
            },
            recommendations=self._cards(session, ctx.shown_salon_ids or [], ctx.card_notes),
        )

    def _converse(self, session: Session, ctx: ToolContext, user_message: str, called: list[str]) -> str | None:
        """Run the LLM/tool loop; returns the final reply, or None if the turn failed."""
        if self.client is None:
            return "The Bookly assistant is not configured yet (missing OpenAI API key). Please contact support."

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt(session)},
            *session.history,
            {"role": "user", "content": user_message},
        ]
        # While a booking awaits a payment choice, require an explicit tool decision rather than
        # letting the model claim a booking was created without calling the booking API.
        tool_choice = "required" if session.awaiting_confirmation else "auto"
        try:
            for _ in range(MAX_TOOL_ROUNDS):
                response = self.client.chat.completions.create(
                    model=self.settings.openai_model,
                    messages=messages,
                    tools=self.tool_specs,
                    tool_choice=tool_choice,
                    temperature=0.2,
                )
                tool_choice = "auto"
                message = response.choices[0].message
                if not message.tool_calls:
                    return (message.content or "").strip() or None

                messages.append(
                    {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [call.model_dump() for call in message.tool_calls],
                    }
                )
                for call in message.tool_calls:
                    called.append(call.function.name)
                    result = self._run_tool(ctx, call.function.name, call.function.arguments)
                    messages.append(
                        {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)}
                    )
        except OpenAIError:
            logger.exception("LLM_FAILED: session=%s", session.session_id)
            return None
        logger.warning("LLM_TOOL_LOOP_LIMIT: session=%s tools=%s", session.session_id, called)
        return None

    @staticmethod
    def _payment_choice(message: str) -> str | None:
        """Recognize only an explicit Pay Now or Pay at Store selection."""
        normalized = " ".join(message.lower().replace("-", " ").split())
        pay_now = any(phrase in normalized for phrase in ("pay now", "pay immediately", "pay upfront", "pay online", "online payment"))
        pay_at_store = any(phrase in normalized for phrase in ("pay later", "pay at store", "pay at salon", "pay after", "pay afterwards"))
        if pay_now == pay_at_store:
            return None
        return "Pay Now" if pay_now else "Pay at Store"

    @staticmethod
    def _cards(session: Session, salon_ids: list[str], notes: dict[str, str]) -> list[SalonRecommendation]:
        cards = []
        for sid in salon_ids:
            s = session.known_salons[sid]
            cards.append(
                SalonRecommendation(
                    vendor_id=s.vendor_id,
                    salon_name=s.salon_name,
                    rating=s.rating,
                    reason=notes.get(sid) or (f"Rated {s.rating}/5" if s.rating else "New on Bookly"),
                    location=s.location,
                    services=s.services,
                    image=s.image,
                    redirect_url=f"/salon/{s.vendor_id}",
                )
            )
        return cards
