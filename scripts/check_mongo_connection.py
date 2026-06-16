"""Connection + data-fetch diagnostic for MongoDB (salon location focus)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

URI = os.getenv("MONGODB_URI", "")
DB_NAME = os.getenv("MONGODB_DB_NAME", "bookly")


def mask(uri: str) -> str:
    if "@" in uri:
        head, tail = uri.split("@", 1)
        if "//" in head:
            proto, creds = head.split("//", 1)
            user = creds.split(":", 1)[0]
            return f"{proto}//{user}:****@{tail}"
    return uri


def main() -> None:
    print("=" * 70)
    print("1) CONNECTION CHECK")
    print("=" * 70)
    print("URI:", mask(URI) if URI else "(not set)")
    print("DB :", DB_NAME)
    if not URI:
        raise SystemExit("MONGODB_URI not set in .env")

    from pymongo import MongoClient

    t0 = time.time()
    client = MongoClient(URI, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    print(f"PING OK  ({(time.time()-t0)*1000:.0f} ms)")
    server_info = client.server_info()
    print("MongoDB server version:", server_info.get("version"))
    db = client[DB_NAME]
    print("Collections:", sorted(db.list_collection_names()))

    print()
    print("=" * 70)
    print("2) SALON LOCATION DATA (users[Vendor].businessAddress)")
    print("=" * 70)
    users = db["users"]
    total_vendors = users.count_documents({"userType": "Vendor", "isDeleted": {"$ne": True}})
    with_addr = users.count_documents(
        {"userType": "Vendor", "isDeleted": {"$ne": True}, "businessAddress": {"$nin": [None, ""]}}
    )
    print(f"Non-deleted vendors: {total_vendors} | with businessAddress: {with_addr}")
    print("Sample vendor locations:")
    for v in users.find(
        {"userType": "Vendor", "isDeleted": {"$ne": True}, "businessAddress": {"$nin": [None, ""]}},
        {"businessName": 1, "businessAddress": 1, "businessLocation": 1},
    ).limit(20):
        print(
            "  -",
            {
                "id": str(v["_id"]),
                "name": v.get("businessName"),
                "businessAddress": v.get("businessAddress"),
                "businessLocation": v.get("businessLocation"),
            },
        )

    print()
    print("=" * 70)
    print("3) ADDRESSES COLLECTION (geo / city data)")
    print("=" * 70)
    addresses = db["addresses"]
    print("Total addresses:", addresses.estimated_document_count())
    print("Distinct cities:", addresses.distinct("city"))
    vendor_ids = {v["_id"] for v in users.find({"userType": "Vendor"}, {"_id": 1})}
    addr_user_ids = {a.get("userId") for a in addresses.find({}, {"userId": 1})}
    print("Vendor ids that also appear in addresses.userId:", len(vendor_ids & addr_user_ids))
    print("Sample address docs (location focus):")
    for a in addresses.find({}, {"city": 1, "fullAddress": 1, "location": 1, "userId": 1}).limit(8):
        print(
            "  -",
            {
                "userId": str(a.get("userId")),
                "city": a.get("city"),
                "fullAddress": a.get("fullAddress"),
                "location": a.get("location"),
            },
        )

    print()
    print("=" * 70)
    print("4) REPOSITORY FETCH (what the app actually reads)")
    print("=" * 70)
    from app.repositories.salon_repository import SalonRepository

    repo = SalonRepository()
    print("repo.is_available():", repo.is_available())
    for loc in ["Noida", "India", "Dubai", "Abu Dhabi"]:
        ids = repo.get_salons_by_location(loc)
        print(f"  get_salons_by_location({loc!r}) -> {len(ids)} vendor(s)")
    print()
    print("Full discover('Noida', category='Hair', service='Hair'):")
    for s in repo.discover(location="Noida", category="Hair", service="Hair"):
        print("  -", {"salonId": s["salonId"], "salonName": s["salonName"], "location": s["location"], "rating": s["rating"], "services": s["services"][:3]})


if __name__ == "__main__":
    main()
