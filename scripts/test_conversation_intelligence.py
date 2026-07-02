"""End-to-end conversation intelligence QA (orchestration only)."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    if detail:
        print(f"        {detail}")


def chat(msg: str, session: str | None = None) -> dict:
    session = session or ("ci_" + uuid.uuid4().hex[:8])
    r = httpx.post(f"{BASE}/chat", json={"session_id": session, "message": msg}, timeout=120)
    r.raise_for_status()
    return r.json()


def intent_of(resp: dict) -> str:
    return str(resp.get("intent", "")).split(".")[-1].lower()


def main() -> int:
    print("=" * 72)
    print("CONVERSATION INTELLIGENCE QA")
    print("=" * 72)

    # Greeting
    for msg, needle in [
        ("Hi", "welcome to bookly"),
        ("Hello", "welcome to bookly"),
        ("How are you", "doing well"),
        ("Thanks", "welcome"),
        ("Bye", "wonderful day"),
    ]:
        r = chat(msg)
        ok = intent_of(r) == "small_talk" and needle in r["reply"].lower()
        record(f"Greeting: {msg}", ok, r["reply"][:70])

    # Category list
    for msg in ["Show all categories", "Available services", "What categories are available?"]:
        r = chat(msg)
        ok = intent_of(r) == "category_list" and "Available Categories:" in r["reply"]
        record(f"CategoryList: {msg}", ok)

    # Category detail
    for cat in ["Tell me about Hair", "Tell me about Hair Removal", "Explain Makeup"]:
        r = chat(cat)
        ok = intent_of(r) == "category_detail" and "available service categor" in r["reply"].lower()
        record(f"CategoryDetail: {cat}", ok, r["reply"][:80])

    # Single-message booking -> confirmation (not immediate book)
    sb = "book_" + uuid.uuid4().hex[:6]
    r = chat("I want Hair Smoothing at Prem Salon Noida on 25 July at 5 PM", sb)
    ok = "confirm your booking" in r["reply"].lower() and "submitted successfully" not in r["reply"].lower()
    record("Single-message booking -> confirmation summary", ok, r["reply"][:90])
    if ok:
        r2 = chat("Yes", sb)
        record("Confirm creates booking", "submitted successfully" in r2["reply"].lower())
    else:
        record("Confirm creates booking", False, "skipped — summary step failed")

    # Multi-step booking
    sb2 = "flow_" + uuid.uuid4().hex[:6]
    r = chat("Hair smoothing", sb2)
    ok_loc = "recommend nearby salons" in r["reply"].lower() and "example" not in r["reply"].lower()
    record("Location prompt (no examples)", ok_loc, r["reply"][:80])
    chat("Hair smoothing", sb2)
    r = chat("Noida", sb2)
    recs = r.get("recommendations") or []
    salon_name = recs[0].get("salon_name", "Prem Salon") if recs else "Prem Salon"
    chat(salon_name, sb2)
    chat("Tomorrow", sb2)
    r = chat("5 PM", sb2)
    record("Multi-step reaches confirmation", "confirm your booking" in r["reply"].lower(), r["reply"][:80])
    r = chat("Confirm", sb2)
    record("Multi-step booking completes", "submitted successfully" in r["reply"].lower())

    # FAQ interrupt during booking (after summary shown)
    sb3 = "faq_" + uuid.uuid4().hex[:6]
    chat("I want Hair Smoothing at Prem Salon Noida on 26/06/2026 at 5 PM", sb3)
    r = chat("cancellation policy", sb3)
    ok = "continue your booking" in r["reply"].lower()
    record("FAQ interrupt resumes booking", ok, r["reply"][:100])

    # Salon recommendation
    sb4 = "salon_" + uuid.uuid4().hex[:6]
    chat("Hair", sb4)
    r = chat("Noida", sb4)
    record("Salon cards after location", bool(r.get("recommendations")), f"cards={len(r.get('recommendations') or [])}")

    # Regression
    r = chat("What is Bookly?")
    record(
        "Bookly platform routing",
        intent_of(r) == "bookly_platform_information"
        and "salon and wellness appointment booking platform" in r["reply"].lower(),
    )
    r = chat("What is the cancellation policy?")
    record("RAG FAQ regression", intent_of(r) in {"faq", "policy"} and len(r["reply"]) > 20)
    r = chat("list categories")
    record("Categories API regression", "Hair" in r["reply"])

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{'=' * 72}\nRESULT: {passed}/{len(results)} PASSED\n{'=' * 72}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
