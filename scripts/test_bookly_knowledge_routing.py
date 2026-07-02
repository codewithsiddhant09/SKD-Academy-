"""Verify Bookly platform vs AI assistant routing (orchestration only)."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"
PLATFORM_NEEDLE = "salon and wellness appointment booking platform"
AI_NEEDLE = "bookly's ai assistant"
NOT_AI_PLATFORM = "ai-powered appointment booking assistant"


def chat(msg: str) -> dict:
    session = "bk_" + uuid.uuid4().hex[:8]
    r = httpx.post(f"{BASE}/chat", json={"session_id": session, "message": msg}, timeout=120)
    r.raise_for_status()
    return r.json()


def intent_of(resp: dict) -> str:
    return str(resp.get("intent", "")).split(".")[-1].lower()


def main() -> int:
    print("=" * 72)
    print("BOOKLY KNOWLEDGE ROUTING QA")
    print("=" * 72)

    passed = 0
    failed = 0

    platform_cases = [
        "What is Bookly?",
        "Tell me about Bookly.",
        "Explain Bookly.",
        "What does Bookly do?",
        "About Bookly",
        "Who is Bookly?",
        "Give me introduction about this application.",
        "What is this platform?",
        "What does this application do?",
        "How does this software work?",
    ]
    for msg in platform_cases:
        r = chat(msg)
        ok = (
            intent_of(r) == "bookly_platform_information"
            and PLATFORM_NEEDLE in r["reply"].lower()
            and AI_NEEDLE not in r["reply"].lower()
            and NOT_AI_PLATFORM not in r["reply"].lower()
        )
        print(f"[{'PASS' if ok else 'FAIL'}] Platform: {msg}")
        if not ok:
            print(f"        intent={intent_of(r)} reply={r['reply'][:90]}...")
        passed += int(ok)
        failed += int(not ok)

    ai_cases = [
        "Who are you?",
        "What are you?",
        "How can you help me?",
        "What can you do?",
        "Are you an AI?",
        "What is this chatbot?",
        "Who am I chatting with?",
        "Introduce yourself.",
    ]
    for msg in ai_cases:
        r = chat(msg)
        ok = (
            intent_of(r) == "bookly_ai_information"
            and AI_NEEDLE in r["reply"].lower()
            and PLATFORM_NEEDLE not in r["reply"].lower()
        )
        print(f"[{'PASS' if ok else 'FAIL'}] AI: {msg}")
        if not ok:
            print(f"        intent={intent_of(r)} reply={r['reply'][:90]}...")
        passed += int(ok)
        failed += int(not ok)

    # RAG still works for other FAQ topics
    r = chat("What is the cancellation policy?")
    ok = intent_of(r) in {"faq", "policy"} and len(r["reply"]) > 30
    print(f"[{'PASS' if ok else 'FAIL'}] RAG regression: cancellation policy")
    passed += int(ok)
    failed += int(not ok)

    total = passed + failed
    print(f"\n{'=' * 72}\nRESULT: {passed}/{total} PASSED\n{'=' * 72}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
