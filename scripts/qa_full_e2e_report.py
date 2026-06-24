"""Full QA E2E report — Phases 1-12 (testing only, no code changes).

Run (backend on :8000):
    python scripts/qa_full_e2e_report.py
"""
from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"
client = httpx.Client(base_url=BASE, timeout=120.0)


@dataclass
class Result:
    phase: str
    name: str
    passed: bool
    detail: str = ""


report: list[Result] = []


def record(phase: str, name: str, passed: bool, detail: str = "") -> None:
    report.append(Result(phase, name, passed, detail))
    flag = "PASS" if passed else "FAIL"
    print(f"[{flag}] [{phase}] {name}")
    if detail:
        print(f"        {detail}")


def chat(msg: str, session: str | None = None) -> dict:
    session = session or ("qa_" + uuid.uuid4().hex[:8])
    r = client.post("/chat", json={"session_id": session, "message": msg})
    if r.status_code != 200:
        return {"reply": "", "intent": "error", "status": r.status_code}
    return r.json()


def intent_of(resp: dict) -> str:
    return str(resp.get("intent", "")).split(".")[-1].lower()


def wait_ready() -> bool:
    for _ in range(25):
        try:
            h = client.get("/health").json()
            if h.get("status") == "ok":
                client.post("/chat", json={"session_id": "warmup", "message": "hi"})
                return True
        except Exception:
            pass
        import time
        time.sleep(1)
    return False


def main() -> int:
    print("=" * 70)
    print("BOOKLY AI AGENT — FULL QA E2E REPORT")
    print("=" * 70)

    # PHASE 1 — Application
    p1_ok = wait_ready()
    record("P1", "Backend health", p1_ok, "GET /health")
    try:
        fe = httpx.get("http://127.0.0.1:3000", timeout=10)
        record("P1", "Frontend loads (:3000)", fe.status_code == 200, f"status={fe.status_code}")
    except Exception as exc:
        record("P1", "Frontend loads (:3000)", False, str(exc))
    try:
        docs = client.get("/docs")
        record("P1", "Swagger /docs", docs.status_code == 200)
    except Exception as exc:
        record("P1", "Swagger /docs", False, str(exc))

    try:
        from app.repositories.salon_repository import SalonRepository
        mongo_ok = SalonRepository().is_available()
        record("P1", "MongoDB connection", mongo_ok)
    except Exception as exc:
        record("P1", "MongoDB connection", False, str(exc))

    # PHASE 2 — Greeting / Small Talk
    greetings = ["Hello", "Hi", "Hey", "Good Morning", "Good Evening",
                 "How are you?", "Who are you?", "What can you do?", "Thank you", "Bye"]
    for g in greetings:
        r = chat(g)
        it = intent_of(r)
        reply = r.get("reply", "")
        ok = it == "small_talk" and len(reply) > 10 and not r.get("recommendations")
        record("P2", f"Greeting: {g!r}", ok, f"intent={it}")

    # PHASE 3 — Categories
    cat_queries = ["Show categories", "List categories", "Available categories",
                   "What services do you offer?", "Give me category list"]
    for q in cat_queries:
        r = chat(q)
        ok = intent_of(r) == "category_list" and "Available Categories:" in r.get("reply", "")
        record("P3", f"Category: {q!r}", ok, f"intent={intent_of(r)}")
    r = chat("show categories")
    junk = any(x in r.get("reply", "").lower() for x in ("saloon", "shivvvvvvvvvvvvv"))
    record("P3", "No deleted admin categories in list", not junk)

    # PHASE 4 — RAG
    rag_q = [
        ("What is Bookly?", "faq"),
        ("What payment methods are supported?", "faq"),
        ("What is the refund policy?", "policy"),
        ("What is Bookly's mission?", "faq"),
    ]
    for q, exp in rag_q:
        r = chat(q)
        it = intent_of(r)
        ok = it in {"faq", "policy"} and len(r.get("reply", "")) > 20
        ok = ok and "do not have enough information" not in r.get("reply", "").lower()
        record("P4", f"RAG: {q!r}", ok, f"intent={it}")

    # PHASE 5 — Salon Search
    for q in ["Show salons in Noida", "Show vendors in Noida", "Show salons in Dubai", "Find salons in Abu Dhabi"]:
        r = chat(q)
        recs = r.get("recommendations") or []
        ok = intent_of(r) == "salon_search" and len(recs) > 0 if "noida" in q.lower() else intent_of(r) == "salon_search"
        record("P5", f"Salon search: {q!r}", ok, f"intent={intent_of(r)} cards={len(recs)}")
    r = chat("Show vendors in Noida")
    recs = r.get("recommendations") or []
    if recs:
        first = recs[0]
        record("P5", "Salon card has image", "image" in first, f"image={first.get('image')}")
        record("P5", "Salon card has isFavorite", "isFavorite" in first, "field missing in payload")
        record("P5", "Salon card has totalRating", "totalRating" in first, "field missing in payload")
    else:
        record("P5", "Salon card fields check", False, "no recommendations")

    # PHASE 6 — Service Search
    for svc in ["Hair Smoothing", "Keratin Treatment", "Bridal Makeup", "Facial", "Waxing"]:
        r = chat(svc)
        reply = r.get("reply", "").lower()
        ok = "location" in reply and "dubai marina" not in reply and "example" not in reply
        record("P6", f"Service: {svc!r}", ok, reply[:70])

    # PHASE 7 — Booking
    sb = "bookqa_" + uuid.uuid4().hex[:6]
    chat("I want Hair Smoothing", sb)
    r = chat("Noida", sb)
    recs = r.get("recommendations") or []
    salon = recs[0]["salon_name"] if recs else "Salon"
    chat(salon, sb)
    chat("25 June 2026", sb)
    r_done = chat("4 PM", sb)
    br = (r_done.get("structured") or {}).get("booking_response") or {}
    record("P7A", "Booking flow complete", "booked" in r_done.get("reply", "").lower() and bool(br.get("booking_id")),
           f"booking_id={br.get('booking_id')}")

    sb2 = "past_" + uuid.uuid4().hex[:6]
    chat("I want Hair Smoothing", sb2)
    chat("Noida", sb2)
    chat("proceed", sb2)
    r_past = chat("10 January 2020", sb2)
    record("P7B", "Past date rejected", "past" in r_past.get("reply", "").lower())

    sb3 = "nodate_" + uuid.uuid4().hex[:6]
    chat("I want Hair Smoothing", sb3)
    chat("Noida", sb3)
    chat("proceed", sb3)
    chat("25 June 2026", sb3)
    br3 = (chat("hello", sb3).get("structured") or {}).get("booking_response")
    record("P7C", "Missing time - no booking", not br3)

    sb4 = "notime_" + uuid.uuid4().hex[:6]
    chat("I want Hair Smoothing", sb4)
    chat("Noida", sb4)
    chat("proceed", sb4)
    br4 = (chat("4 PM", sb4).get("structured") or {}).get("booking_response")
    record("P7D", "Missing date - no booking", not br4)

    # PHASE 8 — Disabled salon (verify filter via repo)
    try:
        from pymongo import MongoClient
        from app.core.config import get_settings
        s = get_settings()
        db = MongoClient(s.mongodb_uri)[s.mongodb_db_name]
        disabled = db[s.mongodb_users_collection].find_one({"userType": "Vendor", "status": False})
        if disabled:
            from app.repositories.salon_repository import SalonRepository
            repo = SalonRepository()
            loc = disabled.get("businessAddress") or ""
            ids = repo.get_salons_by_location(loc) if loc else set()
            record("P8", "Disabled salon filtered", disabled["_id"] not in ids)
        else:
            record("P8", "Disabled salon filtered", True, "no disabled vendor to test")
    except Exception as exc:
        record("P8", "Disabled salon filtered", False, str(exc))

    # PHASE 9 — Category dynamic (API/Mongo source)
    try:
        from app.services.category_service import CategoryService
        cats = CategoryService().get_categories(force_refresh=True)
        record("P9", "Categories fetched dynamically", len(cats) > 0, f"count={len(cats)}")
    except Exception as exc:
        record("P9", "Categories fetched dynamically", False, str(exc))

    # PHASE 10 — Intent
    intent_cases = [
        ("Show vendors in Noida", "salon_search"),
        ("Hair Smoothing", "service_search"),
        ("Hair Smoothing in Noida", "service_search"),
        ("What is Bookly?", "faq"),
        ("Hello", "small_talk"),
    ]
    for q, exp in intent_cases:
        r = client.get(f"/debug/intent?q={httpx.QueryParams({'q': q})['q']}")
        if r.status_code == 200:
            got = str(r.json().get("intent", "")).split(".")[-1].lower()
            record("P10", f"Intent {q!r}", got == exp, f"got={got} expected={exp}")
        else:
            record("P10", f"Intent {q!r}", False, f"status={r.status_code}")

    # Summary
    passed = sum(1 for r in report if r.passed)
    failed = [r for r in report if not r.passed]
    print("\n" + "=" * 70)
    print(f"SUMMARY: {passed}/{len(report)} PASSED | {len(failed)} FAILED")
    print("=" * 70)
    if failed:
        print("\nFAILED TESTS:")
        for f in failed:
            print(f"  - [{f.phase}] {f.name}: {f.detail}")
    print("\nURLS FOR MANUAL TESTING:")
    print("  Frontend Chat:  http://127.0.0.1:3000")
    print("  Backend API:    http://127.0.0.1:8000")
    print("  Swagger:        http://127.0.0.1:8000/docs")
    print("  Health:         http://127.0.0.1:8000/health")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
