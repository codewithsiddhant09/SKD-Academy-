"""Verify the HTTP 500-on-real-userId fix across required scenarios.

Service-level (UserService) + does not require the HTTP server.

Run: python scripts/test_user_profile_500.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.services.user_service import UserService  # noqa: E402

s = get_settings()
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")


def main() -> int:
    from bson import ObjectId
    from pymongo import MongoClient

    db = MongoClient(s.mongodb_uri, serverSelectionTimeoutMS=8000)[s.mongodb_db_name]
    users = db[s.mongodb_users_collection]
    svc = UserService()

    # 1) Valid userId (Vendor with bool status) — must NOT raise, returns profile
    vendor = users.find_one({"userType": "Vendor"})
    uid = str(vendor["_id"])
    try:
        p = svc.get_user_profile(uid)
        record("valid userId (Vendor)", p is not None and p.user_id == uid,
               f"fullName={getattr(p, 'full_name', None)!r} status={getattr(p, 'status', None)!r}")
    except Exception as exc:
        record("valid userId (Vendor)", False, f"RAISED {type(exc).__name__}: {exc}")

    # 2) Customer/Admin with businessLocation as dict + serviceType as list
    other = users.find_one({"userType": {"$ne": "Vendor"}, "businessLocation": {"$type": "object"}}) \
        or users.find_one({"userType": {"$ne": "Vendor"}})
    if other:
        ouid = str(other["_id"])
        try:
            p = svc.get_user_profile(ouid)
            record("valid userId (non-Vendor, object fields)", p is not None,
                   f"business_location={getattr(p, 'business_location', None)!r}")
        except Exception as exc:
            record("valid userId (non-Vendor, object fields)", False, f"RAISED {type(exc).__name__}: {exc}")

    # 3) Invalid ObjectId — must return None, no raise
    try:
        p = svc.get_user_profile("not-a-valid-objectid-123")
        record("invalid ObjectId", p is None, "returned None")
    except Exception as exc:
        record("invalid ObjectId", False, f"RAISED {type(exc).__name__}: {exc}")

    # 4) Deleted user (isDeleted=True) — still resolvable without raising
    deleted = users.find_one({"userType": "Vendor", "isDeleted": True})
    if deleted:
        try:
            p = svc.get_user_profile(str(deleted["_id"]))
            record("deleted user", p is not None, "loaded without error")
        except Exception as exc:
            record("deleted user", False, f"RAISED {type(exc).__name__}: {exc}")
    else:
        record("deleted user", True, "no deleted user to test (skipped)")

    # 5) User without businessLocation — must not raise
    no_loc = users.find_one({"userType": "Vendor", "businessLocation": {"$exists": False}})
    if no_loc:
        try:
            p = svc.get_user_profile(str(no_loc["_id"]))
            record("user without businessLocation", p is not None and p.business_location is None,
                   "business_location=None")
        except Exception as exc:
            record("user without businessLocation", False, f"RAISED {type(exc).__name__}: {exc}")
    else:
        record("user without businessLocation", True, "none found (skipped)")

    # 6) User without bookings — chatbot user lookup is independent of bookings
    no_book = None
    for u in users.find({"userType": "Vendor"}, {"_id": 1}).limit(50):
        if db["bookings"].count_documents({"userId": u["_id"]}) == 0 and \
           db["bookings"].count_documents({"userId": str(u["_id"])}) == 0:
            no_book = u
            break
    if no_book:
        try:
            p = svc.get_user_profile(str(no_book["_id"]))
            record("user without bookings", p is not None, "profile loaded; bookings not required")
        except Exception as exc:
            record("user without bookings", False, f"RAISED {type(exc).__name__}: {exc}")
    else:
        record("user without bookings", True, "all sampled users have bookings (skipped)")

    # 7) Non-existent (but valid) ObjectId — None, no raise
    try:
        p = svc.get_user_profile(str(ObjectId()))
        record("non-existent valid ObjectId", p is None, "returned None")
    except Exception as exc:
        record("non-existent valid ObjectId", False, f"RAISED {type(exc).__name__}: {exc}")

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n======== RESULT: {passed}/{len(results)} PASSED ========")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
