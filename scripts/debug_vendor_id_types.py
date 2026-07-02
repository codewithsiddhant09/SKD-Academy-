"""Check vendorId type consistency in salon discovery sets."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.repositories.salon_repository import SalonRepository

repo = SalonRepository()
loc = repo.get_salons_by_location("Noida")
cat = repo.get_salons_by_category("Hair")
svc = repo.get_salons_by_service("Hair Smoothing")

print("by_location:", len(loc), "types:", {type(x).__name__ for x in loc})
print("by_category:", len(cat), "types:", {type(x).__name__ for x in cat})
print("by_service:", len(svc), "types:", {type(x).__name__ for x in svc})

loc_str = {str(x) for x in loc}
cat_str = {str(x) for x in cat}
print("intersection strict:", len(loc & cat))
print("intersection str-normalized:", len(loc_str & cat_str))
