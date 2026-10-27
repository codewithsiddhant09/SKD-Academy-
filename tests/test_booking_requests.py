"""Existing booking requests: look up by ID, modify on the same ID, cancel."""
from bson import ObjectId
from conftest import FUTURE, MARINA_LUXE, booking, call, make_assistant

from app.models.schemas import SessionContext


def create_request(a, llm, sid="owner") -> str:
    """Book Hair Smoothing at Marina Luxe through the normal flow; returns the request ID."""
    call(a, sid, "search_salons", location="Dubai Marina")
    call(a, sid, "update_booking", **booking("Hair Smoothing", MARINA_LUXE, FUTURE, "16:00"))
    a.sessions.get(sid).payment_option = "Pay Later"
    a.sessions.get(sid).awaiting_confirmation = True
    llm.queue = ["Summary..."]
    a.chat(sid, "hair smoothing please")
    llm.queue = [[("confirm_booking", {})], "Submitted."]
    return a.chat(sid, "yes").structured["booking_response"]["request_id"]


def stored(a, request_id) -> dict:
    return a.bookings.find_request(request_id)


def next_turn(a, sid):
    a.sessions.get(sid).turn += 1


class TestLookup:
    def test_fetch_by_id(self):
        a, llm = make_assistant()
        rid = create_request(a, llm)
        r = call(a, "other", "get_booking_request", request_id=rid.lower())
        assert r["request_id"] == rid and r["salon"] == "Marina Luxe Salon" and r["time"] == "16:00"
        assert r["status"] == "pending" and r["can_modify"] and r["can_cancel"]

    def test_unknown_id(self):
        a, _ = make_assistant()
        assert "No booking request found" in call(a, "s", "get_booking_request", request_id="BKLY-01012026-999")["error"]

    def test_signed_in_customers_requests_are_private(self):
        a, llm = make_assistant()
        owner = str(ObjectId())
        a.sessions.get("owner").user = SessionContext(user_id=owner)
        rid = create_request(a, llm)
        a.sessions.get("intruder").user = SessionContext(user_id=str(ObjectId()))
        assert "another customer" in call(a, "intruder", "get_booking_request", request_id=rid)["error"]
        a.sessions.get("owner-again").user = SessionContext(user_id=owner)
        assert call(a, "owner-again", "get_booking_request", request_id=rid)["request_id"] == rid


class TestModify:
    def test_reschedule_updates_same_request_id(self):
        a, llm = make_assistant()
        rid = create_request(a, llm)
        count_before = len(a.bookings._memory)

        llm.queue = [[("modify_booking_request", {"request_id": rid})], "What would you like to change?"]
        a.chat("s2", f"I want to change {rid}")
        llm.queue = [[("update_booking", booking(time="18:00"))], "Updated summary: 6:00 PM. Confirm?"]
        r = a.chat("s2", "make it 6pm")
        assert r.structured["awaiting_confirmation"] is True
        llm.queue = [[("confirm_booking", {})], "Your request has been updated."]
        r = a.chat("s2", "yes")

        assert r.structured["booking_response"] == {
            "request_id": rid, "status": "pending", "modified": True,
            "service": "Hair Smoothing", "date": FUTURE, "time": "18:00",
        }
        doc = stored(a, rid)
        assert (doc["requestedTime"], doc["slot"]) == ("18:00", "06:00 PM")
        assert (doc["previousRequestedDate"], doc["previousRequestedTime"]) == (FUTURE, "16:00")
        assert "rescheduledAt" in doc
        assert len(a.bookings._memory) == count_before  # no new request created
        assert a.sessions.get("s2").editing_request is None

    def test_change_service_records_previous_service(self):
        a, llm = make_assistant()
        rid = create_request(a, llm)
        call(a, "s2", "modify_booking_request", request_id=rid)
        assert call(a, "s2", "update_booking", **booking("Hair Coloring"))["applied"]
        a.sessions.get("s2").awaiting_confirmation = True  # as if the summary turn completed
        r = call(a, "s2", "confirm_booking")
        assert r["updated"] and r["request_id"] == rid
        doc = stored(a, rid)
        assert (doc["serviceName"], doc["previousServiceName"]) == ("Hair Coloring", "Hair Smoothing")
        assert doc["services"] == [f"mock-{MARINA_LUXE}-1"] and "serviceModifiedAt" in doc

    def test_modification_keeps_all_booking_rules(self):
        a, llm = make_assistant()
        rid = create_request(a, llm)
        call(a, "s2", "modify_booking_request", request_id=rid)
        assert call(a, "s2", "update_booking", **booking("Pedicure"))["applied"] is False  # salon lacks it
        assert call(a, "s2", "update_booking", **booking(time="21:00"))["applied"] is False  # after closing
        assert call(a, "s2", "update_booking", **booking("Hair Coloring", mentioned_as="not_named"))["applied"] is False

    def test_salon_cannot_change_on_existing_request(self):
        a, llm = make_assistant()
        rid = create_request(a, llm)
        call(a, "s2", "search_salons", location="Abu Dhabi")
        call(a, "s2", "modify_booking_request", request_id=rid)
        r = call(a, "s2", "update_booking", **booking(salon_id="104"))
        assert r["applied"] is False and "cannot be changed" in r["problems"][0]

    def test_same_salon_by_name_or_id_is_not_a_salon_change(self):
        a, llm = make_assistant()
        rid = create_request(a, llm)
        call(a, "s2", "modify_booking_request", request_id=rid)
        for salon_ref in ("Marina Luxe Salon", MARINA_LUXE):
            r = call(a, "s2", "update_booking", **booking(salon_id=salon_ref, date=FUTURE, time="17:00"))
            assert r["applied"] and r["draft"]["salon_id"] == MARINA_LUXE

    def test_loading_without_changes_cannot_be_confirmed(self):
        a, llm = make_assistant()
        rid = create_request(a, llm)
        llm.queue = [[("modify_booking_request", {"request_id": rid})], "What would you like to change?"]
        r = a.chat("s2", f"change {rid}")
        assert r.structured["awaiting_confirmation"] is False
        assert "error" in call(a, "s2", "confirm_booking")

    def test_only_pending_requests_can_be_modified(self):
        a, llm = make_assistant()
        rid = create_request(a, llm)
        a.bookings._memory[rid]["status"] = "rejected"
        r = call(a, "s2", "modify_booking_request", request_id=rid)
        assert "can no longer be modified" in r["error"]

    def test_salon_responds_while_customer_is_modifying(self):
        a, llm = make_assistant()
        rid = create_request(a, llm)
        call(a, "s2", "modify_booking_request", request_id=rid)
        call(a, "s2", "update_booking", **booking(time="18:00"))
        a.sessions.get("s2").awaiting_confirmation = True
        a.bookings._memory[rid]["status"] = "payment_pending"  # salon accepted meanwhile
        assert "no longer pending" in call(a, "s2", "confirm_booking")["error"]
        assert stored(a, rid)["requestedTime"] == "16:00"


class TestCancel:
    def test_cancel_after_details_were_shown(self):
        a, llm = make_assistant()
        rid = create_request(a, llm)
        call(a, "s2", "get_booking_request", request_id=rid)
        next_turn(a, "s2")
        r = call(a, "s2", "cancel_booking_request", request_id=rid, reason="plans changed")
        assert r == {"cancelled": True, "request_id": rid}
        doc = stored(a, rid)
        assert (doc["status"], doc["bookingStatus"], doc["cancelReason"]) == ("cancelled", "cancelled", "plans changed")
        assert "cancelledAt" in doc

    def test_cancel_refused_in_the_same_turn_as_lookup(self):
        a, llm = make_assistant()
        rid = create_request(a, llm)
        llm.queue = [
            [("get_booking_request", {"request_id": rid}), ("cancel_booking_request", {"request_id": rid, "reason": None})],
            "Please confirm you want to cancel.",
        ]
        r = a.chat("s2", f"cancel {rid}")
        assert r.structured["booking_response"] is None
        assert stored(a, rid)["status"] == "pending"

    def test_cancel_refused_if_never_shown(self):
        a, llm = make_assistant()
        rid = create_request(a, llm)
        next_turn(a, "s2")
        assert "details first" in call(a, "s2", "cancel_booking_request", request_id=rid)["error"]

    def test_cancelled_request_cannot_be_cancelled_or_modified_again(self):
        a, llm = make_assistant()
        rid = create_request(a, llm)
        call(a, "s2", "get_booking_request", request_id=rid)
        next_turn(a, "s2")
        call(a, "s2", "cancel_booking_request", request_id=rid)
        next_turn(a, "s2")
        assert "cannot be cancelled" in call(a, "s2", "cancel_booking_request", request_id=rid)["error"]
        assert "can no longer be modified" in call(a, "s2", "modify_booking_request", request_id=rid)["error"]
