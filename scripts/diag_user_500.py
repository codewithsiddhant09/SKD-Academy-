"""Diagnose HTTP 500 on real userId: inspect field types + reproduce profile build.

Run: python scripts/diag_user_500.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.services.user_service import UserService  # noqa: E402

s = get_settings()


def main() -> None:
    from pymongo import MongoClient

    client = MongoClient(s.mongodb_uri, serverSelectionTimeoutMS=8000)
    db = client[s.mongodb_db_name]
    users = db[s.mongodb_users_collection]

    # Sample one Vendor and one Customer
    samples = {
        "Vendor": users.find_one({"userType": "Vendor"}),
        "Customer": users.find_one({"userType": {"$ne": "Vendor"}}),
    }

    fields = ["fullName", "countryCode", "phoneNumber", "email", "userType",
              "isVerified", "status", "businessLocation", "serviceType",
              "isCompleted", "adminApproval", "dob", "gender", "nationality"]

    for label, doc in samples.items():
        print(f"\n=== {label} sample types ===")
        if not doc:
            print("  (none)")
            continue
        print(f"  _id={doc.get('_id')}")
        for f in fields:
            if f in doc:
                print(f"  {f:18s}: {type(doc[f]).__name__:8s} = {str(doc[f])[:50]!r}")

    # Reproduce: run the real UserService.get_user_profile on real ids
    svc = UserService()
    print("\n=== REPRODUCE get_user_profile on real userIds ===")
    for label, doc in samples.items():
        if not doc:
            continue
        uid = str(doc["_id"])
        try:
            profile = svc.get_user_profile(uid)
            print(f"  [{label}] uid={uid} -> OK profile={profile is not None}")
        except Exception as exc:
            print(f"  [{label}] uid={uid} -> RAISED {type(exc).__name__}: {str(exc)[:160]}")


if __name__ == "__main__":
    main()
