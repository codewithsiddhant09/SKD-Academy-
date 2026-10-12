"""MongoDB salon discovery repository.

A "salon" is a vendor user (`users.userType == "Vendor"`). The data is joined
across collections discovered in Phase 1:

    salonId / vendorId  -> users._id
    salonName           -> users.businessName
    location            -> users.businessAddress (the `addresses` collection holds
                           NO vendor rows; it is joined by userId only when present)
    services            -> services.name        (services.vendorId -> users._id)
    category            -> categories.name       (services.categoryId -> categories._id)
    rating              -> avg(reviews.rating)   (reviews.vendorId -> users._id)

All access is lazy and fault-tolerant: when the URI is unset or Atlas is
unreachable, every method returns empty so callers can fall back gracefully.
"""
from __future__ import annotations

import re
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.repositories.mongo import get_database
from app.utils.location import sanitize_location
from app.utils.text import title_case_safe

logger = get_logger(__name__)

# Words ignored when turning a free-text service phrase into search tokens.
_STOPWORDS = {
    "i", "a", "an", "the", "to", "for", "of", "my", "me", "please",
    "want", "need", "book", "booking", "get", "looking", "would", "like",
    "service", "services", "appointment", "salon", "near", "in", "at",
}


class SalonRepository:
    def __init__(self) -> None:
        self._settings = get_settings()

    def _database(self) -> Any | None:
        return get_database()

    def is_available(self) -> bool:
        return self._database() is not None

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _regex(value: str) -> dict[str, Any]:
        return {"$regex": re.escape(value.strip()), "$options": "i"}

    @staticmethod
    def _active_vendor_filter() -> dict[str, Any]:
        """Mongo filter that keeps ONLY visible salons.

        Discovered status semantics (Phase 1 audit of users[userType=Vendor]):
            status        : True = active, False = disabled  (Bug 2 fix)
            isDeleted     : True = soft-deleted / removed
            adminApproval : must equal "Approved"

        `isActive`, `isBlocked`, `isSuspended` do NOT exist in this DB.
        Missing `status` is treated as active ($ne False) for forward safety.
        """
        return {
            "userType": "Vendor",
            "status": {"$ne": False},
            "isDeleted": {"$ne": True},
            "adminApproval": "Approved",
        }

    def _category_ids_for_name(self, db: Any, category: str) -> list[Any]:
        """IDs of categories named exactly `category` (case-insensitive).

        Exact, not contains: "Hair" must not also match "Hair Removal" or "Hair Coloring".
        """
        coll = db[self._settings.mongodb_categories_collection]
        query = {"name": {"$regex": f"^{re.escape(category.strip())}$", "$options": "i"}}
        return [doc["_id"] for doc in coll.find(query, {"_id": 1})]

    def list_services(self, category: str, location: str | None = None) -> list[dict[str, Any]]:
        """Distinct services offered in `category` by active salons (optionally in `location`),
        with price range and number of salons."""
        db = self._database()
        if db is None:
            return []
        category_ids = self._category_ids_for_name(db, category)
        if not category_ids:
            return []
        query: dict[str, Any] = {"categoryId": {"$in": category_ids}, "isDeleted": {"$ne": True}}
        if location:
            query["vendorId"] = {"$in": list(self.get_salons_by_location(location))}
        rows = list(db[self._settings.mongodb_services_collection].find(query, {"name": 1, "price": 1, "vendorId": 1}))
        active = {
            v["_id"]
            for v in db[self._settings.mongodb_users_collection].find(
                {"_id": {"$in": list({r["vendorId"] for r in rows})}, **self._active_vendor_filter()}, {"_id": 1}
            )
        }
        services: dict[str, dict[str, Any]] = {}
        for r in rows:
            if r.get("vendorId") not in active or not r.get("name"):
                continue
            entry = services.setdefault(r["name"].strip().lower(), {"name": r["name"].strip(), "prices": [], "salons": set()})
            if r.get("price") is not None:
                entry["prices"].append(r["price"])
            entry["salons"].add(r["vendorId"])
        return [
            {
                "service": e["name"],
                "price_from": min(e["prices"]) if e["prices"] else None,
                "price_to": max(e["prices"]) if e["prices"] else None,
                "salons": len(e["salons"]),
            }
            for e in sorted(services.values(), key=lambda e: e["name"].lower())
        ]

    @staticmethod
    def _service_tokens(service: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z]+", service.lower())
        return [t for t in tokens if t not in _STOPWORDS and len(t) > 2]

    # ------------------------------------------------------------------ #
    # Public query functions (Phase 2)
    # ------------------------------------------------------------------ #
    def get_salons_by_location(self, location: str) -> set[Any]:
        """Vendor ids whose businessAddress matches `location` (case-insensitive).

        NOTE: The `addresses` collection contains CUSTOMER home/office addresses
        (not vendor addresses); its userId values point to customers, not salons.
        Querying it would add noise, so we rely solely on users.businessAddress
        which is the authoritative location field for vendors (76/76 coverage).
        """
        db = self._database()
        if db is None or not location:
            return set()

        cleaned = sanitize_location(location) or location.strip()
        logger.info("USER_LOCATION: raw=%s cleaned=%s", location, cleaned)
        vendor_ids: set[Any] = set()
        users = db[self._settings.mongodb_users_collection]
        q = {
            **self._active_vendor_filter(),
            "businessAddress": self._regex(cleaned),
        }
        logger.info("MONGO_QUERY: users.find(%s)", q)
        for doc in users.find(q, {"_id": 1, "businessName": 1, "businessAddress": 1}):
            vendor_ids.add(doc["_id"])

        logger.info("TOTAL_MATCHES (by location): %s", len(vendor_ids))
        if vendor_ids:
            sample = users.find_one({"_id": {"$in": list(vendor_ids)[:1]}}, {"businessName": 1, "businessAddress": 1})
            if sample:
                logger.info(
                    "FIRST_LOCATION_MATCH: name=%s address=%s",
                    sample.get("businessName"),
                    (sample.get("businessAddress") or "")[:80],
                )
        return vendor_ids

    def get_salons_by_category(self, category: str) -> set[Any]:
        """Vendor ids offering at least one active service in `category`."""
        db = self._database()
        if db is None or not category:
            return set()

        category_ids = self._category_ids_for_name(db, category)
        if not category_ids:
            return set()

        services = db[self._settings.mongodb_services_collection]
        vendor_ids: set[Any] = set()
        for doc in services.find(
            {"categoryId": {"$in": category_ids}, "isDeleted": {"$ne": True}},
            {"vendorId": 1},
        ):
            if doc.get("vendorId") is not None:
                vendor_ids.add(doc["vendorId"])
        return vendor_ids

    def get_salons_by_service(self, service: str) -> set[Any]:
        """Vendor ids with an active service whose name contains EVERY word of `service`.

        All words must match ("hair smoothing" does not match "Hair Cut"), so a
        salon is only returned when it really offers the requested service.
        """
        db = self._database()
        if db is None or not service:
            return set()

        tokens = self._service_tokens(service)
        if not tokens:
            return set()

        pattern = "".join(f"(?=.*{re.escape(t)})" for t in tokens)
        services = db[self._settings.mongodb_services_collection]
        vendor_ids: set[Any] = set()
        for doc in services.find(
            {"name": {"$regex": pattern, "$options": "i"}, "isDeleted": {"$ne": True}},
            {"vendorId": 1},
        ):
            if doc.get("vendorId") is not None:
                vendor_ids.add(doc["vendorId"])
        return vendor_ids

    def get_salons_by_name(self, salon_name: str) -> set[Any]:
        """Vendor ids of active salons whose businessName contains `salon_name`."""
        db = self._database()
        if db is None or not salon_name:
            return set()
        users = db[self._settings.mongodb_users_collection]
        query = {**self._active_vendor_filter(), "businessName": self._regex(salon_name)}
        return {doc["_id"] for doc in users.find(query, {"_id": 1})}

    # ------------------------------------------------------------------ #
    # Combined discovery
    # ------------------------------------------------------------------ #
    def discover(
        self,
        location: str | None = None,
        category: str | None = None,
        service: str | None = None,
        salon_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Salons matching ALL given filters (location, service or category, name).

        A specific service takes precedence over its category: matching on the
        category would also return salons that offer other services in it.
        """
        db = self._database()
        if db is None:
            return []

        filters: list[set[Any]] = []
        if location:
            filters.append(self.get_salons_by_location(location))
        if service:
            filters.append(self.get_salons_by_service(service))
        elif category:
            filters.append(self.get_salons_by_category(category))
        if salon_name:
            filters.append(self.get_salons_by_name(salon_name))
        if not filters:
            return []

        vendor_ids = set.intersection(*filters)
        logger.info(
            "Query Executed: location=%s category=%s service=%s salon_name=%s -> candidates=%s",
            location, category, service, salon_name, len(vendor_ids),
        )
        return self._build_salons_batch(db, vendor_ids)

    def get_salons_by_ids(self, vendor_ids: list[str]) -> list[dict[str, Any]]:
        """Salon cards for specific vendor ids (e.g. salons from a user's history)."""
        from bson import ObjectId

        db = self._database()
        ids = {ObjectId(v) for v in vendor_ids if ObjectId.is_valid(v)}
        return self._build_salons_batch(db, ids) if db is not None else []

    def _build_salons_batch(self, db: Any, vendor_ids: set[Any]) -> list[dict[str, Any]]:
        """Build all salon cards with a fixed number of queries (no N+1).

        Total reads: 1 vendors + 1 services + 1 categories + 1 reviews = 4,
        regardless of how many salons match.
        """
        if not vendor_ids:
            return []

        ids = list(vendor_ids)

        # 1) Vendors — only Approved, active, non-deleted, non-disabled salons.
        #    profileImage is the primary image; logo is the fallback (Bug 8).
        vendors = {
            v["_id"]: v
            for v in db[self._settings.mongodb_users_collection].find(
                {"_id": {"$in": ids}, **self._active_vendor_filter()},
                {
                    "businessName": 1,
                    "businessAddress": 1,
                    "profileImage": 1,
                    "logo": 1,
                },
            )
        }
        if not vendors:
            return []

        # 2) Active services grouped by vendor (single query)
        services_by_vendor: dict[Any, list[dict[str, Any]]] = {}
        category_ids_by_vendor: dict[Any, set[Any]] = {}
        all_category_ids: set[Any] = set()
        for svc in db[self._settings.mongodb_services_collection].find(
            {"vendorId": {"$in": ids}, "isDeleted": {"$ne": True}},
            {"name": 1, "categoryId": 1, "vendorId": 1, "price": 1, "duration": 1},
        ):
            vid = svc.get("vendorId")
            cat_id = svc.get("categoryId")
            if svc.get("name"):
                services_by_vendor.setdefault(vid, []).append(
                    {
                        "id": str(svc["_id"]),
                        "name": svc["name"],
                        "price": svc.get("price"),
                        "duration": svc.get("duration"),
                        "category_id": cat_id,
                    }
                )
            if cat_id is not None:
                category_ids_by_vendor.setdefault(vid, set()).add(cat_id)
                all_category_ids.add(cat_id)

        # 3) Category names (single query)
        category_name_by_id: dict[Any, str] = {}
        if all_category_ids:
            for cat in db[self._settings.mongodb_categories_collection].find(
                {"_id": {"$in": list(all_category_ids)}}, {"name": 1}
            ):
                if cat.get("name"):
                    category_name_by_id[cat["_id"]] = cat["name"]

        # 4) Ratings grouped by vendor (single query; vendorId may be ObjectId or str)
        rating_acc: dict[str, list[float]] = {}
        review_query_ids = ids + [str(i) for i in ids]
        for rev in db[self._settings.mongodb_reviews_collection].find(
            {"vendorId": {"$in": review_query_ids}}, {"vendorId": 1, "rating": 1}
        ):
            try:
                value = float(rev.get("rating"))
            except (TypeError, ValueError):
                continue
            rating_acc.setdefault(str(rev.get("vendorId")), []).append(value)

        salons: list[dict[str, Any]] = []
        for vid, vendor in vendors.items():
            ratings = rating_acc.get(str(vid), [])
            rating = round(sum(ratings) / len(ratings), 1) if ratings else None
            category_names = [
                category_name_by_id[c]
                for c in category_ids_by_vendor.get(vid, set())
                if c in category_name_by_id
            ]
            image = vendor.get("profileImage") or vendor.get("logo") or None
            offers = [
                {
                    "id": o["id"],
                    "name": o["name"],
                    "price": o["price"],
                    "duration": o["duration"],
                    "category": category_name_by_id.get(o["category_id"]),
                }
                for o in services_by_vendor.get(vid, [])
            ]
            salons.append(
                {
                    "salonId": str(vid),
                    "salonName": vendor.get("businessName") or "Salon",
                    "rating": rating,
                    "location": vendor.get("businessAddress") or "",
                    "services": [o["name"] for o in offers],
                    "offers": offers,
                    "categories": category_names,
                    "image": image,
                    "redirectUrl": f"/salon/{vid}",
                }
            )
        return salons

    # ------------------------------------------------------------------ #
    # City / location discovery (Bug 1 & Bug 6)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _clean_city(raw: str) -> str | None:
        """Best-effort city normalization from a free-text businessAddress.

        businessAddress is unstructured (e.g. "G-18, Sector 63, Noida, Uttar
        Pradesh, India"). We take the most meaningful comma segment, drop the
        country/obvious-noise tail, and title-case it. Junk like "s", "asdd"
        (< 3 chars or no vowel) is discarded.
        """
        if not raw:
            return None
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            return None
        _DROP = {"india", "uae", "united arab emirates"}
        candidates = [p for p in parts if p.lower() not in _DROP] or parts
        # Prefer a segment that looks like a city name (last meaningful token group).
        city = candidates[-1] if len(candidates) == 1 else candidates[-2] if len(candidates) >= 2 else candidates[-1]
        city = re.sub(r"\b(uttar pradesh|madhya pradesh|rajasthan|state)\b", "", city, flags=re.IGNORECASE).strip()
        if not city or len(city) < 3:
            return None
        if not re.search(r"[aeiouAEIOU]", city):  # drop gibberish like "ssx", "dsd"
            return None
        return title_case_safe(city)

    def get_distinct_cities(self) -> list[str]:
        """Distinct, normalized cities that have at least one active salon (Bug 1)."""
        db = self._database()
        if db is None:
            return []
        users = db[self._settings.mongodb_users_collection]
        cities: set[str] = set()
        for doc in users.find(self._active_vendor_filter(), {"businessAddress": 1}):
            city = self._clean_city(doc.get("businessAddress") or "")
            if city:
                cities.add(city)
        result = sorted(cities)
        logger.info("DISTINCT_CITIES: %s", result)
        return result

    def get_cities_by_category(self, category: str) -> list[str]:
        """Distinct cities where active salons offering `category` exist (Bug 6)."""
        db = self._database()
        if db is None or not category:
            return []
        vendor_ids = self.get_salons_by_category(category)
        if not vendor_ids:
            return []
        users = db[self._settings.mongodb_users_collection]
        cities: set[str] = set()
        for doc in users.find(
            {"_id": {"$in": list(vendor_ids)}, **self._active_vendor_filter()},
            {"businessAddress": 1},
        ):
            city = self._clean_city(doc.get("businessAddress") or "")
            if city:
                cities.add(city)
        result = sorted(cities)
        logger.info("CITIES_BY_CATEGORY[%s]: %s", category, result)
        return result
