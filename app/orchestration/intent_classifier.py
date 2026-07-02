from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agents.semantic_intent_classifier import SemanticIntentClassifier
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.enums import IntentType
from app.models.schemas import IntentAnalysis
from app.orchestration.prompts.intent_classification import build_intent_classification_prompt
from app.utils.text import normalize_text

logger = get_logger(__name__)


class IntentClassifier:
    """Classify intent only — never generate user-facing answers."""

    _CATEGORY_DETAIL_PATTERNS = (
        r"tell me about\s+(?P<cat>.+)",
        r"tell me more about\s+(?P<cat>.+)",
        r"explain\s+(?P<cat>.+)",
        r"what is\s+(?P<cat>.+?)(?:\?|$)",
        r"what are\s+(?P<cat>.+?)(?:\?|$)",
        r"describe\s+(?P<cat>.+)",
        r"info(?:rmation)?\s+(?:on|about)\s+(?P<cat>.+)",
    )

    _NEED_SERVICE_PATTERN = re.compile(
        r"^need\s+(?P<service>.+)$",
        re.IGNORECASE,
    )

    def __init__(self, categories: list[str]) -> None:
        self.categories = categories
        self._semantic = SemanticIntentClassifier()
        settings = get_settings()
        self._llm = None
        if settings.openai_api_key:
            self._llm = ChatOpenAI(
                model=settings.openai_model,
                api_key=settings.openai_api_key,
                temperature=0,
            ).with_structured_output(IntentAnalysis)

    def classify(
        self,
        message: str,
        history: list[dict[str, str]],
        *,
        category_names: list[str] | None = None,
    ) -> IntentAnalysis:
        names = category_names or self.categories
        logger.info("INTENT_CLASSIFIER: %s", message)

        need_match = self._NEED_SERVICE_PATTERN.match(message.strip())
        if need_match:
            service = need_match.group("service").strip(" .?!")
            category = self._match_category(service, names)
            logger.info("INTENT_CLASSIFIER: need-service -> service_search service=%s", service)
            return IntentAnalysis(
                intent=IntentType.SERVICE_SEARCH,
                service=service,
                category=category,
                confidence=0.94,
                reason="User expressed need for a specific service.",
            )

        semantic = self._semantic.classify(message)
        if semantic and semantic.intent != IntentType.GENERAL_CONVERSATION:
            return IntentAnalysis(
                intent=semantic.intent,
                confidence=semantic.confidence,
                reason=semantic.reason,
            )

        category_detail = self._detect_category_detail(message, names)
        if category_detail:
            return IntentAnalysis(
                intent=IntentType.CATEGORY_DETAIL,
                category=category_detail,
                confidence=0.92,
                reason=f"User asked about the {category_detail} category.",
            )

        if self._is_small_talk(message):
            return IntentAnalysis(
                intent=IntentType.SMALL_TALK,
                confidence=0.95,
                reason="Greeting or conversational small talk.",
            )

        if not self._llm:
            return self._heuristic(message, names)

        prompt = build_intent_classification_prompt(names)
        history_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])
        user_message = (
            "Return ONLY structured classification fields (intent, category, service, location).\n"
            "Do NOT generate a reply.\n\n"
            f"History:\n{history_text}\n\nUser: {message}"
        )
        result = self._llm.invoke(
            [SystemMessage(content=prompt), HumanMessage(content=user_message)]
        )
        logger.info("INTENT_CLASSIFIER: llm -> %s", result.intent)
        return result

    def _match_category(self, phrase: str, names: list[str]) -> str | None:
        lower_names = {n.lower(): n for n in names}
        text = normalize_text(phrase)
        if text in lower_names:
            return lower_names[text]
        for key, canonical in lower_names.items():
            if key in text or text in key:
                return canonical
        return None

    def _detect_category_detail(self, message: str, names: list[str]) -> str | None:
        text = normalize_text(message)
        if not text or self._semantic.is_category_list(message):
            return None
        lower_names = {n.lower(): n for n in names}

        for pattern in self._CATEGORY_DETAIL_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            candidate = match.group("cat").strip(" .?!")
            if candidate in lower_names:
                return lower_names[candidate]
            for key, canonical in lower_names.items():
                if candidate == key or candidate.startswith(key) or key in candidate:
                    return canonical

        if len(text.split()) <= 2 and text in lower_names:
            return lower_names[text]
        return None

    def _is_small_talk(self, message: str) -> bool:
        from app.orchestration.handlers.greeting_handler import GreetingHandler

        return GreetingHandler.match_reply(message) is not None

    def _heuristic(self, message: str, names: list[str]) -> IntentAnalysis:
        text = normalize_text(message)
        category = next((c for c in names if normalize_text(c) in text), None)
        service_words = (
            "hair", "makeup", "facial", "wax", "henna", "nail", "spa", "massage", "bridal",
        )
        has_service = any(w in text for w in service_words)

        if any(k in text for k in ("cancel", "cancellation")):
            return IntentAnalysis(intent=IntentType.APPOINTMENT_CANCELLATION)
        if any(k in text for k in ("policy", "refund", "privacy", "terms")):
            return IntentAnalysis(intent=IntentType.POLICY)
        if any(w in text for w in ("salon", "salons", "vendor")) and not has_service:
            return IntentAnalysis(intent=IntentType.SALON_SEARCH)
        if any(k in text for k in ("book", "appointment", "reserve", "schedule")):
            return IntentAnalysis(
                intent=IntentType.APPOINTMENT_BOOKING,
                category=category,
            )
        if has_service:
            return IntentAnalysis(
                intent=IntentType.SERVICE_SEARCH,
                category=category,
            )
        return IntentAnalysis(intent=IntentType.GENERAL_CONVERSATION)
