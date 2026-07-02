"""Semantic intent classification QA — paraphrase routing without exact keywords."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.agents.semantic_intent_classifier import SemanticIntentClassifier
from app.models.enums import IntentType

BASE = "http://127.0.0.1:8000"
PLATFORM_NEEDLE = "salon and wellness appointment booking platform"
AI_NEEDLE = "bookly's ai assistant"
classifier = SemanticIntentClassifier()


def expect_intent(message: str, expected: IntentType) -> tuple[bool, str]:
    result = classifier.classify(message)
    if result is None:
        return False, "no semantic match"
    ok = result.intent == expected and result.confidence >= 0.65
    detail = f"got={result.intent.value} conf={result.confidence_pct}% reason={result.reason}"
    return ok, detail


def chat(msg: str) -> dict:
    session = "sem_" + uuid.uuid4().hex[:8]
    r = httpx.post(f"{BASE}/chat", json={"session_id": session, "message": msg}, timeout=120)
    r.raise_for_status()
    return r.json()


def intent_of(resp: dict) -> str:
    return str(resp.get("intent", "")).split(".")[-1].lower()


def main() -> int:
    print("=" * 72)
    print("SEMANTIC INTENT CLASSIFIER — UNIT TESTS")
    print("=" * 72)

    passed = 0
    failed = 0

    unit_cases: list[tuple[str, IntentType]] = [
        # Platform paraphrases (no "Bookly" required)
        ("What is Bookly?", IntentType.BOOKLY_PLATFORM_INFORMATION),
        ("Tell me about Bookly.", IntentType.BOOKLY_PLATFORM_INFORMATION),
        ("Explain Bookly.", IntentType.BOOKLY_PLATFORM_INFORMATION),
        ("Give me introduction about this application.", IntentType.BOOKLY_PLATFORM_INFORMATION),
        ("What is this application?", IntentType.BOOKLY_PLATFORM_INFORMATION),
        ("What does this platform do?", IntentType.BOOKLY_PLATFORM_INFORMATION),
        ("Can you explain this app?", IntentType.BOOKLY_PLATFORM_INFORMATION),
        ("How does Bookly work?", IntentType.BOOKLY_PLATFORM_INFORMATION),
        ("What services does this app provide?", IntentType.BOOKLY_PLATFORM_INFORMATION),
        ("What is this software?", IntentType.BOOKLY_PLATFORM_INFORMATION),
        ("What exactly is Bookly?", IntentType.BOOKLY_PLATFORM_INFORMATION),
        ("What can I do using this application?", IntentType.BOOKLY_PLATFORM_INFORMATION),
        ("What is this platform?", IntentType.BOOKLY_PLATFORM_INFORMATION),
        ("What does this application do?", IntentType.BOOKLY_PLATFORM_INFORMATION),
        ("How does this software work?", IntentType.BOOKLY_PLATFORM_INFORMATION),
        # AI assistant paraphrases
        ("Who are you?", IntentType.BOOKLY_AI_INFORMATION),
        ("Who am I chatting with?", IntentType.BOOKLY_AI_INFORMATION),
        ("Are you an AI?", IntentType.BOOKLY_AI_INFORMATION),
        ("What can you do?", IntentType.BOOKLY_AI_INFORMATION),
        ("Introduce yourself.", IntentType.BOOKLY_AI_INFORMATION),
        ("Who is this assistant?", IntentType.BOOKLY_AI_INFORMATION),
        # Booking paraphrases
        ("Book appointment", IntentType.APPOINTMENT_BOOKING),
        ("Book a salon", IntentType.APPOINTMENT_BOOKING),
        ("Need appointment", IntentType.APPOINTMENT_BOOKING),
        ("Reserve appointment", IntentType.APPOINTMENT_BOOKING),
        ("I want booking", IntentType.APPOINTMENT_BOOKING),
        ("Can you schedule?", IntentType.APPOINTMENT_BOOKING),
        ("Book hair service", IntentType.APPOINTMENT_BOOKING),
        ("Need salon booking", IntentType.APPOINTMENT_BOOKING),
        ("I need an appointment", IntentType.APPOINTMENT_BOOKING),
        ("Help me book", IntentType.APPOINTMENT_BOOKING),
        ("I want to book Hair Smoothing.", IntentType.APPOINTMENT_BOOKING),
        ("Book Hair Appointment.", IntentType.APPOINTMENT_BOOKING),
        ("Reserve Hair Service.", IntentType.APPOINTMENT_BOOKING),
        # Category list
        ("Available services", IntentType.CATEGORY_LIST),
        ("Categories", IntentType.CATEGORY_LIST),
        ("What services do you have?", IntentType.CATEGORY_LIST),
        ("Show categories", IntentType.CATEGORY_LIST),
        ("List all services", IntentType.CATEGORY_LIST),
        ("Service list", IntentType.CATEGORY_LIST),
        ("Available categories", IntentType.CATEGORY_LIST),
        ("What services are available?", IntentType.CATEGORY_LIST),
        # Salon search
        ("Nearby salons", IntentType.SALON_SEARCH),
        ("Recommend salons", IntentType.SALON_SEARCH),
        ("Show salons", IntentType.SALON_SEARCH),
        ("Find salon", IntentType.SALON_SEARCH),
        ("Best salon", IntentType.SALON_SEARCH),
        ("Salon near me", IntentType.SALON_SEARCH),
        ("Suggest salon", IntentType.SALON_SEARCH),
        # FAQ / policy -> RAG
        ("Cancellation policy", IntentType.POLICY),
        ("Refund policy", IntentType.POLICY),
        ("Payment methods", IntentType.FAQ),
        ("Working hours", IntentType.FAQ),
        ("Privacy policy", IntentType.POLICY),
        ("Terms", IntentType.FAQ),
        ("What is the refund policy?", IntentType.POLICY),
    ]

    for msg, expected in unit_cases:
        ok, detail = expect_intent(msg, expected)
        print(f"[{'PASS' if ok else 'FAIL'}] {expected.value}: {msg}")
        if not ok:
            print(f"        {detail}")
        passed += int(ok)
        failed += int(not ok)

    print(f"\n{'=' * 72}")
    print("SEMANTIC INTENT — HTTP INTEGRATION (key paraphrases)")
    print("=" * 72)

    http_cases: list[tuple[str, str, str]] = [
        ("Give me introduction about this application.", "bookly_platform_information", PLATFORM_NEEDLE),
        ("What is this platform?", "bookly_platform_information", PLATFORM_NEEDLE),
        ("Who am I chatting with?", "bookly_ai_information", AI_NEEDLE),
        ("Introduce yourself.", "bookly_ai_information", AI_NEEDLE),
        ("What is the refund policy?", "policy", "refund"),
        ("Need appointment.", "appointment_booking", "book"),
        ("Available services", "category_list", ""),
    ]

    for msg, exp_intent, needle in http_cases:
        try:
            r = chat(msg)
            got = intent_of(r)
            ok = got == exp_intent or (exp_intent == "policy" and got in {"policy", "faq"})
            if exp_intent == "appointment_booking":
                ok = got == "appointment_booking" or needle in r["reply"].lower()
            elif exp_intent == "category_list":
                ok = got == "category_list"
            else:
                ok = got == exp_intent and needle in r["reply"].lower()
            print(f"[{'PASS' if ok else 'FAIL'}] HTTP {msg}")
            if not ok:
                print(f"        intent={got} reply={r['reply'][:90]}...")
        except httpx.HTTPError as exc:
            ok = False
            print(f"[FAIL] HTTP {msg} — server error: {exc}")
        passed += int(ok)
        failed += int(not ok)

    total = passed + failed
    print(f"\n{'=' * 72}\nRESULT: {passed}/{total} PASSED\n{'=' * 72}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
