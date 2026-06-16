from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import DebugRagResponse
from app.rag.vector_store import create_rag_store

logger = get_logger(__name__)


class FaqAgent:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._store = create_rag_store() if self._settings.openai_api_key else None
        self._llm = (
            ChatOpenAI(
                model=self._settings.openai_model,
                api_key=self._settings.openai_api_key,
                temperature=0,
            )
            if self._settings.openai_api_key
            else None
        )

    def answer(self, question: str) -> str:
        debug_result = self.debug_answer(question)
        return debug_result.answer

    def debug_answer(self, question: str) -> DebugRagResponse:
        logger.info("RAG debug query: %s", question)

        if not self._llm or not self._store:
            explanation = (
                "RAG is unavailable because the OpenAI API key or vector store is not configured. "
                "Ensure environment variables and vector data are set up."
            )
            logger.info("RAG debug explanation: %s", explanation)
            return DebugRagResponse(
                question=question,
                retrieved_chunks=[],
                similarity_scores=[],
                context="",
                prompt="",
                answer=explanation,
                explanation=explanation,
            )

        docs_with_scores = self._store.retrieve_with_scores(question, top_k=self._settings.top_k_retrieval)
        retrieved_chunks = [doc.page_content for doc, _ in docs_with_scores]
        similarity_scores = [score for _, score in docs_with_scores]
        context = retrieved_chunks

        if not retrieved_chunks:
            explanation = (
                "No chunks were retrieved because the query did not match any documents in the Bookly knowledge base. "
                "Please ask a question covered by Bookly FAQs or policies."
            )
            logger.info("RAG debug no chunks: %s", explanation)
            return DebugRagResponse(
                question=question,
                retrieved_chunks=[],
                similarity_scores=[],
                context="",
                prompt="",
                answer=(
                    "I apologize, but I do not have enough information to answer that at this time. "
                    "Please contact our support team for further assistance."
                ),
                explanation=explanation,
            )

        context_text = "\n\n---\n\n".join(retrieved_chunks)
        system_prompt = (
            "You are Bookly AI Assistant — a professional, polite, and service-oriented booking assistant. "
            "Answer questions using only the provided Bookly context. "
            "Do not use any outside knowledge or general world knowledge. "
            "Keep responses concise, accurate, and structured. "
            "Do not use filler words such as: Awesome, Great, Cool, Amazing, Perfect. "
            "If the answer is not present in the context, respond with: "
            "'I apologize, but I do not have enough information to answer that at this time. "
            "Please contact our support team for further assistance.'"
        )
        prompt = (
            f"{system_prompt}\n\n"
            f"Context:\n{context_text}\n\n"
            f"Question: {question}"
        )

        result = self._llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Context:\n{context_text}\n\nQuestion: {question}"),
            ]
        )

        answer = result.content.strip()
        if not answer:
            explanation = "The model returned an empty answer despite retrieved chunks."
        elif "do not have enough information" in answer.lower() or "not enough information" in answer.lower() or "i don't know" in answer.lower():
            explanation = "Chunks were retrieved, but the answer was not contained in the provided context."
        else:
            explanation = "Chunks were retrieved and included in the prompt. The answer is grounded on Bookly context only."

        logger.info("RAG debug retrieved_chunks: %s", retrieved_chunks)
        logger.info("RAG debug similarity_scores: %s", similarity_scores)
        logger.info("RAG debug final_context: %s", context_text)
        logger.info("RAG debug prompt: %s", prompt)
        logger.info("RAG debug answer: %s", answer)
        logger.info("RAG debug explanation: %s", explanation)

        return DebugRagResponse(
            question=question,
            retrieved_chunks=retrieved_chunks,
            similarity_scores=similarity_scores,
            context=context_text,
            prompt=prompt,
            answer=answer,
            explanation=explanation,
        )
