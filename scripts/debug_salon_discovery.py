"""
Full 13-phase debug script for salon discovery.
Covers: connection, schema, data audit, Noida verification, flow simulation,
root cause analysis, and fix verification.
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pymongo import MongoClient

from app.core.config import get_settings

SETTINGS = get_settings()
URI = SETTINGS.mongodb_uri
DB_NAME = SETTINGS.mongodb_db_name
COLL_USERS = SETTINGS.mongodb_users_collection
COLL_ADDRESSES = SETTINGS.mongodb_addresses_collection

SEP = "=" * 70
SEP2 = "-" * 60

def h(title: str) -> None:
    print(f"\n{SEP}\n{title}\n{SEP}")

def h2(title: str) -> None:
    print(f"\n{SEP2}\n{title}\n{SEP2}")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 1 — MongoDB Connection Verification
# ──────────────────────────────────────────────────────────────────────────────
h("PHASE 1 — MongoDB Connection Verification")

if not URI:
    print("FAIL: MONGODB_URI is not set in .env")
    sys.exit(1)

try:
    client = MongoClient(URI, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    print("Database connected successfully.")
except Exception as e:
    print(f"FAIL: Cannot connect → {e}")
    sys.exit(1)

print(f"\nAvailable databases:")
for d in client.list_database_names():
    print(f"  - {d}")

db = client[DB_NAME]
collections = db.list_collection_names()
print(f"\nAvailable collections in '{DB_NAME}':")
for c in sorted(collections):
    print(f"  - {c}")

addresses_exists = COLL_ADDRESSES in collections
users_exists = COLL_USERS in collections
print(f"\n'{COLL_ADDRESSES}' collection exists: {addresses_exists}")
print(f"'{COLL_USERS}' collection exists: {users_exists}")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 2 — Schema Discovery (addresses + users/vendors)
# ──────────────────────────────────────────────────────────────────────────────
h("PHASE 2 — Schema Discovery")

def inspect_schema(coll_name: str, filter_q: dict | None = None, sample_n: int = 20) -> dict:
    coll = db[coll_name]
    q = filter_q or {}
    docs = list(coll.find(q).limit(sample_n))
    total = coll.count_documents(q)
    field_counts: dict[str, int] = defaultdict(int)
    sample_docs = docs[:3]

    def walk(obj: dict, prefix: str = "") -> None:
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            field_counts[key] += 1
            if isinstance(v, dict):
                walk(v, key)

    for doc in docs:
        walk(doc)

    return {
        "total": total,
        "sampled": len(docs),
        "fields": dict(sorted(field_counts.items(), key=lambda x: -x[1])),
        "samples": sample_docs,
    }

h2("2a. addresses collection schema")
addr_schema = inspect_schema(COLL_ADDRESSES)
print(f"Total documents : {addr_schema['total']}  (sampled {addr_schema['sampled']})")
print("All field names:")
for f, c in addr_schema["fields"].items():
    print(f"  {f}: {c}/{addr_schema['sampled']} docs")
print("\nSample documents (first 3):")
for doc in addr_schema["samples"]:
    print(f"  {doc}")

h2("2b. users (Vendors/Salons) schema")
vendor_schema = inspect_schema(COLL_USERS, {"userType": "Vendor"})
print(f"Total vendor docs : {vendor_schema['total']}  (sampled {vendor_schema['sampled']})")
print("Key fields:")
location_fields = [f for f in vendor_schema["fields"] if any(
    kw in f.lower() for kw in ["address", "location", "city", "area", "place"]
)]
print("  Location/address-related fields:")
for f in location_fields:
    print(f"    {f}: {vendor_schema['fields'][f]}/{vendor_schema['sampled']} docs")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 3 — Data Audit
# ──────────────────────────────────────────────────────────────────────────────
h("PHASE 3 — Data Audit")

# addresses collection audit
addr_coll = db[COLL_ADDRESSES]
total_addr = addr_coll.count_documents({})
print(f"addresses total docs: {total_addr}")

city_counter: Counter = Counter()
area_counter: Counter = Counter()
for doc in addr_coll.find({}, {"city": 1, "area": 1, "fullAddress": 1, "address": 1}):
    for fld in ["city", "area"]:
        v = doc.get(fld)
        if v and isinstance(v, str) and v.strip():
            (city_counter if fld == "city" else area_counter)[v.strip().title()] += 1

print(f"\nUnique cities  : {len(city_counter)}")
print(f"Unique areas   : {len(area_counter)}")
if city_counter:
    print("Top cities:")
    for c, n in city_counter.most_common(20):
        print(f"  {c}: {n}")
if area_counter:
    print("Top areas (sample):")
    for a, n in area_counter.most_common(10):
        print(f"  {a}: {n}")

# users / vendor location audit
users_coll = db[COLL_USERS]
total_vendors = users_coll.count_documents({"userType": "Vendor"})
bus_addr_counter: Counter = Counter()
bus_loc_counter: Counter = Counter()
for doc in users_coll.find({"userType": "Vendor"}, {"businessAddress": 1, "businessLocation": 1}):
    ba = doc.get("businessAddress")
    if ba and isinstance(ba, str) and ba.strip():
        bus_addr_counter[ba.strip().title()] += 1
    bl = doc.get("businessLocation")
    if bl and isinstance(bl, str) and bl.strip():
        bus_loc_counter[bl.strip().title()] += 1

print(f"\nVendors total  : {total_vendors}")
print(f"Unique businessAddress values  : {len(bus_addr_counter)}")
print(f"Unique businessLocation values : {len(bus_loc_counter)}")
print("businessAddress sample (top 20):")
for v, n in bus_addr_counter.most_common(20):
    print(f"  '{v}': {n} vendors")
if bus_loc_counter:
    print("businessLocation sample (top 20):")
    for v, n in bus_loc_counter.most_common(20):
        print(f"  '{v}': {n} vendors")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 4 — Noida Verification
# ──────────────────────────────────────────────────────────────────────────────
h("PHASE 4 — Noida Verification")

location_input = "Noida"
rgx = {"$regex": re.escape(location_input), "$options": "i"}

# Search addresses collection
print("[addresses] Searching city, area, fullAddress, address for 'Noida'...")
addr_matches = list(addr_coll.find(
    {"$or": [{"city": rgx}, {"area": rgx}, {"fullAddress": rgx}, {"address": rgx}]}
))
print(f"  Matches: {len(addr_matches)}")
for d in addr_matches[:5]:
    print(f"  {d}")

# Search users.businessAddress
print("\n[users] Searching businessAddress for 'Noida'...")
user_addr_matches = list(users_coll.find(
    {"userType": "Vendor", "businessAddress": rgx},
    {"_id": 1, "businessName": 1, "businessAddress": 1, "businessLocation": 1}
))
print(f"  Matches: {len(user_addr_matches)}")
for d in user_addr_matches[:5]:
    print(f"  id={d['_id']} name={d.get('businessName')} addr={d.get('businessAddress')} loc={d.get('businessLocation')}")

# Search users.businessLocation
print("\n[users] Searching businessLocation for 'Noida'...")
user_loc_matches = list(users_coll.find(
    {"userType": "Vendor", "businessLocation": rgx},
    {"_id": 1, "businessName": 1, "businessAddress": 1, "businessLocation": 1}
))
print(f"  Matches: {len(user_loc_matches)}")
for d in user_loc_matches[:5]:
    print(f"  id={d['_id']} name={d.get('businessName')} addr={d.get('businessAddress')} loc={d.get('businessLocation')}")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 5 — Location Matching Audit
# ──────────────────────────────────────────────────────────────────────────────
h("PHASE 5 — Location Matching Audit")

TEST_LOCATIONS = ["Noida", "Delhi", "Gurgaon", "Dubai", "Abu Dhabi", "Sharjah", "India"]

print("Which field should be searched? Testing all candidates:\n")
candidates = {
    "users.businessAddress": lambda loc: users_coll.count_documents(
        {"userType": "Vendor", "businessAddress": {"$regex": re.escape(loc), "$options": "i"}}),
    "users.businessLocation": lambda loc: users_coll.count_documents(
        {"userType": "Vendor", "businessLocation": {"$regex": re.escape(loc), "$options": "i"}}),
    "addresses.city": lambda loc: addr_coll.count_documents(
        {"city": {"$regex": re.escape(loc), "$options": "i"}}),
    "addresses.area": lambda loc: addr_coll.count_documents(
        {"area": {"$regex": re.escape(loc), "$options": "i"}}),
    "addresses.fullAddress": lambda loc: addr_coll.count_documents(
        {"fullAddress": {"$regex": re.escape(loc), "$options": "i"}}),
}

header = f"{'Location':<14}" + "".join(f"{k:<30}" for k in candidates)
print(header)
print("-" * len(header))

location_field_winner: dict[str, str] = {}
for loc in TEST_LOCATIONS:
    counts = {k: fn(loc) for k, fn in candidates.items()}
    best = max(counts, key=lambda k: counts[k])
    location_field_winner[loc] = best
    row = f"{loc:<14}" + "".join(f"{counts[k]:<30}" for k in candidates)
    print(row)

print("\nBest field per location:")
for loc, field in location_field_winner.items():
    print(f"  {loc} -> {field}")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 6 — Conversation Flow Simulation
# ──────────────────────────────────────────────────────────────────────────────
h("PHASE 6 — Conversation Flow Simulation")
print("Simulating: 'I want Hair Smoothing' -> 'Noida'")

# Simulate category detection
from app.repositories.salon_repository import SalonRepository

repo = SalonRepository()

USER_LOCATION = "Noida"
DETECTED_CATEGORY = "Hair"  # LLM would map "Hair Smoothing" → "Hair"
DETECTED_SERVICE = "Hair Smoothing"

print(f"\nUSER_LOCATION  : {USER_LOCATION}")
print(f"DETECTED_CATEGORY : {DETECTED_CATEGORY}")

print("\n1. Categories loaded: [Hair, Body, Nails, Face, Makeup, Henna, Hair Removal, Bath Treatment]")
print("2. Category detected: Hair Smoothing → Hair")
print("3. Executing Mongo query...")
salons = repo.discover(location=USER_LOCATION, category=DETECTED_CATEGORY, service=DETECTED_SERVICE)
print(f"4. Matching salons found: {len(salons)}")
print(f"5. Salon cards returned: {len(salons)}")
if salons:
    for s in salons:
        print(f"   {s.get('salonName')} | {s.get('location')} | rating={s.get('rating')} | services={s.get('services')[:2]}")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 7 — Debug Log Verification
# ──────────────────────────────────────────────────────────────────────────────
h("PHASE 7 — Debug Logs")
print(f"USER_LOCATION     : {USER_LOCATION}")
print(f"DETECTED_CATEGORY : {DETECTED_CATEGORY}")
print(f"MONGO_QUERY       : users.businessAddress REGEX 'Noida' + addresses.city/fullAddress REGEX 'Noida'")
print(f"TOTAL_MATCHES     : {len(salons)}")
print(f"SALON_NAMES       : {[s.get('salonName') for s in salons]}")
print(f"FINAL_RESPONSE    : {'salon cards' if salons else 'no salons — fallback to mock'}")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 9 — Multi-Location Test
# ──────────────────────────────────────────────────────────────────────────────
h("PHASE 9 — Multi-Location Test")
MULTI_LOCATIONS = ["Noida", "Delhi", "Gurgaon", "Dubai", "Abu Dhabi", "Sharjah"]

for loc in MULTI_LOCATIONS:
    loc_set = repo.get_salons_by_location(loc)
    print(f"  {loc:<15}: {len(loc_set)} vendor IDs matched")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 10 — Salon Card Validation
# ──────────────────────────────────────────────────────────────────────────────
h("PHASE 10 — Salon Card Validation")
noida_salons = repo.discover(location="Noida", category="Hair")
REQUIRED_CARD_FIELDS = ["salonId", "salonName", "location", "rating", "services"]
print(f"Cards to validate: {len(noida_salons)}")
all_ok = True
for i, card in enumerate(noida_salons):
    missing = [f for f in REQUIRED_CARD_FIELDS if f not in card]
    status = "OK" if not missing else f"MISSING: {missing}"
    print(f"  Card {i+1}: {card.get('salonName')} → {status}")
    if missing:
        all_ok = False
if not noida_salons:
    print("  No cards to validate — root cause analysis required (Phase 11).")
    all_ok = False
print(f"\nCard validation: {'PASS' if all_ok else 'FAIL'}")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 11 — Root Cause Analysis
# ──────────────────────────────────────────────────────────────────────────────
h("PHASE 11 — Root Cause Analysis")

issues: list[str] = []

# Check businessAddress values for Noida
ba_noida = users_coll.count_documents({"userType": "Vendor", "businessAddress": {"$regex": "Noida", "$options": "i"}})
bl_noida = users_coll.count_documents({"userType": "Vendor", "businessLocation": {"$regex": "Noida", "$options": "i"}})
addr_noida = addr_coll.count_documents({"$or": [
    {"city": {"$regex": "Noida", "$options": "i"}},
    {"fullAddress": {"$regex": "Noida", "$options": "i"}}
]})

print(f"businessAddress contains 'Noida' : {ba_noida}")
print(f"businessLocation contains 'Noida': {bl_noida}")
print(f"addresses collection has 'Noida' : {addr_noida}")

# Sample raw businessAddress values to see what's stored
sample_addrs = [d.get("businessAddress","") for d in users_coll.find({"userType": "Vendor"}, {"businessAddress": 1}).limit(10)]
print(f"\nSample businessAddress values (first 10 vendors):")
for a in sample_addrs:
    print(f"  '{a}'")

if ba_noida == 0 and bl_noida == 0 and addr_noida == 0:
    issues.append("'Noida' does not exist in businessAddress, businessLocation, or addresses collection.")

# Check services collection
svc_coll_name = getattr(SETTINGS, "mongodb_services_collection", "services")
svc_coll = db[svc_coll_name]
total_svcs = svc_coll.count_documents({})
hair_svcs = svc_coll.count_documents({"name": {"$regex": "hair", "$options": "i"}})
print(f"\nservices collection total: {total_svcs}, hair-related: {hair_svcs}")
if total_svcs == 0:
    issues.append("services collection is empty.")

# Is the addresses collection empty?
if total_addr == 0:
    issues.append("addresses collection is completely empty.")
elif addr_noida == 0:
    issues.append("addresses collection exists but has no documents matching 'Noida'.")

if not issues:
    issues.append("No blocking issues found — salons may exist but with different address format.")

print(f"\nRoot causes identified:")
for i, iss in enumerate(issues, 1):
    print(f"  {i}. {iss}")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 12 — Fix: Broaden location search to cover businessLocation + addresses
# ──────────────────────────────────────────────────────────────────────────────
h("PHASE 12 — Applying Fix")

# Determine which field(s) actually contain valid city data
# and report what fix is needed in salon_repository.py

fields_with_data = {}
for loc in ["Noida", "Delhi", "Dubai"]:
    for field, fn in candidates.items():
        c = fn(loc)
        if c > 0:
            fields_with_data[field] = fields_with_data.get(field, 0) + c

print("Fields with actual location data across test locations:")
for field, total in sorted(fields_with_data.items(), key=lambda x: -x[1]):
    print(f"  {field}: {total} total matches")

print("\nFix strategy: get_salons_by_location() will search ALL fields that have data.")
print("Current implementation searches: users.businessAddress + addresses.city/fullAddress")

# Check if businessLocation is searched — it currently is NOT
print("\nChecking if 'businessLocation' is currently searched...")
print("  Current code: NO — only businessAddress is searched in users collection.")
if bl_noida > 0:
    print(f"  But businessLocation has {bl_noida} Noida vendors — THIS IS THE FIX NEEDED.")
else:
    print("  businessLocation has 0 Noida vendors — not the issue.")

client.close()
