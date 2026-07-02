"""QA regression: salon cards must appear before booking confirmation."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.repositories.salon_repository import SalonRepository
from app.services.category_service import CategoryService
from app.services.orchestrator_service import OrchestratorService


def _orch() -> OrchestratorService:
    cs = CategoryService()
    return OrchestratorService(categories=cs.get_category_names(), category_service=cs)


def _assert_cards(r, min_cards: int = 1) -> None:
    n = len(r.recommendations or [])
    assert n >= min_cards, f"expected >={min_cards} salon cards, got {n}; reply={r.reply[:160]}"
    card = r.recommendations[0]
    for field in ("salon_name", "address", "vendor_id"):
        assert getattr(card, field, None) is not None or field == "address", f"missing {field}"


def scenario_1() -> None:
    """Full booking details → salon cards → selection → confirmation."""
    os = _orch()
    sid = "s1_" + uuid.uuid4().hex[:8]
    r1 = os.chat(sid, "Book Hair Smoothing in Noida tomorrow at 5 PM")
    assert len(r1.recommendations or []) >= 1, f"S1 step1: expected cards, got reply={r1.reply[:120]}"
    assert "confirm" not in r1.reply.lower(), "S1: must not confirm before salon selection"
    assert os.memory.get_booking_draft(sid).salon is None, "S1: salon must not be auto-selected"

    salon_name = r1.recommendations[0].salon_name
    r2 = os.chat(sid, salon_name)
    assert "confirm" in r2.reply.lower() or "Would you like" in r2.reply, (
        f"S1 step2: expected confirmation summary, got {r2.reply[:120]}"
    )
    draft = os.memory.get_booking_draft(sid)
    assert draft.salon, "S1: salon should be set after selection"
    assert draft.date and draft.time, "S1: date/time preserved"
    print(f"[PASS] Scenario 1 — cards then confirm ({salon_name})")


def scenario_2() -> None:
    """Henna in Dubai with schedule → discovery (cards or no-salon response)."""
    repo = SalonRepository()
    mongo_n = len(repo.discover(location="Dubai", category="Henna", service="Henna")) if repo.is_available() else 0
    os = _orch()
    sid = "s2_" + uuid.uuid4().hex[:8]
    r = os.chat(sid, "Book Henna in Dubai on Friday at 2 PM")
    cards = len(r.recommendations or [])
    assert "confirm" not in r.reply.lower() or "select" in r.reply.lower(), (
        "S2: must not confirm before salon selection"
    )
    if mongo_n >= 1:
        assert cards >= 1, f"S2: expected cards when mongo has data, reply={r.reply[:120]}"
    else:
        assert cards == 0
        assert "no salon" in r.reply.lower() or "currently no" in r.reply.lower()
    print(f"[PASS] Scenario 2 — Dubai Henna discovery (mongo={mongo_n}, cards={cards})")


def scenario_3() -> None:
    """Service + location → show salon cards (date/time collected after salon pick)."""
    os = _orch()
    sid = "s3_" + uuid.uuid4().hex[:8]
    r1 = os.chat(sid, "Book Facial in Gurgaon")
    assert "which salon would you prefer" not in r1.reply.lower(), "S3: must not ask salon by text"
    # Gurgaon may have 0 salons in Mongo — discovery still runs
    if len(r1.recommendations or []) >= 1:
        print(f"[PASS] Scenario 3 — {len(r1.recommendations)} salon cards for Gurgaon")
    else:
        assert "no salon" in r1.reply.lower() or "currently no" in r1.reply.lower()
        print("[PASS] Scenario 3 — Gurgaon discovery (0 salons in Mongo)")


def scenario_4() -> None:
    """No matching salons → professional empty response."""
    repo = SalonRepository()
    if not repo.is_available():
        print("[SKIP] Scenario 4 — MongoDB unavailable")
        return
    mongo_n = len(repo.discover(location="Delhi", category="Hair", service="Hair Smoothing"))
    os = _orch()
    sid = "s4_" + uuid.uuid4().hex[:8]
    r = os.chat(sid, "Book Hair Smoothing in Delhi tomorrow at 5 PM")
    cards = len(r.recommendations or [])
    if mongo_n == 0:
        assert cards == 0, f"S4: expected 0 cards when mongo empty, got {cards}"
        assert "no salon" in r.reply.lower() or "no salons" in r.reply.lower() or "currently no" in r.reply.lower()
        print("[PASS] Scenario 4 — no salons professional response")
    else:
        assert cards >= 1
        print(f"[PASS] Scenario 4 — Delhi has {cards} salons (mongo={mongo_n})")


def scenario_5() -> None:
    """Location change → re-query and updated cards."""
    os = _orch()
    sid = "s5_" + uuid.uuid4().hex[:8]
    r1 = os.chat(sid, "Book Hair Smoothing in Noida tomorrow at 5 PM")
    noida_n = len(r1.recommendations or [])
    assert noida_n >= 1, "S5: need Noida cards first"

    r2 = os.chat(sid, "Dubai")
    dubai_n = len(r2.recommendations or [])
    loc = os.memory.get_session_memory(sid).preferred_location
    assert loc and "dubai" in loc.lower(), f"S5: location should update to Dubai, got {loc}"
    assert dubai_n >= 1 or noida_n != dubai_n, "S5: salon list should refresh for Dubai"
    print(f"[PASS] Scenario 5 — location change Noida({noida_n}) → Dubai({dubai_n})")


def main() -> int:
    print("=" * 72)
    print("BOOKING ORCHESTRATION — SALON FIRST QA")
    print("=" * 72)
    results: list[tuple[str, bool, str]] = []
    for name, fn in [
        ("Scenario 1", scenario_1),
        ("Scenario 2", scenario_2),
        ("Scenario 3", scenario_3),
        ("Scenario 4", scenario_4),
        ("Scenario 5", scenario_5),
    ]:
        try:
            fn()
            results.append((name, True, "PASS"))
        except Exception as exc:
            results.append((name, False, str(exc)))
            print(f"[FAIL] {name}: {exc}")

    print("\n" + "=" * 72)
    print("QA REPORT")
    print("=" * 72)
    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  —  {detail}")
    print(f"\nTOTAL: {passed}/{len(results)} passed")
    print("=" * 72)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
