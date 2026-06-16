"""Phase 8 — temporary debug endpoint for salon discovery verification.

GET /debug/salons?location=Noida&category=Hair&service=Hair+Smoothing

Remove this file after debugging is complete.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.repositories.salon_repository import SalonRepository

router = APIRouter()
_repo = SalonRepository()


@router.get("/debug/salons")
def debug_salons(
    location: str | None = Query(default=None),
    category: str | None = Query(default=None),
    service: str | None = Query(default=None),
) -> dict:
    """Return raw MongoDB discovery results for debugging."""
    salons = _repo.discover(location=location, category=category, service=service)

    # Also expose individual set sizes for diagnosis
    loc_count = len(_repo.get_salons_by_location(location)) if location else None
    cat_count = len(_repo.get_salons_by_category(category)) if category else None
    svc_count = len(_repo.get_salons_by_service(service)) if service else None

    return {
        "query": {
            "location": location,
            "category": category,
            "service": service,
        },
        "diagnosis": {
            "vendors_by_location": loc_count,
            "vendors_by_category": cat_count,
            "vendors_by_service": svc_count,
        },
        "count": len(salons),
        "matches": salons,
    }
