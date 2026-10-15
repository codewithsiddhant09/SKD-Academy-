from datetime import date
from unittest.mock import Mock

import httpx
import pytest

from app.agent.session import Session
from app.agent.tools import ToolContext, confirm_booking, run_confirm_booking
from app.models.schemas import BookingPayload, Salon, ServiceOffer, SessionContext
from app.services.booking_service import BookingService
from fastapi.testclient import TestClient


class NoMongo:
    def is_available(self):
        return False


def ready_context(user=True):
    booking_service = BookingService(repository=NoMongo())
    salon = Salon(
        vendor_id="6ac4899b6b8a5b0808cad3a8",
        salon_name="Test salon",
        categories=["Hair"],
        services=["Hair smoothing"],
        offers=[ServiceOffer(id="6ac48ac68aa334febff8f837", name="Hair smoothing", price=899)],
        location="Noida",
    )
    session = Session("session-1")
    session.known_salons[salon.vendor_id] = salon
    session.draft = BookingPayload(
        salon="Test salon", salon_id=salon.vendor_id, service="Hair smoothing",
        date="2099-01-15", time="16:20",
    )
    session.awaiting_confirmation = True
    if user:
        session.user = SessionContext(
            user_id="6a95256c6e2ce14bdd67a45a", full_name="Test Customer", email="test@example.com",
            country_code="+91", phone_number="9999999999", address="1 Main Street", city="Noida",
            zip_code="201309", latitude=28.6167, longitude=77.3887,
        )
    class Empty:
        pass
    ctx = ToolContext(session, Empty(), Empty(), booking_service, None)
    return ctx


def mock_success(monkeypatch, result):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = result
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.post.return_value = response
    monkeypatch.setattr("app.services.booking_service.httpx.Client", lambda **kwargs: client)
    return client


def test_booking_api_payload_and_success(monkeypatch):
    client = mock_success(monkeypatch, {"error": False, "results": {"booking": {"orderId": "BKLY-123", "bookingStatus": "Pending", "paymentStatus": "Pending"}}})
    ctx = ready_context()

    result = run_confirm_booking(ctx, confirm_booking())

    sent = client.post.call_args.kwargs["json"]
    assert client.post.call_args.args[0].endswith("/booking/createBooking")
    assert sent["vendorId"] == "6ac4899b6b8a5b0808cad3a8"
    assert sent["serviceId"] == ["6ac48ac68aa334febff8f837"]
    assert sent["slot"] == "04:20 PM"
    assert sent["bookingcreatedBy"] == "6a95256c6e2ce14bdd67a45a"
    assert sent["location"] == {"type": "Point", "coordinates": [77.3887, 28.6167]}
    assert result["order_id"] == "BKLY-123"
    assert result["booking_status"] == "Pending"
    assert ctx.session.last_booking_order_id == "BKLY-123"


def test_requires_signed_in_customer(monkeypatch):
    ctx = ready_context(user=False)
    result = run_confirm_booking(ctx, confirm_booking())
    assert "signed-in" in result["error"]


def test_requires_contact_and_real_service_id():
    ctx = ready_context()
    ctx.session.user.address = None
    result = run_confirm_booking(ctx, confirm_booking())
    assert "address" in result["error"]

    ctx = ready_context()
    ctx.session.known_salons[ctx.session.draft.salon_id].offers[0].id = "mock-service"
    result = run_confirm_booking(ctx, confirm_booking())
    assert "real Bookly service ID" in result["error"]


def test_api_rejection_and_http_errors(monkeypatch):
    mock_success(monkeypatch, {"error": True, "message": "Invalid vendor"})
    result = ready_context()
    assert "Invalid vendor" in run_confirm_booking(result, confirm_booking())["error"]

    client = mock_success(monkeypatch, {})
    client.post.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
        "bad", request=Mock(), response=Mock(status_code=503, text="unavailable")
    )
    result = run_confirm_booking(ready_context(), confirm_booking())
    assert "HTTP 503" in result["error"]


def test_timeout_is_not_safe_to_retry(monkeypatch):
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.post.side_effect = httpx.TimeoutException("timed out")
    monkeypatch.setattr("app.services.booking_service.httpx.Client", lambda **kwargs: client)
    result = run_confirm_booking(ready_context(), confirm_booking())
    assert result["retry_safe"] is False
    assert "verify booking status" in result["error"]


def test_confirmation_required_before_api_call(monkeypatch):
    client = mock_success(monkeypatch, {"error": False, "results": {"booking": {"orderId": "BKLY-123"}}})
    ctx = ready_context()
    ctx.session.awaiting_confirmation = False
    result = run_confirm_booking(ctx, confirm_booking())
    assert "explicit confirmation" in result["error"]
    client.post.assert_not_called()


def test_view_external_booking_forwards_only_expected_auth_headers(monkeypatch):
    booking = {
        "_id": "6acf08e821c04f990fe0832d", "orderId": "BKLY-14102026-001",
        "bookingStatus": "Pending", "paymentStatus": "Pending",
    }
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"error": False, "results": {"booking": booking}}
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.get.return_value = response
    monkeypatch.setattr("app.services.booking_service.httpx.Client", lambda **kwargs: client)

    result = BookingService(repository=NoMongo()).view_external_booking(
        "6acf08e821c04f990fe0832d",
        {"x-auth-language": "English", "x-user-type": "User", "x-auth-token-user": "not-a-real-token"},
    )

    assert result["orderId"] == "BKLY-14102026-001"
    assert client.get.call_args.args[0].endswith("/booking/viewBooking/6acf08e821c04f990fe0832d")
    assert set(client.get.call_args.kwargs["headers"]) == {
        "x-auth-language", "x-user-type", "x-auth-token-user",
    }


def test_view_booking_route_requires_headers_before_upstream_call(monkeypatch):
    from app.api import deps
    from app.main import fastapi_app

    client = Mock()
    monkeypatch.setattr(deps, "assistant", Mock())
    deps.assistant.bookings.view_external_booking = client
    response = TestClient(fastapi_app).get("/api/v1/bookings/6acf08e821c04f990fe0832d")
    assert response.status_code == 401
    client.assert_not_called()


def test_view_booking_route_returns_restricted_booking_fields(monkeypatch):
    from app.api import deps
    from app.main import fastapi_app

    booking = {
        "_id": "6acf08e821c04f990fe0832d", "orderId": "BKLY-14102026-001",
        "bookingStatus": "Pending", "paymentStatus": "Pending", "completionCode": 123456,
        "date": "2026-10-14T00:00:00.000Z", "slot": "04:20 PM", "BookingAppointment": "Home",
        "vendorId": {"businessName": "Test salon"},
        "services": [{"_id": "service-1", "name": "Hair", "price": 899}],
        "contactId": {"contactName": "Test", "address": "1 Main Street", "email": "private@example.com"},
    }
    assistant = Mock()
    assistant.bookings.view_external_booking.return_value = booking
    monkeypatch.setattr(deps, "assistant", assistant)

    response = TestClient(fastapi_app).get(
        "/api/v1/bookings/6acf08e821c04f990fe0832d",
        headers={"x-auth-language": "English", "x-user-type": "User", "x-auth-token-user": "not-a-real-token"},
    )
    assert response.status_code == 200
    result = response.json()["booking"]
    assert result["order_id"] == "BKLY-14102026-001"
    assert result["salon"] == "Test salon"
    assert result["services"][0]["name"] == "Hair"
    assert "completionCode" not in result
    assert "email" not in result["contact"]


def test_view_booking_route_rejects_invalid_id_without_upstream_call(monkeypatch):
    from app.api import deps
    from app.main import fastapi_app

    assistant = Mock()
    monkeypatch.setattr(deps, "assistant", assistant)
    response = TestClient(fastapi_app).get(
        "/api/v1/bookings/not-a-booking-id",
        headers={"x-auth-language": "English", "x-user-type": "User", "x-auth-token-user": "not-a-real-token"},
    )
    assert response.status_code == 400
    assistant.bookings.view_external_booking.assert_not_called()


def test_view_external_booking_rejects_api_error(monkeypatch):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"error": True, "message": "Booking not found"}
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.get.return_value = response
    monkeypatch.setattr("app.services.booking_service.httpx.Client", lambda **kwargs: client)

    with pytest.raises(RuntimeError, match="Booking not found"):
        BookingService(repository=NoMongo()).view_external_booking(
            "6acf08e821c04f990fe0832d",
            {"x-auth-language": "English", "x-user-type": "User", "x-auth-token-user": "not-a-real-token"},
        )


def test_view_booking_sanitizes_response_fields():
    from app.api.routes.booking import _public_booking

    result = _public_booking({
        "_id": "booking-id", "orderId": "BKLY-1", "completionCode": 111,
        "vendorId": {"businessName": "Salon", "email": "private@example.com"},
        "services": [{"name": "Hair", "price": 50, "description": "details"}],
        "contactId": {"contactName": "Customer", "address": "Address", "email": "private@example.com"},
    })
    assert result["salon"] == "Salon"
    assert "email" not in result["contact"]
    assert "completionCode" not in result
    assert "description" not in result["services"][0]


def test_booking_id_must_be_a_mongo_object_id():
    from fastapi.testclient import TestClient
    from app.main import fastapi_app

    response = TestClient(fastapi_app).get("/api/v1/bookings/BKLY-14102026-001")
    assert response.status_code == 400
