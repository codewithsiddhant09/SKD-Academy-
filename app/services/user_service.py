from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.repositories.mongo import get_database
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

    def _ensure_collection(self) -> Any | None:
        db = get_database()
        return db[self._settings.mongodb_users_collection] if db is not None else None

    def is_available(self) -> bool:
        """True when the users collection is reachable (for 404 vs 503 decisions)."""
        return self._ensure_collection() is not None

    def _find_document(self, collection: Any, user_id: str) -> dict[str, Any] | None:
        from bson import ObjectId

        is_valid_oid = ObjectId.is_valid(user_id)
        logger.info("RECEIVED_USER_ID: %s (valid ObjectId=%s)", user_id, is_valid_oid)

        # 1) Direct string _id match (covers non-ObjectId ids).
        query_str = {"_id": user_id}
        logger.info("MONGO_QUERY: users.find_one(%s)", query_str)
        doc = collection.find_one(query_str)
        if doc:
            logger.info("QUERY_RESULT: matched by string _id")
            return doc

        # 2) ObjectId match when the id is a valid ObjectId.
        if is_valid_oid:
            query_oid = {"_id": ObjectId(user_id)}
            logger.info("MONGO_QUERY: users.find_one(%s)", query_oid)
            doc = collection.find_one(query_oid)
            if doc:
                logger.info("QUERY_RESULT: matched by ObjectId _id")
                return doc

        logger.info("QUERY_RESULT: no document for user_id=%s", user_id)
        return None

    @staticmethod
    def _as_str(value: Any) -> str | None:
        """Coerce a Mongo value to a clean string, or None for objects/arrays.

        Prevents Pydantic ValidationError (HTTP 500) when fields like
        `businessLocation` (dict) or `serviceType` (list) are non-scalar.
        """
        if value is None:
            return None
        if isinstance(value, str):
            return value or None
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, (int, float)):
            return str(value)
        # dict / list / ObjectId / datetime -> not a usable scalar string
        return None

    def _to_profile(self, user_id: str, doc: dict[str, Any]) -> UserProfile:
        status = doc.get("status")
        if not isinstance(status, (bool, str)):
            status = None
        return UserProfile(
            user_id=str(doc.get("_id", user_id)),
            full_name=self._as_str(doc.get("fullName")),
            country_code=self._as_str(doc.get("countryCode")),
            phone_number=self._as_str(doc.get("phoneNumber")),
            email=self._as_str(doc.get("email")),
            user_type=self._as_str(doc.get("userType")),
            is_verified=doc.get("isVerified") if isinstance(doc.get("isVerified"), bool) else None,
            status=status,
            business_location=self._as_str(doc.get("businessLocation")),
            service_type=self._as_str(doc.get("serviceType")),
            is_completed=doc.get("isCompleted") if isinstance(doc.get("isCompleted"), bool) else None,
            admin_approval=self._as_str(doc.get("adminApproval")),
            dob=self._as_str(doc.get("dob")),
            gender=self._as_str(doc.get("gender")),
            nationality=self._as_str(doc.get("nationality")),
        )

    def get_user_profile(self, user_id: str) -> UserProfile | None:
        if not user_id:
            return None

        collection = self._ensure_collection()
        if collection is None:
            logger.info("USER_LOADED: MongoDB unavailable; skipping lookup for user_id=%s", user_id)
            return None

        try:
            doc = self._find_document(collection, user_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("USER_LOOKUP_FAILED: query error for user_id=%s", user_id)
            return None

        if not doc:
            logger.info("USER_LOADED: no document found for user_id=%s", user_id)
            return None

        # Build the profile defensively: a schema/type mismatch must NEVER
        # surface as an HTTP 500 — degrade to a generic (None) profile instead.
        try:
            profile = self._to_profile(user_id, doc)
        except Exception:  # pragma: no cover - defensive
            logger.exception(
                "USER_PROFILE_BUILD_FAILED: user_id=%s doc_keys=%s",
                user_id,
                sorted(doc.keys()),
            )
            return None

        logger.info(
            "USER_LOADED: user_id=%s fullName=%s email=%s userType=%s location=%s",
            profile.user_id,
            profile.full_name,
            profile.email,
            profile.user_type,
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
