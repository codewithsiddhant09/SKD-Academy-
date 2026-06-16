"""Phase 13 — Final rerun after all fixes."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.repositories.salon_repository import SalonRepository

repo = SalonRepository()
SEP = "-" * 65

tests = [
    ("Hair Smoothing", "Hair",   "Noida",     "SHOULD find salons (service tokens + category)"),
    ("Hair Coloring",  "Hair",   "Noida",     "SHOULD find salons"),
    ("Facial",         "Face",   "Delhi",     "No approved vendors in Delhi - 0 (fall to mock)"),
    ("Bridal Makeup",  "Makeup", "Gurgaon",   "No vendors in Gurgaon - 0 (fall to mock)"),
    ("Hair",           "Hair",   "India",     "SHOULD find salons (vendors set businessAddress=India)"),
    ("Hair",           "Hair",   "Abu Dhabi", "1 approved vendor in Abu Dhabi may appear"),
    ("Nail",           "Nails",  "Noida",     "No Nail services in DB - 0 expected (correct)"),
    (None,             None,     "Noida",     "Location-only: returns all approved Noida vendors"),
]

print("=== PHASE 13 — Final Rerun After Fix ===\n")
print(f"{'Test':<35} {'Count':>5}  {'Card OK':>7}  Note")
print(SEP)

all_pass = True
for svc, cat, loc, note in tests:
    salons = repo.discover(location=loc, category=cat, service=svc)
    fields_ok = all(
        all(k in s for k in ["salonId", "salonName", "location", "rating", "services"])
        for s in salons
    ) if salons else True

    label = f"{svc or '-'} + {loc}"
    status = "YES" if fields_ok else "FAIL"
    print(f"{label:<35} {len(salons):>5}  {status:>7}  {note}")
    for s in salons[:2]:
        print(f"  {s.get('salonName')} | loc={s.get('location')} | svcs={s.get('services', [])[:2]}")
    if not fields_ok:
        all_pass = False

print(SEP)
print(f"Card validation global PASS: {all_pass}")

# Debug endpoint simulation (Phase 8)
print("\n=== PHASE 8 — Debug Endpoint Simulation ===")
import json
for loc in ["Noida", "Delhi", "Gurgaon", "Dubai", "Abu Dhabi", "Sharjah"]:
    salons = repo.discover(location=loc, category="Hair", service="Hair Smoothing")
    print(json.dumps({"location": loc, "count": len(salons), "matches": [s.get("salonName") for s in salons]}, ensure_ascii=False))
