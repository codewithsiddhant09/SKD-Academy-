"""QA audit: inspect live MongoDB schema for bugs 1, 2, 6, 8.

Run: python scripts/audit_qa_schema.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402

settings = get_settings()


def main() -> None:
    from pymongo import MongoClient

    if not settings.mongodb_uri:
        print("MONGODB_URI not set")
        return

    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    db = client[settings.mongodb_db_name]
    print(f"Connected to db={settings.mongodb_db_name}")
    print("Collections:", db.list_collection_names())

    users = db[settings.mongodb_users_collection]

    # ---- Vendor field discovery -------------------------------------------
    vendor = users.find_one({"userType": "Vendor"})
    print("\n=== SAMPLE VENDOR FIELDS ===")
    if vendor:
        for k in sorted(vendor.keys()):
            v = vendor[k]
            preview = str(v)[:60]
            print(f"  {k}: {preview}")

    # ---- Status field distribution ----------------------------------------
    print("\n=== VENDOR STATUS FIELDS ===")
    for field in ["status", "isDeleted", "isActive", "adminApproval", "isVerified", "isBlocked", "isSuspended"]:
        vals = Counter()
        present = 0
        for d in users.find({"userType": "Vendor"}, {field: 1}):
            if field in d:
                present += 1
                vals[str(d.get(field))] += 1
        if present:
            print(f"  {field}: present={present} values={dict(vals)}")
        else:
            print(f"  {field}: NOT PRESENT")

    # ---- Image field discovery --------------------------------------------
    print("\n=== VENDOR IMAGE FIELDS ===")
    for field in ["profileImage", "avatar", "image", "logo", "coverImage", "businessLogo", "photo", "picture"]:
        present = sum(1 for _ in users.find({"userType": "Vendor", field: {"$exists": True, "$ne": None, "$nin": ["", None]}}, {field: 1}).limit(200))
        sample = users.find_one({"userType": "Vendor", field: {"$exists": True, "$ne": ""}}, {field: 1})
        sval = str(sample.get(field))[:70] if sample else "-"
        print(f"  {field}: nonempty~{present}  sample={sval}")

    # ---- City source comparison -------------------------------------------
    total_vendors = users.count_documents({"userType": "Vendor"})
    approved = users.count_documents({"userType": "Vendor", "adminApproval": "Approved", "isDeleted": {"$ne": True}})
    print(f"\n=== VENDOR COUNTS ===\n  total={total_vendors} approved&active={approved}")

    print("\n=== DISTINCT businessAddress (vendors) ===")
    addrs = users.distinct("businessAddress", {"userType": "Vendor"})
    print(f"  count={len(addrs)}")
    for a in sorted(str(x) for x in addrs if x):
        print(f"   - {a}")

    # ---- addresses collection ---------------------------------------------
    print("\n=== addresses COLLECTION ===")
    addresses = db[settings.mongodb_addresses_collection]
    print(f"  total docs={addresses.count_documents({})}")
    sample = addresses.find_one()
    if sample:
        print("  sample fields:", sorted(sample.keys()))
    for field in ["city", "area", "state", "fullAddress", "location"]:
        vals = addresses.distinct(field)
        print(f"  distinct {field}: {len(vals)} -> {[str(v)[:30] for v in vals[:10] if v]}")

    # ---- categories -------------------------------------------------------
    print("\n=== categories COLLECTION ===")
    cats = db[settings.mongodb_categories_collection]
    print(f"  total={cats.count_documents({})}")
    for c in cats.find({}, {"name": 1, "isDeleted": 1, "status": 1}):
        print(f"   - {c.get('name')!r} isDeleted={c.get('isDeleted')} status={c.get('status')}")


if __name__ == "__main__":
    main()
