from typing import Dict
from services.openai_service import OpenAIService
import logging

logger = logging.getLogger("bookly.agents.intent")


class IntentAgent:
    def __init__(self):
        self.openai = OpenAIService()

    def predict_intent_sync(self, text: str) -> Dict:
        try:
            result = self.openai.detect_intent(text)
            # Normalize result
            intent = result.get("intent") if isinstance(result, dict) else str(result)
            return {"intent": intent, "raw": result}
        except Exception:
            logger.exception("Intent detection failed")
            return {"intent": "FAQ", "raw": {}}

    async def predict_intent(self, text: str) -> Dict:
        return self.predict_intent_sync(text)
