"""Phase 7 — MongoDB connectivity + sample queries.

Run: python scripts/mongo_verify.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402

s = get_settings()


def main() -> None:
    from pymongo import MongoClient

    client = MongoClient(s.mongodb_uri, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    print("MongoDB: CONNECTED")
    db = client[s.mongodb_db_name]
    names = db.list_collection_names()
    print(f"Database: {s.mongodb_db_name}")

    for expected in ["users", "addresses", "categories", "appointments", "bookings", "services", "reviews"]:
        status = "present" if expected in names else "ABSENT"
        count = db[expected].count_documents({}) if expected in names else 0
        print(f"  {expected:14s}: {status:8s} docs={count}")

    print("\nSample: active+approved vendors in Noida")
    q = {
        "userType": "Vendor",
        "status": {"$ne": False},
        "isDeleted": {"$ne": True},
        "adminApproval": "Approved",
        "businessAddress": {"$regex": "Noida", "$options": "i"},
    }
    for d in db["users"].find(q, {"businessName": 1, "businessAddress": 1, "profileImage": 1, "logo": 1}).limit(5):
        img = d.get("profileImage") or d.get("logo") or "-"
        print(f"  - {d.get('businessName')!r} @ {str(d.get('businessAddress'))[:40]!r} img={'yes' if img != '-' else 'no'}")


if __name__ == "__main__":
    main()
