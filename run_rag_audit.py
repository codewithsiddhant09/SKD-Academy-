#!/usr/bin/env python3
"""
Complete RAG debugging audit
"""
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.rag.vector_store import RagStore
from app.rag.ingest import ingest_rag_documents, load_docs_from_directory

print("=" * 80)
print("RAG SYSTEM COMPLETE DEBUGGING AUDIT")
print("=" * 80)

# Task 1: Verify all uploaded documents are loaded
print("\n1. VERIFYING DOCUMENT LOADING...")
base_path = Path(__file__).parent / "app" / "rag" / "documents"
docs = load_docs_from_directory(base_path)
print(f"   ✓ Documents loaded from: {base_path}")
print(f"   ✓ Document files found: {list(base_path.glob('*.md'))}")

# Task 2: Print total document count
print(f"\n2. TOTAL DOCUMENT COUNT: {len(docs)}")
for i, doc in enumerate(docs, 1):
    print(f"   Doc {i}: {doc.metadata.get('source', 'unknown')} ({len(doc.page_content)} chars)")

# Reingest to ensure fresh state
print("\n3. RE-INGESTING DOCUMENTS...")
try:
    ingest_rag_documents()
    print("   ✓ Documents re-ingested successfully")
except Exception as e:
    print(f"   ✗ Ingestion error: {e}")
    import traceback
    traceback.print_exc()

# Initialize vector store
store = RagStore()

# Task 3: Print total chunk count
print("\n4. TOTAL CHUNK COUNT IN VECTOR DATABASE:")
try:
    count = store._vectorstore._collection.count()
    print(f"   ✓ Total chunks: {count}")
except Exception as e:
    print(f"   ✗ Error getting count: {e}")

# Task 4: Print first 10 chunks
print("\n5. FIRST 10 CHUNKS:")
try:
    all_results = store._vectorstore.similarity_search("bookly", k=100)
    for i, chunk in enumerate(all_results[:10], 1):
        content = chunk.page_content[:80].replace('\n', ' ')
        print(f"   Chunk {i}: {content}...")
except Exception as e:
    print(f"   ✗ Error retrieving chunks: {e}")

# Task 5: Verify embeddings are created
print("\n6. VERIFYING EMBEDDINGS:")
try:
    test_embedding = store._embeddings.embed_query("test query")
    print(f"   ✓ Embeddings working: dimension={len(test_embedding)}")
except Exception as e:
    print(f"   ✗ Embedding error: {e}")

# Task 6: Verify ChromaDB contains vectors
print("\n7. CHROMADB COLLECTION STATISTICS:")
try:
    collection = store._vectorstore._collection
    count = collection.count()
    print(f"   ✓ Collection name: {collection.name}")
    print(f"   ✓ Vector count: {count}")
    print(f"   ✓ Collection ID: {collection.id}")
except Exception as e:
    print(f"   ✗ Collection error: {e}")

# Task 8: Run retrieval for three specific questions
questions = [
    "What is Bookly's mission?",
    "What payment methods are supported?",
    "What happens if I cancel 5 hours before my appointment?"
]

print("\n8. RETRIEVAL TESTING FOR 3 QUESTIONS:")
print("=" * 80)

for q_idx, question in enumerate(questions, 1):
    print(f"\nQ{q_idx}: {question}")
    print("-" * 80)
    
    try:
        # Retrieve chunks with scores
        retrieved = store.retrieve_with_scores(question, top_k=2)
        
        print(f"Retrieved: {len(retrieved)} chunks")
        
        if not retrieved:
            print("   ✗ NO CHUNKS RETRIEVED!")
        else:
            print("\nRetrieved Chunks:")
            for i, (chunk, score) in enumerate(retrieved, 1):
                content = chunk.page_content[:100].replace('\n', ' ')
                print(f"   Chunk {i} (score {score:.4f}): {content}...")
            
            # Test with LLM
            print("\nTesting with LLM...")
            from app.agents.faq_agent import FaqAgent
            agent = FaqAgent()
            debug_response = agent.debug_answer(question)
            
            print(f"\nSimilarity Scores: {debug_response.similarity_scores}")
            print(f"\nFinal Context (chars): {sum(len(c) for c in debug_response.context)}")
            print(f"\nFinal Answer Preview:")
            answer_preview = debug_response.answer[:150]
            print(f"   {answer_preview}...")
            print(f"\nExplanation: {debug_response.explanation}")
            
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)
