import shutil
from pathlib import Path

from app.rag.vector_store import RagStore, load_docs_from_directory


def ingest_rag_documents() -> None:
    base_path = Path(__file__).resolve().parent / "documents"
    docs = load_docs_from_directory(base_path)
    if not docs:
        return
    from app.core.config import get_settings
    settings = get_settings()
    persist_dir = Path(settings.rag_persist_directory)
    try:
        if persist_dir.exists():
            shutil.rmtree(persist_dir)
    except (OSError, PermissionError):
        pass
    store = RagStore()
    store.upsert_documents(docs)
