import pytest

from app.core.config import get_settings

# Live evaluation: needs a real OpenAI key (embeddings + chat).
pytestmark = pytest.mark.skipif(not get_settings().openai_api_key, reason="OPENAI_API_KEY not set")


def test_rag_evaluation():
    from app.api import deps
    from app.rag.evaluation import RAGEvaluator

    deps.initialize_dependencies()
    report = RAGEvaluator().run()

    assert report["summary"]["cases"] >= 1
    assert report["summary"]["retrieval_accuracy"] >= 0.8
    for result in report["results"]:
        assert result["chat"]["status_code"] == 200
        assert result["chat"]["reply"]
