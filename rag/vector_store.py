import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger("bookly.rag.vector_store")

try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils import embedding_functions
except Exception:
    chromadb = None


class ChromaVectorStore:
    def __init__(self, persist_directory: str = None, collection_name: str = "bookly"):
        self.persist_directory = persist_directory or os.getenv("CHROMADB_PERSIST_DIR", "vector_db")
        self.collection_name = collection_name
        self.client = None
        self.collection = None
        self._init()

    def _init(self):
        if chromadb is None:
            logger.warning("chromadb not installed - vector store disabled")
            return
        try:
            settings = Settings(
                persist_directory=self.persist_directory,
                anonymized_telemetry=False
            )
            self.client = chromadb.Client(settings=settings)
            
            # Try to get existing collection
            try:
                self.collection = self.client.get_collection(self.collection_name)
                logger.info("Loaded existing collection: %s", self.collection_name)
            except Exception:
                # Create new collection with default embeddings
                self.collection = self.client.create_collection(
                    self.collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
                logger.info("Created new collection: %s", self.collection_name)
        except Exception as e:
            logger.exception("Failed to init chromadb: %s", e)

    def add_documents(self, docs: List[Dict[str, Any]]):
        if not self.collection:
            logger.warning("No chroma collection available - skipping add_documents")
            return
        try:
            ids = [d["id"] for d in docs]
            metadatas = [{"source": d.get("source", "upload")} for d in docs]
            texts = [d["text"] for d in docs]
            self.collection.add(ids=ids, documents=texts, metadatas=metadatas)
            logger.info("Added %d documents to collection", len(docs))
        except Exception as e:
            logger.exception("Failed to add documents: %s", e)

    def similarity_search(self, query: str, top_k: int = 3) -> List[str]:
        if not self.collection:
            logger.warning("No chroma collection available - returning empty")
            return []
        try:
            results = self.collection.query(query_texts=[query], n_results=top_k)
            docs = []
            for docs_list in results.get("documents", []):
                docs.extend(docs_list)
            logger.info("Found %d results for query", len(docs))
            return docs
        except Exception as e:
            logger.exception("Similarity search failed: %s", e)
            return []
