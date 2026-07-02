"""QA tests for booking entity extraction and completeness check."""
from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(message)s")

from app.agents.booking_agent import BookingAgent
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


def booking_created(reply: str) -> bool:
    return "submitted successfully" in reply.lower()


def run_case(
    orch: OrchestratorService,
    message: str,
    *,
    session_id: str | None = None,
    prior_messages: list[str] | None = None,
) -> dict:
    sid = session_id or ("qa-" + uuid.uuid4().hex[:8])
    if prior_messages:
        for prior in prior_messages:
            orch.chat(sid, prior)
    response = orch.chat(sid, message)
    return {
        "session_id": sid,
        "message": message,
        "reply": response.reply,
        "structured": response.structured,
        "created": booking_created(response.reply),
    }


def main() -> int:
    orch = make_orchestrator()
    agent = BookingAgent()

    cases = [
        {
            "name": "Case 1: single message with all fields",
            "message": "Hair Smoothing at Prem Salon Noida on 25 July 2026 at 5 PM",
            "expect_created": False,
            "expect_summary": True,
            "expect_missing": [],
        },
        {
            "name": "Case 2: service + salon only",
            "message": "Hair Smoothing at Prem Salon",
            "expect_created": False,
            "expect_missing": ["date", "time"],
        },
        {
            "name": "Case 3: service + date + time only",
            "message": "Hair Smoothing on 25 July 2026 at 5 PM",
            "expect_created": False,
            "expect_missing": ["salon"],
        },
        {
            "name": "Case 4: salon + date + time only",
            "message": "Prem Salon Noida tomorrow at 5 PM",
            "expect_created": False,
            "expect_missing": ["service"],
        },
        {
            "name": "Case 5: service + salon + date only",
            "message": "Hair Smoothing at Prem Salon Noida tomorrow",
            "expect_created": False,
            "expect_missing": ["time"],
        },
        {
            "name": "User bug: two-turn booking",
            "message": "I want to book an appointment on 25 July 2026 at 5:00 PM.",
            "prior_messages": ["I want Hair Smoothing at Prem Salon Noida."],
            "expect_created": False,
            "expect_summary": True,
            "confirm_after": True,
            "expect_missing": [],
        },
    ]

    passed: list[str] = []
    failed: list[str] = []

    print("=" * 72)
    print("BOOKING EXTRACTION QA REPORT")
    print("=" * 72)

    for case in cases:
        print(f"\n--- {case['name']} ---")
        print(f"Message: {case['message']}")

        payload = agent.extract_booking_fields(case["message"], BookingPayload())
        agent.log_detected_entities(payload)
        complete, missing = agent.booking_data_completeness_check(payload)
        print(f"Detected Service: {payload.service}")
        print(f"Detected Salon: {payload.salon}")
        print(f"Detected Date: {payload.date}")
        print(f"Detected Time: {payload.time}")
        if complete:
            print("Booking Created: (entities complete in message)")
        else:
            print(f"Missing Fields: {missing}")

        result = run_case(
            orch,
            case["message"],
            prior_messages=case.get("prior_messages"),
        )
        print(f"Bot Reply: {result['reply'].splitlines()[0]}")
        if result["created"]:
            print("Booking Created: YES")
        else:
            print("Booking Created: NO")
        if case.get("expect_summary"):
            has_summary = "confirm your booking details" in result["reply"].lower()
            print(f"Summary Shown: {'YES' if has_summary else 'NO'}")
            if case.get("confirm_after") and has_summary:
                confirm = orch.chat(result["session_id"], "Yes")
                result["created"] = booking_created(confirm.reply)
                print(f"After Yes — Booking Created: {'YES' if result['created'] else 'NO'}")

        ok = result["created"] == case["expect_created"]
        if case.get("expect_summary") and not case.get("confirm_after"):
            ok = "confirm your booking details" in result["reply"].lower()
        if case.get("confirm_after"):
            ok = result["created"] is True
        if not case["expect_created"] and case["expect_missing"]:
            reply_lower = result["reply"].lower()
            first_missing = case["expect_missing"][0]
            if first_missing == "date" and "date" not in reply_lower:
                ok = False
            if first_missing == "time" and "time" not in reply_lower:
                ok = False
            if first_missing == "service" and "service" not in reply_lower:
                ok = False
            if first_missing == "salon" and "salon" not in reply_lower:
                ok = False

        if ok:
            passed.append(case["name"])
            print("RESULT: PASS")
        else:
            failed.append(case["name"])
            print("RESULT: FAIL")
            print(f"Expected created={case['expect_created']}, got created={result['created']}")

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"Passed: {len(passed)}/{len(cases)}")
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
