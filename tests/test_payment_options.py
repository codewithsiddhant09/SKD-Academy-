from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.agent import tools
from app.agent.assistant import BookingAssistant
from app.agent.session import Session


def booking_context(monkeypatch, payment_url: str | None = None):
    from test_external_booking_api import ready_context

    ctx = ready_context()
    monkeypatch.setattr(
        ctx.bookings,
        "create_external_booking",
        Mock(return_value={"results": {"booking": {
            "_id": "booking-id",
            "orderId": "order-id",
            "bookingStatus": "Pending",
            "paymentStatus": "Pending",
            "paymentUrl": payment_url,
        }}}),
    )
    return ctx


def test_confirm_requires_explicit_payment_choice_and_does_not_call_api(monkeypatch):
    ctx = booking_context(monkeypatch)
    result = tools.run_confirm_booking(ctx, tools.confirm_booking())
    assert "choose Pay Now or Pay Later" in result["error"]
    ctx.bookings.create_external_booking.assert_not_called()


@pytest.mark.parametrize("choice", ["Pay Now", "Pay Later"])
def test_selected_payment_option_is_sent_to_booking_api(monkeypatch, choice):
    ctx = booking_context(monkeypatch, payment_url="https://pay.example/checkout")
    ctx.session.payment_option = choice
    result = tools.run_confirm_booking(ctx, tools.confirm_booking(payment_option=choice))

    payload = ctx.bookings.create_external_booking.call_args.args[0]
    assert payload["payOption"] == ("PayNow" if choice == "Pay Now" else "PayAtStore")
    assert result["payment_option"] == choice
    if choice == "Pay Now":
        assert result["payment_url"] == "https://pay.example/checkout"
        assert ctx.booking_result["payment_url"] == result["payment_url"]
    else:
        assert "payment_url" not in result
        assert "payment_url" not in ctx.booking_result


def test_pay_now_without_returned_url_does_not_invent_one(monkeypatch):
    ctx = booking_context(monkeypatch, payment_url=None)
    ctx.session.payment_option = "Pay Now"
    result = tools.run_confirm_booking(ctx, tools.confirm_booking(payment_option="Pay Now"))
    assert "payment_url" not in result
    assert "payment_url" not in ctx.booking_result


def test_session_only_recognizes_explicit_unambiguous_choice():
    assert BookingAssistant._payment_choice("I want to Pay Now") == "Pay Now"
    assert BookingAssistant._payment_choice("please pay later") == "Pay Later"
    assert BookingAssistant._payment_choice("yes, proceed") is None
    assert BookingAssistant._payment_choice("not pay now, pay later") is None
    assert BookingAssistant._payment_choice("pay now and maybe pay later") is None


def test_ambiguous_turn_does_not_arm_booking_confirmation(monkeypatch):
    from app.models.schemas import BookingPayload

    class FakeSessions:
        def get(self, _session_id):
            return session

    class NoClientAssistant(BookingAssistant):
        def _converse(self, current, _ctx, _message, _called):
            return "Please select Pay Now or Pay Later."

    session = Session("s")
    session.draft = BookingPayload(service="Hair", salon_id="salon", date="2099-01-01", time="10:00")
    session.awaiting_confirmation = True
    assistant = object.__new__(NoClientAssistant)
    assistant.ensure_user_context = lambda *_: None
    assistant.sessions = FakeSessions()
    assistant.categories = assistant.users = assistant.salons = assistant.bookings = assistant.knowledge = None
    response = assistant.chat("s", "yes")

    assert response.structured["awaiting_confirmation"] is True
    assert response.structured["payment_option"] is None
    assert session.awaiting_confirmation is True


def test_explicit_payment_choice_is_available_to_booking_tool(monkeypatch):
    ctx = booking_context(monkeypatch, payment_url="https://pay.example/checkout")
    ctx.session.payment_option = "Pay Now"
    assert tools.run_confirm_booking(ctx, tools.confirm_booking(payment_option="Pay Later"))["error"].startswith(
        "Use only the payment option"
    )
    ctx.bookings.create_external_booking.assert_not_called()


def test_no_payment_choice_is_not_injected_for_existing_request_modification(monkeypatch):
    ctx = booking_context(monkeypatch)
    ctx.session.editing_request = {"request_id": "BKLY-1"}
    ctx.session.payment_option = None
    monkeypatch.setattr(tools, "_save_modification", lambda _ctx, _offer: {"updated": True})
    assert tools.run_confirm_booking(ctx, tools.confirm_booking()) == {"updated": True}
    ctx.bookings.create_external_booking.assert_not_called()
