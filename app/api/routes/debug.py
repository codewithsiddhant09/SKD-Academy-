"""Debug endpoints for QA verification of salon discovery, cities,
and categories.

These are diagnostic-only and safe to remove after QA sign-off.

    GET /debug/cities
    GET /debug/categories
    GET /debug/salons?city=Noida
    GET /debug/salons?category=Hair
    GET /debug/salons?location=Noida&category=Hair&service=Hair+Smoothing
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.repositories.salon_repository import SalonRepository
from app.services.category_service import CategoryService

router = APIRouter()
_repo = SalonRepository()
_category_service = CategoryService()


@router.get("/debug/salons")
def debug_salons(
    location: str | None = Query(default=None),
    city: str | None = Query(default=None),
    category: str | None = Query(default=None),
    service: str | None = Query(default=None),
) -> dict:
    """Return raw MongoDB discovery results for debugging.

    `city` is an alias for `location` so QA can use either parameter.
    """
    effective_location = location or city
    salons = _repo.discover(location=effective_location, category=category, service=service)

    loc_count = len(_repo.get_salons_by_location(effective_location)) if effective_location else None
    cat_count = len(_repo.get_salons_by_category(category)) if category else None
    svc_count = len(_repo.get_salons_by_service(service)) if service else None

    return {
        "query": {
            "location": effective_location,
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


@router.get("/debug/cities")
def debug_cities(category: str | None = Query(default=None)) -> dict:
    """All cities with active salons. When `category` is given, only cities
    where that category is offered (Bug 1 & Bug 6)."""
    if category:
        cities = _repo.get_cities_by_category(category)
    else:
        cities = _repo.get_distinct_cities()
    return {"category": category, "count": len(cities), "cities": cities}


@router.get("/debug/categories")
def debug_categories() -> dict:
    """Categories exactly as served from the Categories API (Bug 5)."""
    categories = _category_service.get_categories(force_refresh=True)
    return {
        "count": len(categories),
        "source": _category_service.settings.categories_api_url,
        "categories": [{"id": c.id, "name": c.name} for c in categories],
    }
