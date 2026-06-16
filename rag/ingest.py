import os
from pathlib import Path
import logging
from typing import List
from docx import Document
from rag.vector_store import ChromaVectorStore

logger = logging.getLogger("bookly.rag.ingest")

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def extract_text_from_docx(path: Path) -> str:
    doc = Document(path)
    paragraphs = [p.text for p in doc.paragraphs if p.text]
    return "\n".join(paragraphs)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    # Simple character-based chunker
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = max(start + chunk_size - overlap, end)
    return chunks


async def ingest_file(path: Path, persist_dir: str = None) -> int:
    logger.info("Ingesting %s", path)
    text = extract_text_from_docx(path)
    chunks = chunk_text(text)
    store = ChromaVectorStore(persist_directory=persist_dir)
    docs = [{"id": f"{path.name}-{i}", "text": c} for i, c in enumerate(chunks)]
    store.add_documents(docs)
    return len(chunks)


async def ingest_all_uploads():
    UPLOAD_DIR = Path(os.getenv("UPLOADS_DIR", "uploads"))
    PERSIST_DIR = os.getenv("CHROMADB_PERSIST_DIR", "vector_db")
    if not UPLOAD_DIR.exists():
        logger.info("No uploads folder found: %s", UPLOAD_DIR)
        return 0

    total = 0
    for p in UPLOAD_DIR.glob("*.docx"):
        try:
            cnt = await ingest_file(p, persist_dir=PERSIST_DIR)
            total += cnt
        except Exception:
            logger.exception("Failed to ingest %s", p)
    logger.info("Ingested %d chunks total", total)
    return total
