"""Fetch salon (vendor) details directly from the `users` collection."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymongo import MongoClient

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.mongodb_uri:
        print("MONGODB_URI not configured in .env")
        return

    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[settings.mongodb_db_name]
    users = db[settings.mongodb_users_collection]

    total = users.count_documents({})
    vendors = users.count_documents({"userType": "Vendor"})
    print(f"DB={settings.mongodb_db_name}  collection={settings.mongodb_users_collection}")
    print(f"Total users={total}  Vendors (salons)={vendors}\n")

    # Field coverage across vendor docs
    field_counts: dict[str, int] = {}
    cursor = users.find({"userType": "Vendor"})
    sample_docs = []
    for i, doc in enumerate(cursor):
        for k in doc.keys():
            field_counts[k] = field_counts.get(k, 0) + 1
        if i < 3:
            sample_docs.append(doc)

    print("=== Vendor field coverage (field: count present) ===")
    for k, c in sorted(field_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {c}/{vendors}")

    print("\n=== Sample salon details (first 3 vendors) ===")
    for doc in sample_docs:
        print("-" * 60)
        print(f"  _id            : {doc.get('_id')}")
        print(f"  businessName   : {doc.get('businessName')}")
        print(f"  fullName       : {doc.get('fullName')}")
        print(f"  businessAddress: {doc.get('businessAddress')}")
        print(f"  email          : {doc.get('email')}")
        print(f"  phoneNumber    : {doc.get('phoneNumber')}")
        print(f"  serviceType    : {doc.get('serviceType')}")
        print(f"  status         : {doc.get('status')}")
        print(f"  adminApproval  : {doc.get('adminApproval')}")

    client.close()


if __name__ == "__main__":
    main()
