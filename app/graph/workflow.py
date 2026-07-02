from __future__ import annotations

import re

from langgraph.graph import END, StateGraph

from app.agents.booking_agent import BookingAgent
from app.agents.category_agent import CategoryAgent
from app.agents.faq_agent import FaqAgent
from app.agents.intent_agent import IntentAgent
from app.agents.location_agent import LocationAgent
from app.agents.salon_discovery_agent import SalonDiscoveryAgent
from app.agents.salon_ranking_agent import SalonRankingAgent
from app.agents.semantic_intent_classifier import SemanticIntentClassifier
from app.core.logging import get_logger
from app.memory.conversation_store import ConversationStore
from app.models.enums import IntentType
from app.utils.location import sanitize_location
from app.utils.text import title_case_safe
from app.models.schemas import BookingPayload, IntentAnalysis
from app.models.state import GraphState
from app.graph.booking_orchestration import (
    BOOKING_SLOT_PRIORITY,
    BookingEntityState,
    compute_missing_slots,
    decide_booking_action,
    is_generic_salon_phrase,
)
from app.repositories.salon_repository import SalonRepository

logger = get_logger(__name__)


class OrchestratorWorkflow:
    def __init__(
        self,
        memory: ConversationStore,
        categories: list[str],
        intent_agent: IntentAgent,
        category_agent: CategoryAgent,
        location_agent: LocationAgent,
        discovery_agent: SalonDiscoveryAgent,
        ranking_agent: SalonRankingAgent,
        faq_agent: FaqAgent,
        booking_agent: BookingAgent,
        booking_service: BookingService,
        category_service=None,
    ) -> None:
        self.memory = memory
        self.categories = categories
        self.intent_agent = intent_agent
        self.category_agent = category_agent
        self.location_agent = location_agent
        self.discovery_agent = discovery_agent
        self.ranking_agent = ranking_agent
        self.faq_agent = faq_agent
        self.booking_agent = booking_agent
        self.booking_service = booking_service
        self.category_service = category_service
        self.semantic_classifier = SemanticIntentClassifier()
        self._salon_repo = SalonRepository()

        graph = StateGraph(GraphState)
        graph.add_node("detect_intent", self.detect_intent)
        graph.add_node("small_talk", self.small_talk)
        graph.add_node("category_list", self.category_list)
        graph.add_node("category_detail", self.category_detail)
        graph.add_node("bookly_platform_info", self.bookly_platform_info)
        graph.add_node("bookly_ai_info", self.bookly_ai_info)
        graph.add_node("faq_policy", self.faq_policy)
        graph.add_node("service_prepare", self.service_prepare)
        graph.add_node("service_check", self.service_check)
        graph.add_node("location_check", self.location_check)
        graph.add_node("discover", self.discover)
        graph.add_node("booking", self.booking)
        graph.add_node("general", self.general)

        graph.set_entry_point("detect_intent")
        graph.add_conditional_edges(
            "detect_intent",
            self.route_intent,
            {
                "small_talk": "small_talk",
                "category_list": "category_list",
                "category_detail": "category_detail",
                "bookly_platform_info": "bookly_platform_info",
                "bookly_ai_info": "bookly_ai_info",
                "faq_policy": "faq_policy",
                "service_prepare": "service_prepare",
                "booking": "booking",
                "general": "general",
            },
        )
        graph.add_edge("service_prepare", "service_check")
        graph.add_conditional_edges(
            "service_check",
            self.route_service_check,
            {"location_check": "location_check", "end": END},
        )
        graph.add_conditional_edges(
            "location_check",
            self.route_location,
            {"discover": "discover", "end": END},
        )
        graph.add_edge("small_talk", END)
        graph.add_edge("category_list", END)
        graph.add_edge("category_detail", END)
        graph.add_edge("bookly_platform_info", END)
        graph.add_edge("bookly_ai_info", END)
        graph.add_edge("faq_policy", END)
        graph.add_edge("discover", END)
        graph.add_edge("booking", END)
        graph.add_edge("general", END)

        self.app = graph.compile()

    def detect_intent(self, state: GraphState) -> GraphState:
        message = state["user_message"]
        logger.info("USER_QUERY: %s", message)
        history = self.memory.get_history(state["session_id"])
        state["history"] = history

        # Location follow-up after salon discovery prompt — skip LLM (avoids token blow-ups on "Noida", etc.)
        session_memory = self.memory.get_session_memory(state["session_id"])
        if self._awaiting_location(state):
            pending_service = session_memory.selected_service or self.get_last_service_query(state)
            pending_category = session_memory.selected_category
            candidate = message.strip()
            if candidate and len(candidate.split()) <= 5 and (pending_service or pending_category):
                cleaned = sanitize_location(candidate) or candidate
                service = pending_service or pending_category
                state["intent_analysis"] = IntentAnalysis(
                    intent=IntentType.SERVICE_SEARCH,
                    service=service,
                    category=pending_category,
                    location=cleaned,
                    confidence=0.95,
                    reason="User provided location after salon discovery prompt.",
                )
                logger.info(
                    "DETECTED_INTENT: service_search (location follow-up) service=%s location=%s",
                    service,
                    cleaned,
                )
                return state

        # Step 1–2: semantic understanding + normalized intent (before LLM / keyword heuristics)
        semantic = self.semantic_classifier.classify(message)
        if semantic:
            state["intent_analysis"] = IntentAnalysis(
                intent=semantic.intent,
                confidence=semantic.confidence,
                reason=semantic.reason,
            )
            logger.info(
                "DETECTED_INTENT: %s confidence=%s%% reason=%s",
                semantic.intent.value,
                semantic.confidence_pct,
                semantic.reason,
            )
            state["history"] = history
            return state

        # Specific category detail (e.g. "Tell me about Hair") — before LLM can misroute to list/FAQ
        category_detail = self._detect_category_detail(message)
        if category_detail:
            state["intent_analysis"] = IntentAnalysis(
                intent=IntentType.CATEGORY_DETAIL,
                category=category_detail,
                confidence=0.92,
                reason=f"User asked about the {category_detail} service category.",
            )
            logger.info(
                "DETECTED_INTENT: category_detail confidence=92%% reason=User asked about %s",
                category_detail,
            )
            state["history"] = history
            return state

        analysis = self.intent_agent.analyze(
            message=message,
            categories=self.categories,
            history=history,
        )
        state["intent_analysis"] = analysis
        state["history"] = history
        return state

    def route_intent(self, state: GraphState) -> str:
        intent = state["intent_analysis"].intent
        session_id = state["session_id"]
        user_message = state["user_message"]
        session_memory = self.memory.get_session_memory(session_id)

        logger.info("ROUTING: Starting intent-based routing for message: %s", user_message)
        logger.info("DETECTED_INTENT: %s", intent)

        # ---------------------------------------------------------------- #
        # Intent priority (highest first):
        #   1. Booking (active session, confirmation, slot collection)
        #   2. Salon / service search
        #   3. Category list
        #   4. Category detail
        #   5. FAQ / policy (RAG) — with booking resume when interrupted
        #   6. Greeting / small talk
        #   7. General fallback
        # ---------------------------------------------------------------- #

        pending_service = self.get_last_service_query(state) or session_memory.selected_service
        booking_stage = self.memory.get_booking_stage(session_id)
        if (
            (self.is_location_only(user_message) or self._awaiting_location(state))
            and pending_service
            and not session_memory.awaiting_confirmation
        ):
            candidate = user_message.strip()
            if candidate and (self.is_location_only(user_message) or len(candidate.split()) <= 5):
                self._prepare_booking_discovery_route(session_id, user_message, state)
                logger.info("SELECTED_AGENT: discovery_agent (location reply for booking)")
                return "service_prepare"
            if not self.memory.get_booking_stage(session_id):
                state["intent_analysis"] = IntentAnalysis(
                    intent=IntentType.SERVICE_SEARCH,
                    service=pending_service,
                )
                logger.info("SELECTED_AGENT: discovery_agent (location reply for pending service)")
                return "service_prepare"

        if booking_stage == "awaiting_location" and not session_memory.awaiting_confirmation:
            if self._extract_location(user_message) or self.is_location_only(user_message):
                self._prepare_booking_discovery_route(session_id, user_message, state)
                logger.info("SELECTED_AGENT: discovery_agent (awaiting_location reply)")
                return "service_prepare"
            logger.info("SELECTED_AGENT: booking_agent (awaiting location)")
            state["booking_stage"] = "awaiting_location"
            return "booking"

        # --- FAQ interrupt during active booking (must run before booking resume) ---
        awaiting_confirm = (
            session_memory.awaiting_confirmation or booking_stage == "awaiting_confirmation"
        )
        # Yes / No / change requests during confirmation are booking turns, not FAQ interrupts.
        is_confirmation_turn = awaiting_confirm and (
            self._is_booking_confirmation(user_message)
            or self._is_booking_decline(user_message)
            or self._detect_booking_modification(user_message) is not None
        )
        if (
            not is_confirmation_turn
            and (
                intent in {IntentType.FAQ, IntentType.POLICY, IntentType.APPOINTMENT_CANCELLATION}
                or self._is_policy_or_faq_message(user_message)
            )
            and (
                self._has_booking_in_progress(session_id)
                or session_memory.awaiting_confirmation
                or booking_stage == "awaiting_confirmation"
            )
        ):
            state["resume_booking_after_faq"] = True
            self.memory.update_session_memory(session_id, booking_status="paused")
            logger.info("BOOKING_INTERRUPT: FAQ during active booking — will resume after answer")
            logger.info("SELECTED_AGENT: faq_agent (intent: %s)", intent)
            logger.info("RAG_TRIGGERED: True")
            return "faq_policy"

        # --- Salon discovery before booking when schedule is complete but no salon chosen ---
        if self._should_rediscover_for_location_change(session_id, user_message, state):
            self._prepare_booking_discovery_route(session_id, user_message, state)
            logger.info("SELECTED_AGENT: discovery_agent (location change — re-query salons)")
            return "service_prepare"

        if self._should_discover_salons_for_booking(session_id, user_message, state):
            self._prepare_booking_discovery_route(session_id, user_message, state)
            logger.info("SELECTED_AGENT: discovery_agent (salon search before booking confirmation)")
            return "service_prepare"

        # --- Priority 1: Booking ------------------------------------------------
        if booking_stage == "awaiting_salon":
            logger.info("SELECTED_AGENT: booking_agent (awaiting salon selection from cards)")
            state["booking_stage"] = "awaiting_salon"
            return "booking"

        if booking_stage == "awaiting_confirmation" or session_memory.awaiting_confirmation:
            logger.info("SELECTED_AGENT: booking_agent (awaiting customer confirmation)")
            state["booking_stage"] = "awaiting_confirmation"
            return "booking"

        if booking_stage in ["awaiting_date", "awaiting_time"]:
            logger.info("SELECTED_AGENT: booking_agent (post-discovery booking stage)")
            state["booking_stage"] = booking_stage
            return "booking"

        if self.memory.has_active_booking_session(session_id):
            logger.info("SELECTED_AGENT: booking_agent (active booking session)")
            return "booking"

        if self._try_route_booking_with_memory(session_id, user_message, state):
            logger.info("SELECTED_AGENT: booking_agent (session memory / complete booking)")
            return "booking"

        booking_draft = self.memory.get_booking_draft(session_id)
        if any(getattr(booking_draft, field) for field in self.booking_agent.REQUIRED_FIELDS):
            if self.booking_agent.missing_fields(booking_draft):
                booking_started = bool(
                    booking_draft.salon
                    or self.memory.get_booking_stage(session_id)
                    or self.memory.has_active_booking_session(session_id)
                    or self._is_explicit_booking_request(user_message)
                    or self.is_booking_details(user_message)
                )
                if booking_started:
                    logger.info("SELECTED_AGENT: booking_agent (incomplete booking draft)")
                    return "booking"

        if intent == IntentType.APPOINTMENT_BOOKING:
            if self._should_use_booking_agent(user_message, session_id):
                logger.info("SELECTED_AGENT: booking_agent (explicit booking with extracted entities)")
                return "booking"
            logger.info("SELECTED_AGENT: discovery_agent (generic booking request)")
            return "service_prepare"

        # --- Priority 2: Salon / service search ---------------------------------
        if intent in {
            IntentType.SERVICE_SEARCH,
            IntentType.SALON_SEARCH,
            IntentType.LOCATION_SEARCH,
            IntentType.SALON_DISCOVERY,
        }:
            logger.info("SELECTED_AGENT: discovery_agent (intent: %s)", intent)
            return "service_prepare"

        if self._is_salon_search(user_message):
            logger.info("SELECTED_AGENT: discovery_agent (heuristic salon_search)")
            return "service_prepare"

        # --- Priority 3: Category detail (specific category — before list) ---------------
        if intent == IntentType.CATEGORY_DETAIL or self._detect_category_detail(user_message):
            logger.info("SELECTED_AGENT: category_detail")
            return "category_detail"

        # --- Priority 4: Category list ------------------------------------------
        if intent == IntentType.CATEGORY_LIST or self._is_category_list_request(user_message):
            logger.info("SELECTED_AGENT: category_list (Categories API)")
            return "category_list"

        # --- Priority 5: Bookly platform vs AI (deterministic — never RAG) ---
        if intent == IntentType.BOOKLY_PLATFORM_INFORMATION or self._is_bookly_platform_question(user_message):
            logger.info("SELECTED_AGENT: bookly_platform_info")
            logger.info("RAG_TRIGGERED: False")
            return "bookly_platform_info"

        if intent == IntentType.BOOKLY_AI_INFORMATION or self._is_bookly_ai_question(user_message):
            logger.info("SELECTED_AGENT: bookly_ai_info")
            logger.info("RAG_TRIGGERED: False")
            return "bookly_ai_info"

        # --- Priority 5: Greeting / small talk (never RAG) ------------------------
        if self._small_talk_reply(user_message) is not None:
            logger.info("SELECTED_AGENT: small_talk")
            return "small_talk"

        # --- Priority 6: FAQ / policy (RAG) -------------------------------------
        if intent in {IntentType.FAQ, IntentType.POLICY, IntentType.APPOINTMENT_CANCELLATION} or self._is_policy_or_faq_message(user_message):
            logger.info("SELECTED_AGENT: faq_agent (intent: %s)", intent)
            logger.info("RAG_TRIGGERED: True")
            return "faq_policy"

        # --- Priority 7: Fallback -----------------------------------------------
        logger.info("SELECTED_AGENT: general_agent (general conversation)")
        logger.info("RAG_TRIGGERED: False")
        return "general"

    # ------------------------------------------------------------------ #
    # Bookly platform vs AI assistant — separate intents, never mixed
    # ------------------------------------------------------------------ #
    _BOOKLY_PLATFORM_REPLY = (
        "Bookly is a salon and wellness appointment booking platform that helps customers "
        "discover nearby salons, explore beauty and wellness services, compare service providers, "
        "and book appointments online. It also enables users to manage bookings, payments, "
        "cancellations, reviews, and recommendations through a seamless digital experience."
    )
    _BOOKLY_AI_REPLY = (
        "I am Bookly's AI Assistant.\n\n"
        "I can help you discover salons, explore services, book appointments, and answer "
        "questions about Bookly's policies and features.\n\n"
        "How may I assist you today?"
    )

    @staticmethod
    def _mentions_bookly_ai(text: str) -> bool:
        """True when the user is asking about the assistant/chatbot, not the platform."""
        ai_markers = (
            "assistant",
            "chatbot",
            "chat bot",
            " are you ",
            "who are you",
            "what are you",
            "what can you",
            "how can you help",
            "how can you assist",
            "what is this bot",
            "what is this chatbot",
            "who is this",
            "what is your name",
        )
        padded = f" {text} "
        if any(m in text for m in ai_markers):
            return True
        if " ai " in padded or text.endswith(" ai") or text.startswith("ai "):
            return True
        if "bookly ai" in text or "bookly assistant" in text:
            return True
        return False

    def _is_bookly_ai_question(self, message: str) -> bool:
        """Detect questions about this chatbot / AI assistant."""
        return self.semantic_classifier.is_ai_question(message)

    def _is_bookly_platform_question(self, message: str) -> bool:
        """Detect questions about the Bookly platform (not the AI assistant)."""
        if self._is_bookly_ai_question(message):
            return False
        return self.semantic_classifier.is_platform_question(message)

    def bookly_platform_info(self, state: GraphState) -> GraphState:
        state["reply"] = self._BOOKLY_PLATFORM_REPLY
        state["intent_analysis"] = IntentAnalysis(intent=IntentType.BOOKLY_PLATFORM_INFORMATION)
        logger.info("BOOKLY_PLATFORM_INFO: %s", state["user_message"])
        return state

    def bookly_ai_info(self, state: GraphState) -> GraphState:
        state["reply"] = self._BOOKLY_AI_REPLY
        state["intent_analysis"] = IntentAnalysis(intent=IntentType.BOOKLY_AI_INFORMATION)
        logger.info("BOOKLY_AI_INFO: %s", state["user_message"])
        return state

    # ------------------------------------------------------------------ #
    # Small Talk layer (Issue #1) — deterministic, no LLM / RAG / booking
    # ------------------------------------------------------------------ #
    _SMALL_TALK_GREETING = (
        "Hello!\n\n"
        "Welcome to Bookly.\n\n"
        "I'm here to help you discover salons, answer your questions, and book appointments.\n\n"
        "How may I assist you today?"
    )
    _SMALL_TALK_GREETING_WITH_WELLBEING = (
        "Hello!\n\n"
        "Welcome to Bookly.\n\n"
        "I'm doing well, thank you for asking.\n\n"
        "I'm here to help you discover salons, answer your questions, and book appointments.\n\n"
        "How may I assist you today?"
    )
    _SMALL_TALK_HOW_ARE_YOU = _SMALL_TALK_GREETING_WITH_WELLBEING
    _SMALL_TALK_THANKS = (
        "You're most welcome.\n\n"
        "Please let me know if there is anything else I can help you with."
    )
    _SMALL_TALK_GOODBYE = (
        "Thank you for visiting Bookly.\n\n"
        "Have a wonderful day, and feel free to return whenever you need assistance."
    )
    _SMALL_TALK_NICE_TO_MEET = (
        "It is a pleasure to meet you.\n\n"
        "Welcome to Bookly. I am here to help you discover salons, book appointments, "
        "and answer any questions you may have.\n\n"
        "How may I assist you today?"
    )

    @staticmethod
    def _normalize_small_talk(message: str) -> str:
        text = re.sub(r"[^\w\s]", " ", message.lower())
        return re.sub(r"\s+", " ", text).strip()

    def _small_talk_reply(self, message: str) -> str | None:
        """Return a professional small-talk reply, or None if not small talk.

        Matching is strict: any message carrying real domain intent (a service,
        booking, salon/category/location keyword) is NOT treated as small talk.
        """
        text = self._normalize_small_talk(message)
        if not text:
            return None
        words = text.split()

        # Exclude messages that carry real intent so we never hijack a flow.
        domain_kw = {
            "book", "booking", "appointment", "reserve", "schedule", "cancel",
            "cancellation", "salon", "salons", "vendor", "vendors", "policy",
            "refund", "price", "cost", "near", "location", "faq", "category",
            "categories",
        }
        if self._has_service_keyword(message) or any(w in domain_kw for w in words):
            return None

        # Thanks
        if text in {"thanks", "thank you", "thank u", "thankyou", "thx", "ty",
                    "many thanks", "much appreciated", "appreciate it",
                    "thanks a lot", "thank you so much"} or text.startswith("thank "):
            return self._SMALL_TALK_THANKS

        # How are you / how's your day
        if (text in {"how are you", "how are you doing", "how r u", "how are u",
                     "hows it going", "how is it going", "how do you do",
                     "how are things", "how you doing", "hows your day",
                     "how is your day", "how's your day"}
                or text.startswith("how are you")
                or text.startswith("how r u")
                or "hows your day" in text
                or "how is your day" in text):
            return self._SMALL_TALK_HOW_ARE_YOU

        # Goodbye / good night
        if text in {"bye", "goodbye", "good bye", "see you", "see ya", "take care",
                    "good night", "goodnight", "gn", "bye bye"} or text.startswith("goodbye"):
            return self._SMALL_TALK_GOODBYE

        # Nice to meet you
        if "nice to meet you" in text or "pleasure to meet you" in text:
            return self._SMALL_TALK_NICE_TO_MEET

        # Greetings
        greetings = ("hi", "hello", "hey", "greetings", "good morning",
                     "good afternoon", "good evening", "good day")
        if text in set(greetings) | {"hey there", "hi there", "hello there",
                                     "gm", "ge", "yo", "hiya"}:
            return self._SMALL_TALK_GREETING
        if len(words) <= 5 and any(
            text == g or text.startswith(g + " ") for g in greetings
        ):
            return self._SMALL_TALK_GREETING
        if words and words[0] in {"hi", "hello", "hey", "greetings"} and len(words) <= 3:
            return self._SMALL_TALK_GREETING

        return None

    # ------------------------------------------------------------------ #
    # Category-list layer (Issue #2) — answered straight from Categories API
    # ------------------------------------------------------------------ #
    def _is_category_list_request(self, message: str) -> bool:
        if self.semantic_classifier.is_category_list(message):
            return True
        text = self._normalize_small_talk(message)
        if not text:
            return False
        words = text.split()
        # Any standalone mention of "category"/"categories" -> list categories.
        # Covers bare "category", "categories", and every listed variation.
        if "category" in words or "categories" in words:
            return True
        direct = (
            "list categories", "show categories", "available categories",
            "category list", "categories list", "service categories",
            "list of categories", "show me categories", "show all categories",
            "list all categories", "what categories", "which categories",
            "all categories", "give me category list", "available service categories",
            "what services do you provide", "what categories are available",
        )
        if any(p in text for p in direct):
            return True
        # "what services do you offer" family — only when no concrete service named.
        if ("service" in text or "services" in text) and any(
            k in text for k in ("offer", "provide", "available", "have",
                                "list", "what", "which", "show")
        ):
            if not self._has_service_keyword(message):
                return True
        return False

    def small_talk(self, state: GraphState) -> GraphState:
        reply = self._small_talk_reply(state["user_message"]) or self._SMALL_TALK_GREETING
        state["reply"] = reply
        state["intent_analysis"] = IntentAnalysis(intent=IntentType.SMALL_TALK)
        logger.info("SMALL_TALK_HANDLED: %s", state["user_message"])
        return state

    def category_list(self, state: GraphState) -> GraphState:
        names: list[str] = []
        if self.category_service is not None:
            try:
                # Always refresh from the Categories API for chatbot listings.
                names = [c.name for c in self.category_service.get_categories(force_refresh=True)]
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("CATEGORY_LIST: Categories API fetch failed: %s", exc)
                names = []

        if not names:
            state["reply"] = (
                "I am unable to retrieve the category list at the moment.\n\n"
                "Please try again shortly."
            )
            state["intent_analysis"] = IntentAnalysis(intent=IntentType.CATEGORY_LIST)
            logger.warning("CATEGORY_LIST_RETURNED: no active admin categories available")
            return state

        body = "\n".join(f"• {name}" for name in names)
        state["reply"] = (
            f"Available Categories:\n\n{body}\n\n"
            "How can I assist you with one of these services?"
        )
        state["intent_analysis"] = IntentAnalysis(intent=IntentType.CATEGORY_LIST)
        logger.info("CATEGORY_LIST_RETURNED: %s categories -> %s", len(names), names)
        return state

    def _get_active_category_names(self) -> list[str]:
        if self.category_service is not None:
            try:
                return [c.name for c in self.category_service.get_categories(force_refresh=False)]
            except Exception:
                pass
        return list(self.categories)

    def _detect_category_detail(self, message: str) -> str | None:
        """Return matched category name when user asks about a specific category."""
        text = self._normalize_small_talk(message)
        if not text:
            return None
        if self._is_category_list_request(message):
            return None

        category_names = self._get_active_category_names()
        lower_names = {n.lower(): n for n in category_names}

        patterns = (
            r"tell me about\s+(?P<cat>.+)",
            r"tell me more about\s+(?P<cat>.+)",
            r"explain\s+(?P<cat>.+)",
            r"what is\s+(?P<cat>.+?)(?:\?|$)",
            r"what are\s+(?P<cat>.+?)(?:\?|$)",
            r"describe\s+(?P<cat>.+)",
            r"info(?:rmation)?\s+(?:on|about)\s+(?P<cat>.+)",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            candidate = match.group("cat").strip(" .?!")
            if candidate in lower_names:
                return lower_names[candidate]
            for key, canonical in lower_names.items():
                if candidate == key or candidate.startswith(key) or key in candidate:
                    return canonical

        # Bare category name when message is short (e.g. user says "Hair" after list)
        if len(text.split()) <= 2 and text in lower_names:
            return lower_names[text]
        return None

    def category_detail(self, state: GraphState) -> GraphState:
        category = self._detect_category_detail(state["user_message"]) or ""
        session_id = state["session_id"]
        self.memory.update_session_memory(
            session_id,
            selected_category=category,
            last_intent="category_detail",
        )
        state["reply"] = (
            f"Certainly!\n\n"
            f"{category} is one of our available service categories.\n\n"
            f"It includes various {category.lower()}-related beauty and grooming services "
            f"offered by our partner salons.\n\n"
            f"Would you like me to recommend nearby salons that provide {category} services?"
        )
        state["intent_analysis"] = IntentAnalysis(
            intent=IntentType.CATEGORY_DETAIL,
            category=category,
        )
        logger.info("CATEGORY_DETAIL: %s", category)
        return state

    def _has_booking_in_progress(self, session_id: str) -> bool:
        """True when an in-progress booking should resume after an FAQ interrupt."""
        mem = self.memory.get_session_memory(session_id)
        stage = self.memory.get_booking_stage(session_id)
        if mem.awaiting_confirmation or stage in {"awaiting_date", "awaiting_time", "awaiting_confirmation"}:
            return True
        if self.memory.has_active_booking_session(session_id):
            return True
        draft = self.memory.get_booking_draft(session_id)
        return any(getattr(draft, f) for f in self.booking_agent.REQUIRED_FIELDS)

    def _booking_resume_prompt(self, session_id: str) -> str:
        """Next booking prompt after an FAQ interrupt."""
        mem = self.memory.get_session_memory(session_id)
        draft = self.memory.get_booking_draft(session_id)
        if mem.awaiting_confirmation or self.memory.get_booking_stage(session_id) == "awaiting_confirmation":
            return (
                "Please confirm your booking when you are ready, or let me know if you "
                "would like to change any detail."
            )
        _, missing = self.booking_agent.booking_data_completeness_check(draft)
        if not missing:
            return "Please confirm your booking when you are ready."
        field = missing[0]
        prompts = {
            "date": "Could you please share your preferred appointment date?",
            "time": "Could you please share your preferred appointment time?",
            "salon": "Could you please select your preferred salon?",
            "service": "Could you please let me know which service you would like to book?",
        }
        return prompts.get(field, "Could you please share the next booking detail?")

    def _should_resume_booking_after_faq(self, session_id: str) -> bool:
        """Detect FAQ interrupt during booking — uses session memory (LangGraph edge routing does not persist state flags)."""
        mem = self.memory.get_session_memory(session_id)
        stage = self.memory.get_booking_stage(session_id)
        if mem.booking_status == "paused":
            return True
        if mem.awaiting_confirmation or stage in {"awaiting_date", "awaiting_time", "awaiting_confirmation"}:
            return True
        return self.memory.has_active_booking_session(session_id)

    def faq_policy(self, state: GraphState) -> GraphState:
        logger.info("EXECUTING_AGENT: faq_agent")
        logger.info("RAG_PIPELINE: Retrieving from knowledge base")
        answer = self.faq_agent.answer(state["user_message"])
        logger.info("ANSWER: %s", answer)
        session_id = state["session_id"]
        # Resume booking when FAQ was asked mid-flow (memory flag survives graph routing).
        if state.get("resume_booking_after_faq") or self._should_resume_booking_after_faq(session_id):
            resume = self._booking_resume_prompt(session_id)
            state["reply"] = f"Sure.\n\n{answer}\n\nNow let's continue your booking.\n\n{resume}"
            mem = self.memory.get_session_memory(session_id)
            status = "awaiting_confirmation" if mem.awaiting_confirmation else "collecting"
            self.memory.update_session_memory(session_id, booking_status=status)
            logger.info("BOOKING_RESUMED: after FAQ interrupt")
        else:
            state["reply"] = answer
        analysis = state.get("intent_analysis")
        if analysis:
            state["intent_analysis"] = analysis
        else:
            state["intent_analysis"] = IntentAnalysis(intent=IntentType.FAQ)
        return state

    def service_prepare(self, state: GraphState) -> GraphState:
        analysis = state["intent_analysis"]
        message = state["user_message"]
        session_id = state["session_id"]
        session_memory = self.memory.get_session_memory(session_id)

        # ---------------------------------------------------------------- #
        # Step 1: Decide salon-search vs service-search (intent first).
        # ---------------------------------------------------------------- #
        salon_search = analysis.intent in {
            IntentType.SALON_SEARCH,
            IntentType.LOCATION_SEARCH,
        } or self._is_salon_search(message)
        state["salon_search"] = salon_search

        # ---------------------------------------------------------------- #
        # Step 2: Extract LOCATION independently (LLM hint -> message -> history).
        # When the bot just asked for a location, trust the plain user reply.
        # ---------------------------------------------------------------- #
        location = None
        if self._awaiting_location(state):
            candidate = message.strip()
            if candidate and len(candidate.split()) <= 5 and not self.is_generic_booking_request(candidate):
                location = candidate

        if not location:
            location = analysis.location or self._extract_location(message)
        if not location and self.is_location_only(message):
            location = self._extract_location_from_message(message) or message.strip()
        if not location:
            for msg in reversed(state.get("history", [])):
                if msg["role"] == "user":
                    found = self._extract_location(msg["content"])
                    if found:
                        location = found
                        break
        # Free-form location: when we just asked for a location, accept the reply.
        if not location and self._awaiting_location(state):
            candidate = message.strip()
            if candidate and len(candidate.split()) <= 5 and not self.is_generic_booking_request(candidate):
                location = candidate

        # ---------------------------------------------------------------- #
        # Step 3: Extract SERVICE + CATEGORY independently.
        #   - Salon search: NEVER set service or category.
        #   - Service search: detect service, map category ONLY if a service exists.
        #     Never default a category.
        # ---------------------------------------------------------------- #
        if salon_search:
            state["service"] = None
            state["category"] = None
            logger.info("INTENT_RESOLVED: SALON_SEARCH (no service/category mapping)")
        else:
            service = self._detect_service(message) or analysis.service
            if service:
                service = self._strip_location_clause(service).strip() or service
            # Carry forward a pending service when the user only sent a location.
            if (not service or self.is_location_only(message)) and self.get_last_service_query(state):
                service = self.get_last_service_query(state)
            if not service and session_memory.selected_service:
                service = session_memory.selected_service

            category = analysis.category
            if not category and service:
                category = self.category_agent.map_category(service, self.categories)
            if not category and session_memory.selected_category:
                category = session_memory.selected_category

            state["service"] = service
            state["category"] = category  # may be None — never forced
            logger.info("SERVICE_DETECTED: %s", service)
            logger.info(
                "CATEGORY_MAPPED: %s (source: %s)",
                category,
                "LLM" if analysis.category else ("keyword" if category else "none"),
            )

        if not location and session_memory.preferred_location:
            location = session_memory.preferred_location

        if location:
            cleaned = sanitize_location(location) or location.strip()
            state["location"] = cleaned
        logger.info("LOCATION_DETECTED: raw=%s normalized=%s", message, state.get("location"))

        memory_updates: dict[str, str | None] = {"last_intent": analysis.intent.value}
        if state.get("service"):
            memory_updates["selected_service"] = state["service"]
        if state.get("category"):
            memory_updates["selected_category"] = state["category"]
        if state.get("location"):
            memory_updates["preferred_location"] = state["location"]
        self.memory.update_session_memory(session_id, **memory_updates)
        return state

    def _awaiting_location(self, state: GraphState) -> bool:
        """True when the most recent assistant turn asked for the preferred location."""
        for msg in reversed(state.get("history", [])):
            if msg["role"] == "assistant":
                lower = msg["content"].lower()
                return (
                    "preferred location" in lower
                    or "recommend nearby salons" in lower
                    or "available salons nearby" in lower
                    or "show you the available salons" in lower
                )
        return False

    def _extract_location_from_message(self, message: str) -> str | None:
        candidate_locations = [
            "dubai marina",
            "jumeirah",
            "abu dhabi",
            "sharjah",
            "ajman",
            "ras al khaimah",
            "al ain",
            "marina",
        ]
        lower = message.lower()
        for candidate in candidate_locations:
            if candidate in lower:
                return title_case_safe(candidate)
        return None

    # Specific service/treatment keywords. Used to decide whether a message
    # names a concrete service (SERVICE_SEARCH) vs. just asks for a salon list.
    _SERVICE_KEYWORDS = (
        "hair", "haircut", "smoothing", "smoothening", "keratin", "coloring", "colouring",
        "color", "colour", "makeup", "make up", "facial", "face", "wax", "waxing", "pedicure",
        "manicure", "nail", "nails", "henna", "spa", "massage", "bridal", "threading",
        "beard", "shave", "grooming", "treatment",
    )
    _SALON_TARGET_WORDS = ("salon", "salons", "vendor", "vendors", "parlour", "parlor", "shop", "shops")
    _LOCATION_STOPWORDS = {
        "who", "that", "which", "please", "and", "the", "a", "an", "can", "could",
        "provide", "providing", "service", "services", "me", "for", "by", "with",
        "available", "near", "around", "is", "are", "to", "on", "at",
        "tomorrow", "today", "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday", "am", "pm",
    }

    def _has_service_keyword(self, message: str) -> bool:
        text = message.lower()
        return any(k in text for k in self._SERVICE_KEYWORDS)

    def _is_salon_search(self, message: str) -> bool:
        """True when the user asks for a list of salons/vendors without a service."""
        text = message.lower()
        targets_salon = any(w in text for w in self._SALON_TARGET_WORDS)
        return targets_salon and not self._has_service_keyword(message)

    def _strip_location_clause(self, message: str) -> str:
        """Remove a trailing 'in/at/near <location>' clause from a phrase."""
        return re.sub(
            r"\b(?:in|at|near|around|within|located in)\s+.+$",
            "",
            message,
            flags=re.IGNORECASE,
        ).strip()

    def _extract_location(self, message: str) -> str | None:
        """Extract a location from the message, independently of service/category.

        Order: known UAE areas first, then a free-form 'in/at/near <place>' clause
        so arbitrary cities present in MongoDB (Noida, Delhi, ...) are supported.
        """
        known = self._extract_location_from_message(message)
        if known:
            return known

        # "at Glow Salon, Noida on ..." — city follows salon name after comma.
        salon_city = re.search(
            r"\b(?:at|in)\s+[^,]{2,80},\s*([A-Za-z][A-Za-z\s]{1,40}?)"
            r"(?:\s+(?:on|at|tomorrow|today)\b|\s+\d{1,2}|\s*$)",
            message,
            flags=re.IGNORECASE,
        )
        if salon_city:
            candidate = sanitize_location(salon_city.group(1).strip())
            if candidate:
                return title_case_safe(candidate)

        match = re.search(
            r"\b(?:in|at|near|around|within|located in)\s+(.+)",
            message,
            flags=re.IGNORECASE,
        )
        if not match:
            return None

        clause = match.group(1).split(",")[0]
        clause = re.split(r"\bon\s*\d{1,2}/", clause, maxsplit=1, flags=re.IGNORECASE)[0]
        clause = re.split(r"\b\d{1,2}/\d{1,2}/\d{4}\b", clause, maxsplit=1)[0]
        clause = re.split(
            r"\s+on\s+(?:tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            clause,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        clause = re.split(r"\s+at\s+", clause, maxsplit=1, flags=re.IGNORECASE)[0]
        clause = re.split(r"\s+(?:tomorrow|today)\b", clause, maxsplit=1, flags=re.IGNORECASE)[0]

        words = re.findall(r"[A-Za-z]+", clause)
        loc_words: list[str] = []
        for word in words:
            if word.lower() in self._LOCATION_STOPWORDS:
                break
            loc_words.append(word)
            if len(loc_words) >= 3:
                break
        if not loc_words:
            return None
        candidate = title_case_safe(" ".join(loc_words))
        if self._salon_repo.find_vendor_by_name(candidate):
            return None
        return candidate

    def _extract_salon_from_message_clause(self, message: str) -> str | None:
        """Extract salon from 'at {Salon}, {City}' or trailing 'at {Salon}'."""
        match = re.search(
            r"\bat\s+([^,]{2,80}),\s*[A-Za-z]",
            message,
            flags=re.IGNORECASE,
        )
        if match:
            name = match.group(1).strip(" .,-")
            if name and not is_generic_salon_phrase(name):
                return title_case_safe(name)
        match = re.search(
            r"\bat\s+((?:[A-Za-z0-9][A-Za-z0-9\s&'.-]{1,80}?Salon))\s*(?:$|on\s|,\s)",
            message,
            flags=re.IGNORECASE,
        )
        if match:
            name = match.group(1).strip(" .,-")
            if name and not is_generic_salon_phrase(name):
                return title_case_safe(name)
        return None

    def _resolve_booking_entities(
        self,
        session_id: str,
        message: str,
    ) -> tuple[BookingPayload, str | None]:
        """Merge extracted booking fields with session memory."""
        lookup = self.memory.get_salon_lookup(session_id)
        draft = self.memory.get_booking_draft(session_id)
        preview = self.booking_agent.extract_booking_fields(message, draft, lookup)
        session_memory = self.memory.get_session_memory(session_id)

        location = self._extract_location(message) or session_memory.preferred_location
        if location:
            location = sanitize_location(location) or location

        return preview, location

    def _booking_schedule_complete(self, payload: BookingPayload) -> bool:
        return bool(
            payload.date
            and payload.time
            and payload.date.strip()
            and payload.time.strip()
        )

    def _booking_schedule_ready(
        self,
        session_id: str,
        message: str,
        payload: BookingPayload,
    ) -> bool:
        """True when date+time are known or the message carries a full schedule hint."""
        if self._booking_schedule_complete(payload):
            return True
        if not payload.time or not str(payload.time).strip():
            return False
        return self._message_has_schedule(message)

    def _salon_is_user_selected(self, session_id: str, payload: BookingPayload) -> bool:
        if not payload.salon or not str(payload.salon).strip():
            return False
        lookup = self.memory.get_salon_lookup(session_id)
        if not lookup:
            return False
        salon_key = payload.salon.strip().lower()
        if salon_key in lookup:
            return True
        return any(salon_key in name or name in salon_key for name in lookup)

    def _has_service_and_location(
        self,
        session_id: str,
        message: str,
        payload: BookingPayload | None = None,
    ) -> bool:
        preview, location = (
            (payload, self._extract_location(message) or self.memory.get_session_memory(session_id).preferred_location)
            if payload is not None
            else self._resolve_booking_entities(session_id, message)
        )
        if not location:
            location = self.memory.get_session_memory(session_id).preferred_location
        service = preview.service or self.memory.get_session_memory(session_id).selected_service
        return bool(service and location)

    def _should_discover_salons_for_booking(
        self,
        session_id: str,
        message: str,
        state: GraphState,
    ) -> bool:
        """Route to MongoDB salon search when booking details exist but no salon was chosen."""
        session_memory = self.memory.get_session_memory(session_id)
        if session_memory.awaiting_confirmation:
            return False

        booking_stage = self.memory.get_booking_stage(session_id)
        if booking_stage == "awaiting_confirmation":
            return False

        preview, location = self._resolve_booking_entities(session_id, message)
        if self._salon_is_user_selected(session_id, preview):
            return False

        if not self._has_service_and_location(session_id, message, preview):
            return False

        entity_state = self._compute_booking_entity_state(session_id, message)
        if entity_state.action == "confirm":
            return False
        if entity_state.salon_verified:
            return False

        intent = state.get("intent_analysis")
        explicit_booking = self._is_explicit_booking_request(message)
        booking_intent = bool(intent and intent.intent == IntentType.APPOINTMENT_BOOKING)
        return explicit_booking or booking_intent or self.is_booking_details(message)

    def _should_rediscover_for_location_change(
        self,
        session_id: str,
        message: str,
        state: GraphState,
    ) -> bool:
        """Re-run salon discovery when the customer changes location after seeing cards."""
        session_memory = self.memory.get_session_memory(session_id)
        if session_memory.awaiting_confirmation:
            return False

        lookup = self.memory.get_salon_lookup(session_id)
        booking_stage = self.memory.get_booking_stage(session_id)
        if not lookup and booking_stage != "awaiting_salon":
            return False

        new_location = self._extract_location(message)
        if not new_location and self.is_location_only(message):
            new_location = sanitize_location(message.strip()) or message.strip()

        if not new_location:
            return False

        current = session_memory.preferred_location
        if current and new_location.lower() == current.lower():
            return False

        preview, _ = self._resolve_booking_entities(session_id, message)
        service = preview.service or session_memory.selected_service
        return bool(service)

    def _prepare_booking_discovery_route(
        self,
        session_id: str,
        message: str,
        state: GraphState,
    ) -> None:
        """Persist booking slots and aim discovery at MongoDB before confirmation."""
        preview, location = self._resolve_booking_entities(session_id, message)
        session_memory = self.memory.get_session_memory(session_id)
        service = preview.service or session_memory.selected_service
        category = preview.category or session_memory.selected_category
        if service and location:
            stripped = self._strip_location_clause(service).strip()
            if stripped:
                service = stripped
                preview.service = service
        if service and not category:
            category = self.category_agent.map_category(service, self.categories)

        # Keep schedule slots; never auto-assign salon before card selection.
        preview.salon = None
        preview.salon_id = None
        self.memory.set_booking_draft(session_id, preview)
        self.memory.end_booking_session(session_id)
        self.memory.update_session_memory(
            session_id,
            selected_service=service,
            selected_category=category,
            preferred_location=location,
            appointment_date=preview.date,
            appointment_time=preview.time,
            selected_salon=None,
            salon_id=None,
            awaiting_confirmation=False,
            booking_summary_shown=False,
            booking_status="discovering",
        )
        self.memory.set_booking_stage(session_id, "awaiting_salon")

        state["intent_analysis"] = IntentAnalysis(
            intent=IntentType.SERVICE_SEARCH,
            service=service,
            category=category,
            location=location,
            confidence=0.95,
            reason="Salon discovery required before booking confirmation.",
        )

    def _resolve_named_salon(
        self,
        salon_name: str,
        location_hint: str | None = None,
    ) -> tuple[str, str, str | None] | None:
        """Verify salon in MongoDB; return (name, vendor_id, city_from_address)."""
        if is_generic_salon_phrase(salon_name):
            return None
        vendor = self._salon_repo.find_vendor_by_name(salon_name, location_hint)
        if not vendor:
            return None
        name = title_case_safe(str(vendor.get("businessName") or salon_name))
        vendor_id = str(vendor.get("_id"))
        city = self._salon_repo._clean_city(str(vendor.get("businessAddress") or ""))
        return name, vendor_id, city

    def _compute_booking_entity_state(
        self,
        session_id: str,
        message: str,
    ) -> BookingEntityState:
        """Merge extracted entities, validate, and compute priority-ordered missing slots."""
        preview, location = self._resolve_booking_entities(session_id, message)
        session_memory = self.memory.get_session_memory(session_id)

        service = preview.service or session_memory.selected_service
        category = preview.category or session_memory.selected_category
        if service and location:
            stripped = self._strip_location_clause(service).strip()
            if stripped:
                service = stripped

        location = location or session_memory.preferred_location
        date = preview.date or session_memory.appointment_date
        time = preview.time or session_memory.appointment_time

        salon = preview.salon
        salon_id = preview.salon_id
        if not salon:
            salon = self._extract_salon_from_message_clause(message)
        if salon and is_generic_salon_phrase(salon):
            salon = None
            salon_id = None

        salon_verified = self._salon_is_user_selected(session_id, preview)
        if not salon_verified and salon:
            resolved = self._resolve_named_salon(salon, location)
            if resolved:
                salon, salon_id, inferred_city = resolved
                salon_verified = True
                if not location and inferred_city:
                    location = inferred_city

        service_valid = bool(
            service
            and self.booking_agent._is_plausible_service(service)
        )
        date_valid = bool(date and self.booking_agent._is_valid_date(date))
        time_valid = bool(time and self.booking_agent._is_valid_time(time))

        missing = compute_missing_slots(
            service=service if service_valid else None,
            location=location,
            salon_verified=salon_verified,
            date=date if date_valid else None,
            time=time if time_valid else None,
            service_valid=service_valid,
            date_valid=date_valid,
            time_valid=time_valid,
        )
        action, next_slot = decide_booking_action(missing)

        return BookingEntityState(
            service=service if service_valid else service,
            category=category,
            location=location,
            salon=salon if salon_verified else None,
            salon_id=salon_id if salon_verified else None,
            date=date if date_valid else date,
            time=time if time_valid else time,
            salon_verified=salon_verified,
            missing=missing,
            action=action,
            next_slot=next_slot,
        )

    def _sync_entity_state_to_draft(
        self,
        session_id: str,
        entity: BookingEntityState,
    ) -> BookingPayload:
        draft = entity.to_payload()
        if entity.category:
            draft.category = entity.category
        self.memory.set_booking_draft(session_id, draft)
        memory_updates: dict[str, str | None] = {
            "appointment_date": draft.date,
            "appointment_time": draft.time,
        }
        if draft.service:
            memory_updates["selected_service"] = draft.service
        if entity.category:
            memory_updates["selected_category"] = entity.category
        if entity.location:
            memory_updates["preferred_location"] = entity.location
        if entity.salon_verified and draft.salon:
            memory_updates["selected_salon"] = draft.salon
            memory_updates["salon_id"] = draft.salon_id
        self.memory.update_session_memory(session_id, **memory_updates)
        return draft

    def _detect_service(self, message: str) -> str | None:
        """Return a cleaned canonical service phrase, or None when no service is named."""
        if not self._has_service_keyword(message):
            return None
        return self.booking_agent.extract_service_from_message(message)

    def _should_use_booking_agent(self, message: str, session_id: str) -> bool:
        """Route explicit booking phrases to the booking agent when entities are extractable."""
        entity = self._compute_booking_entity_state(session_id, message)
        if entity.action == "discover":
            return False
        if entity.action == "confirm":
            return True
        if entity.action == "ask":
            return bool(
                self._is_explicit_booking_request(message)
                or self.is_booking_details(message)
                or entity.service
            )
        lookup = self.memory.get_salon_lookup(session_id)
        preview = self.booking_agent.extract_booking_fields(message, BookingPayload(), lookup)
        if not self._is_explicit_booking_request(message):
            return False
        return bool(preview.service or preview.salon or preview.date or preview.time)

    def _format_booking_progress_reply(self, draft: BookingPayload, missing: str) -> str:
        """Natural conversational prompts while collecting booking slots (no category lectures)."""
        service = draft.service or "appointment"
        salon = draft.salon

        if missing == "service":
            return (
                "Certainly!\n\n"
                "Could you please let me know which service you would like to book?"
            )
        if missing == "location":
            return (
                f"I'd be happy to help you book a {service}.\n\n"
                f"May I know your preferred location so I can show you the available salons nearby?"
            )
        if missing == "salon" and draft.service:
            return (
                f"Certainly!\n\n"
                f"I'd be happy to help you book a {draft.service} appointment.\n\n"
                f"Please select your preferred salon from the list above to continue."
            )
        if missing == "date" and salon:
            return (
                f"Certainly!\n\n"
                f"I'd be happy to help you book a {service} appointment at {salon}.\n\n"
                f"May I know your preferred appointment date?"
            )
        if missing == "date":
            return (
                f"Certainly!\n\n"
                f"I'd be happy to help you book a {service} appointment.\n\n"
                f"May I know your preferred appointment date?"
            )
        if missing == "time" and salon:
            return (
                f"Great choice.\n\n"
                f"May I know your preferred appointment time for {service} at {salon}?"
            )
        if missing == "time":
            return (
                f"Absolutely.\n\n"
                f"May I know your preferred appointment time?"
            )
        return "Let me help you with that. Could you share the next booking detail?"

    def _next_booking_slot_to_collect(
        self,
        session_id: str,
        message: str,
    ) -> tuple[str, BookingEntityState]:
        """Return (next_slot, entity_state) using priority orchestration."""
        entity = self._compute_booking_entity_state(session_id, message)
        if entity.action == "discover":
            return "discover", entity
        if entity.action == "confirm":
            return "confirm", entity
        return entity.next_slot or "service", entity

    def _route_booking_collection(
        self,
        state: GraphState,
        session_id: str,
        entity: BookingEntityState,
    ) -> GraphState | None:
        """Handle ask/discover/confirm actions from entity state. Returns state or None."""
        if entity.action == "discover":
            self._prepare_booking_discovery_route(session_id, state["user_message"], state)
            prepared = self.service_prepare(state)
            if prepared.get("location_analysis"):
                return self.discover(prepared)
            prepared.setdefault(
                "reply",
                "May I know your preferred location so I can recommend nearby salons?",
            )
            return prepared

        draft = self._sync_entity_state_to_draft(session_id, entity)

        if entity.action == "confirm":
            logger.info("BOOKING_DETAILS_EXTRACTED: all fields present — showing confirmation summary")
            return self._present_booking_summary(state, session_id, draft)

        slot = entity.next_slot or "service"
        self.memory.start_booking_session(session_id)
        if slot in {"date", "time", "location"}:
            self.memory.set_booking_stage(session_id, f"awaiting_{slot}")
            state["booking_stage"] = f"awaiting_{slot}"
        state["reply"] = self._format_booking_progress_reply(draft, slot)
        state["booking_payload"] = draft
        return state

    def service_check(self, state: GraphState) -> GraphState:
        # Salon-search bypasses service identification entirely.
        if state.get("salon_search"):
            return state
        service = state.get("service")
        if not service:
            service = self.memory.get_session_memory(state["session_id"]).selected_service
            if service:
                state["service"] = service
        if not service or self.is_generic_booking_request(service):
            state["reply"] = (
                "Thank you for reaching out.\n\n"
                "To assist you, could you please let me know which service you are looking for?\n\n"
                "You may explore the following categories:\n\n"
                "• Hair Services\n"
                "• Nail Services\n"
                "• Makeup Services\n"
                "• Facial & Skincare\n"
                "• Grooming Services\n\n"
                "Please let me know which service you would like to book."
            )
            return state
        return state

    def route_service_check(self, state: GraphState) -> str:
        # Salon-search only needs a location; skip the service requirement.
        if state.get("salon_search"):
            return "location_check"
        service = state.get("service")
        if not service or self.is_generic_booking_request(service):
            return "end"
        return "location_check"

    def location_check(self, state: GraphState) -> GraphState:
        location = state.get("location")
        if not location:
            location = self.memory.get_session_memory(state["session_id"]).preferred_location
            if location:
                state["location"] = location
        if not location:
            if state.get("salon_search"):
                state["reply"] = (
                    "May I know your preferred location so I can recommend nearby salons?"
                )
                return state
            state["reply"] = (
                "May I know your preferred location so I can recommend nearby salons?"
            )
            return state

        state["location_analysis"] = self.location_agent.analyze(location)
        return state

    def route_location(self, state: GraphState) -> str:
        return "discover" if state.get("location_analysis") else "end"

    def discover(self, state: GraphState) -> GraphState:
        location_analysis = state["location_analysis"]
        service = state.get("service")
        category = state.get("category")
        salon_search = state.get("salon_search", False)

        salon_payload = {
            "service": service,
            "category": category,
            "location": location_analysis.normalized_location,
        }
        logger.info("SALON_API_PAYLOAD: %s", salon_payload)
        # Pass empty strings (not None) so downstream matching treats them as
        # "unspecified" rather than failing on a missing filter.
        salons = self.discovery_agent.discover(
            category=category or "",
            service=service or "",
            location=location_analysis.normalized_location,
            radius_km=location_analysis.radius_km,
        )
        recommendations = self.ranking_agent.rank(
            salons=salons,
            service=service or "",
            radius_km=location_analysis.radius_km,
        )

        state["recommendations"] = recommendations[:5]
        logger.info("SALONS_FOUND: %s", len(recommendations))
        logger.info("SALON_NAMES: %s", [r.salon_name for r in recommendations[:5]])
        logger.info(
            "SALON_LOADED: %s salon(s) matched for service=%s category=%s location=%s (salon_search=%s)",
            len(state["recommendations"]),
            service,
            category,
            location_analysis.normalized_location,
            salon_search,
        )
        if recommendations:
            logger.info(
                "API_RESPONSE_SALONS: count=%s first=%s",
                len(recommendations),
                recommendations[0].model_dump(),
            )
        else:
            logger.warning(
                "API_RESPONSE_SALONS: empty for location=%s category=%s service=%s",
                location_analysis.normalized_location,
                category,
                service,
            )
        location_display = state.get("location") or location_analysis.normalized_location

        if recommendations:
            top = recommendations[0]
            if salon_search or not service:
                offer_clause = ""
            else:
                offer_clause = f" that offer {service}"
            state["reply"] = (
                f"Thank you.\n\n"
                f"I found several salons in {location_display}{offer_clause}.\n\n"
                f"Please select your preferred salon to continue."
            )
            session_id = state["session_id"]
            draft = self.memory.get_booking_draft(session_id)
            if service:
                draft.service = service
            if category:
                draft.category = category
            # Never auto-select a salon — customer must choose from cards.
            draft.salon = None
            draft.salon_id = None
            self.memory.set_booking_draft(session_id, draft)
            lookup = {
                title_case_safe(r.salon_name).lower(): (r.vendor_id or "")
                for r in state["recommendations"]
            }
            self.memory.set_salon_lookup(session_id, lookup)
            self.memory.start_booking_session(session_id)
            if draft.date and draft.time:
                self.memory.set_booking_stage(session_id, "awaiting_salon")
                state["booking_stage"] = "awaiting_salon"
            elif draft.date:
                self.memory.set_booking_stage(session_id, "awaiting_time")
                state["booking_stage"] = "awaiting_time"
            else:
                self.memory.set_booking_stage(session_id, "awaiting_date")
                state["booking_stage"] = "awaiting_date"
            self.memory.sync_session_from_draft(
                session_id,
                draft,
                last_intent="discovery",
                preferred_location=location_display,
                selected_category=category,
            )
        else:
            if salon_search or not service:
                state["reply"] = (
                    f"Thank you.\n\n"
                    f"There are currently no salons available in {location_display}.\n\n"
                    f"You may try a nearby location, or let me know a specific service "
                    f"you are looking for."
                )
            else:
                state["reply"] = (
                    f"Thank you.\n\n"
                    f"Although {service} is available on our platform, there are currently no salons "
                    f"offering this service in {location_display}.\n\n"
                    f"You may choose one of the following options:\n\n"
                    f"1. Search nearby locations.\n"
                    f"2. Explore alternative services.\n"
                    f"3. Receive a notification when the service becomes available.\n\n"
                    f"How would you like to proceed?"
                )
        return state

    _BOOKING_CONFIRM_WORDS = frozenset({
        "yes", "y", "confirm", "confirmed", "book it", "proceed", "continue",
        "looks good", "looks great", "ok", "okay", "sure", "go ahead",
    })

    def _is_booking_confirmation(self, message: str) -> bool:
        lower = message.lower().strip().rstrip(".!?")
        if lower in self._BOOKING_CONFIRM_WORDS:
            return True
        return bool(re.match(
            r"^(yes|confirm|proceed|book it|looks good|continue|ok|okay|sure)[\s!.]*$",
            lower,
        ))

    def _is_booking_decline(self, message: str) -> bool:
        lower = message.lower().strip().rstrip(".!?")
        return lower in {
            "no", "nope", "cancel", "decline", "not now", "don't", "stop", "never mind", "nevermind",
        } or bool(re.match(r"^no[\s!.]*$", lower))

    def _detect_booking_modification(self, message: str) -> str | None:
        lower = message.lower().strip()
        if re.search(r"\bchange\s+(?:the\s+)?time\b", lower) or re.search(r"\bchange\s+time\s+to\b", lower):
            return "time"
        if re.search(r"\bchange\s+(?:the\s+)?date\b", lower) or re.search(r"\bchange\s+date\s+to\b", lower):
            return "date"
        if re.search(r"\bchange\s+(?:the\s+)?salon\b", lower) or re.search(r"\bchange\s+salon\s+to\b", lower):
            return "salon"
        if re.search(r"\bchange\s+(?:the\s+)?service\b", lower) or re.search(r"\bchange\s+service\s+to\b", lower):
            return "service"
        if re.search(r"\bmodify\s+(?:the\s+)?(?:booking|appointment)\b", lower) or lower == "modify booking":
            return "modify"
        return None

    def _format_booking_summary(self, payload: BookingPayload, *, updated: bool = False) -> str:
        heading = (
            "Updated appointment details:"
            if updated
            else "Please confirm your booking details:"
        )
        return (
            f"{heading}\n\n"
            f"Service:\n{payload.service}\n\n"
            f"Salon:\n{payload.salon}\n\n"
            f"Date:\n{payload.date}\n\n"
            f"Time:\n{payload.time}\n\n"
            "Would you like me to confirm this booking?"
        )

    def _present_booking_summary(
        self,
        state: GraphState,
        session_id: str,
        payload: BookingPayload,
        *,
        updated: bool = False,
    ) -> GraphState:
        logger.info(
            "SUMMARY_GENERATED: service=%s salon=%s date=%s time=%s updated=%s",
            payload.service,
            payload.salon,
            payload.date,
            payload.time,
            updated,
        )
        self.memory.set_booking_draft(session_id, payload)
        self.memory.start_booking_session(session_id)
        self.memory.set_booking_stage(session_id, "awaiting_confirmation")
        self.memory.update_session_memory(
            session_id,
            booking_summary_shown=True,
            awaiting_confirmation=True,
            booking_status="awaiting_confirmation",
            last_intent="appointment_booking",
        )
        state["reply"] = self._format_booking_summary(payload, updated=updated)
        state["booking_stage"] = "awaiting_confirmation"
        state["booking_payload"] = payload
        return state

    def _handle_booking_confirmation(
        self,
        state: GraphState,
        session_id: str,
        draft: BookingPayload,
        lookup: dict[str, str],
    ) -> GraphState:
        message = state["user_message"]
        draft = self.memory.get_booking_draft(session_id)

        if self._is_booking_confirmation(message):
            logger.info("CONFIRMATION_RECEIVED: %s", message.strip())
            is_complete, missing = self.booking_agent.booking_data_completeness_check(draft)
            if is_complete:
                logger.info("BOOKING_REQUEST_CREATED: customer confirmed")
                self.memory.update_session_memory(
                    session_id,
                    booking_summary_shown=False,
                    awaiting_confirmation=False,
                )
                return self._finalize_booking(state, session_id, draft)
            logger.info("BOOKING_INCOMPLETE_AT_CONFIRM: missing=%s", missing)
            self.memory.update_session_memory(
                session_id,
                booking_summary_shown=False,
                awaiting_confirmation=False,
            )
            self.memory.set_booking_stage(session_id, f"awaiting_{missing[0]}")
            state["reply"] = f"Please provide your preferred appointment {missing[0]}."
            state["booking_payload"] = draft
            return state

        if self._is_booking_decline(message):
            logger.info("CONFIRMATION_DECLINED: booking not created")
            self.memory.update_session_memory(
                session_id,
                booking_summary_shown=False,
                awaiting_confirmation=False,
            )
            self.memory.end_booking_session(session_id)
            state["reply"] = (
                "Understood. Your appointment has not been booked.\n\n"
                "You may update any detail (for example, \"Change time to 6 PM\") "
                "or start a new request whenever you are ready."
            )
            state["booking_payload"] = draft
            return state

        mod_field = self._detect_booking_modification(message)
        if mod_field == "modify":
            logger.info("BOOKING_MODIFY_REQUEST: general modification")
            return self._present_booking_summary(state, session_id, draft, updated=True)

        if mod_field:
            updated = self.booking_agent.extract_booking_fields(message, draft, lookup)
            if mod_field == "time":
                if updated.time:
                    logger.info("BOOKING_MODIFIED: time=%s", updated.time)
                    return self._present_booking_summary(state, session_id, updated, updated=True)
                updated.time = None
                self.memory.set_booking_draft(session_id, updated)
                self.memory.update_session_memory(
                    session_id,
                    booking_summary_shown=False,
                    awaiting_confirmation=False,
                    appointment_time=None,
                )
                self.memory.set_booking_stage(session_id, "awaiting_time")
                state["reply"] = (
                    "Please provide your preferred appointment time.\n\n"
                    "(Format: HH AM/PM — for example, 4 PM)"
                )
                state["booking_payload"] = updated
                return state

            if mod_field == "date":
                if updated.date and not self.booking_agent.is_past_date(updated.date):
                    logger.info("BOOKING_MODIFIED: date=%s", updated.date)
                    return self._present_booking_summary(state, session_id, updated, updated=True)
                updated.date = None
                self.memory.set_booking_draft(session_id, updated)
                self.memory.update_session_memory(
                    session_id,
                    booking_summary_shown=False,
                    awaiting_confirmation=False,
                    appointment_date=None,
                )
                self.memory.set_booking_stage(session_id, "awaiting_date")
                state["reply"] = (
                    "Please provide your preferred appointment date.\n\n"
                    "(Format: DD Month YYYY — for example, 15 July 2026)"
                )
                state["booking_payload"] = updated
                return state

            if mod_field == "salon":
                salon_match = re.search(r"change\s+salon\s+to\s+(.+?)(?:\.|$)", message, re.IGNORECASE)
                if salon_match:
                    candidate = title_case_safe(salon_match.group(1).strip())
                    if self.booking_agent._is_valid_salon_name(candidate):
                        updated.salon = candidate
                        lookup_match = lookup.get(candidate.lower())
                        if lookup_match:
                            updated.salon_id = lookup_match
                if updated.salon and self.booking_agent._is_valid_salon_name(updated.salon):
                    logger.info("BOOKING_MODIFIED: salon=%s", updated.salon)
                    return self._present_booking_summary(state, session_id, updated, updated=True)
                updated.salon = None
                updated.salon_id = None
                self.memory.set_booking_draft(session_id, updated)
                self.memory.update_session_memory(
                    session_id,
                    booking_summary_shown=False,
                    awaiting_confirmation=False,
                    selected_salon=None,
                    salon_id=None,
                )
                self.memory.set_booking_stage(session_id, "awaiting_date")
                state["reply"] = "Please select your preferred salon to continue."
                state["booking_payload"] = updated
                return state

            if mod_field == "service":
                if updated.service:
                    logger.info("BOOKING_MODIFIED: service=%s", updated.service)
                    return self._present_booking_summary(state, session_id, updated, updated=True)
                updated.service = None
                self.memory.set_booking_draft(session_id, updated)
                self.memory.update_session_memory(
                    session_id,
                    booking_summary_shown=False,
                    awaiting_confirmation=False,
                    selected_service=None,
                )
                state["reply"] = (
                    "To assist you, could you please let me know which service you are looking for?"
                )
                state["booking_payload"] = updated
                return state

        # Allow inline value updates while awaiting confirmation (e.g. "6 PM")
        updated = self.booking_agent.extract_booking_fields(message, draft, lookup)
        self.booking_agent.log_detected_entities(updated)
        is_complete, _ = self.booking_agent.booking_data_completeness_check(updated)
        if is_complete and (
            updated.date != draft.date
            or updated.time != draft.time
            or updated.salon != draft.salon
            or updated.service != draft.service
        ):
            logger.info("BOOKING_MODIFIED: inline update detected")
            return self._present_booking_summary(state, session_id, updated, updated=True)

        state["reply"] = (
            "Please reply Yes to confirm your appointment, or tell me what you would "
            "like to change (for example, \"Change time to 6 PM\")."
        )
        state["booking_payload"] = draft
        state["booking_stage"] = "awaiting_confirmation"
        return state

    def booking(self, state: GraphState) -> GraphState:
        session_id = state["session_id"]
        draft = self.memory.get_booking_draft(session_id)
        lookup = self.memory.get_salon_lookup(session_id)
        session_memory = self.memory.get_session_memory(session_id)
        analysis = state.get("intent_analysis")

        # Safety net: policy/FAQ questions must never be handled as booking confirmations.
        awaiting_confirm = (
            session_memory.awaiting_confirmation
            or self.memory.get_booking_stage(session_id) == "awaiting_confirmation"
        )
        is_confirmation_turn = awaiting_confirm and (
            self._is_booking_confirmation(state["user_message"])
            or self._is_booking_decline(state["user_message"])
            or self._detect_booking_modification(state["user_message"]) is not None
        )
        if not is_confirmation_turn and (
            (analysis and analysis.intent in {
                IntentType.FAQ,
                IntentType.POLICY,
                IntentType.APPOINTMENT_CANCELLATION,
            })
            or self._is_policy_or_faq_message(state["user_message"])
        ):
            if session_memory.awaiting_confirmation or self._has_booking_in_progress(session_id):
                state["resume_booking_after_faq"] = True
                logger.info("BOOKING_INTERRUPT: FAQ routed from booking node safety net")
                return self.faq_policy(state)

        if (
            session_memory.awaiting_confirmation
            or self.memory.get_booking_stage(session_id) == "awaiting_confirmation"
        ):
            return self._handle_booking_confirmation(state, session_id, draft, lookup)

        # Resolve salon selection from explicit phrases or salon-card lookup.
        draft, salon_selected = self._apply_salon_selection(session_id, state["user_message"], draft)
        if salon_selected:
            self.memory.set_booking_draft(session_id, draft)
            self.memory.start_booking_session(session_id)
            self.memory.update_session_memory(
                session_id,
                selected_salon=draft.salon,
                salon_id=draft.salon_id,
            )
            if draft.date and draft.time:
                logger.info("SALON_SELECTED: all slots present — showing confirmation summary")
                return self._present_booking_summary(state, session_id, draft)
            if not draft.date:
                self.memory.set_booking_stage(session_id, "awaiting_date")
            elif not draft.time:
                self.memory.set_booking_stage(session_id, "awaiting_time")
            booking_stage = self.memory.get_booking_stage(session_id) or "awaiting_date"
        else:
            booking_stage = state.get("booking_stage") or self.memory.get_booking_stage(session_id)
            if booking_stage == "awaiting_salon":
                state["reply"] = (
                    "Please select your preferred salon from the list above to continue."
                )
                state["booking_stage"] = "awaiting_salon"
                state["booking_payload"] = draft
                return state
            if not booking_stage and draft.salon and draft.service:
                booking_stage = "awaiting_date"

        updated = self.booking_agent.extract_booking_fields(
            state["user_message"],
            draft,
            lookup,
        )
        self.booking_agent.log_detected_entities(updated)
        self.memory.set_booking_draft(session_id, updated)

        entity = self._compute_booking_entity_state(session_id, state["user_message"])

        if updated.date and self.booking_agent.is_past_date(updated.date):
            logger.info("BOOKING_DATE: %s", updated.date)
            logger.info("VALIDATION_RESULT: REJECTED (past date)")
            entity.date = None
            updated.date = None
            self.memory.set_booking_draft(session_id, updated)
            self.memory.update_session_memory(session_id, appointment_date=None)
            self.memory.set_booking_stage(session_id, "awaiting_date")
            state["reply"] = (
                "The date you selected is in the past and cannot be booked.\n\n"
                "Please share a date that is today or later.\n\n"
                "(Format: DD Month YYYY — for example, 15 July 2026)"
            )
            state["booking_stage"] = "awaiting_date"
            state["booking_payload"] = updated
            return state

        routed = self._route_booking_collection(state, session_id, entity)
        if routed is not None:
            return routed

        state["reply"] = self._format_booking_progress_reply(updated, entity.next_slot or "service")
        state["booking_payload"] = updated
        return state

    def _is_booking_ready(self, payload: BookingPayload) -> bool:
        complete, _ = self.booking_agent.booking_data_completeness_check(payload)
        return complete

    def _apply_salon_selection(
        self,
        session_id: str,
        message: str,
        draft: BookingPayload,
    ) -> tuple[BookingPayload, bool]:
        """Resolve salon from explicit selection or salon-card lookup."""
        text = message.strip()
        text_lower = text.lower()
        if is_generic_salon_phrase(text):
            return draft, False
        if text_lower in {
            "proceed", "continue", "yes", "ok", "okay", "next",
            "confirm", "confirmed", "book it", "looks good", "sure",
        }:
            return draft, False

        salon_choice = self._extract_salon_selection(message)
        if salon_choice and not is_generic_salon_phrase(salon_choice):
            draft.salon = salon_choice
            lookup = self.memory.get_salon_lookup(session_id)
            resolved_id = lookup.get(salon_choice.lower())
            if resolved_id:
                draft.salon_id = resolved_id
            logger.info("SALON_SELECTED: %s salon_id=%s", draft.salon, draft.salon_id)
            return draft, True

        lookup = self.memory.get_salon_lookup(session_id)
        if not lookup:
            return draft, False

        if text_lower in lookup:
            draft.salon = title_case_safe(text)
            draft.salon_id = lookup[text_lower]
            logger.info("SALON_SELECTED: %s salon_id=%s", draft.salon, draft.salon_id)
            return draft, True

        for name, sid in lookup.items():
            if name in text_lower or text_lower in name:
                draft.salon = title_case_safe(name)
                draft.salon_id = sid
                logger.info("SALON_SELECTED: %s salon_id=%s", draft.salon, draft.salon_id)
                return draft, True

        salon, salon_id = self.booking_agent.extract_salon_from_message(message, lookup)
        if salon and self.booking_agent._is_valid_salon_name(salon):
            draft.salon = salon
            if salon_id:
                draft.salon_id = salon_id
            logger.info("SALON_SELECTED: %s salon_id=%s", draft.salon, draft.salon_id)
            return draft, True

        if lookup and not re.search(r"\d|tomorrow|today|\bam\b|\bpm\b", text_lower):
            if is_generic_salon_phrase(text):
                return draft, False
            words = text.split()
            if 1 <= len(words) <= 5 and text_lower not in {"proceed", "continue", "yes", "ok", "okay", "next"}:
                candidate = title_case_safe(text)
                if self.booking_agent._is_valid_salon_name(candidate):
                    draft.salon = candidate
                    for name, sid in lookup.items():
                        if text_lower in name or name in text_lower:
                            draft.salon_id = sid
                            break
                    logger.info("SALON_SELECTED: %s salon_id=%s", draft.salon, draft.salon_id)
                    return draft, True

        return draft, False

    def _finalize_booking(
        self,
        state: GraphState,
        session_id: str,
        updated: BookingPayload,
    ) -> GraphState:
        if self.booking_agent.is_past_date(updated.date):
            logger.info("BOOKING_DATE: %s", updated.date)
            logger.info("VALIDATION_RESULT: REJECTED (past date at confirm)")
            updated.date = None
            self.memory.set_booking_draft(session_id, updated)
            self.memory.set_booking_stage(session_id, "awaiting_date")
            state["reply"] = (
                "The date you selected is in the past and cannot be booked.\n\n"
                "Please share a date that is today or later.\n\n"
                "(Format: DD Month YYYY — for example, 15 July 2026)"
            )
            state["booking_stage"] = "awaiting_date"
            state["booking_payload"] = updated
            return state

        user_context = self.memory.get_user_context(session_id)
        if user_context and user_context.user_id:
            updated.user_id = user_context.user_id

        logger.info(
            "BOOKING_PAYLOAD_GENERATED: %s",
            {
                "userId": updated.user_id,
                "salonId": updated.salon_id,
                "selectedSalon": updated.salon,
                "selectedService": updated.service,
                "appointmentDate": updated.date,
                "appointmentTime": updated.time,
            },
        )
        logger.info("BOOKING_API_CALLED: creating booking request")
        confirmed = self.booking_service.create_booking(updated)
        logger.info("BOOKING_STORED: booking_id=%s status=%s", confirmed.booking_id, confirmed.status)
        logger.info("BOOKING_SUCCESS: booking_id=%s", confirmed.booking_id)

        self.memory.clear_booking_draft(session_id)
        self.memory.end_booking_session(session_id)
        self.memory.update_session_memory(session_id, booking_status="completed")

        state["intent_analysis"] = IntentAnalysis(
            intent=IntentType.APPOINTMENT_BOOKING,
            service=updated.service,
        )
        state["booking_payload"] = BookingPayload.model_validate(confirmed.payload.model_dump())
        state["booking_response"] = confirmed.model_dump()
        state["reply"] = (
            "Your appointment request has been submitted successfully.\n\n"
            f"Salon:\n{updated.salon}\n\n"
            f"Service:\n{updated.service}\n\n"
            f"Date:\n{updated.date}\n\n"
            f"Time:\n{updated.time}\n\n"
            "Thank you for choosing Bookly."
        )
        return state

    def _message_has_schedule(self, message: str) -> bool:
        lower = message.lower()
        return bool(
            self.booking_agent.extract_relative_date(message)
            or re.search(r"\bon\d{1,2}/\d{1,2}/\d{4}\b", message, re.IGNORECASE)
            or re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", message)
            or re.search(r"\b\d{4}-\d{2}-\d{2}\b", message)
            or re.search(r"\b\d{1,2}:\d{2}\s*(?:am|pm)\b", lower)
            or re.search(r"\b\d{1,2}\s*(?:am|pm)\b", lower)
            or "tomorrow" in lower
            or "today" in lower
            or re.search(
                r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                lower,
            )
        )

    def _try_route_booking_with_memory(
        self,
        session_id: str,
        message: str,
        state: GraphState,
    ) -> bool:
        draft = self.memory.get_booking_draft(session_id)
        lookup = self.memory.get_salon_lookup(session_id)
        preview = self.booking_agent.extract_booking_fields(message, draft, lookup)
        self.booking_agent.log_detected_entities(preview)

        is_complete, missing = self.booking_agent.booking_data_completeness_check(preview)
        entity = self._compute_booking_entity_state(session_id, message)

        if entity.action == "confirm" and entity.salon_verified:
            self._sync_entity_state_to_draft(session_id, entity)
            self.memory.start_booking_session(session_id)
            state["booking_stage"] = "awaiting_confirmation"
            return True

        if entity.action == "discover":
            return False

        if is_complete and self._salon_is_user_selected(session_id, preview):
            self.memory.set_booking_draft(session_id, preview)
            self.memory.start_booking_session(session_id)
            state["booking_stage"] = "awaiting_confirmation"
            return True

        if (
            is_complete
            and not entity.salon_verified
            and self._has_service_and_location(session_id, message, preview)
        ):
            return False

        has_schedule = self._message_has_schedule(message)
        has_booking_context = bool(
            preview.service
            or preview.salon
            or draft.service
            or draft.salon
            or self.memory.get_session_memory(session_id).selected_service
            or self.memory.get_session_memory(session_id).selected_salon
        )
        if has_schedule and has_booking_context and len(missing) < 4:
            if entity.action == "discover":
                return False
            if "salon" in missing and self._has_service_and_location(session_id, message, preview):
                return False
            self.memory.set_booking_draft(session_id, preview)
            self.memory.start_booking_session(session_id)
            if "date" in missing:
                self.memory.set_booking_stage(session_id, "awaiting_date")
            elif "time" in missing:
                self.memory.set_booking_stage(session_id, "awaiting_time")
            elif not entity.location:
                self.memory.set_booking_stage(session_id, "awaiting_location")
            state["booking_stage"] = self.memory.get_booking_stage(session_id)
            return True

        if has_schedule and self._is_explicit_booking_request(message) and len(missing) < 4:
            if entity.action == "discover":
                return False
            if "salon" in missing and self._has_service_and_location(session_id, message, preview):
                return False
            self.memory.set_booking_draft(session_id, preview)
            self.memory.start_booking_session(session_id)
            state["booking_stage"] = self.memory.get_booking_stage(session_id) or "awaiting_date"
            return True

        memory = self.memory.get_session_memory(session_id)
        if memory.selected_service and memory.selected_salon and has_schedule:
            self.memory.set_booking_draft(session_id, preview)
            self.memory.start_booking_session(session_id)
            state["booking_stage"] = self.memory.get_booking_stage(session_id) or "awaiting_date"
            return True

        if preview.salon and self._is_explicit_booking_request(message):
            self.memory.set_booking_draft(session_id, preview)
            self.memory.start_booking_session(session_id)
            state["booking_stage"] = self.memory.get_booking_stage(session_id) or "awaiting_date"
            return True

        if preview.service and self._is_explicit_booking_request(message):
            self.memory.set_booking_draft(session_id, preview)
            self.memory.start_booking_session(session_id)
            return True

        return False

    @staticmethod
    def extract_relative_date_hint(message: str) -> bool:
        lower = message.lower()
        return "tomorrow" in lower or "today" in lower

    @staticmethod
    def _is_explicit_booking_request(message: str) -> bool:
        lower = message.lower()
        return any(term in lower for term in ("book", "appointment", "reserve", "schedule"))

    def _extract_salon_selection(self, message: str) -> str | None:
        match = re.search(r"\b(?:proceed with|book at|select|choose)\s+(?P<salon>.+)\b", message, re.IGNORECASE)
        if not match:
            return None
        salon = match.group("salon").strip()
        if salon:
            return title_case_safe(salon)
        return None

    def is_location_only(self, message: str) -> bool:
        text = message.lower()
        return any(area in text for area in [
            "dubai",
            "jumeirah",
            "abu dhabi",
            "sharjah",
            "marina",
            "ajman",
            "ras al khaimah",
            "al ain",
        ]) and all(
            keyword not in text for keyword in [
                "book",
                "appointment",
                "reserve",
                "cancel",
                "cancellation",
                "policy",
                "terms",
                "refund",
                "privacy",
                "faq",
                "how",
                "what",
                "name",
                "phone",
                "service",
                "salon",
                "date",
                "time",
            ]
        )

    def is_generic_booking_request(self, message: str) -> bool:
        text = message.lower()
        generic_terms = ["book", "appointment", "reserve", "schedule", "slot"]
        service_terms = [
            "hair",
            "makeup",
            "facial",
            "wax",
            "pedicure",
            "massage",
            "nails",
            "henna",
            "spa",
            "bridal",
            "body",
        ]
        return any(term in text for term in generic_terms) and not any(term in text for term in service_terms)

    def is_booking_details(self, message: str) -> bool:
        text = message.lower()
        return bool(
            re.search(r"\d{4}-\d{2}-\d{2}", text)
            or re.search(r"\bon\d{1,2}/\d{1,2}/\d{4}\b", text)
            or re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", text)
            or re.search(r"\d{1,2}:\d{2}", text)
            or re.search(r"\b\d{1,2}\s*(?:am|pm)\b", text)
            or re.search(r"\b(tomorrow|today)\b", text)
            or "name" in text
            or "phone" in text
            or "salon" in text
            or re.search(
                r"\b\d{1,2}\s+(?:january|february|march|april|may|june|july|august|"
                r"september|october|november|december)(?:\s+\d{4})?\b",
                text,
            )
        )

    @staticmethod
    def _is_policy_or_faq_message(message: str) -> bool:
        """Heuristic for policy/FAQ queries that must route to RAG, not booking."""
        lower = message.lower()
        phrases = (
            "cancellation policy",
            "cancel policy",
            "refund policy",
            "privacy policy",
            "terms and conditions",
            "terms of service",
            "what is the policy",
        )
        return any(p in lower for p in phrases)

    def get_last_service_query(self, state: GraphState) -> str | None:
        session_id = state.get("session_id")
        if session_id:
            memory_service = self.memory.get_session_memory(session_id).selected_service
            if memory_service:
                return memory_service
        for msg in reversed(state.get("history", [])):
            if msg["role"] != "user":
                continue
            content = msg["content"].strip()
            if self.is_location_only(content):
                continue
            lower = content.lower()
            if any(keyword in lower for keyword in [
                "hair",
                "makeup",
                "facial",
                "waxing",
                "pedicure",
                "massage",
                "nails",
                "henna",
                "hair removal",
                "body",
                "bridal",
                "spa",
            ]):
                return content
        return None

    def general(self, state: GraphState) -> GraphState:
        context = self.memory.get_user_context(state["session_id"])
        if context and context.full_name:
            state["reply"] = (
                f"Welcome back {context.full_name}.\n\n"
                "I can assist you with salon discovery, appointment bookings, and any questions "
                "about our services or policies.\n\n"
                "How may I assist you today?"
            )
        else:
            state["reply"] = (
                "Welcome to Bookly.\n\n"
                "I can assist you with salon discovery, appointment bookings, and any questions "
                "about our services or policies.\n\n"
                "How may I assist you today?"
            )
        return state

    def run(self, state: GraphState) -> GraphState:
        session_id = state.get("session_id")
        if session_id:
            booking_stage = state.get("booking_stage") or self.memory.get_booking_stage(session_id)
            if booking_stage:
                state["booking_stage"] = booking_stage
            if "booking_payload" not in state or not state.get("booking_payload"):
                state["booking_payload"] = self.memory.get_booking_draft(session_id)
        return self.app.invoke(state)
