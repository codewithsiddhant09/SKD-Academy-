import urllib.request
import json

question = 'What happens if I cancel 5 hours before my appointment?'
data = json.dumps({'question': question}).encode('utf-8')
req = urllib.request.Request(
    'http://127.0.0.1:8000/debug-rag',
    data=data,
    headers={'Content-Type': 'application/json'},
    method='POST'
)
with urllib.request.urlopen(req) as response:
    result = json.loads(response.read().decode('utf-8'))
    print('1. USER QUESTION:')
    print(f'   {question}')
    print('\n2. RETRIEVED CHUNKS:')
    for i, chunk in enumerate(result['retrieved_chunks'], 1):
        print(f'   Chunk {i} ({len(chunk)} chars):')
        print(f'   {chunk[:80]}...')
    print('\n3. SIMILARITY SCORES:')
    for i, score in enumerate(result['similarity_scores'], 1):
        print(f'   Chunk {i}: {score:.4f}')
    print('\n4. FINAL CONTEXT SENT TO LLM:')
    total_chunks = len(result['context'])
    total_chars = sum(len(c) for c in result['context'])
    print(f'   ({total_chunks} total chunks, {total_chars} total chars)')
    print('\n5. FINAL PROMPT SENT TO LLM:')
    print(f'   (First 180 chars): {result["prompt"][:180]}...')
    print('\n6. FINAL ANSWER:')
    print(f'   {result["answer"][:200]}...')
    print('\n7. EXPLANATION:')
    print(f'   {result.get("explanation", "N/A")}')
