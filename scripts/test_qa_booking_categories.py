"""QA verification for Bug #1 (auto booking) and Bug #2 (admin categories only).

Run (backend on :8000):
    python scripts/test_qa_booking_categories.py
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.services.category_service import CategoryService, _is_active_admin_category  # noqa: E402

BASE = "http://127.0.0.1:8000"
client = httpx.Client(base_url=BASE, timeout=120.0)
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    if detail:
        print(f"        {detail}")


def chat(session: str, message: str) -> dict:
    r = client.post("/chat", json={"session_id": session, "message": message})
    r.raise_for_status()
    return r.json()


def wait_ready() -> None:
    for _ in range(20):
        try:
            if client.get("/health").json().get("status") == "ok":
                r = client.post("/chat", json={"session_id": "warm", "message": "hi"})
                if r.status_code == 200:
                    return
        except Exception:
            pass
        import time
        time.sleep(1)


def main() -> int:
    wait_ready()

    # ---- Bug #2: categories from admin source only --------------------
    svc = CategoryService()
    cats = svc.get_categories(force_refresh=True)
    record("Categories loaded from API/Mongo", len(cats) > 0, f"count={len(cats)} names={[c.name for c in cats]}")

    # Deleted categories must not appear
    deleted_names = {"saloon", "Hair servicess", "beauty", "shivvvvvvvvvvvvv"}
    shown = {c.name for c in cats}
    record("Deleted categories excluded", not (shown & deleted_names), f"shown={sorted(shown)}")

    r = chat("cat_" + uuid.uuid4().hex[:6], "show categories")
    record("Category list intent", str(r.get("intent", "")).endswith("category_list"),
           f"intent={r.get('intent')}")
    record("Category list not hardcoded-only check",
           "Available Categories:" in r["reply"] and "•" in r["reply"],
           r["reply"].replace("\n", " ")[:100])
    record("Category list excludes deleted junk",
           not any(d in r["reply"].lower() for d in ("saloon", "shivvvvvvvvvvvvv")),
           "reply checked")

    # ---- Bug #1: automatic booking creation ---------------------------
    sb = "qa_book_" + uuid.uuid4().hex[:6]
    chat(sb, "I want Hair Smoothing")
    r2 = chat(sb, "Noida")
    recs = r2.get("recommendations") or []
    record("Salon cards returned", len(recs) > 0, f"count={len(recs)}")

    # Pick a real salon name from cards (simulates ABC Salon selection)
    salon_name = recs[0]["salon_name"] if recs else "Salon"
    r3 = chat(sb, salon_name)
    record("Salon selected by name", "date" in r3["reply"].lower(), f"salon={salon_name}")

    r4 = chat(sb, "25 June 2026")
    record("Date accepted", "time" in r4["reply"].lower(), r4["reply"][:70])

    r5 = chat(sb, "4 PM")
    br = (r5.get("structured") or {}).get("booking_response") or {}
    bp = (r5.get("structured") or {}).get("booking_payload") or {}
    record("Booking auto-created on time",
           "booked" in r5["reply"].lower() and bool(br.get("booking_id")),
           f"booking_id={br.get('booking_id')} status={br.get('status')}")
    record("Booking payload has required fields",
           all(bp.get(k) for k in ("salon", "service", "date", "time")),
           f"salon={bp.get('salon')} service={bp.get('service')} date={bp.get('date')} time={bp.get('time')}")
    record("No PII requested",
           all(w not in r5["reply"].lower() for w in ("full name", "phone number", "email")),
           "confirmed without name/phone/email")

    # Unit: active category filter
    record("Active filter rejects deleted",
           not _is_active_admin_category({"name": "X", "isDeleted": True, "status": True}))
    record("Active filter accepts active",
           _is_active_admin_category({"name": "Hair", "isDeleted": False, "status": True}))

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n======== RESULT: {passed}/{len(results)} PASSED ========")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
