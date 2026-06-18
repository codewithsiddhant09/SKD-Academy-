"""End-to-end local verification against the running backend (port 8000).

Covers: Greeting/General, FAQ+RAG, Category detection, Intent detection,
Salon search, Location search, and the full booking flow incl. past-date
rejection.

Run (backend must be running on :8000):
    python scripts/e2e_local_test.py
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://127.0.0.1:8000"
client = httpx.Client(base_url=BASE, timeout=60.0)

results: list[tuple[str, bool, str]] = []


def record(name: str, passed: bool, detail: str = "") -> None:
    results.append((name, passed, detail))
    flag = "PASS" if passed else "FAIL"
    print(f"[{flag}] {name}")
    if detail:
        print(f"        {detail}")


def chat(session: str, message: str) -> dict:
    r = client.post("/chat", json={"session_id": session, "message": message})
    r.raise_for_status()
    return r.json()


def get(path: str) -> dict:
    r = client.get(path)
    r.raise_for_status()
    return r.json()


def main() -> int:
    # ---- Phase 4: API surface ----------------------------------------
    health = get("/health")
    record("Health endpoint", health.get("status") == "ok", str(health))

    # ---- Phase 8: Greeting / general ---------------------------------
    s = "greet_" + uuid.uuid4().hex[:6]
    r = chat(s, "hi")
    record("Greeting", "Bookly" in r["reply"] or "assist" in r["reply"].lower(),
           f"intent={r['intent']} reply={r['reply'][:60]!r}")

    # ---- Phase 9: RAG / FAQ ------------------------------------------
    rag_questions = [
        "What is Bookly?",
        "What payment methods are supported?",
        "What is the refund policy?",
        "What is Bookly's mission?",
    ]
    for q in rag_questions:
        rr = chat("rag_" + uuid.uuid4().hex[:6], q)
        reply = rr["reply"]
        ok = bool(reply) and len(reply) > 15 and "unavailable" not in reply.lower()
        record(f"RAG: {q}", ok, f"intent={rr['intent']} reply={reply[:90]!r}")

    # ---- Phase 8: Intent detection (debug endpoint) ------------------
    intent_cases = [
        ("Show vendors in Noida", "salon_search"),
        ("Hair Smoothing", "service_search"),
        ("What is Bookly?", "faq"),
    ]
    for q, expected in intent_cases:
        di = get(f"/debug/intent?q={httpx.QueryParams({'q': q})['q']}")
        got = str(di.get("intent", "")).split(".")[-1].lower()
        record(f"Intent '{q}'", got == expected, f"got={got} expected={expected} location={di.get('location')}")

    # ---- Phase 8: Category detection (debug endpoint) ----------------
    cats = get("/debug/categories")
    record("Categories from API", cats.get("count", 0) > 0,
           f"count={cats['count']} names={[c['name'] for c in cats['categories']]}")

    # ---- Bug1/6: cities ----------------------------------------------
    cities = get("/debug/cities")
    record("Cities listing", cities.get("count", 0) > 0, f"count={cities['count']} cities={cities['cities']}")

    # ---- Phase 8/Salon search via chat -------------------------------
    s2 = "salon_" + uuid.uuid4().hex[:6]
    r = chat(s2, "Show me salons in Noida")
    recs = r.get("recommendations") or []
    record("Salon search (Noida)", len(recs) > 0,
           f"intent={r['intent']} salons={[x['salon_name'] for x in recs]}")
    if recs:
        first = recs[0]
        record("Salon card has image field", "image" in first,
               f"image={first.get('image')}")

    # ---- Phase 10: full booking flow ---------------------------------
    sb = "book_" + uuid.uuid4().hex[:6]
    step1 = chat(sb, "I want Hair Smoothing")
    record("Booking step1 asks location", "location" in step1["reply"].lower(),
           f"reply={step1['reply'][:80]!r}")

    step2 = chat(sb, "Noida")
    recs2 = step2.get("recommendations") or []
    record("Booking step2 returns salons", len(recs2) > 0,
           f"salons={[x['salon_name'] for x in recs2]}")

    # Select / proceed
    step3 = chat(sb, "proceed")
    record("Booking step3 asks date", "date" in step3["reply"].lower(),
           f"reply={step3['reply'][:80]!r}")

    # Past date must be rejected
    step4 = chat(sb, "10 January 2020")
    record("Booking rejects PAST date",
           "past" in step4["reply"].lower() or "today or later" in step4["reply"].lower(),
           f"reply={step4['reply'][:90]!r}")

    # Valid future date
    step5 = chat(sb, "15 December 2026")
    record("Booking accepts future date (asks time)", "time" in step5["reply"].lower(),
           f"reply={step5['reply'][:80]!r}")

    step6 = chat(sb, "4 PM")
    confirmed = "booked" in step6["reply"].lower() or "booking id" in step6["reply"].lower()
    no_pii = all(w not in step6["reply"].lower() for w in ["full name", "phone number", "email"])
    record("Booking confirmed (no PII asked)", confirmed and no_pii,
           f"reply={step6['reply'][:120]!r}")

    passed = sum(1 for _, p, _ in results if p)
    total = len(results)
    print(f"\n================ RESULT: {passed}/{total} PASSED ================")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
