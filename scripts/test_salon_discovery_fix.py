"""Regression tests for MongoDB salon discovery location fix."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.repositories.salon_repository import SalonRepository
from app.services.location_service import LocationService
from app.utils.location import sanitize_location


def test_sanitize() -> None:
    assert sanitize_location("Noida}]}") == "Noida"
    assert sanitize_location("  noida  ") == "noida"
    assert sanitize_location("NOIDA") == "NOIDA"
    assert sanitize_location("  Dubai  ") == "Dubai"
    print("[PASS] sanitize_location")


def test_location_service() -> None:
    ls = LocationService()
    assert ls.analyze("Noida}]}").normalized_location == "Noida"
    assert ls.analyze("noida").normalized_location == "Noida"
    print("[PASS] LocationService.analyze")


def test_mongo_discover() -> None:
    repo = SalonRepository()
    assert repo.is_available(), "MongoDB must be reachable"

    # Corrupted location now sanitized inside repository
    corrupt = repo.discover(location="Noida}]}", category="Hair", service="Hair Smoothing")
    clean = repo.discover(location="Noida", category="Hair", service="Hair Smoothing")
    assert len(corrupt) == len(clean) and len(clean) > 0, f"expected salons, got corrupt={len(corrupt)} clean={len(clean)}"
    print(f"[PASS] discover corrupt->clean ({len(clean)} salons)")

    scenarios = [
        ("Noida", "Hair", "Hair Smoothing"),
        ("Noida", "Henna", "Henna"),
        ("Dubai", "Hair", "Hair Smoothing"),
    ]
    for loc, cat, svc in scenarios:
        n = len(repo.discover(location=loc, category=cat, service=svc))
        print(f"[{'PASS' if n else 'INFO'}] discover {svc} @ {loc}: {n} salons")


def test_orchestrator_flow() -> None:
    from app.services.category_service import CategoryService
    from app.services.orchestrator_service import OrchestratorService

    cs = CategoryService()
    os = OrchestratorService(categories=cs.get_category_names(), category_service=cs)
    cases = [
        ("Hair Smoothing", "Noida", 1),
        ("I want Henna", "Noida", 1),
    ]
    for service, location, min_recs in cases:
        sid = "reg_" + uuid.uuid4().hex[:8]
        os.chat(sid, service)
        r2 = os.chat(sid, location)
        loc = os.memory.get_session_memory(sid).preferred_location
        assert loc == location, f"expected clean location {location!r}, got {loc!r}"
        assert len(r2.recommendations) >= min_recs, (
            f"{service}->{location}: expected >={min_recs} cards, got {len(r2.recommendations)}; "
            f"reply={r2.reply[:120]}"
        )
        print(
            f"[PASS] {service} -> {location} ({len(r2.recommendations)} cards): "
            f"{[x.salon_name for x in r2.recommendations[:3]]}"
        )


def main() -> int:
    print("=" * 72)
    print("SALON DISCOVERY FIX REGRESSION")
    print("=" * 72)
    test_sanitize()
    test_location_service()
    test_mongo_discover()
    try:
        test_orchestrator_flow()
    except AssertionError as exc:
        print(f"[FAIL] orchestrator flow: {exc}")
        return 1
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
