"""Semantic intent classification — meaning over exact keywords (orchestration only)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.logging import get_logger
from app.models.enums import IntentType

logger = get_logger(__name__)

# Confidence thresholds
_ROUTE_THRESHOLD = 0.65
_HIGH_CONFIDENCE = 0.85


@dataclass(frozen=True)
class SemanticIntentResult:
    intent: IntentType
    confidence: float
    reason: str

    @property
    def confidence_pct(self) -> int:
        return int(round(self.confidence * 100))


class SemanticIntentClassifier:
    """Maps paraphrased user messages to normalized intents using semantic signal clusters."""

    _APP_PLATFORM_REFS = (
        "this application",
        "this app",
        "this platform",
        "this software",
        "the application",
        "the app",
        "the platform",
        "the software",
        "your application",
        "your app",
        "your platform",
        "this service app",
    )

    _INTRO_ASK_SIGNALS = (
        "introduction",
        "introduce",
        "introduce yourself",
        "overview",
        "tell me about",
        "tell me more",
        "explain",
        "describe",
        "what is",
        "what are",
        "what does",
        "what can",
        "what exactly",
        "how does",
        "how do",
        "how can i use",
        "who is",
        "about",
        "give me an introduction",
        "give me introduction",
        "can you explain",
    )

    _AI_IDENTITY_SIGNALS = (
        "who are you",
        "what are you",
        "who am i chatting",
        "who am i talking",
        "who is this assistant",
        "who is this chatbot",
        "who is this bot",
        "introduce yourself",
        "what is your name",
        "what can you do",
        "how can you help",
        "how can you assist",
        "are you an ai",
        "are you ai",
        "are you a bot",
        "are you a chatbot",
        "what is this chatbot",
        "what is this bot",
        "what is this assistant",
        "who is this",
    )

    _BOOKING_SIGNALS = (
        "book appointment",
        "book a salon",
        "book an appointment",
        "i need an appointment",
        "i need appointment",
        "reserve appointment",
        "reserve a",
        "schedule appointment",
        "schedule a",
        "help me book",
        "i want to book",
        "i need to book",
        "i want booking",
        "need booking",
        "can you schedule",
        "can you book",
        "make an appointment",
        "make appointment",
        "set up an appointment",
        "salon booking",
    )

    _CATEGORY_LIST_SIGNALS = (
        "available services",
        "available categories",
        "list categories",
        "list all categories",
        "show categories",
        "show all categories",
        "service list",
        "category list",
        "list all services",
        "list services",
        "what services do you have",
        "what services do you offer",
        "what categories",
        "which categories",
        "what categories are available",
        "give me category list",
        "service categories",
    )

    _SALON_SEARCH_SIGNALS = (
        "nearby salons",
        "recommend salons",
        "salon near me",
        "salons near me",
        "find salon",
        "find salons",
        "show salons",
        "best salon",
        "suggest salon",
        "suggest salons",
        "recommend a salon",
    )

    _FAQ_POLICY_SIGNALS = (
        "cancellation policy",
        "cancel policy",
        "refund policy",
        "privacy policy",
        "terms and conditions",
        "terms of service",
        "payment methods",
        "working hours",
        "refund",
        "privacy",
        "terms",
    )

    _SERVICE_WORDS = (
        "hair", "makeup", "facial", "nail", "nails", "henna", "spa", "wax",
        "smoothing", "keratin", "massage", "bridal", "threading", "grooming",
    )

    @staticmethod
    def normalize(text: str) -> str:
        cleaned = re.sub(r"[^\w\s']", " ", text.lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    def _has_service_word(self, text: str) -> bool:
        return any(w in text for w in self._SERVICE_WORDS)

    def _mentions_ai(self, text: str) -> bool:
        if any(s in text for s in self._AI_IDENTITY_SIGNALS):
            return True
        if "chatbot" in text or "this bot" in text:
            return True
        if any(s in text for s in ("assistant", " chat bot", " ai ")):
            if any(s in text for s in ("who", "what are you", "introduce", "are you")):
                return True
        return False

    def _mentions_app_platform(self, text: str) -> bool:
        return "bookly" in text or any(ref in text for ref in self._APP_PLATFORM_REFS)

    def _mentions_intro_ask(self, text: str) -> bool:
        return any(sig in text for sig in self._INTRO_ASK_SIGNALS)

    def _score_platform(self, text: str) -> SemanticIntentResult | None:
        if self._mentions_ai(text):
            return None

        bookly = "bookly" in text
        app_ref = any(ref in text for ref in self._APP_PLATFORM_REFS)
        intro = self._mentions_intro_ask(text)
        platform_word = any(w in text for w in ("platform", "application", "software")) or " app" in f" {text} "

        # Explicit Bookly questions
        if bookly and intro:
            return SemanticIntentResult(
                IntentType.BOOKLY_PLATFORM_INFORMATION,
                0.98,
                "User is asking about Bookly (named explicitly).",
            )
        if bookly:
            return SemanticIntentResult(
                IntentType.BOOKLY_PLATFORM_INFORMATION,
                0.92,
                "User mentioned Bookly in an informational context.",
            )

        # "Give me introduction about this application" — Bookly chat context
        if app_ref and intro:
            return SemanticIntentResult(
                IntentType.BOOKLY_PLATFORM_INFORMATION,
                0.96,
                "User is asking for an introduction to this application (Bookly context).",
            )

        # "What does this platform do?", "How does this software work?"
        if (app_ref or platform_word) and intro:
            return SemanticIntentResult(
                IntentType.BOOKLY_PLATFORM_INFORMATION,
                0.90,
                "User is asking how the platform/application works.",
            )

        # "What services does this app provide?" — about Bookly, not category API list
        if (app_ref or bookly) and "service" in text and any(
            w in text for w in ("provide", "offer", "does", "do", "can", "what")
        ):
            return SemanticIntentResult(
                IntentType.BOOKLY_PLATFORM_INFORMATION,
                0.88,
                "User is asking what services the Bookly platform provides.",
            )

        return None

    def _score_ai(self, text: str) -> SemanticIntentResult | None:
        if any(sig in text for sig in self._AI_IDENTITY_SIGNALS):
            return SemanticIntentResult(
                IntentType.BOOKLY_AI_INFORMATION,
                0.97,
                "User is asking about the AI assistant.",
            )
        if text.startswith(("what can you", "how can you help", "how can you assist", "are you ")):
            return SemanticIntentResult(
                IntentType.BOOKLY_AI_INFORMATION,
                0.94,
                "User is asking about assistant capabilities or identity.",
            )
        if "bookly ai" in text or "bookly assistant" in text:
            return SemanticIntentResult(
                IntentType.BOOKLY_AI_INFORMATION,
                0.95,
                "User is asking about Bookly's AI assistant.",
            )
        return None

    def _score_faq(self, text: str) -> SemanticIntentResult | None:
        for sig in self._FAQ_POLICY_SIGNALS:
            if sig in text:
                intent = IntentType.POLICY if "policy" in sig or sig in {
                    "refund", "privacy", "terms and conditions", "terms of service",
                } else IntentType.FAQ
                return SemanticIntentResult(
                    intent,
                    0.93,
                    f"User is asking about {sig}.",
                )
        return None

    def _score_category_list(self, text: str) -> SemanticIntentResult | None:
        # "Tell me about Hair" is category detail, not a list request
        if re.search(r"\b(tell me about|explain|what is|describe)\s+\w", text):
            return None

        # Do not hijack platform questions about "what services does this app provide"
        if any(ref in text for ref in self._APP_PLATFORM_REFS) or "bookly" in text:
            if any(w in text for w in ("provide", "offer", "does", "do", "introduction", "explain")):
                return None

        if any(sig in text for sig in self._CATEGORY_LIST_SIGNALS):
            return SemanticIntentResult(
                IntentType.CATEGORY_LIST,
                0.91,
                "User wants a list of available service categories.",
            )

        words = text.split()
        if "category" in words or "categories" in words:
            return SemanticIntentResult(
                IntentType.CATEGORY_LIST,
                0.89,
                "User mentioned categories and likely wants the category list.",
            )

        if ("service" in text or "services" in text) and any(
            w in text for w in ("available", "list", "show", "have", "offer")
        ):
            if not self._has_service_word(text):
                return SemanticIntentResult(
                    IntentType.CATEGORY_LIST,
                    0.86,
                    "User is asking which services/categories are available.",
                )
        return None

    def _score_salon_search(self, text: str) -> SemanticIntentResult | None:
        if any(sig in text for sig in self._SALON_SEARCH_SIGNALS):
            return SemanticIntentResult(
                IntentType.SALON_SEARCH,
                0.88,
                "User wants salon recommendations or a salon list.",
            )
        if "salon" in text and any(w in text for w in ("near", "nearby", "find", "show", "list", "recommend")):
            if not self._has_service_word(text):
                return SemanticIntentResult(
                    IntentType.SALON_SEARCH,
                    0.85,
                    "User is searching for salons without naming a specific service.",
                )
        return None

    def _score_booking(self, text: str) -> SemanticIntentResult | None:
        if any(sig in text for sig in self._BOOKING_SIGNALS):
            return SemanticIntentResult(
                IntentType.APPOINTMENT_BOOKING,
                0.90,
                "User wants to book or schedule an appointment.",
            )
        if any(w in text for w in ("book", "reserve", "schedule")) and (
            self._has_service_word(text) or "appointment" in text or "salon" in text
        ):
            return SemanticIntentResult(
                IntentType.APPOINTMENT_BOOKING,
                0.87,
                "User expressed booking intent with service or salon context.",
            )
        if text.startswith(("need appointment", "need an appointment", "need booking")):
            return SemanticIntentResult(
                IntentType.APPOINTMENT_BOOKING,
                0.88,
                "User needs an appointment.",
            )
        return None

    def classify(self, message: str) -> SemanticIntentResult | None:
        """Return the best semantic intent if confidence meets the routing threshold."""
        text = self.normalize(message)
        if not text:
            return None

        candidates: list[SemanticIntentResult] = []

        for scorer in (
            self._score_faq,
            self._score_ai,
            self._score_platform,
            self._score_booking,
            self._score_category_list,
            self._score_salon_search,
        ):
            result = scorer(text)
            if result:
                candidates.append(result)

        if not candidates:
            return None

        # Prefer highest confidence; FAQ/policy wins ties at equal confidence over platform
        best = max(candidates, key=lambda c: c.confidence)
        if best.confidence < _ROUTE_THRESHOLD:
            return None

        logger.info(
            "SEMANTIC_INTENT: %s confidence=%s%% reason=%s",
            best.intent.value,
            best.confidence_pct,
            best.reason,
        )
        return best

    def is_platform_question(self, message: str) -> bool:
        result = self._score_platform(self.normalize(message))
        return result is not None and result.confidence >= _ROUTE_THRESHOLD

    def is_ai_question(self, message: str) -> bool:
        result = self._score_ai(self.normalize(message))
        return result is not None and result.confidence >= _ROUTE_THRESHOLD

    def is_category_list(self, message: str) -> bool:
        result = self._score_category_list(self.normalize(message))
        return result is not None and result.confidence >= _ROUTE_THRESHOLD
