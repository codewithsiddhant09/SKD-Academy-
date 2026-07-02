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
        self._db: Any | None = None
        self._init_attempted = False
        self._schema_logged = False

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    def _database(self) -> Any | None:
        if self._db is not None:
            return self._db
        if self._init_attempted:
            return None

        self._init_attempted = True
        uri = self._settings.mongodb_uri
        if not uri:
            logger.info("SALON_REPO: MONGODB_URI not configured; MongoDB discovery disabled")
            return None

        try:
            from pymongo import MongoClient

            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            client.admin.command("ping")
            self._db = client[self._settings.mongodb_db_name]
            logger.info("Mongo Connected (db=%s)", self._settings.mongodb_db_name)
            self._log_schema_once()
            return self._db
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("SALON_REPO: MongoDB unavailable: %s", exc)
            self._db = None
            return None

    def _log_schema_once(self) -> None:
        if self._schema_logged:
            return
        self._schema_logged = True
        logger.info(
            "Schema Loaded: salon=users[userType=Vendor] name=businessName "
            "location=businessAddress services=services[vendorId,categoryId,name] "
            "category=categories.name rating=avg(reviews.rating)"
        )

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
        """Return ALL category IDs whose name contains `category` (case-insensitive).

        The DB has BOTH clean names ("Hair", id=6a02...) and legacy names
        ("Hair servicess", "Hair treatment", etc., older IDs).  Services are
        only linked to the LEGACY IDs.  Using a contains-match ensures we
        capture every relevant category regardless of naming era.
        """
        coll = db[self._settings.mongodb_categories_collection]
        docs = list(coll.find({"name": self._regex(category)}))
        return [doc["_id"] for doc in docs]

    @staticmethod
    def _service_tokens(service: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z]+", service.lower())
        return [t for t in tokens if t not in _STOPWORDS and len(t) > 2]

    def _avg_rating(self, db: Any, vendor_id: Any) -> float | None:
        coll = db[self._settings.mongodb_reviews_collection]
        ratings: list[float] = []
        # reviews.vendorId may be stored as ObjectId or string.
        for query_id in {vendor_id, str(vendor_id)}:
            for doc in coll.find({"vendorId": query_id}):
                try:
                    ratings.append(float(doc.get("rating")))
                except (TypeError, ValueError):
                    continue
            if ratings:
                break
        if not ratings:
            return None
        return round(sum(ratings) / len(ratings), 1)

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
        """Vendor ids with an active service whose name matches any token in `service`."""
        db = self._database()
        if db is None or not service:
            return set()

        tokens = self._service_tokens(service)
        if not tokens:
            return set()

        pattern = "|".join(re.escape(t) for t in tokens)
        services = db[self._settings.mongodb_services_collection]
        vendor_ids: set[Any] = set()
        for doc in services.find(
            {"name": {"$regex": pattern, "$options": "i"}, "isDeleted": {"$ne": True}},
            {"vendorId": 1},
        ):
            if doc.get("vendorId") is not None:
                vendor_ids.add(doc["vendorId"])
        return vendor_ids

    # ------------------------------------------------------------------ #
    # Combined discovery (Phase 4)
    # ------------------------------------------------------------------ #
    def discover(
        self,
        location: str | None = None,
        category: str | None = None,
        service: str | None = None,
    ) -> list[dict[str, Any]]:
        db = self._database()
        if db is None:
            return []

        if location:
            logger.info("Location Received: %s", location)

        location_set = self.get_salons_by_location(location) if location else None
        category_set = self.get_salons_by_category(category) if category else set()
        service_set = self.get_salons_by_service(service) if service else set()
        wanted = category_set | service_set

        # Routing logic:
        # 1. Both location AND service/category specified → strict intersection.
        # 2. Location only (no category/service requested) → all vendors in area.
        # 3. Category/service only (no location) → all vendors matching the service.
        # 4. Service/category was specified but returned nothing → return empty so
        #    the caller's mock fallback can handle it (do NOT dump all-location results).
        service_or_category_requested = bool(category or service)

        if location_set is not None and wanted:
            vendor_ids = location_set & wanted
        elif location_set is not None and not service_or_category_requested:
            vendor_ids = location_set
        elif location_set is not None and service_or_category_requested and not wanted:
            # Service/category requested but nothing found in DB → signal no match.
            vendor_ids = set()
        else:
            vendor_ids = wanted

        logger.info(
            "Query Executed: location=%s category=%s service=%s -> by_location=%s by_category=%s by_service=%s candidates=%s",
            location,
            category,
            service,
            len(location_set) if location_set is not None else "n/a",
            len(category_set),
            len(service_set),
            len(vendor_ids),
        )

        salons = self._build_salons_batch(db, vendor_ids)
        logger.info("Matching Salons Found: %s (MongoDB)", len(salons))
        logger.info("SALON_NAMES: %s", [s.get("salonName") for s in salons])
        return salons

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
        services_by_vendor: dict[Any, list[str]] = {}
        category_ids_by_vendor: dict[Any, set[Any]] = {}
        all_category_ids: set[Any] = set()
        for svc in db[self._settings.mongodb_services_collection].find(
            {"vendorId": {"$in": ids}, "isDeleted": {"$ne": True}},
            {"name": 1, "categoryId": 1, "vendorId": 1},
        ):
            vid = svc.get("vendorId")
            if svc.get("name"):
                services_by_vendor.setdefault(vid, []).append(svc["name"])
            cat_id = svc.get("categoryId")
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
        id_str_to_key = {str(i): i for i in ids}
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
            salons.append(
                {
                    "salonId": str(vid),
                    "salonName": vendor.get("businessName") or "Salon",
                    "rating": rating,
                    "location": vendor.get("businessAddress") or "",
                    "services": services_by_vendor.get(vid, []),
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

    def find_vendor_by_name(
        self,
        salon_name: str,
        location_hint: str | None = None,
    ) -> dict[str, Any] | None:
        """Look up an active vendor by businessName (optional location filter)."""
        db = self._database()
        if db is None or not salon_name or not salon_name.strip():
            return None

        query: dict[str, Any] = {
            **self._active_vendor_filter(),
            "businessName": self._regex(salon_name.strip()),
        }
        if location_hint:
            query["businessAddress"] = self._regex(location_hint.strip())

        users = db[self._settings.mongodb_users_collection]
        doc = users.find_one(
            query,
            {"businessName": 1, "businessAddress": 1, "profileImage": 1, "logo": 1},
        )
        if doc:
            return doc

        # Fuzzy contains match when exact regex match fails.
        for candidate in users.find(
            {**self._active_vendor_filter(), "businessName": {"$exists": True}},
            {"businessName": 1, "businessAddress": 1, "profileImage": 1, "logo": 1},
        ):
            name = str(candidate.get("businessName") or "")
            if not name:
                continue
            name_l = name.lower()
            target_l = salon_name.strip().lower()
            if target_l in name_l or name_l in target_l:
                if location_hint:
                    addr = str(candidate.get("businessAddress") or "").lower()
                    if location_hint.strip().lower() not in addr:
                        continue
                return candidate
        return None
