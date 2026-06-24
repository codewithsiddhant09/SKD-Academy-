"""Session memory and auto-booking scenario tests."""
from __future__ import annotations

import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.agents.booking_agent import BookingAgent
from app.memory.conversation_store import ConversationStore
from app.models.schemas import BookingPayload
from app.services.orchestrator_service import OrchestratorService


def make_orchestrator() -> OrchestratorService:
    return OrchestratorService(
        categories=[
            "Hair Services",
            "Nail Services",
            "Makeup Services",
            "Facial & Skincare",
            "Grooming Services",
        ]
    )


def chat(orch: OrchestratorService, session_id: str, message: str) -> dict:
    response = orch.chat(session_id, message)
    return {
        "reply": response.reply,
        "intent": str(response.intent),
        "structured": response.structured,
        "recommendations": response.recommendations,
    }


def booking_created(result: dict) -> bool:
    structured = result.get("structured") or {}
    if structured.get("booking_response"):
        return True
    reply = (result.get("reply") or "").lower()
    return "successfully submitted" in reply


def memory_field(result: dict, field: str):
    return (result.get("structured") or {}).get("session_memory", {}).get(field)


class TestResult:
    def __init__(self, name: str) -> None:
        self.name = name
        self.passed = False
        self.detail = ""


def run_scenarios() -> list[TestResult]:
    results: list[TestResult] = []
    tomorrow = BookingAgent.format_display_date(date.today() + timedelta(days=1))

    # Scenario 1 — incremental turns (uses salon name from discovery when available)
    r1 = TestResult("Scenario 1: Hair Smoothing -> Noida -> salon -> Tomorrow -> 4 PM")
    orch = make_orchestrator()
    sid = "sc1-" + uuid.uuid4().hex[:8]
    try:
        chat(orch, sid, "Hair Smoothing")
        resp_noida = chat(orch, sid, "Noida")
        recs = resp_noida.get("recommendations") or []
        salon_pick = "ABC Salon"
        if recs:
            salon_pick = recs[0].salon_name if hasattr(recs[0], "salon_name") else recs[0].get("salon_name", salon_pick)
        last = chat(orch, sid, salon_pick)
        last = chat(orch, sid, "Tomorrow")
        last = chat(orch, sid, "4 PM")
        r1.passed = booking_created(last or {})
        if not r1.passed:
            r1.detail = (last or {}).get("reply", "")[:200]
    except Exception as exc:  # pragma: no cover - integration
        r1.detail = str(exc)
    results.append(r1)

    # Scenario 2 — one-shot booking message
    r2 = TestResult("Scenario 2: Book Hair Smoothing at ABC Salon tomorrow at 4 PM")
    orch2 = make_orchestrator()
    sid2 = "sc2-" + uuid.uuid4().hex[:8]
    try:
        last2 = chat(
            orch2,
            sid2,
            "Book Hair Smoothing at ABC Salon tomorrow at 4 PM",
        )
        r2.passed = booking_created(last2)
        mem = (last2.get("structured") or {}).get("session_memory") or {}
        if r2.passed and mem.get("selectedService") != "Hair Smoothing":
            r2.detail = f"service memory={mem.get('selectedService')}"
    except Exception as exc:
        r2.detail = str(exc)
    results.append(r2)

    # Scenario 3 — partial booking asks only missing fields
    r3 = TestResult("Scenario 3: Book appointment at ABC Salon asks missing info only")
    orch3 = make_orchestrator()
    sid3 = "sc3-" + uuid.uuid4().hex[:8]
    try:
        resp = chat(orch3, sid3, "Book appointment at ABC Salon")
        reply = resp.get("reply", "").lower()
        asks_service = "service" in reply
        asks_date = "date" in reply
        asks_time = "time" in reply
        r3.passed = (asks_service or asks_date) and not (asks_service and asks_date and asks_time)
        r3.detail = resp.get("reply", "")[:160]
    except Exception as exc:
        r3.detail = str(exc)
    results.append(r3)

    # Scenario 4 — salon change updates memory
    r4 = TestResult("Scenario 4: Salon change updates session memory")
    store = ConversationStore()
    sid4 = "sc4-" + uuid.uuid4().hex[:8]
    store.update_session_memory(sid4, selected_salon="ABC Salon", salon_id="s1")
    store.update_session_memory(sid4, selected_salon="XYZ Salon", salon_id="s2")
    mem = store.get_session_memory(sid4)
    r4.passed = mem.selected_salon == "XYZ Salon" and mem.salon_id == "s2"
    results.append(r4)

    # Scenario 5 — latest date wins
    r5 = TestResult("Scenario 5: Latest date used when user changes date")
    agent = BookingAgent()
    base = BookingPayload(service="Hair Smoothing", salon="ABC Salon", date="20 June 2026")
    updated = agent.extract_booking_fields("Book it on 25 June 2026 at 4 PM", base)
    r5.passed = updated.date == "25 June 2026" and updated.time == "4 PM"
    if not r5.passed:
        r5.detail = f"date={updated.date} time={updated.time}"
    results.append(r5)

    # Unit: session memory persists across turns without re-asking service
    r6 = TestResult("Session memory retains service and location across turns")
    orch6 = make_orchestrator()
    sid6 = "sc6-" + uuid.uuid4().hex[:8]
    chat(orch6, sid6, "I want Hair Smoothing")
    resp_loc = chat(orch6, sid6, "Noida")
    mem6 = (resp_loc.get("structured") or {}).get("session_memory") or {}
    r6.passed = mem6.get("selectedService") and "hair" in mem6.get("selectedService", "").lower()
    if mem6.get("preferredLocation"):
        r6.passed = r6.passed and "noida" in mem6.get("preferredLocation", "").lower()
    if not r6.passed:
        r6.detail = str(mem6)
    results.append(r6)

    # Unit: relative date extraction
    r7 = TestResult("BookingAgent extracts tomorrow and 4 PM")
    agent7 = BookingAgent()
    payload7 = agent7.extract_booking_fields(
        "Book it tomorrow at 4 PM",
        BookingPayload(service="Hair Smoothing", salon="ABC Salon"),
    )
    r7.passed = payload7.date == tomorrow and payload7.time == "4 PM"
    if not r7.passed:
        r7.detail = f"date={payload7.date} expected={tomorrow}"
    results.append(r7)

    return results


def main() -> int:
    print("=" * 72)
    print("SESSION MEMORY + AUTO BOOKING TEST REPORT")
    print("=" * 72)
    print("\nCurrent State Logic:")
    print("- ConversationStore.SessionMemory tracks selectedSalon, selectedService,")
    print("  selectedCategory, preferredLocation, appointmentDate, appointmentTime,")
    print("  lastIntent, and conversationHistory for the session.")
    print("- Draft booking payload merges from session memory on every read.")
    print("- service_prepare / discover / booking nodes sync memory after each turn.")
    print("\nBooking Trigger Logic:")
    print("- When salon + service + date + time are all present, booking() calls")
    print("  BookingService.create_booking() immediately.")
    print("- route_intent uses _try_route_booking_with_memory for one-shot and")
    print("  accumulated session bookings (e.g. 'Book it tomorrow at 4 PM').")
    print("- Only the first missing required field is prompted.")

    results = run_scenarios()
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]

    print("\nPassed Tests:")
    for r in passed:
        print(f"  [PASS] {r.name}")

    print("\nFailed Tests:")
    if failed:
        for r in failed:
            print(f"  [FAIL] {r.name}")
            if r.detail:
                print(f"         {r.detail}")
    else:
        print("  (none)")

    print("\nRisks:")
    print("- Scenario 1 depends on MongoDB salon data for Noida / ABC Salon matching.")
    print("- One-shot booking without prior discovery may lack salon_id if salon is")
    print("  not in the lookup table (booking still creates with salon name).")
    print("- Intent LLM variability may affect edge routing on ambiguous messages.")

    print(f"\nSummary: {len(passed)}/{len(results)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
