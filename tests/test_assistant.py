"""Happy-path conversation through the LLM tool loop (scripted fake LLM)."""
from conftest import FUTURE, MARINA_LUXE, booking, make_assistant

from app.models.enums import IntentType


def test_full_conversation_through_llm_loop():
    a, llm = make_assistant()

    llm.queue = [
        [("search_salons", {"location": "Dubai Marina", "service": "Hair Smoothing", "category": None, "salon_name": None, "date": None})],
        "I found salons in Dubai Marina offering Hair Smoothing.",
    ]
    r = a.chat("s1", "hair smoothing in dubai marina")
    assert r.intent == IntentType.SALON_SEARCH
    assert [c.salon_name for c in r.recommendations] == ["Marina Luxe Salon"]

    llm.queue = [
        [("update_booking", booking("Hair Smoothing", MARINA_LUXE, FUTURE, "16:00"))],
        "Please confirm: Hair Smoothing at Marina Luxe Salon on 15 January 2099 at 4:00 PM.",
    ]
    r = a.chat("s1", "Marina Luxe, 15 Jan 2099 at 4pm")
    assert r.structured["awaiting_confirmation"] is True

    llm.queue = [[("update_booking", booking("Pedicure"))], "Marina Luxe Salon does not offer Pedicure."]
    r = a.chat("s1", "actually make it a pedicure")
    assert r.structured["booking_payload"]["service"] == "Hair Smoothing"

    llm.queue = [[("confirm_booking", {})], "Booked."]
    r = a.chat("s1", "yes, confirm")
    assert r.structured["booking_response"]["status"] == "pending"
    assert r.structured["booking_response"]["request_id"].startswith("BKLY-")
    assert r.structured["booking_payload"]["service"] is None
