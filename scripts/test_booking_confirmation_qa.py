"""QA tests for booking confirmation step before creation."""
from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(message)s")

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


def chat(orch: OrchestratorService, sid: str, message: str) -> dict:
    response = orch.chat(sid, message)
    mem = (response.structured or {}).get("session_memory") or {}
    return {
        "reply": response.reply,
        "structured": response.structured,
        "created": "submitted successfully" in response.reply.lower(),
        "summary": "confirm your booking details" in response.reply.lower()
        or "updated appointment details" in response.reply.lower(),
        "awaiting_confirmation": mem.get("awaitingConfirmation"),
        "summary_shown": mem.get("bookingSummaryShown"),
    }


def main() -> int:
    orch = make_orchestrator()
    passed: list[str] = []
    failed: list[str] = []

    print("=" * 72)
    print("BOOKING CONFIRMATION QA REPORT")
    print("=" * 72)

    # Case 1 — show summary, not create
    sid1 = "c1-" + uuid.uuid4().hex[:8]
    r1 = chat(orch, sid1, "Hair Smoothing at Prem Salon Noida on 25 July 2026 at 5 PM")
    print("\nCase 1: all fields in one message")
    print(f"  Summary shown: {r1['summary']}")
    print(f"  Awaiting confirmation: {r1['awaiting_confirmation']}")
    print(f"  Booking created: {r1['created']}")
    if r1["summary"] and not r1["created"] and r1["awaiting_confirmation"]:
        passed.append("Case 1: summary shown, booking not created")
    else:
        failed.append("Case 1: summary shown, booking not created")

    # Case 2 — confirm creates booking
    r2 = chat(orch, sid1, "Yes")
    print("\nCase 2: customer confirms")
    print(f"  Booking created: {r2['created']}")
    if r2["created"]:
        passed.append("Case 2: booking created after Yes")
    else:
        failed.append("Case 2: booking created after Yes")

    # Case 3 — change time, updated summary
    sid3 = "c3-" + uuid.uuid4().hex[:8]
    chat(orch, sid3, "Hair Smoothing at Prem Salon Noida on 25 July 2026 at 5 PM")
    r3 = chat(orch, sid3, "Change time to 6 PM")
    print("\nCase 3: change time")
    print(f"  Updated summary: {r3['summary']}")
    print(f"  Time in reply: {'6 PM' in r3['reply']}")
    print(f"  Booking created: {r3['created']}")
    if r3["summary"] and "6 PM" in r3["reply"] and not r3["created"]:
        passed.append("Case 3: time updated in summary")
    else:
        failed.append("Case 3: time updated in summary")

    # Case 4 — change salon
    sid4 = "c4-" + uuid.uuid4().hex[:8]
    chat(orch, sid4, "Hair Smoothing at Prem Salon Noida on 25 July 2026 at 5 PM")
    r4 = chat(orch, sid4, "Change salon to ABC Salon Noida")
    print("\nCase 4: change salon")
    print(f"  Summary/response: {r4['reply'][:120]}...")
    ok4 = (
        r4["summary"]
        and "abc salon" in r4["reply"].lower()
        and not r4["created"]
    )
    if ok4:
        passed.append("Case 4: salon updated in summary")
    else:
        failed.append("Case 4: salon updated in summary")

    # Case 5 — decline
    sid5 = "c5-" + uuid.uuid4().hex[:8]
    chat(orch, sid5, "Hair Smoothing at Prem Salon Noida on 25 July 2026 at 5 PM")
    r5 = chat(orch, sid5, "No")
    print("\nCase 5: customer declines")
    print(f"  Booking created: {r5['created']}")
    print(f"  Declined message: {'not been booked' in r5['reply'].lower()}")
    if not r5["created"] and "not been booked" in r5["reply"].lower():
        passed.append("Case 5: booking not created on decline")
    else:
        failed.append("Case 5: booking not created on decline")

    print("\n" + "=" * 72)
    print(f"Passed: {len(passed)}/{len(passed) + len(failed)}")
    for name in passed:
        print(f"  [PASS] {name}")
    if failed:
        print(f"Failed: {len(failed)}")
        for name in failed:
            print(f"  [FAIL] {name}")
        return 1
    print("Failed: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
