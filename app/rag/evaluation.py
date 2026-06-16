from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from app.rag.vector_store import RagStore, load_docs_from_directory


@dataclass
class QACase:
    name: str
    message: str
    expected_source: str
    expected_keywords: list[str]
    expected_answer_terms: list[str]


EVALUATION_CASES: list[QACase] = [
    QACase(
        name="faq_booking",
        message="How do I book an appointment?",
        expected_source="faqs.md",
        expected_keywords=["book an appointment"],
        expected_answer_terms=["book", "salon", "service", "date", "time"],
    ),
    QACase(
        name="faq_cancel",
        message="Can I cancel my appointment?",
        expected_source="faqs.md",
        expected_keywords=["cancel", "cancellation", "appointment", "salon's cancellation terms"],
        expected_answer_terms=["cancel", "cancellation", "terms"],
    ),
    QACase(
        name="faq_refund",
        message="What is the refund policy?",
        expected_source="policies.md",
        expected_keywords=["refund policy", "refunds depend"],
        expected_answer_terms=["refund", "salon-specific", "terms"],
    ),
    QACase(
        name="faq_privacy",
        message="What does Bookly do with my data?",
        expected_source="policies.md",
        expected_keywords=["customer data", "privacy policy"],
        expected_answer_terms=["privacy", "customer data", "processes"],
    ),
    QACase(
        name="faq_recommendation",
        message="How is a salon recommendation generated?",
        expected_source="faqs.md",
        expected_keywords=["recommendation generated", "distance", "rating", "availability"],
        expected_answer_terms=["service fit", "distance", "rating", "availability"],
    ),
]


class RAGEvaluator:
    def __init__(self) -> None:
        self.client = TestClient(app)
        self.store = RagStore()
        self.document_path = Path(__file__).resolve().parent / "documents"
        self.documents = load_docs_from_directory(self.document_path)

    def _match_expected(self, text: str, keywords: list[str]) -> bool:
        normalized = text.lower()
        return any(keyword.lower() in normalized for keyword in keywords)

    def evaluate_retrieval(self, case: QACase) -> dict[str, Any]:
        retriever = self.store.as_retriever()
        retrieved = []
        success = False
        try:
            if hasattr(retriever, "invoke"):
                docs = retriever.invoke(case.message)
            elif hasattr(retriever, "get_relevant_documents"):
                docs = retriever.get_relevant_documents(case.message)
            else:
                docs = []

            for doc in docs:
                content = getattr(doc, "page_content", str(doc))
                retrieved.append(content)
                if self._match_expected(content, case.expected_keywords):
                    success = True
        except Exception as exc:
            retrieved = [f"retrieval_error: {exc}"]
            success = False

        return {
            "case": case.name,
            "retrieved_count": len(retrieved),
            "retrieved_texts": retrieved,
            "retrieval_match": success,
        }

    def evaluate_chat(self, client: TestClient, case: QACase, session_id: str) -> dict[str, Any]:
        response = client.post(
            "/chat",
            json={"session_id": session_id, "message": case.message},
        )
        payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        reply = payload.get("reply", "") if isinstance(payload, dict) else ""
        reply_match = self._match_expected(reply, case.expected_answer_terms)

        return {
            "case": case.name,
            "status_code": response.status_code,
            "reply": reply,
            "reply_match": reply_match,
            "structured": payload.get("structured") if isinstance(payload, dict) else None,
        }

    def run(self) -> dict[str, Any]:
        recovery = []
        with self.client as client:
            for case in EVALUATION_CASES:
                retrieval = self.evaluate_retrieval(case)
                chat = self.evaluate_chat(client, case, session_id=f"eval-{case.name}")
                recovery.append({"case": case.name, "retrieval": retrieval, "chat": chat})

        retrieval_success = sum(1 for item in recovery if item["retrieval"]["retrieval_match"])
        chat_success = sum(1 for item in recovery if item["chat"]["status_code"] == 200 and item["chat"]["reply_match"])
        total = len(recovery)

        report = {
            "summary": {
                "cases": total,
                "retrieval_success_count": retrieval_success,
                "chat_success_count": chat_success,
                "retrieval_accuracy": retrieval_success / total,
                "chat_accuracy": chat_success / total,
            },
            "results": recovery,
        }
        return report


def main(output_path: Path | str = "rag_evaluation_report.json") -> dict[str, Any]:
    evaluator = RAGEvaluator()
    report = evaluator.run()
    Path(output_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"RAG evaluation report written to {output_path}")
    return report


if __name__ == "__main__":
    main()
