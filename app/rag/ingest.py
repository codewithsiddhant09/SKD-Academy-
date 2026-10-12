"""Rebuild the knowledge base from app/rag/documents/*.md: python -m app.rag.ingest"""
import shutil
from pathlib import Path

from app.core.config import get_settings
from app.rag.vector_store import RagStore, load_docs_from_directory

DOCUMENTS_DIR = Path(__file__).resolve().parent / "documents"


def ingest_rag_documents() -> None:
    docs = load_docs_from_directory(DOCUMENTS_DIR)
    if not docs:
        return
    shutil.rmtree(get_settings().rag_persist_directory, ignore_errors=True)
    RagStore().upsert_documents(docs)


if __name__ == "__main__":
    ingest_rag_documents()
