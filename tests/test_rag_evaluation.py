from app.rag.evaluation import RAGEvaluator
from app.api import deps


def test_rag_evaluation_retrieval():
    deps.initialize_dependencies()
    evaluator = RAGEvaluator()
    report = evaluator.run()

    assert report["summary"]["cases"] >= 1
    assert report["summary"]["retrieval_accuracy"] >= 0.8
    assert report["summary"]["chat_accuracy"] >= 0.8


def test_chat_endpoint_with_startup():
    deps.initialize_dependencies()
    evaluator = RAGEvaluator()
    report = evaluator.run()

    for result in report["results"]:
        assert result["chat"]["status_code"] == 200
        assert result["chat"]["reply"]
