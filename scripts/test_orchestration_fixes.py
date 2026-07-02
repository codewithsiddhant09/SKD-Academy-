"""Verify conversation-orchestration fixes (Issues #1, #2, #3) + regression.

Run (backend on :8000):
    python scripts/test_orchestration_fixes.py
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=60.0)
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    if detail:
        print(f"        {detail}")


def chat(msg: str, session: str | None = None) -> dict:
    session = session or ("s_" + uuid.uuid4().hex[:6])
    r = client.post("/chat", json={"session_id": session, "message": msg})
    r.raise_for_status()
    return r.json()


def intent_of(resp: dict) -> str:
    return str(resp.get("intent", "")).split(".")[-1].lower()


def main() -> int:
    # ---- Issue #1: Small Talk ----------------------------------------
    small_talk = {
        "hi": "welcome to bookly",
        "hello": "welcome to bookly",
        "hey": "welcome to bookly",
        "good morning": "welcome to bookly",
        "good evening": "welcome to bookly",
        "how are you": "doing well",
        "how are you doing": "doing well",
        "thanks": "welcome",
        "thank you": "welcome",
        "who are you": "bookly's ai assistant",
        "what can you do": "bookly's ai assistant",
    }
    for msg, needle in small_talk.items():
        r = chat(msg)
        it = intent_of(r)
        reply = r["reply"].lower()
        expected_intent = (
            "bookly_ai_information"
            if msg in {"what can you do", "who are you"}
            else "small_talk"
        )
        ok = it == expected_intent and needle in reply and not r.get("recommendations")
        record(f"SmallTalk: {msg!r}", ok, f"intent={it} reply={r['reply'][:55]!r}")

    # ---- Issue #2: Category List -------------------------------------
    cat_cases = ["list categories", "show categories", "available categories",
                 "what services do you offer", "give me category list", "service categories"]
    for msg in cat_cases:
        r = chat(msg)
        it = intent_of(r)
        ok = it == "category_list" and "Available Categories:" in r["reply"] and "•" in r["reply"]
        record(f"CategoryList: {msg!r}", ok, f"intent={it} reply={r['reply'][:60]!r}")

    # Category list must be dynamic (from API/loaded list), not RAG/LLM prose
    r = chat("list categories")
    ok = "Hair" in r["reply"] and "\n•" in r["reply"]
    record("CategoryList dynamic content", ok, r["reply"].replace("\n", " ")[:80])

    # ---- Issue #3: Location prompt (no examples) ---------------------
    r = chat("I want Hair Smoothing")
    reply = r["reply"]
    ok = ("recommend nearby salons" in reply.lower()
          and "example" not in reply.lower()
          and "dubai marina" not in reply.lower())
    record("LocationPrompt has no examples", ok, f"reply={reply!r}")

    # ---- Regression: real intents NOT hijacked ----------------------
    r = chat("What is Bookly?")
    record(
        "Regression Bookly platform info",
        intent_of(r) == "bookly_platform_information"
        and "salon and wellness appointment booking platform" in r["reply"].lower(),
        f"intent={intent_of(r)}",
    )

    r = chat("What is the cancellation policy?")
    record("Regression FAQ/RAG still works", intent_of(r) in {"faq", "policy"} and len(r["reply"]) > 20,
           f"intent={intent_of(r)}")

    r = chat("Show me salons in Noida")
    record("Regression salon search", intent_of(r) == "salon_search" and bool(r.get("recommendations")),
           f"intent={intent_of(r)} salons={len(r.get('recommendations') or [])}")

    # "hi I want hair smoothing" must NOT be small talk (carries a service)
    r = chat("hi I want hair smoothing")
    record("Greeting+service is NOT small talk", intent_of(r) != "small_talk",
           f"intent={intent_of(r)} reply={r['reply'][:55]!r}")

    # Full booking still flows (date/time) and rejects past date
    sb = "book_" + uuid.uuid4().hex[:6]
    chat("I want Hair Smoothing", sb)
    chat("Noida", sb)
    chat("proceed", sb)
    past = chat("10 January 2020", sb)
    record("Regression booking rejects past date",
           "past" in past["reply"].lower(), past["reply"][:60])
    chat("20 December 2026", sb)
    chat("4 PM", sb)
    done = chat("Yes", sb)
    record("Regression booking confirms", "submitted successfully" in done["reply"].lower(), done["reply"][:60])

    passed = sum(1 for _, p, _ in results if p)
    print(f"\n============ RESULT: {passed}/{len(results)} PASSED ============")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
