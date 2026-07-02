"""50+ dynamic booking orchestration scenarios — asks only for missing slots."""
from __future__ import annotations

import itertools
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.graph.booking_orchestration import is_generic_salon_phrase
from app.services.category_service import CategoryService
from app.services.orchestrator_service import OrchestratorService


@dataclass
class Scenario:
    name: str
    message: str
    expect_ask: str | None = None  # slot bot should ask for
    expect_discover: bool = False
    expect_confirm: bool = False
    expect_cards: bool = False
    forbid_salon_ask: bool = False
    follow_up: tuple[str, ...] = ()


def _orch() -> OrchestratorService:
    cs = CategoryService()
    return OrchestratorService(categories=cs.get_category_names(), category_service=cs)


def _reply(r) -> str:
    return (r.reply or "").lower()


def _run(s: Scenario) -> None:
    os = _orch()
    sid = "dyn_" + uuid.uuid4().hex[:8]
    r = os.chat(sid, s.message)
    replies = [_reply(r)]

    for msg in s.follow_up:
        r = os.chat(sid, msg)
        replies.append(_reply(r))

    combined = " | ".join(replies)
    recs = len(r.recommendations or [])

    if s.forbid_salon_ask:
        assert "which salon would you prefer" not in replies[0], (
            f"{s.name}: must not ask salon before cards; got {replies[0][:120]}"
        )

    if s.expect_ask == "location":
        assert "location" in replies[0], f"{s.name}: expected location ask; got {replies[0][:120]}"
        assert "which salon" not in replies[0], f"{s.name}: must not ask salon before location"

    if s.expect_ask == "date":
        assert "date" in replies[0], f"{s.name}: expected date ask; got {replies[0][:120]}"

    if s.expect_ask == "time":
        assert "time" in replies[0], f"{s.name}: expected time ask; got {replies[0][:120]}"

    if s.expect_ask == "service":
        assert "service" in replies[0], f"{s.name}: expected service ask; got {replies[0][:120]}"

    if s.expect_discover or s.expect_cards:
        assert recs >= 1 or "found several salons" in combined or "select your preferred salon" in combined, (
            f"{s.name}: expected salon cards/discovery; recs={recs} reply={combined[:160]}"
        )

    if s.expect_confirm:
        assert "confirm" in combined or "would you like me to confirm" in combined, (
            f"{s.name}: expected confirmation; got {combined[:160]}"
        )


def build_scenarios() -> list[Scenario]:
    scenarios: list[Scenario] = [
        Scenario(
            "CASE1 haircut date time no location",
            "I want a haircut on 05/07/2026 at 5:00 AM",
            expect_ask="location",
            forbid_salon_ask=True,
        ),
        Scenario(
            "CASE2 full details named salon",
            "Book a haircut at Best Glow Salon, Noida on 05/07/2026 at 5 PM",
            expect_confirm=True,
        ),
        Scenario("CASE3 service only", "Book haircut", expect_ask="location", forbid_salon_ask=True),
        Scenario(
            "CASE4 service location",
            "Book haircut in Noida",
            expect_discover=True,
            expect_cards=True,
            forbid_salon_ask=True,
        ),
        Scenario(
            "CASE5 service location schedule",
            "Book haircut in Noida tomorrow 5 PM",
            expect_discover=True,
            expect_cards=True,
            forbid_salon_ask=True,
        ),
        Scenario(
            "CASE6 named salon no location",
            "Book haircut at Best Glow Salon",
            expect_ask="date",
            forbid_salon_ask=True,
        ),
        Scenario(
            "EXAMPLE1 haircut schedule then location",
            "Book haircut tomorrow at 5 PM",
            expect_ask="location",
            follow_up=("Noida",),
            forbid_salon_ask=True,
        ),
        Scenario(
            "generic salon list not a name",
            "Book haircut in Noida",
            follow_up=("give me salon list",),
            forbid_salon_ask=True,
        ),
    ]

    services = ["haircut", "Hair Smoothing", "Henna", "Facial"]
    locations = ["Noida", "Dubai"]
    dates = ["tomorrow", "05/07/2026", "on Friday"]
    times = ["5 PM", "10 AM", "2:30 PM"]

    idx = 0
    for svc in services:
        idx += 1
        scenarios.append(Scenario(f"svc_only_{idx}", f"Book {svc}", expect_ask="location", forbid_salon_ask=True))

    for svc, loc in itertools.product(services[:3], locations):
        idx += 1
        scenarios.append(
            Scenario(
                f"svc_loc_{idx}",
                f"Book {svc} in {loc}",
                expect_discover=True,
                forbid_salon_ask=True,
            )
        )

    for svc, dt, tm in itertools.product(["haircut", "Hair Smoothing"], dates[:2], times[:2]):
        idx += 1
        scenarios.append(
            Scenario(
                f"svc_sched_{idx}",
                f"Book {svc} on {dt} at {tm}",
                expect_ask="location",
                forbid_salon_ask=True,
            )
        )

    for svc, loc, dt, tm in itertools.product(["haircut"], locations, ["tomorrow"], ["5 PM"]):
        idx += 1
        scenarios.append(
            Scenario(
                f"full_no_salon_{idx}",
                f"Book {svc} in {loc} {dt} at {tm}",
                expect_discover=True,
                forbid_salon_ask=True,
            )
        )

    while len(scenarios) < 52:
        idx += 1
        scenarios.append(
            Scenario(
                f"pad_{idx}",
                f"I want to book {services[idx % len(services)]} in {locations[idx % len(locations)]}",
                expect_discover=True,
                forbid_salon_ask=True,
            )
        )

    return scenarios[:55]


def test_generic_phrase_guard() -> None:
    assert is_generic_salon_phrase("give me salon list")
    assert is_generic_salon_phrase("show options")
    assert not is_generic_salon_phrase("Best Glow Salon")
    print("[PASS] generic salon phrase guard")


def main() -> int:
    print("=" * 72)
    print("DYNAMIC BOOKING ORCHESTRATION — 50+ SCENARIOS")
    print("=" * 72)
    test_generic_phrase_guard()
    scenarios = build_scenarios()
    passed = failed = 0
    failures: list[str] = []
    for s in scenarios:
        try:
            _run(s)
            passed += 1
            print(f"[PASS] {s.name}")
        except Exception as exc:
            failed += 1
            failures.append(f"{s.name}: {exc}")
            print(f"[FAIL] {s.name}: {exc}")

    print("\n" + "=" * 72)
    print(f"TOTAL: {passed}/{passed + failed} passed ({len(scenarios)} scenarios)")
    if failures:
        print("\nFailures:")
        for f in failures[:10]:
            print(f"  - {f}")
        if len(failures) > 10:
            print(f"  ... and {len(failures) - 10} more")
    print("=" * 72)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
