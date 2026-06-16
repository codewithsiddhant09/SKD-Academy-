from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.enums import IntentType
from app.models.schemas import IntentAnalysis
from app.prompts.system_prompt import build_system_prompt
from app.utils.text import normalize_text

logger = get_logger(__name__)


class IntentAgent:
    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        self._llm = None
        if settings.openai_api_key:
            self._llm = ChatOpenAI(
                model=settings.openai_model,
                api_key=settings.openai_api_key,
                temperature=0,
            ).with_structured_output(IntentAnalysis)

    # Words that indicate a request to list salons/vendors (no specific service).
    _SALON_TARGET_WORDS = ("salon", "salons", "vendor", "vendors", "parlour", "parlor", "shop", "shops")
    _SERVICE_WORDS = (
        "hair", "haircut", "smoothing", "smoothening", "keratin", "color", "colour", "coloring",
        "colouring", "makeup", "make up", "facial", "wax", "waxing", "pedicure", "manicure",
        "nail", "nails", "henna", "spa", "massage", "bridal", "threading", "beard", "shave",
        "grooming", "treatment",
    )

    def _heuristic(self, message: str, categories: list[str]) -> IntentAnalysis:
        text = normalize_text(message)
        category = next((c for c in categories if normalize_text(c) in text), None)
        has_service_word = any(s in text for s in self._SERVICE_WORDS)

        # Check for cancellation
        if any(k in text for k in ["cancel", "cancellation"]):
            logger.info("INTENT: APPOINTMENT_CANCELLATION detected (heuristic)")
            return IntentAnalysis(intent=IntentType.APPOINTMENT_CANCELLATION)

        # Check for policy/FAQ keywords first (informational questions)
        faq_keywords = [
            "policy", "terms", "refund", "privacy",
            "faq", "how", "what", "why", "can i", "do i",
            "bookly", "mission", "vision", "payment", "methods",
            "cancel fee", "cancellation fee", "refund policy",
        ]
        if any(k in text for k in faq_keywords):
            logger.info("INTENT: FAQ detected (heuristic) - keywords: %s", [k for k in faq_keywords if k in text])
            return IntentAnalysis(intent=IntentType.FAQ)

        # Salon/vendor LIST request without a specific service -> SALON_SEARCH (no category)
        if any(w in text for w in self._SALON_TARGET_WORDS) and not has_service_word:
            logger.info("INTENT: SALON_SEARCH detected (heuristic)")
            return IntentAnalysis(intent=IntentType.SALON_SEARCH)

        # Check for booking (specific service/salon context)
        if any(k in text for k in ["book", "appointment", "reserve"]):
            logger.info("INTENT: APPOINTMENT_BOOKING detected (heuristic)")
            service = message.strip() if has_service_word else None
            return IntentAnalysis(intent=IntentType.APPOINTMENT_BOOKING, category=category, service=service)

        # Specific service mentioned -> SERVICE_SEARCH
        if has_service_word or any(k in text for k in ["find salon", "recommend", "looking for"]):
            logger.info("INTENT: SERVICE_SEARCH detected (heuristic)")
            service = message.strip() if has_service_word else None
            return IntentAnalysis(intent=IntentType.SERVICE_SEARCH, category=category, service=service)

        logger.info("INTENT: GENERAL_CONVERSATION detected (heuristic)")
        return IntentAnalysis(intent=IntentType.GENERAL_CONVERSATION)

    def analyze(self, message: str, categories: list[str], history: list[dict[str, str]]) -> IntentAnalysis:
        logger.info("QUESTION: %s", message)
        
        if not self._llm:
            logger.info("Using heuristic intent detection (LLM not available)")
            return self._heuristic(message, categories)

        logger.info("Using LLM for intent detection")
        prompt = build_system_prompt(categories)
        history_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])
        
        # Enhanced user message with clear instructions
        user_message = (
            "Analyze the user's message and return ONLY a JSON object with these fields:\n"
            "- intent: MUST be one of: faq, policy, appointment_cancellation, appointment_booking, "
            "service_search, salon_search, location_search, salon_discovery, general_conversation\n"
            "- category: category from the available list ONLY if a service is named (optional, can be null)\n"
            "- service: the specific service name ONLY if named (optional, can be null)\n"
            "- location: the city/area if mentioned, e.g. 'in Noida' -> 'Noida' (optional, can be null)\n\n"
            "IMPORTANT RULES:\n"
            "1. For ANY question starting with 'What', 'Why', 'How', 'Do', 'Can', or containing keywords like "
            "'bookly', 'mission', 'payment', 'methods', 'policy', 'refund', 'cancel' - use intent='faq' or 'policy'.\n"
            "2. If the user asks for a LIST of salons/vendors (e.g. 'show salons in Noida', 'give vendor list in Noida') "
            "and does NOT name a specific service, use intent='salon_search' and set BOTH service AND category to null.\n"
            "3. NEVER assume a category when no specific service is mentioned.\n"
            "4. Extract location independently whenever a place is mentioned.\n"
            "5. Never use 'general_conversation' for informational questions.\n\n"
            f"Conversation history (for context):\n{history_text}\n\n"
            f"User input: {message}"
        )
        
        structured = self._llm.invoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=user_message),
            ]
        )
        logger.info("INTENT: %s (from LLM)", structured.intent)
        return structured
