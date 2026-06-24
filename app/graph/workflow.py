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
from app.core.logging import get_logger
from app.memory.conversation_store import ConversationStore
from app.models.enums import IntentType
from app.utils.text import title_case_safe
from app.models.schemas import BookingPayload, IntentAnalysis
from app.models.state import GraphState
from app.services.booking_service import BookingService

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

        graph = StateGraph(GraphState)
        graph.add_node("detect_intent", self.detect_intent)
        graph.add_node("small_talk", self.small_talk)
        graph.add_node("category_list", self.category_list)
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
        graph.add_edge("faq_policy", END)
        graph.add_edge("discover", END)
        graph.add_edge("booking", END)
        graph.add_edge("general", END)

        self.app = graph.compile()

    def detect_intent(self, state: GraphState) -> GraphState:
        logger.info("USER_QUERY: %s", state["user_message"])
        history = self.memory.get_history(state["session_id"])
        analysis = self.intent_agent.analyze(
            message=state["user_message"],
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
        
        logger.info("ROUTING: Starting intent-based routing for message: %s", user_message)
        logger.info("DETECTED_INTENT: %s", intent)

        # ---------------------------------------------------------------- #
        # Intent priority (highest first):
        #   1. Small Talk  -> never triggers booking / category / RAG
        #   2. Category List -> answered directly from the Categories API
        # These are deterministic and run before all other routing so that
        # greetings and category-list requests bypass the LLM/RAG paths.
        # ---------------------------------------------------------------- #
        if self._small_talk_reply(user_message) is not None:
            logger.info("SELECTED_AGENT: small_talk (intent priority 1)")
            return "small_talk"

        if self._is_category_list_request(user_message):
            logger.info("SELECTED_AGENT: category_list (intent priority 2)")
            return "category_list"

        pending_service = self.get_last_service_query(state) or self.memory.get_session_memory(session_id).selected_service
        session_memory = self.memory.get_session_memory(session_id)
        if (
            (self.is_location_only(user_message) or self._awaiting_location(state))
            and pending_service
            and not session_memory.awaiting_confirmation
        ):
            if not self.memory.get_booking_stage(session_id):
                state["intent_analysis"] = IntentAnalysis(
                    intent=IntentType.SERVICE_SEARCH,
                    service=pending_service,
                )
                logger.info("SELECTED_AGENT: discovery_agent (location reply for pending service)")
                return "service_prepare"

        if intent in {IntentType.FAQ, IntentType.POLICY, IntentType.APPOINTMENT_CANCELLATION}:
            logger.info("SELECTED_AGENT: faq_agent (intent: %s)", intent)
            logger.info("RAG_TRIGGERED: True")
            return "faq_policy"
        
        # Check if we're in post-discovery booking flow (skip to date/time collection)
        booking_stage = self.memory.get_booking_stage(session_id)
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
            if self.is_booking_details(user_message):
                logger.info("SELECTED_AGENT: booking_agent (detailed booking request)")
                return "booking"
            logger.info("SELECTED_AGENT: discovery_agent (generic booking request)")
            return "service_prepare"

        if intent in {
            IntentType.SERVICE_SEARCH,
            IntentType.SALON_SEARCH,
            IntentType.LOCATION_SEARCH,
            IntentType.SALON_DISCOVERY,
        }:
            logger.info("SELECTED_AGENT: discovery_agent (intent: %s)", intent)
            return "service_prepare"

        # Heuristic safety net: a salon/vendor list request that the classifier
        # mislabeled (e.g. "give the list of vendors in Noida") still routes to
        # discovery as a salon-search instead of general conversation.
        if self._is_salon_search(user_message):
            logger.info("SELECTED_AGENT: discovery_agent (heuristic salon_search)")
            return "service_prepare"

        logger.info("SELECTED_AGENT: general_agent (general conversation)")
        logger.info("RAG_TRIGGERED: False")
        return "general"

    # ------------------------------------------------------------------ #
    # Small Talk layer (Issue #1) — deterministic, no LLM / RAG / booking
    # ------------------------------------------------------------------ #
    _SMALL_TALK_GREETING = (
        "Hello and welcome to Bookly.\n\n"
        "I hope you're doing well today.\n\n"
        "How may I assist you?"
    )
    _SMALL_TALK_HOW_ARE_YOU = (
        "Thank you for asking.\n\n"
        "I'm doing well and ready to assist you with salon discovery, "
        "appointments, and Bookly related questions."
    )
    _SMALL_TALK_THANKS = (
        "You're most welcome.\n\n"
        "Please let me know if there's anything else I can help you with."
    )
    _SMALL_TALK_IDENTITY = (
        "I am Bookly's AI appointment assistant.\n\n"
        "I can help you discover salons, book appointments, and answer questions "
        "about our services and policies.\n\n"
        "How may I assist you?"
    )
    _SMALL_TALK_CAPABILITY = (
        "I can assist you with the following:\n\n"
        "• Discovering salons by location\n"
        "• Finding services by category\n"
        "• Booking appointments\n"
        "• Answering questions about Bookly's services and policies\n\n"
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

        # Identity
        if text in {"who are you", "what are you", "who is this",
                    "what is your name", "whats your name", "who r u"}:
            return self._SMALL_TALK_IDENTITY

        # Capability
        if (text in {"what can you do", "what do you do", "how can you help",
                     "how can you assist", "what can you help me with",
                     "what can you help with", "how do you work"}
                or text.startswith("what can you")
                or text.startswith("how can you help")
                or text.startswith("how can you assist")):
            return self._SMALL_TALK_CAPABILITY

        # How are you
        if (text in {"how are you", "how are you doing", "how r u", "how are u",
                     "hows it going", "how is it going", "how do you do",
                     "how are things", "how you doing"}
                or text.startswith("how are you")
                or text.startswith("how r u")):
            return self._SMALL_TALK_HOW_ARE_YOU

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
            "all categories",
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
            "Please select a category or tell me the service you are looking for."
        )
        state["intent_analysis"] = IntentAnalysis(intent=IntentType.CATEGORY_LIST)
        logger.info("CATEGORY_LIST_RETURNED: %s categories -> %s", len(names), names)
        return state

    def faq_policy(self, state: GraphState) -> GraphState:
        logger.info("EXECUTING_AGENT: faq_agent")
        logger.info("RAG_PIPELINE: Retrieving from knowledge base")
        answer = self.faq_agent.answer(state["user_message"])
        logger.info("ANSWER: %s", answer)
        state["reply"] = answer
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
        # ---------------------------------------------------------------- #
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
            state["location"] = location
        logger.info("LOCATION_DETECTED: %s", location)

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
                return "preferred location" in msg["content"].lower()
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
        "color", "colour", "makeup", "make up", "facial", "wax", "waxing", "pedicure",
        "manicure", "nail", "nails", "henna", "spa", "massage", "bridal", "threading",
        "beard", "shave", "grooming",
    )
    _SALON_TARGET_WORDS = ("salon", "salons", "vendor", "vendors", "parlour", "parlor", "shop", "shops")
    _LOCATION_STOPWORDS = {
        "who", "that", "which", "please", "and", "the", "a", "an", "can", "could",
        "provide", "providing", "service", "services", "me", "for", "by", "with",
        "available", "near", "around", "is", "are", "to",
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

        match = re.search(
            r"\b(?:in|at|near|around|within|located in)\s+(.+)",
            message,
            flags=re.IGNORECASE,
        )
        if not match:
            return None

        words = re.findall(r"[A-Za-z]+", match.group(1))
        loc_words: list[str] = []
        for word in words:
            if word.lower() in self._LOCATION_STOPWORDS:
                break
            loc_words.append(word)
            if len(loc_words) >= 3:
                break
        if not loc_words:
            return None
        return title_case_safe(" ".join(loc_words))

    def _detect_service(self, message: str) -> str | None:
        """Return a cleaned service phrase, or None when no service is named."""
        if not self._has_service_keyword(message):
            return None
        cleaned = self._strip_location_clause(message)
        cleaned = re.sub(
            r"\b(i want|i need|i would like|i'd like|looking for|book|reserve|please|"
            r"give me|can i get|get me|i am looking for|show me)\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip(" .,-")
        return cleaned or None

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
                    "Certainly.\n\n"
                    "Which location would you like me to search for salons in?\n\n"
                    "Examples:\n"
                    "• Noida\n"
                    "• Dubai\n"
                    "• Abu Dhabi\n"
                    "• Sharjah"
                )
                return state
            service = state.get("service") or ""
            category = state.get("category") or ""
            intro = ""
            if service and category:
                intro = f"Thank you.\n\n{service} falls under our {category} category.\n\n"
            elif service:
                intro = "Thank you.\n\n"
            state["reply"] = (
                f"{intro}"
                "Please share your preferred location so I can find available salons near you."
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
            # Auto-populate salon name and service for booking flow
            session_id = state["session_id"]
            draft = self.memory.get_booking_draft(session_id)
            if service:
                draft.service = service
            if category:
                draft.category = category
            draft.salon = top.salon_name
            draft.salon_id = top.vendor_id
            self.memory.set_booking_draft(session_id, draft)
            # Persist a salon name -> id lookup so later selection resolves salonId
            lookup = {
                title_case_safe(r.salon_name).lower(): (r.vendor_id or "")
                for r in state["recommendations"]
            }
            self.memory.set_salon_lookup(session_id, lookup)
            # Set booking stage to only ask for date/time
            self.memory.start_booking_session(session_id)
            self.memory.set_booking_stage(session_id, "awaiting_date")
            self.memory.sync_session_from_draft(
                session_id,
                draft,
                last_intent="discovery",
                preferred_location=location_display,
                selected_category=category,
            )
            state["booking_stage"] = "awaiting_date"
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
            else "Please review your appointment details:"
        )
        return (
            f"{heading}\n\n"
            f"Service:\n{payload.service}\n\n"
            f"Salon:\n{payload.salon}\n\n"
            f"Date:\n{payload.date}\n\n"
            f"Time:\n{payload.time}\n\n"
            "Would you like me to confirm this appointment?\n\n"
            "Reply:\n"
            "Yes\n"
            "Confirm\n"
            "Book It\n"
            "Proceed"
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
            if not draft.date:
                self.memory.set_booking_stage(session_id, "awaiting_date")
            elif not draft.time:
                self.memory.set_booking_stage(session_id, "awaiting_time")
            booking_stage = self.memory.get_booking_stage(session_id) or "awaiting_date"
        else:
            booking_stage = state.get("booking_stage") or self.memory.get_booking_stage(session_id)
            if not booking_stage and draft.salon and draft.service:
                booking_stage = "awaiting_date"

        updated = self.booking_agent.extract_booking_fields(
            state["user_message"],
            draft,
            lookup,
        )
        self.booking_agent.log_detected_entities(updated)
        self.memory.set_booking_draft(session_id, updated)
        self.memory.sync_session_from_draft(session_id, updated, last_intent="appointment_booking")

        is_complete, missing_fields = self.booking_agent.booking_data_completeness_check(updated)
        if is_complete:
            logger.info("BOOKING_DETAILS_EXTRACTED: all fields present — showing confirmation summary")
            return self._present_booking_summary(state, session_id, updated)

        logger.info("BOOKING_MISSING_FIELDS: %s", missing_fields)

        if updated.date and self.booking_agent.is_past_date(updated.date):
            logger.info("BOOKING_DATE: %s", updated.date)
            logger.info("VALIDATION_RESULT: REJECTED (past date)")
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

        missing = missing_fields[0] if missing_fields else None
        if missing == "date":
            self.memory.start_booking_session(session_id)
            self.memory.set_booking_stage(session_id, "awaiting_date")
            state["reply"] = (
                "Please provide your preferred appointment date.\n\n"
                "(Format: DD Month YYYY — for example, 15 July 2026)"
            )
            state["booking_stage"] = "awaiting_date"
            state["booking_payload"] = updated
            return state

        if missing == "time":
            self.memory.set_booking_stage(session_id, "awaiting_time")
            state["booking_stage"] = "awaiting_time"
            state["reply"] = (
                "Please provide your preferred appointment time.\n\n"
                "(Format: HH AM/PM — for example, 4 PM)"
            )
            state["booking_payload"] = updated
            return state

        if missing == "service":
            state["reply"] = (
                "To assist you, could you please let me know which service you are looking for?"
            )
            state["booking_payload"] = updated
            return state

        if missing == "salon":
            state["reply"] = "Please select your preferred salon to continue."
            state["booking_payload"] = updated
            return state

        state["reply"] = (
            "Please provide your preferred appointment date.\n\n"
            "(Format: DD Month YYYY — for example, 15 July 2026)"
        )
        state["booking_stage"] = "awaiting_date"
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
        if text_lower in {
            "proceed", "continue", "yes", "ok", "okay", "next",
            "confirm", "confirmed", "book it", "looks good", "sure",
        }:
            return draft, False

        salon_choice = self._extract_salon_selection(message)
        if salon_choice:
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
            or re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", message)
            or re.search(r"\b\d{4}-\d{2}-\d{2}\b", message)
            or re.search(r"\b\d{1,2}:\d{2}\s*(?:am|pm)\b", lower)
            or re.search(r"\b\d{1,2}\s*(?:am|pm)\b", lower)
            or "tomorrow" in lower
            or "today" in lower
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
        if is_complete:
            self.memory.set_booking_draft(session_id, preview)
            self.memory.start_booking_session(session_id)
            state["booking_stage"] = "awaiting_confirmation"
            return True

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
            self.memory.set_booking_draft(session_id, preview)
            self.memory.start_booking_session(session_id)
            if "date" in missing:
                self.memory.set_booking_stage(session_id, "awaiting_date")
            elif "time" in missing:
                self.memory.set_booking_stage(session_id, "awaiting_time")
            state["booking_stage"] = self.memory.get_booking_stage(session_id)
            return True

        if has_schedule and self._is_explicit_booking_request(message) and len(missing) < 4:
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
            or re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", text)
            or re.search(r"\d{1,2}:\d{2}", text)
            or re.search(r"\b\d{1,2}\s*(?:am|pm)\b", text)
            or re.search(r"\b(tomorrow|today)\b", text)
            or "name" in text
            or "phone" in text
            or "salon" in text
            or re.search(
                r"\b\d{1,2}\s+(?:january|february|march|april|may|june|july|august|"
                r"september|october|november|december)\s+\d{4}\b",
                text,
            )
        )

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
