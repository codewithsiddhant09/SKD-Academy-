import os
import logging
from typing import List, Optional

logger = logging.getLogger("bookly.openai")

try:
    import openai
except ImportError:
    openai = None

api_key = os.getenv("OPENAI_API_KEY", "").strip().strip('"')
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


class OpenAIService:
    def __init__(self, model: Optional[str] = None):
        self.model = model or DEFAULT_MODEL
        self.api_key = api_key

    def detect_intent(self, text: str) -> dict:
        if not self.api_key or openai is None:
            logger.warning("OpenAI not configured - using default intent")
            # Simple rule-based fallback
            lc = text.lower()
            if any(k in lc for k in ["refund", "cancel", "policy"]):
                intent = "Policy"
            elif any(k in lc for k in ["who are you", "about", "bookly"]):
                intent = "AboutUs"
            elif any(k in lc for k in ["book", "appointment", "reserve"]):
                intent = "Booking"
            elif any(k in lc for k in ["salon", "near me", "find", "location"]):
                intent = "SalonSearch"
            else:
                intent = "FAQ"
            return {"intent": intent, "confidence": 0.5}

        try:
            openai.api_key = self.api_key
            prompt = (
                "Classify the intent of the user's message into one of: FAQ, Policy, AboutUs, Booking, SalonSearch. "
                "Return a single JSON object with key 'intent'.\n\nUser message: " + text
            )
            resp = openai.ChatCompletion.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0
            )
            content = resp["choices"][0]["message"]["content"].strip()
            import json
            try:
                parsed = json.loads(content)
            except Exception:
                parsed = {"intent": "FAQ", "confidence": 0.5}
            return parsed
        except Exception as e:
            logger.exception("Intent detection via OpenAI failed: %s", e)
            return {"intent": "FAQ", "confidence": 0.3}

    def generate_answer(self, prompt: str, context: Optional[str] = None) -> str:
        if not self.api_key or openai is None:
            logger.warning("OpenAI not configured - returning fallback")
            return "I couldn't find that information in Bookly's knowledge base."

        try:
            openai.api_key = self.api_key
            system = "You are Bookly AI assistant. Use the provided context to answer the user. If the answer is not in the context, say you couldn't find it. Never hallucinate."
            messages = [{"role": "system", "content": system}]
            if context:
                messages.append({"role": "system", "content": f"Context:\n{context}"})
            messages.append({"role": "user", "content": prompt})

            resp = openai.ChatCompletion.create(
                model=self.model,
                messages=messages,
                max_tokens=512,
                temperature=0.2
            )
            answer = resp["choices"][0]["message"]["content"].strip()
            return answer if answer else "I couldn't find that information in Bookly's knowledge base."
        except Exception as e:
            logger.exception("Answer generation failed: %s", e)
            return "I couldn't find that information in Bookly's knowledge base."
