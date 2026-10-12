"""MongoDB access for availability, booking history and chatbot booking requests.

Schema (bookly_staging):
  slots     one working window per salon per day: {vendorId, startDate (midnight),
            startTime/endTime "10:00 AM", startMinutes/endMinutes, status, isDeleted}.
            Any time inside the window can be booked; any number of bookings per time.
  bookings  bookings made in the app: {userId, vendorId, services:[serviceId], date, slot,
            bookingStatus, BookingAppointment, bookingType}; reviews link via bookingId.
  booking   booking *requests* created by this chatbot (source "chatbot"), status "pending"
            until the salon responds; request_id BKLY-DDMMYYYY-NNN from booking_request_counters.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from app.core.logging import get_logger
from app.repositories.mongo import get_database

logger = get_logger(__name__)

def to_oid(value: str | None) -> ObjectId | None:
    return ObjectId(value) if value and ObjectId.is_valid(value) else None


class BookingRepository:
    def is_available(self) -> bool:
        return get_database() is not None

    # ------------------------------------------------------------------ #
    # Availability
    # ------------------------------------------------------------------ #
    def working_hours(self, vendor_id: str, day: date) -> tuple[int, int] | None:
        """(open, close) in minutes after midnight for the salon on `day`, or None if closed."""
        db = get_database()
        oid = to_oid(vendor_id)
        if db is None or oid is None:
            return None
        window = db.slots.find_one(
            {
                "vendorId": oid,
                "startDate": datetime(day.year, day.month, day.day),
                "startMinutes": {"$exists": True},
                "isDeleted": {"$ne": True},
                "status": {"$ne": False},
            },
            {"startMinutes": 1, "endMinutes": 1},
        )
        return (window["startMinutes"], window["endMinutes"]) if window else None

    def next_available_dates(self, vendor_ids: list[str], from_day: date) -> dict[str, str]:
        """First date on/after `from_day` each salon has working hours, as {vendor_id: 'YYYY-MM-DD'}.
        Salons without upcoming working hours are omitted."""
        db = get_database()
        oids = [o for o in (to_oid(v) for v in vendor_ids) if o]
        if db is None or not oids:
            return {}
        # ponytail: today's window counts even if its last slot has passed; check_availability filters times.
        rows = db.slots.aggregate(
            [
                {
                    "$match": {
                        "vendorId": {"$in": oids},
                        "startMinutes": {"$exists": True},
                        "isDeleted": {"$ne": True},
                        "status": {"$ne": False},
                        "startDate": {"$gte": datetime(from_day.year, from_day.month, from_day.day)},
                    }
                },
                {"$group": {"_id": "$vendorId", "first": {"$min": "$startDate"}}},
            ]
        )
        return {str(r["_id"]): r["first"].date().isoformat() for r in rows}

    # ------------------------------------------------------------------ #
    # History
    # ------------------------------------------------------------------ #
    def user_history(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        """The user's app bookings (newest first) and their chatbot booking requests."""
        db = get_database()
        if db is None:
            return {"bookings": [], "requests": []}

        oid = to_oid(user_id)
        bookings = list(db.bookings.find({"userId": oid}).sort("date", -1)) if oid else []
        service_ids = {sid for b in bookings for sid in b.get("services", [])}
        services = {s["_id"]: s for s in db.services.find({"_id": {"$in": list(service_ids)}}, {"name": 1})}
        vendors = {
            v["_id"]: v.get("businessName")
            for v in db.users.find({"_id": {"$in": list({b["vendorId"] for b in bookings})}}, {"businessName": 1})
        }
        ratings = {
            r["bookingId"]: r.get("rating")
            for r in db.reviews.find({"bookingId": {"$in": [b["_id"] for b in bookings]}}, {"bookingId": 1, "rating": 1})
        }
        history = [
            {
                "salon_id": str(b["vendorId"]),
                "salon": vendors.get(b["vendorId"]),
                "services": [services[s]["name"] for s in b.get("services", []) if s in services],
                "date": b["date"].date().isoformat() if isinstance(b.get("date"), datetime) else b.get("date"),
                "time": b.get("slot"),
                "status": b.get("bookingStatus"),
                "place": b.get("BookingAppointment"),
                "my_rating": ratings.get(b["_id"]),
            }
            for b in bookings
            if b.get("vendorId") in vendors  # skip bookings at salons that no longer exist
        ]
        requests = [
            {
                "request_id": r.get("request_id"),
                "salon": r.get("vendorName"),
                "service": r.get("serviceName"),
                "date": r.get("requestedDate"),
                "time": r.get("requestedTime"),
                "status": r.get("status"),
            }
            for r in db.booking.find({"userId": user_id, "isDeleted": {"$ne": True}}).sort("createdAt", -1).limit(10)
        ]
        return {"bookings": history, "requests": requests}

    # ------------------------------------------------------------------ #
    # Booking requests
    # ------------------------------------------------------------------ #
    def insert_request(self, doc: dict[str, Any]) -> str:
        """Insert a chatbot booking request; returns its BKLY-DDMMYYYY-NNN request_id."""
        db = get_database()
        now = datetime.now(timezone.utc)
        prefix = f"BKLY-{now:%d%m%Y}"
        counter = db.booking_request_counters.find_one_and_update(
            {"_id": prefix}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER
        )
        request_id = f"{prefix}-{counter['seq']:03d}"
        db.booking.insert_one(
            {
                **doc,
                "vendorId": to_oid(doc["vendorId"]) or doc["vendorId"],
                "request_id": request_id,
                "bookingStatus": "Pending",
                "status": "pending",
                "isDeleted": False,
                "source": "chatbot",
                "createdAt": now,
                "updatedAt": now,
                "responded_at": None,
                "rejection_reason": None,
            }
        )
        logger.info("BOOKING_REQUEST_INSERTED: %s vendor=%s", request_id, doc.get("vendorId"))
        return request_id

    def find_request(self, request_id: str) -> dict[str, Any] | None:
        db = get_database()
        if db is None:
            return None
        return db.booking.find_one({"request_id": request_id.strip().upper(), "isDeleted": {"$ne": True}})

    def update_request(self, request_id: str, expected_status: str, fields: dict[str, Any]) -> bool:
        """Update a request in place (same request_id) if it still has `expected_status`."""
        db = get_database()
        result = db.booking.update_one(
            {"request_id": request_id, "status": expected_status, "isDeleted": {"$ne": True}},
            {"$set": {**fields, "updatedAt": datetime.now(timezone.utc)}},
        )
        logger.info("BOOKING_REQUEST_UPDATED: %s fields=%s matched=%s", request_id, sorted(fields), result.matched_count)
        return result.matched_count == 1
