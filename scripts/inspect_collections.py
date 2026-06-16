"""Inspect categories, services, and vendor isDeleted distribution."""
from __future__ import annotations
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pymongo import MongoClient
from app.core.config import get_settings

s = get_settings()
client = MongoClient(s.mongodb_uri, serverSelectionTimeoutMS=8000)
db = client[s.mongodb_db_name]

# --- categories ---
print("=== categories collection ===")
total_cats = db["categories"].count_documents({})
print(f"Total: {total_cats}")
for c in db["categories"].find({}, {"name": 1}).limit(20):
    print(f"  id={c['_id']}  name={c.get('name')}")

# --- services ---
print(f"\n=== services collection ===")
total_svcs = db["services"].count_documents({})
active_svcs = db["services"].count_documents({"isDeleted": {"$ne": True}})
print(f"Total={total_svcs}  active(isDeleted!=True)={active_svcs}")
for sv in db["services"].find({}, {"name": 1, "categoryId": 1, "vendorId": 1, "isDeleted": 1}).limit(15):
    print(f"  name={sv.get('name')}  catId={sv.get('categoryId')}  vendorId={sv.get('vendorId')}  deleted={sv.get('isDeleted')}")

# --- vendor isDeleted distribution ---
print("\n=== Vendor isDeleted field distribution ===")
deleted_vals = Counter(str(d.get("isDeleted")) for d in db["users"].find({"userType": "Vendor"}, {"isDeleted": 1}))
print(f"  {dict(deleted_vals)}")

# --- Noida vendor counts with and without isDeleted filter ---
import re
rgx = {"$regex": re.escape("Noida"), "$options": "i"}
noida_all = db["users"].count_documents({"userType": "Vendor", "businessAddress": rgx})
noida_ok = db["users"].count_documents({"userType": "Vendor", "isDeleted": {"$ne": True}, "businessAddress": rgx})
print(f"\nNoida vendors total: {noida_all}  (after isDeleted filter: {noida_ok})")

# --- Show the 22 noida vendor names and isDeleted values ---
print("\n=== All Noida vendors (businessAddress matches) ===")
for d in db["users"].find({"userType": "Vendor", "businessAddress": rgx}, {"businessName": 1, "isDeleted": 1, "adminApproval": 1}):
    print(f"  name={d.get('businessName')}  isDeleted={d.get('isDeleted')}  adminApproval={d.get('adminApproval')}")

client.close()
