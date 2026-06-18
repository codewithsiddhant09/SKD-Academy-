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

        if intent in {IntentType.FAQ, IntentType.POLICY, IntentType.APPOINTMENT_CANCELLATION}:
            logger.info("SELECTED_AGENT: faq_agent (intent: %s)", intent)
            logger.info("RAG_TRIGGERED: True")
            return "faq_policy"
        
        # Check if we're in post-discovery booking flow (skip to date/time collection)
        booking_stage = self.memory.get_booking_stage(session_id)
        if booking_stage in ["awaiting_date", "awaiting_time"]:
            logger.info("SELECTED_AGENT: booking_agent (post-discovery booking stage)")
            state["booking_stage"] = booking_stage
            return "booking"
        
        if self.memory.has_active_booking_session(session_id):
            logger.info("SELECTED_AGENT: booking_agent (active booking session)")
            return "booking"

        booking_draft = self.memory.get_booking_draft(session_id)
        if any(getattr(booking_draft, field) for field in self.booking_agent.REQUIRED_FIELDS):
            if self.booking_agent.missing_fields(booking_draft):
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

        if (self.is_location_only(state["user_message"]) or self._awaiting_location(state)) and self.get_last_service_query(state):
            state["intent_analysis"] = IntentAnalysis(
                intent=IntentType.SERVICE_SEARCH,
                service=self.get_last_service_query(state),
            )
            logger.info("SELECTED_AGENT: discovery_agent (location reply for pending service)")
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
                names = self.category_service.get_category_names()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("CATEGORY_LIST: Categories API fetch failed: %s", exc)
                names = []
        if not names:
            names = list(self.categories)

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

            category = analysis.category
            if not category and service:
                category = self.category_agent.map_category(service, self.categories)

            state["service"] = service
            state["category"] = category  # may be None — never forced
            logger.info("SERVICE_DETECTED: %s", service)
            logger.info(
                "CATEGORY_MAPPED: %s (source: %s)",
                category,
                "LLM" if analysis.category else ("keyword" if category else "none"),
            )

        if location:
            state["location"] = location
        logger.info("LOCATION_DETECTED: %s", location)
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

    def booking(self, state: GraphState) -> GraphState:
        session_id = state["session_id"]
        draft = self.memory.get_booking_draft(session_id)

        # Handle salon selection before asking for date/time
        salon_choice = self._extract_salon_selection(state["user_message"])
        if salon_choice:
            draft.salon = salon_choice
            salon_lookup = self.memory.get_salon_lookup(session_id)
            resolved_id = salon_lookup.get(salon_choice.lower())
            if resolved_id:
                draft.salon_id = resolved_id
            self.memory.set_booking_draft(session_id, draft)
            self.memory.start_booking_session(session_id)
            self.memory.set_booking_stage(session_id, "awaiting_date")
            booking_stage = "awaiting_date"
        else:
            booking_stage = state.get("booking_stage") or self.memory.get_booking_stage(session_id)
            if not booking_stage and draft.salon and draft.service:
                booking_stage = "awaiting_date"

        # Only extract date/time - no name/phone/email extraction
        updated = self.booking_agent.extract_date_and_time(state["user_message"], draft)
        self.memory.set_booking_draft(session_id, updated)

        # Stage 1: Ask for date
        if booking_stage == "awaiting_date":
            if not updated.date:
                self.memory.start_booking_session(session_id)
                self.memory.set_booking_stage(session_id, "awaiting_date")
                state["reply"] = (
                    "Please share your preferred date.\n\n"
                    "(Format: DD Month YYYY — for example, 15 July 2026)"
                )
                state["booking_stage"] = "awaiting_date"
                state["booking_payload"] = updated
                return state
            elif self.booking_agent.is_past_date(updated.date):
                # Bug 3: reject past dates and re-ask for a valid one.
                logger.info("BOOKING_DATE: %s", updated.date)
                logger.info("VALIDATION_RESULT: REJECTED (past date)")
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
            else:
                # Date received and valid, move to time
                logger.info("BOOKING_DATE: %s", updated.date)
                logger.info("VALIDATION_RESULT: ACCEPTED")
                self.memory.set_booking_stage(session_id, "awaiting_time")
                state["booking_stage"] = "awaiting_time"
                state["reply"] = (
                    "What time would you prefer?\n\n"
                    "(Format: HH AM/PM — for example, 4 PM)"
                )
                state["booking_payload"] = updated
                return state

        # Stage 2: Ask for time and confirm when received
        if booking_stage == "awaiting_time":
            if not updated.time:
                self.memory.start_booking_session(session_id)
                self.memory.set_booking_stage(session_id, "awaiting_time")
                state["reply"] = (
                    "What time would you prefer?\n\n"
                    "(Format: HH AM/PM — for example, 4 PM)"
                )
                state["booking_stage"] = "awaiting_time"
                state["booking_payload"] = updated
                return state
            elif self.booking_agent.is_past_date(updated.date):
                # Bug 3 safety net: a past date must never reach confirmation.
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
            else:
                # Both date and time received - confirm booking.
                # Enrich payload from the user's session context (no name/phone/email asked).
                logger.info("VALIDATION_RESULT: ACCEPTED")
                user_context = self.memory.get_user_context(session_id)
                if user_context and user_context.user_id:
                    updated.user_id = user_context.user_id

                logger.info(
                    "BOOKING_PAYLOAD_GENERATED: %s",
                    {
                        "userId": updated.user_id,
                        "salonId": updated.salon_id,
                        "service": updated.service,
                        "category": updated.category,
                        "date": updated.date,
                        "time": updated.time,
                    },
                )

                confirmed = self.booking_service.create_booking(updated)
                self.memory.clear_booking_draft(session_id)
                self.memory.end_booking_session(session_id)

                state["intent_analysis"] = IntentAnalysis(
                    intent=IntentType.APPOINTMENT_BOOKING,
                    service=updated.service,
                )
                state["booking_payload"] = BookingPayload.model_validate(confirmed.payload.model_dump())
                state["reply"] = (
                    f"Your appointment has been booked successfully.\n\n"
                    f"Service: {updated.service}\n"
                    f"Salon: {updated.salon}\n"
                    f"Date: {updated.date}\n"
                    f"Time: {updated.time}\n\n"
                    f"Booking ID: {confirmed.booking_id}\n\n"
                    f"Thank you for choosing Bookly."
                )
                return state

        # Fallback (should not reach here in normal flow)
        if draft.salon and draft.service:
            self.memory.set_booking_stage(session_id, "awaiting_date")
            state["reply"] = (
                "Please share your preferred date to complete the booking.\n\n"
                "(Format: DD Month YYYY — for example, 15 July 2026)"
            )
            state["booking_stage"] = "awaiting_date"
            state["booking_payload"] = updated
            return state

        state["reply"] = (
            "Please share your preferred date to complete the booking.\n\n"
            "(Format: DD Month YYYY — for example, 15 July 2026)"
        )
        state["booking_stage"] = "awaiting_date"
        state["booking_payload"] = updated
        return state

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
            or re.search(r"\d{1,2}:\d{2}", text)
            or "name" in text
            or "phone" in text
            or "salon" in text
        )

    def get_last_service_query(self, state: GraphState) -> str | None:
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
