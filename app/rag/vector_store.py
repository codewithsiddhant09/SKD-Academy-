from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def chunk_text(text: str, chunk_size: int = 700, chunk_overlap: int = 100) -> list[str]:
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunks.append(text[start:end])
        if end >= length:
            break
        start = max(start + chunk_size - chunk_overlap, end)
    return chunks


class RagStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        persist_dir = Path(self.settings.rag_persist_directory)
        persist_dir.mkdir(parents=True, exist_ok=True)

        self._embeddings = OpenAIEmbeddings(
            model=self.settings.openai_embedding_model,
            api_key=self.settings.openai_api_key,
        )
        self._vectorstore = Chroma(
            collection_name=self.settings.rag_collection_name,
            persist_directory=str(persist_dir),
            embedding_function=self._embeddings,
        )

    def upsert_documents(self, docs: list[Document]) -> None:
        chunks: list[Document] = []
        for doc in docs:
            text = doc.page_content
            metadata = dict(doc.metadata or {})
            for index, chunk in enumerate(chunk_text(text, chunk_size=700, chunk_overlap=100)):
                chunks.append(Document(page_content=chunk, metadata={**metadata, "chunk_index": index}))
        if chunks:
            self._vectorstore.add_documents(chunks)

    def retrieve_with_scores(self, query: str, top_k: int | None = None) -> List[Tuple[Document, float]]:
        top_k = top_k or self.settings.top_k_retrieval
        results = self._vectorstore.similarity_search_with_score(query, k=top_k * 3)
        unique: list[Tuple[Document, float]] = []
        seen: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
        for doc, score in results:
            metadata_tuple = tuple(sorted((doc.metadata or {}).items()))
            key = (doc.page_content, metadata_tuple)
            if key in seen:
                continue
            seen.add(key)
            unique.append((doc, score))
            if len(unique) >= top_k:
                break
        return unique

    def as_retriever(self):
        return self._vectorstore.as_retriever(search_kwargs={"k": self.settings.top_k_retrieval})

    def is_ready(self) -> bool:
        try:
            self._vectorstore.get(limit=1)
            return True
        except Exception:
            return False


def create_rag_store() -> RagStore | None:
    """Create RagStore or return None when ChromaDB is unavailable (e.g. readonly DB)."""
    try:
        return RagStore()
    except Exception as exc:
        logger.warning("RAG vector store unavailable: %s", exc)
        return None


def load_docs_from_directory(path: Path) -> list[Document]:
    docs: list[Document] = []
    for file_path in path.glob("*.md"):
        text = file_path.read_text(encoding="utf-8")
        docs.append(Document(page_content=text, metadata={"source": str(file_path.name)}))
    return docs
