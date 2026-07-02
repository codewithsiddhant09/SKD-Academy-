"""Debug MongoDB salon discovery — schema + query investigation."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pymongo import MongoClient

from app.core.config import get_settings
from app.repositories.salon_repository import SalonRepository


def main() -> None:
    s = get_settings()
    print("=" * 72)
    print("MONGODB SALON DEBUG")
    print("=" * 72)
    print(f"URI configured: {bool(s.mongodb_uri)}")
    print(f"DB: {s.mongodb_db_name}")
    print(f"users collection: {s.mongodb_users_collection}")
    print(f"addresses collection: {s.mongodb_addresses_collection}")

    client = MongoClient(s.mongodb_uri, serverSelectionTimeoutMS=15000)
    client.admin.command("ping")
    db = client[s.mongodb_db_name]
    print("Connection: OK\n")

    # --- addresses sample ---
    print("=== SAMPLE addresses document ===")
    addr = db["addresses"].find_one()
    if addr:
        for k, v in sorted(addr.items()):
            print(f"  {k}: {type(v).__name__} = {str(v)[:100]}")
        addr_noida = db["addresses"].count_documents({"city": {"$regex": "Noida", "$options": "i"}})
        print(f"  addresses with city~Noida: {addr_noida}")
    else:
        print("  (collection empty or missing)")

    # --- vendor sample ---
    print("\n=== SAMPLE Vendor user (location fields) ===")
    vendor = db["users"].find_one({"userType": "Vendor"})
    if vendor:
        for k in (
            "businessName", "businessAddress", "businessLocation", "city",
            "status", "isDeleted", "adminApproval", "userType",
        ):
            if k in vendor:
                print(f"  {k}: {vendor[k]}")

    rgx = {"$regex": re.escape("Noida"), "$options": "i"}
    active = {
        "userType": "Vendor",
        "status": {"$ne": False},
        "isDeleted": {"$ne": True},
        "adminApproval": "Approved",
    }

    print("\n=== Noida vendor counts (users.businessAddress) ===")
    q1 = {"userType": "Vendor", "businessAddress": rgx}
    q2 = {**active, "businessAddress": rgx}
    print(f"  all vendors: {db['users'].count_documents(q1)}")
    print(f"  active+approved: {db['users'].count_documents(q2)}")

    print("\n=== First 5 active Noida vendors ===")
    for d in db["users"].find(q2, {"businessName": 1, "businessAddress": 1}).limit(5):
        print(f"  {d.get('businessName')} | {d.get('businessAddress', '')[:60]}")

    # Category IDs for Hair
    print("\n=== Hair category IDs ===")
    hair_cats = list(db["categories"].find({"name": {"$regex": "Hair", "$options": "i"}}, {"name": 1}))
    for c in hair_cats[:10]:
        print(f"  id={c['_id']} name={c.get('name')}")
    hair_cat_ids = [c["_id"] for c in hair_cats]

    print("\n=== Services in Hair categories (sample) ===")
    svc_count = db["services"].count_documents(
        {"categoryId": {"$in": hair_cat_ids}, "isDeleted": {"$ne": True}}
    )
    print(f"  active services in Hair categories: {svc_count}")

    # Intersection test
    repo = SalonRepository()
    loc_set = repo.get_salons_by_location("Noida")
    cat_set = repo.get_salons_by_category("Hair")
    svc_set = repo.get_salons_by_service("Hair Smoothing")
    print("\n=== Set sizes ===")
    print(f"  by_location(Noida): {len(loc_set)}")
    print(f"  by_category(Hair): {len(cat_set)}")
    print(f"  by_service(Hair Smoothing): {len(svc_set)}")
    print(f"  intersection loc & (cat|svc): {len(loc_set & (cat_set | svc_set))}")

    print("\n=== discover() scenarios ===")
    scenarios = [
        ("Noida", "Hair", "Hair Smoothing"),
        ("Noida", "Hair", None),
        ("Noida", None, None),
        ("Delhi", "Hair", "Hair Smoothing"),
        ("Dubai", "Hair", "Hair Smoothing"),
        ("Noida", "Henna", "Henna"),
        ("Noida", "Face", "Facial"),
        ("Noida", "Body", "Massage"),
        ("Noida", "Hair Removal", "Waxing"),
    ]
    for loc, cat, svc in scenarios:
        results = repo.discover(location=loc, category=cat, service=svc)
        names = [r.get("salonName") for r in results[:3]]
        print(f"  [{len(results)}] loc={loc} cat={cat} svc={svc} -> {names}")

    client.close()


if __name__ == "__main__":
    main()
