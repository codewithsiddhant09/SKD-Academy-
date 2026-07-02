"""Regression tests for one-shot booking message parsing."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.agents.booking_agent import BookingAgent
from app.graph.workflow import OrchestratorWorkflow
from app.models.schemas import BookingPayload
from app.utils.location import sanitize_location


USER_MESSAGE = "I want book appointment for my haircut at noida, on02/07/2026 at 7PM"


def test_booking_field_extraction() -> None:
    ba = BookingAgent(categories=["Hair"])
    payload = ba.extract_booking_fields(USER_MESSAGE, BookingPayload())
    assert payload.service in {"Hair", "Haircut"}, f"service={payload.service!r}"
    assert payload.date == "02/07/2026", f"date={payload.date!r}"
    assert payload.salon is None, f"salon={payload.salon!r}"
    print("[PASS] booking field extraction")


def test_location_extraction() -> None:
    from app.services.category_service import CategoryService
    from app.services.orchestrator_service import OrchestratorService

    cs = CategoryService()
    os = OrchestratorService(categories=cs.get_category_names(), category_service=cs)
    wf: OrchestratorWorkflow = os.workflow
    location = wf._extract_location(USER_MESSAGE)
    assert location == "Noida", f"location={location!r}"
    assert sanitize_location("Noida On At") == "Noida"
    print("[PASS] location extraction")


def test_orchestrator_reply() -> None:
    from app.services.category_service import CategoryService
    from app.services.orchestrator_service import OrchestratorService

    cs = CategoryService()
    os = OrchestratorService(categories=cs.get_category_names(), category_service=cs)
    sid = "parse_" + uuid.uuid4().hex[:8]
    reply = os.chat(sid, USER_MESSAGE)
    draft = os.memory.get_booking_draft(sid)
    assert draft.service in {"Hair", "Haircut"}, f"draft.service={draft.service!r}"
    assert draft.date == "02/07/2026", f"draft.date={draft.date!r}"
    assert "Ppointment" not in reply.reply
    assert "Noida On At" not in reply.reply
    assert "Which salon" in reply.reply or "salon" in reply.reply.lower()
    print(f"[PASS] orchestrator reply: {reply.reply[:100]}...")


def main() -> int:
    print("=" * 72)
    print("ONE-SHOT BOOKING PARSING REGRESSION")
    print("=" * 72)
    test_booking_field_extraction()
    test_location_extraction()
    test_orchestrator_reply()
    print("=" * 72)
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
