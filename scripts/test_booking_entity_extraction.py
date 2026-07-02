"""Booking entity extraction and natural response QA."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services.orchestrator_service import OrchestratorService
from app.services.category_service import CategoryService

CASES = [
    ("Book a Hair appointment", {"service": "Hair"}, ["falls under", "category"]),
    ("Book Hair Session", {"service": "Hair"}, ["falls under", "category"]),
    ("Book Hair Service", {"service": "Hair"}, ["falls under", "category"]),
    ("Book Hair Smoothing", {"service": "Hair Smoothing"}, ["falls under", "category"]),
    ("Book Hair Spa", {"service": "Hair Spa"}, ["falls under", "category"]),
    ("Book Henna", {"service": "Henna"}, ["falls under", "category"]),
    ("Book Nail Service", {"service": "Nails"}, ["falls under", "category"]),
    ("Book Face Treatment", {"service": "Face Treatment"}, ["falls under", "category"]),
        (
        "Book Hair Session at The Glow Salon",
        {"service": "Hair", "salon": "Glow Salon"},
        ["falls under", "category", "for me"],
    ),
    (
        "Book Hair Smoothing at XYZ Salon",
        {"service": "Hair Smoothing", "salon": "Xyz Salon"},
        ["falls under", "category"],
    ),
        (
        "Book a hair session for me at The Glow Salon",
        {"service": "Hair", "salon": "Glow Salon"},
        ["falls under", "category", "for me", "a hair session"],
    ),
    ("Book Hair Service tomorrow", {"service": "Hair"}, ["falls under", "category"]),
    (
        "Book Hair Service tomorrow 5 PM",
        {"service": "Hair"},
        ["falls under", "category"],
    ),
]


def main() -> int:
    cs = CategoryService()
    orch = OrchestratorService(categories=cs.get_category_names(), category_service=cs)
    passed = 0
    failed = 0

    print("=" * 72)
    print("BOOKING ENTITY EXTRACTION QA")
    print("=" * 72)

    for message, expect, bad_phrases in CASES:
        sid = "be_" + uuid.uuid4().hex[:6]
        r = orch.chat(sid, message)
        bp = (r.structured or {}).get("booking_payload") or {}
        reply_lower = r.reply.lower()

        ok = True
        details: list[str] = []

        for key, val in expect.items():
            actual = bp.get(key)
            if not actual or val.lower() not in str(actual).lower():
                ok = False
                details.append(f"{key} expected~={val!r} got={actual!r}")

        for bad in bad_phrases:
            if bad in reply_lower or (bad in str(bp.get("service", "")).lower()):
                ok = False
                details.append(f"bad phrase {bad!r}")

        if "certainly" not in reply_lower and "happy to help" not in reply_lower and "great choice" not in reply_lower:
            if "appointment_booking" in str(r.intent) and "submitted successfully" not in reply_lower:
                # allow confirmation summaries
                if "confirm your booking" not in reply_lower:
                    ok = False
                    details.append("missing natural opener")

        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {message}")
        if details:
            for d in details:
                print(f"        {d}")
            print(f"        reply={r.reply[:100].replace(chr(10), ' ')}...")
            print(f"        payload service={bp.get('service')} salon={bp.get('salon')} date={bp.get('date')} time={bp.get('time')}")
        passed += int(ok)
        failed += int(not ok)

    print(f"\n{'=' * 72}\nRESULT: {passed}/{passed + failed} PASSED\n{'=' * 72}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
