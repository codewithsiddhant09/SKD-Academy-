"""Availability, booking history and booking-request storage."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from bson import ObjectId
from conftest import FUTURE, MARINA_LUXE, FakeUsers, booking, call, make_assistant

import app.agent.tools as tools
import app.repositories.booking_repository as booking_repo
from app.agent.tools import recommend_from_history
from app.models.schemas import SessionContext
from app.repositories.booking_repository import BookingRepository


def search_marina(a, sid="s"):
    call(a, sid, "search_salons", location="Dubai Marina")


# --------------------------------------------------------------------------- #
# Availability (mock salons open 10:00-19:00; any time inside, booked >= 2 hours ahead)
# --------------------------------------------------------------------------- #
@pytest.fixture
def now_1430(monkeypatch):
    monkeypatch.setattr(tools, "now_local", lambda: datetime(2026, 10, 9, 14, 30, tzinfo=ZoneInfo("Asia/Dubai")))


class TestAvailability:
    def test_reports_opening_hours_as_a_range(self):
        a, _ = make_assistant()
        search_marina(a)
        r = call(a, "s", "check_availability", salon_id=MARINA_LUXE, date=FUTURE)
        assert r["available"] and r["open_hours"] == "10:00 AM to 7:00 PM"
        assert r["bookable_from"] == "10:00 AM" and "2 hours" in r["note"]

    def test_today_starts_two_hours_from_now(self, now_1430):
        a, _ = make_assistant()
        search_marina(a)
        r = call(a, "s", "check_availability", salon_id=MARINA_LUXE, date="2026-10-09")
        assert r["bookable_from"] == "4:30 PM" and r["bookable_until"] == "7:00 PM"

    def test_too_late_today(self, monkeypatch):
        monkeypatch.setattr(tools, "now_local", lambda: datetime(2026, 10, 9, 17, 30, tzinfo=ZoneInfo("Asia/Dubai")))
        a, _ = make_assistant()
        search_marina(a)
        r = call(a, "s", "check_availability", salon_id=MARINA_LUXE, date="2026-10-09")
        assert r["available"] is False and "2 hours" in r["reason"]

    def test_unknown_salon_and_past_date(self):
        a, _ = make_assistant()
        assert "error" in call(a, "s", "check_availability", salon_id=MARINA_LUXE, date=FUTURE)
        search_marina(a)
        assert "error" in call(a, "s", "check_availability", salon_id=MARINA_LUXE, date="2000-01-01")

    @pytest.mark.parametrize("good_time", ["10:00", "10:30", "16:20", "18:59"])
    def test_any_time_inside_opening_hours_accepted(self, good_time):
        a, _ = make_assistant()
        search_marina(a)
        assert call(a, "s", "update_booking", **booking("Hair Smoothing", MARINA_LUXE, FUTURE, good_time))["applied"]

    @pytest.mark.parametrize("bad_time", ["09:59", "19:00", "23:00"])
    def test_time_outside_opening_hours_rejected(self, bad_time):
        a, _ = make_assistant()
        search_marina(a)
        r = call(a, "s", "update_booking", **booking("Hair Smoothing", MARINA_LUXE, FUTURE, bad_time))
        assert r["applied"] is False and "open 10:00 AM to 7:00 PM" in r["problems"][0]

    def test_less_than_two_hours_ahead_rejected_with_hint(self, now_1430):
        a, _ = make_assistant()
        search_marina(a)
        r = call(a, "s", "update_booking", **booking("Hair Smoothing", MARINA_LUXE, "2026-10-09", "16:00"))
        assert r["applied"] is False and "at least 2 hours" in r["problems"][0]
        assert call(a, "s", "update_booking", **booking("Hair Smoothing", MARINA_LUXE, "2026-10-09", "16:30"))["applied"]

    def test_closed_day_rejected(self, monkeypatch):
        a, _ = make_assistant()
        search_marina(a)
        monkeypatch.setattr(a.bookings, "working_hours", lambda salon_id, day: None)
        r = call(a, "s", "update_booking", **booking("Hair Smoothing", MARINA_LUXE, FUTURE, "16:00"))
        assert "not taking bookings" in r["problems"][0]

    def test_time_is_normalised(self):
        a, _ = make_assistant()
        search_marina(a)
        r = call(a, "s", "update_booking", **booking("Hair Smoothing", MARINA_LUXE, FUTURE, "16:00:00"))
        assert r["applied"] and r["draft"]["time"] == "16:00"


# --------------------------------------------------------------------------- #
# History & scenario-1 recommendation
# --------------------------------------------------------------------------- #
def row(salon_id, status="Completed", rating=None, day="2026-09-01", services=("Haircut",)):
    return {"salon_id": salon_id, "salon": f"Salon {salon_id}", "services": list(services), "date": day,
            "time": "04:00 PM", "status": status, "place": "Home", "my_rating": rating}


class TestRecommendation:
    def test_highest_user_rating_wins(self):
        rows = [row("A", rating=5), row("B"), row("B"), row("B")]
        assert recommend_from_history(rows)["salon_id"] == "A"

    def test_without_ratings_most_booked_wins(self):
        rows = [row("A", day="2026-09-20"), row("B", day="2026-09-01"), row("B", day="2026-09-02")]
        assert recommend_from_history(rows)["salon_id"] == "B"

    def test_tie_on_count_most_recent_wins(self):
        rows = [row("A", day="2026-09-01"), row("B", day="2026-09-10")]
        assert recommend_from_history(rows)["salon_id"] == "B"

    def test_only_completed_bookings_count(self):
        rows = [row("A", status="Cancelled", rating=5), row("B")]
        assert recommend_from_history(rows)["salon_id"] == "B"
        assert recommend_from_history([row("A", status="Rejected")]) is None


class TestGetMyBookings:
    def test_requires_signed_in_user(self):
        a, _ = make_assistant()
        assert "error" in call(a, "s", "get_my_bookings")

    def test_filters_by_service_and_makes_salons_bookable(self, monkeypatch):
        a, _ = make_assistant(users=FakeUsers({"u1": "Sara"}))
        a.ensure_user_context("s", "u1")
        history = {
            "bookings": [
                row(MARINA_LUXE, rating=5, services=("Hair Smoothing",)),
                row("102", services=("Facial",)),
            ],
            "requests": [{"request_id": "BKLY-01102026-001", "status": "pending"}],
        }
        monkeypatch.setattr(a.bookings, "history", lambda user_id: history)
        r = call(a, "s", "get_my_bookings", service="hair smoothing")
        assert [b["salon_id"] for b in r["bookings"]] == [MARINA_LUXE]
        assert r["recommended_salon"]["salon_id"] == MARINA_LUXE
        assert r["pending_requests"][0]["request_id"] == "BKLY-01102026-001"
        # rebook straight from history, no search needed
        assert call(a, "s", "update_booking", **booking("Hair Smoothing", MARINA_LUXE, FUTURE, "16:00"))["applied"]


# --------------------------------------------------------------------------- #
# Booking request written on confirmation
# --------------------------------------------------------------------------- #
class TestBookingRequestDocument:
    def confirm(self, a, llm, monkeypatch, sid="s"):
        written = []
        monkeypatch.setattr(a.bookings, "submit_request", lambda doc: written.append(doc) or "BKLY-09102026-007")
        search_marina(a, sid)
        call(a, sid, "update_booking", **booking("hair smoothing", MARINA_LUXE, FUTURE, "16:00"))
        a.sessions.get(sid).payment_option = "Pay Later"
        a.sessions.get(sid).awaiting_confirmation = True
        llm.queue = ["Summary..."]
        a.chat(sid, "ok")
        llm.queue = [[("confirm_booking", {})], "Request submitted."]
        return a.chat(sid, "yes"), written

    def test_document_matches_booking_collection_format(self, monkeypatch):
        a, llm = make_assistant()
        user = SessionContext(user_id="u1", full_name="Sara", phone_number="+971500000000")
        a.sessions.get("s").user = user
        r, written = self.confirm(a, llm, monkeypatch)
        assert written == [
            {
                "userId": "u1",
                "vendorId": MARINA_LUXE,
                "vendorName": "Marina Luxe Salon",
                "services": [f"mock-{MARINA_LUXE}-0"],
                "serviceName": "Hair Smoothing",
                "categoryName": None,
                "location": "Dubai Marina",
                "bookingType": "Individual",
                "groupSize": 1,
                "companions": [],
                "date": f"{FUTURE} 00:00:00",
                "slot": "04:00 PM",
                "requestedDate": FUTURE,
                "requestedTime": "16:00",
                "customer_name": "Sara",
                "customer_phone": "+971500000000",
            }
        ]
        assert r.structured["booking_response"]["request_id"] == "BKLY-09102026-007"

    def test_anonymous_customer_uses_session_id(self, monkeypatch):
        a, llm = make_assistant()
        _, written = self.confirm(a, llm, monkeypatch, sid="sess-42")
        assert written[0]["userId"] == "sess-42"
        assert written[0]["customer_name"] == "User" and written[0]["customer_phone"] == ""


# --------------------------------------------------------------------------- #
# Repository logic against an in-memory fake database
# --------------------------------------------------------------------------- #
class FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find_one(self, query, *args, **kwargs):
        return next((d for d in self.docs if all(d.get(k) == v for k, v in query.items() if not isinstance(v, dict))), None)

    def find_one_and_update(self, query, update, upsert, return_document):
        doc = self.find_one(query) or self.docs.append({"_id": query["_id"], "seq": 0}) or self.docs[-1]
        doc["seq"] += update["$inc"]["seq"]
        return doc

    def insert_one(self, doc):
        self.docs.append(doc)

    def update_one(self, query, update):
        doc = self.find_one(query)
        if doc:
            doc.update(update["$set"])
        return type("Result", (), {"matched_count": int(doc is not None)})()


class FakeDB:
    def __init__(self, **collections):
        self.__dict__.update(collections)


class TestRepository:
    def test_working_hours_from_slots_window(self, monkeypatch):
        vid = ObjectId()
        window = {"vendorId": vid, "startDate": datetime(2026, 10, 20), "startMinutes": 985, "endMinutes": 1401}
        monkeypatch.setattr(booking_repo, "get_database", lambda: FakeDB(slots=FakeCollection([window])))
        assert BookingRepository().working_hours(str(vid), date(2026, 10, 20)) == (985, 1401)
        assert BookingRepository().working_hours(str(vid), date(2026, 10, 21)) is None
        assert BookingRepository().working_hours("not-an-id", date(2026, 10, 20)) is None

    def test_insert_request_numbers_per_day_and_sets_status(self, monkeypatch):
        db = FakeDB(booking=FakeCollection(), booking_request_counters=FakeCollection())
        monkeypatch.setattr(booking_repo, "get_database", lambda: db)
        vid = str(ObjectId())
        first = BookingRepository().insert_request({"vendorId": vid, "serviceName": "Haircut"})
        second = BookingRepository().insert_request({"vendorId": vid, "serviceName": "Haircut"})
        assert first.endswith("-001") and second.endswith("-002") and first.startswith("BKLY-")
        saved = db.booking.docs[0]
        assert saved["vendorId"] == ObjectId(vid)
        assert (saved["status"], saved["bookingStatus"], saved["source"]) == ("pending", "Pending", "chatbot")
        assert saved["responded_at"] is None and saved["isDeleted"] is False

    def test_update_request_only_while_status_unchanged(self, monkeypatch):
        db = FakeDB(booking=FakeCollection([{"request_id": "BKLY-09102026-004", "status": "pending", "requestedTime": "22:00"}]))
        monkeypatch.setattr(booking_repo, "get_database", lambda: db)
        repo = BookingRepository()
        assert repo.update_request("BKLY-09102026-004", "pending", {"requestedTime": "18:00"})
        doc = db.booking.docs[0]
        assert doc["requestedTime"] == "18:00" and "updatedAt" in doc
        assert repo.update_request("BKLY-09102026-004", "rejected", {"requestedTime": "19:00"}) is False
        assert doc["requestedTime"] == "18:00"
