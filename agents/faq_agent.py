from typing import Optional
from rag.retriever import Retriever
from services.openai_service import OpenAIService
import logging

logger = logging.getLogger("bookly.agents.faq")


class FAQAgent:
    def __init__(self):
        self.retriever = Retriever()
        self.openai = OpenAIService()

    def answer_question_sync(self, question: str) -> str:
        # Retrieve context
        contexts = self.retriever.retrieve(question, top_k=3)
        if not contexts:
            return "I couldn't find that information in Bookly's knowledge base."

        combined = "\n---\n".join(contexts)
        try:
            answer = self.openai.generate_answer(question, context=combined)
            # If answer is not helpful, enforce fallback
            if not answer or "I don't know" in answer or len(answer) < 5:
                return "I couldn't find that information in Bookly's knowledge base."
            return answer
        except Exception as e:
            logger.exception("FAQ generation failed: %s", e)
            return "I couldn't find that information in Bookly's knowledge base."

    async def answer_question(self, question: str) -> str:
        return self.answer_question_sync(question)
