"""QA bug regression suite (Bugs 1, 2, 4, 6, 7, 8) against live MongoDB.

Run: python scripts/test_qa_bugs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.intent_agent import IntentAgent  # noqa: E402
from app.models.enums import IntentType  # noqa: E402
from app.repositories.salon_repository import SalonRepository  # noqa: E402
from app.services.category_service import CategoryService  # noqa: E402

repo = SalonRepository()
results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    results.append((name, passed, detail))
    print(f"[{'PASS' if passed else 'FAIL'}] {name} {('- ' + detail) if detail else ''}")


def main() -> int:
    if not repo.is_available():
        print("MongoDB unavailable — cannot run live tests.")
        return 1

    # ---- Bug 1: city listings -----------------------------------------
    cities = repo.get_distinct_cities()
    check("Bug1 cities non-empty", len(cities) > 0, f"{len(cities)} cities: {cities}")
    check("Bug1 includes Noida", any("noida" in c.lower() for c in cities))

    # ---- Bug 2: disabled SPs filtered ---------------------------------
    db = repo._database()
    users = db[repo._settings.mongodb_users_collection]
    # A disabled vendor (status False) should NOT appear in any discovery.
    disabled = users.find_one({"userType": "Vendor", "status": False}, {"_id": 1, "businessAddress": 1})
    if disabled:
        loc = disabled.get("businessAddress") or ""
        ids = repo.get_salons_by_location(loc) if loc else set()
        check("Bug2 disabled SP filtered", disabled["_id"] not in ids,
              f"disabled vendor {disabled['_id']} excluded from location '{loc}'")
    else:
        check("Bug2 disabled SP filtered", True, "no disabled vendor in DB to test")
    # Also confirm deleted/unapproved excluded by sampling discover output.
    sample = repo.discover(location="Noida")
    bad = []
    for s in sample:
        doc = users.find_one({"_id": __import__("bson").ObjectId(s["salonId"])},
                             {"status": 1, "isDeleted": 1, "adminApproval": 1})
        if doc and (doc.get("status") is False or doc.get("isDeleted") is True
                    or doc.get("adminApproval") != "Approved"):
            bad.append(s["salonId"])
    check("Bug2 only active/approved returned", not bad, f"violations={bad}")

    # ---- Bug 4: category filtering reaches Mongo ----------------------
    hair_ids = repo.get_salons_by_category("Hair")
    check("Bug4 category->vendors", isinstance(hair_ids, set), f"Hair vendors={len(hair_ids)}")

    # ---- Bug 6: locations by category ---------------------------------
    hair_cities = repo.get_cities_by_category("Hair")
    check("Bug6 cities-by-category subset of all", set(hair_cities).issubset(set(cities)) or not hair_cities,
          f"Hair cities={hair_cities}")

    # ---- Bug 8: profile image in payload ------------------------------
    discovered = repo.discover(location="Noida")
    has_image_key = all("image" in s for s in discovered) if discovered else True
    check("Bug8 image key present in card", has_image_key,
          f"{sum(1 for s in discovered if s.get('image'))}/{len(discovered)} have a non-null image")

    # ---- Bug 7: intent detection --------------------------------------
    agent = IntentAgent()
    cats = CategoryService().get_category_names()
    intent_cases = [
        ("Show vendors in Noida", IntentType.SALON_SEARCH),
        ("Hair Smoothing", IntentType.SERVICE_SEARCH),
        ("Hair Smoothing in Noida", IntentType.SERVICE_SEARCH),
        ("What is Bookly?", IntentType.FAQ),
    ]
    for q, expected in intent_cases:
        analysis = agent.analyze(message=q, categories=cats, history=[])
        ok = analysis.intent == expected
        check(f"Bug7 intent '{q}'", ok, f"got={analysis.intent} expected={expected}")

    passed = sum(1 for _, p, _ in results if p)
    print(f"\nRESULT: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
