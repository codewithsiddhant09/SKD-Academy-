from __future__ import annotations

import re

from app.agents.semantic_intent_classifier import SemanticIntentClassifier
from app.core.logging import get_logger
from app.models.enums import IntentType
from app.models.schemas import IntentAnalysis
from app.orchestration.models import OrchestrationContext, PendingQuestion, RouteTarget

logger = get_logger(__name__)


class Router:
    """Route by intent + session state — no response generation."""

    _POLICY_PHRASES = (
        "cancellation policy",
        "cancel policy",
        "refund policy",
        "privacy policy",
        "terms and conditions",
        "payment methods",
        "refund",
        "privacy",
        "terms",
    )

    def __init__(self) -> None:
        self._semantic = SemanticIntentClassifier()

    def route(self, ctx: OrchestrationContext) -> RouteTarget:
        intent = ctx.intent.intent
        message = ctx.user_message
        pending = ctx.pending_question

        logger.info("ROUTER: intent=%s pending=%s", intent, pending)

        if pending == PendingQuestion.CONFIRMATION:
            return RouteTarget.BOOKING
        if pending in {PendingQuestion.DATE, PendingQuestion.TIME, PendingQuestion.SALON}:
            return RouteTarget.BOOKING
        if self._has_booking_context(ctx) and self._is_booking_turn(message, ctx):
            return RouteTarget.BOOKING

        if self._faq_interrupt_during_booking(ctx):
            ctx.resume_booking_after_faq = True
            return RouteTarget.FAQ

        if intent == IntentType.SMALL_TALK:
            return RouteTarget.GREETING
        if intent in {IntentType.BOOKLY_PLATFORM_INFORMATION} or self._semantic.is_platform_question(message):
            return RouteTarget.PLATFORM_INFORMATION
        if intent == IntentType.BOOKLY_AI_INFORMATION or self._semantic.is_ai_question(message):
            return RouteTarget.AI_INFORMATION
        if intent == IntentType.CATEGORY_DETAIL:
            return RouteTarget.CATEGORY_DETAIL
        if intent == IntentType.CATEGORY_LIST or self._semantic.is_category_list(message):
            return RouteTarget.CATEGORY_LIST
        if intent in {
            IntentType.SERVICE_SEARCH,
            IntentType.SALON_SEARCH,
            IntentType.LOCATION_SEARCH,
            IntentType.SALON_DISCOVERY,
        }:
            return RouteTarget.SALON_SEARCH
        if intent == IntentType.APPOINTMENT_BOOKING:
            if self._explicit_booking_entities(ctx):
                return RouteTarget.BOOKING
            return RouteTarget.SALON_SEARCH
        if intent in {IntentType.FAQ, IntentType.POLICY, IntentType.APPOINTMENT_CANCELLATION}:
            return RouteTarget.FAQ
        if self._is_policy_message(message):
            return RouteTarget.FAQ
        if pending == PendingQuestion.LOCATION or pending == PendingQuestion.SERVICE:
            return RouteTarget.SALON_SEARCH

        return RouteTarget.FALLBACK

    def _has_booking_context(self, ctx: OrchestrationContext) -> bool:
        mem = ctx.intent  # placeholder access via session in pipeline
        return False

    def _has_booking_context_from_session(self, session_id: str, session_manager) -> bool:
        if session_manager.has_active_booking(session_id):
            return True
        draft = session_manager.get_booking_draft(session_id)
        return any(getattr(draft, f) for f in ("service", "salon", "date", "time"))

    def route_with_session(self, ctx: OrchestrationContext, session_manager) -> RouteTarget:
        intent = ctx.intent.intent
        message = ctx.user_message
        pending = ctx.pending_question
        session_id = ctx.session_id

        if pending == PendingQuestion.CONFIRMATION:
            return RouteTarget.BOOKING
        if pending in {PendingQuestion.DATE, PendingQuestion.TIME}:
            return RouteTarget.BOOKING
        if pending == PendingQuestion.SALON and self._looks_like_salon_pick(message):
            return RouteTarget.BOOKING

        if self._faq_interrupt_during_booking_ctx(ctx, session_manager):
            ctx.resume_booking_after_faq = True
            return RouteTarget.FAQ

        if session_manager.has_active_booking(session_id) or self._has_booking_draft(session_manager, session_id):
            if intent == IntentType.APPOINTMENT_BOOKING or self._is_booking_turn(message, ctx):
                return RouteTarget.BOOKING
            stage = session_manager.get_booking_stage(session_id)
            if stage in {"awaiting_date", "awaiting_time", "awaiting_confirmation", "awaiting_salon"}:
                return RouteTarget.BOOKING

        if intent == IntentType.SMALL_TALK:
            return RouteTarget.GREETING
        if intent == IntentType.BOOKLY_PLATFORM_INFORMATION or self._semantic.is_platform_question(message):
            return RouteTarget.PLATFORM_INFORMATION
        if intent == IntentType.BOOKLY_AI_INFORMATION or self._semantic.is_ai_question(message):
            return RouteTarget.AI_INFORMATION
        if intent == IntentType.CATEGORY_DETAIL:
            return RouteTarget.CATEGORY_DETAIL
        if intent == IntentType.CATEGORY_LIST or self._semantic.is_category_list(message):
            return RouteTarget.CATEGORY_LIST
        if intent in {
            IntentType.SERVICE_SEARCH,
            IntentType.SALON_SEARCH,
            IntentType.LOCATION_SEARCH,
            IntentType.SALON_DISCOVERY,
        }:
            return RouteTarget.SALON_SEARCH
        if intent == IntentType.APPOINTMENT_BOOKING:
            if self._explicit_booking_entities(ctx):
                return RouteTarget.BOOKING
            return RouteTarget.SALON_SEARCH
        if intent in {IntentType.FAQ, IntentType.POLICY, IntentType.APPOINTMENT_CANCELLATION}:
            return RouteTarget.FAQ
        if self._is_policy_message(message):
            return RouteTarget.FAQ
        if pending in {PendingQuestion.LOCATION, PendingQuestion.SERVICE}:
            return RouteTarget.SALON_SEARCH

        return RouteTarget.FALLBACK

    @staticmethod
    def _has_booking_draft(session_manager, session_id: str) -> bool:
        draft = session_manager.get_booking_draft(session_id)
        return any(getattr(draft, f) for f in ("service", "salon", "date", "time"))

    @staticmethod
    def _looks_like_salon_pick(message: str) -> bool:
        text = message.strip()
        return 1 <= len(text.split()) <= 6 and not re.search(r"\d{1,2}\s*(?:am|pm)\b", text, re.I)

    def _explicit_booking_entities(self, ctx: OrchestrationContext) -> bool:
        e = ctx.entities
        return bool(e.service or e.salon or e.date or e.time)

    def _is_booking_turn(self, message: str, ctx: OrchestrationContext) -> bool:
        lower = message.lower()
        if any(w in lower for w in ("book", "appointment", "reserve", "schedule", "tomorrow", "today")):
            return True
        return bool(re.search(r"\d{1,2}\s*(?:am|pm)\b", lower) or re.search(r"\d{1,2}/\d{1,2}/\d{4}", lower))

    def _faq_interrupt_during_booking_ctx(self, ctx: OrchestrationContext, session_manager) -> bool:
        if not self._has_booking_draft(session_manager, ctx.session_id):
            return False
        if ctx.intent.intent in {IntentType.FAQ, IntentType.POLICY, IntentType.APPOINTMENT_CANCELLATION}:
            return True
        return self._is_policy_message(ctx.user_message)

    def _faq_interrupt_during_booking(self, ctx: OrchestrationContext) -> bool:
        return False

    def _is_policy_message(self, message: str) -> bool:
        lower = message.lower()
        return any(p in lower for p in self._POLICY_PHRASES)
