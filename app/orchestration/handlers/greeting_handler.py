from __future__ import annotations

import re

from app.models.enums import IntentType
from app.orchestration.models import HandlerResult, OrchestrationContext


class GreetingHandler:
    _GREETING = (
        "Hello!\n\n"
        "Welcome to Bookly.\n\n"
        "I'm here to help you discover salons, answer your questions, and book appointments.\n\n"
        "How may I assist you today?"
    )
    _HOW_ARE_YOU = (
        "Hello!\n\n"
        "Welcome to Bookly.\n\n"
        "I'm doing well, thank you for asking.\n\n"
        "I'm here to help you discover salons, answer your questions, and book appointments.\n\n"
        "How may I assist you today?"
    )
    _THANKS = (
        "You're most welcome.\n\n"
        "Please let me know if there is anything else I can help you with."
    )
    _GOODBYE = (
        "Thank you for visiting Bookly.\n\n"
        "Have a wonderful day, and feel free to return whenever you need assistance."
    )

    @classmethod
    def match_reply(cls, message: str) -> str | None:
        text = re.sub(r"[^\w\s]", " ", message.lower())
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return None
        domain = {
            "book", "booking", "appointment", "salon", "cancel", "policy", "refund",
            "category", "hair", "makeup", "facial", "henna",
        }
        if any(w in text.split() or w in text for w in domain):
            return None
        if text in {"thanks", "thank you", "thank u", "thx", "ty"} or text.startswith("thank "):
            return cls._THANKS
        if "how are you" in text or "how r u" in text:
            return cls._HOW_ARE_YOU
        if text in {"bye", "goodbye", "good night", "goodnight"}:
            return cls._GOODBYE
        greetings = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}
        if text in greetings or any(text.startswith(g + " ") for g in greetings):
            return cls._GREETING
        return None

    def handle(self, ctx: OrchestrationContext) -> HandlerResult:
        reply = self.match_reply(ctx.user_message) or self._GREETING
        return HandlerResult(intent=IntentType.SMALL_TALK, reply=reply)
