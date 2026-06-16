"""Phase 9 verification at the repository/service layer (real MongoDB)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.repositories.salon_repository import SalonRepository
from app.services.salon_service import SalonService


def main() -> None:
    repo = SalonRepository()
    svc = SalonService(repository=repo)

    print("available:", repo.is_available())
    print()

    print("=== Phase 2 query functions ===")
    print("by_category('Hair'):", len(repo.get_salons_by_category("Hair")))
    print("by_service('Hair Smoothing'):", len(repo.get_salons_by_service("Hair Smoothing")))
    print("by_location('Noida'):", len(repo.get_salons_by_location("Noida")))
    print("by_location('Dubai'):", len(repo.get_salons_by_location("Dubai")))
    print()

    cases = [
        ("Hair Smoothing", "Hair", "Dubai"),
        ("Hair Coloring", "Hair", "Dubai Marina"),
        ("Facial", "Face", "Abu Dhabi"),
        ("Bridal Makeup", "Makeup", "Sharjah"),
        # Real-data demonstrations (locations that actually exist in the DB)
        ("Hair", "Hair", "Noida"),
        ("Makeup", "Makeup", "India"),
        ("Facial", "Face", "Noida"),
    ]
    print("=== discover() results ===")
    for service, category, location in cases:
        salons = svc.discover(category=category, service=service, location=location, radius_km=15)
        names = [(s.salon_name, s.location, s.rating) for s in salons[:5]]
        print(f"[{service} + {location}] -> {len(salons)} salon(s): {names}")


if __name__ == "__main__":
    main()
