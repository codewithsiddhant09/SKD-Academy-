from typing import List
from rag.vector_store import ChromaVectorStore
import os


class Retriever:
    def __init__(self, persist_directory: str = None):
        self.store = ChromaVectorStore(persist_directory=persist_directory)

    def retrieve(self, query: str, top_k: int = 3) -> List[str]:
        results = self.store.similarity_search(query, top_k=top_k)
        # results may be texts
        return results[:top_k]
