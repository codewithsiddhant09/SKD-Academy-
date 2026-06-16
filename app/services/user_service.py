from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import SessionContext, UserProfile

logger = get_logger(__name__)


class UserService:
    """Loads user profiles from MongoDB.

    The connection is established lazily and any failure (driver missing,
    URI unset, server unreachable) is handled gracefully so the chatbot
    keeps working with a generic, non-personalized experience.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._collection: Any | None = None
        self._init_attempted = False

    def _ensure_collection(self) -> Any | None:
        if self._collection is not None:
            return self._collection
        if self._init_attempted:
            return None

        self._init_attempted = True
        uri = self._settings.mongodb_uri
        if not uri:
            logger.info("USER_SOURCE: MongoDB URI not configured; user enrichment disabled")
            return None

        try:
            from pymongo import MongoClient

            client = MongoClient(uri, serverSelectionTimeoutMS=2000)
            db = client[self._settings.mongodb_db_name]
            self._collection = db[self._settings.mongodb_users_collection]
            logger.info(
                "USER_SOURCE: Connected to MongoDB db=%s collection=%s",
                self._settings.mongodb_db_name,
                self._settings.mongodb_users_collection,
            )
            return self._collection
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("USER_SOURCE: MongoDB unavailable, falling back to generic context: %s", exc)
            self._collection = None
            return None

    def _find_document(self, collection: Any, user_id: str) -> dict[str, Any] | None:
        # Try a direct match first, then an ObjectId match if applicable.
        doc = collection.find_one({"_id": user_id})
        if doc:
            return doc
        try:
            from bson import ObjectId

            if ObjectId.is_valid(user_id):
                return collection.find_one({"_id": ObjectId(user_id)})
        except Exception:  # pragma: no cover - defensive
            return None
        return None

    @staticmethod
    def _to_profile(user_id: str, doc: dict[str, Any]) -> UserProfile:
        return UserProfile(
            user_id=str(doc.get("_id", user_id)),
            full_name=doc.get("fullName"),
            country_code=doc.get("countryCode"),
            phone_number=doc.get("phoneNumber"),
            email=doc.get("email"),
            user_type=doc.get("userType"),
            is_verified=doc.get("isVerified"),
            status=doc.get("status"),
            business_location=doc.get("businessLocation"),
            service_type=doc.get("serviceType"),
            is_completed=doc.get("isCompleted"),
            admin_approval=doc.get("adminApproval"),
            dob=str(doc.get("dob")) if doc.get("dob") is not None else None,
            gender=doc.get("gender"),
            nationality=doc.get("nationality"),
        )

    def get_user_profile(self, user_id: str) -> UserProfile | None:
        if not user_id:
            return None

        collection = self._ensure_collection()
        if collection is None:
            return None

        try:
            doc = self._find_document(collection, user_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("USER_LOADED: lookup failed for user_id=%s: %s", user_id, exc)
            return None

        if not doc:
            logger.info("USER_LOADED: no document found for user_id=%s", user_id)
            return None

        profile = self._to_profile(user_id, doc)
        logger.info(
            "USER_LOADED: user_id=%s fullName=%s email=%s location=%s",
            profile.user_id,
            profile.full_name,
            profile.email,
            profile.business_location,
        )
        return profile

    def build_session_context(self, user_id: str | None, profile: UserProfile | None) -> SessionContext:
        if profile is None:
            return SessionContext(user_id=user_id)
        return SessionContext(
            user_id=profile.user_id,
            full_name=profile.full_name,
            email=profile.email,
            phone_number=profile.phone_number,
            gender=profile.gender,
            nationality=profile.nationality,
            business_location=profile.business_location,
        )
