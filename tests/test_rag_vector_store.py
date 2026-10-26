from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document

from app.core.config import get_settings
from app.rag import vector_store
from app.api import deps
from app.api.router import api_router
from app.models.schemas import Category
from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0, 0.0, 0.0] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 1.0, 0.0, 0.0]


def test_persistent_store_adds_and_retrieves_documents_without_losing_data(
    tmp_path: Path, monkeypatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "rag_persist_directory", str(tmp_path / "chroma"))
    monkeypatch.setattr(settings, "rag_collection_name", "rag_test")
    monkeypatch.setattr(vector_store, "OpenAIEmbeddings", lambda **_: FakeEmbeddings())

    store = vector_store.RagStore()
    store.upsert_documents(
        [Document(page_content="Bookly cancellation policy details", metadata={"source": "policies.md"})]
    )

    assert store.count() == 1
    assert store.is_ready()
    results = store.retrieve_with_scores("cancellation policy", top_k=1)
    assert len(results) == 1
    assert results[0][0].metadata["source"] == "policies.md"
    assert "cancellation policy" in results[0][0].page_content

    reopened = vector_store.RagStore()
    assert reopened.count() == 1
    assert reopened.retrieve_with_scores("cancellation policy", top_k=1)[0][0].metadata["source"] == "policies.md"


def test_health_and_categories_routes_report_initialized_rag(monkeypatch) -> None:
    class TestCategories:
        def get_categories(self, force_refresh: bool = False) -> list[Category]:
            return [Category(id="test-category", name="Hair")]

        def is_cached(self) -> bool:
            return True

    class TestKnowledge:
        def is_ready(self) -> bool:
            return True

    class TestAssistant:
        knowledge = TestKnowledge()

    from app.api.routes import categories as categories_route

    monkeypatch.setattr(categories_route, "category_service", TestCategories())
    monkeypatch.setattr(deps, "assistant", TestAssistant())
    app = FastAPI()
    app.include_router(api_router)
    client = TestClient(app)

    health = client.get("/api/v1/health")
    categories = client.get("/api/v1/categories")

    assert health.status_code == 200
    assert health.json()["rag_ready"] is True
    assert categories.status_code == 200
    assert categories.json() == [{"id": "test-category", "name": "Hair"}]
