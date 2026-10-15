# Bookly createBooking integration

## What changed

The conversational `confirm_booking` tool now submits a booking to the configured Bookly createBooking endpoint after the existing salon, service, date, availability, and explicit-confirmation checks. The API result is returned as `booking_response` with the Bookly `orderId`, `bookingStatus`, and `paymentStatus`. The assistant must report those statuses as returned; the sample response has both statuses `Pending`.

The endpoint is configured by `BOOKING_CREATE_API_URL` (defaults to `http://15.252.235.83:2053/booking/createBooking`). `BOOKING_API_TIMEOUT_SECONDS` defaults to 15 and `BOOKING_VAT_PERCENTAGE` defaults to 5. The HTTP client does not retry POST requests, because a timeout may happen after the booking was created and a retry could duplicate it.

The request maps the selected salon's real `vendorId`, the chosen offer's Bookly service ID, the signed-in user's Bookly ID, and date/time into the external contract. Customer data is read from the user profile and `addresses` collection; session contact data can be supplied with the authenticated `PATCH /api/v1/session/{session_id}/booking-contact` endpoint. The location is sent as GeoJSON Point with `[longitude, latitude]`. Mock salon/service IDs are rejected.

## Booking flow

1. Customer searches for salons/services; only returned salons and their actual service offers can be selected.
2. The assistant validates service, salon, date, opening time, and lead-time rules.
3. It summarizes the booking and waits for a separate explicit customer confirmation.
4. On confirmation it requires a signed-in profile and complete contact data. If needed, the client saves address/city/ZIP/country code and coordinates using the session booking-contact endpoint, then asks the customer to confirm again.
5. Backend posts once to createBooking. Success returns the order ID and API statuses. API rejection or definite HTTP failure is reported as an error. Timeout is marked unsafe to retry until the user checks whether the remote booking exists.

Existing chatbot pending-request modifications/cancellation remain local workflows; the supplied API does not document modify/cancel operations. The standalone legacy `/api/v1/book-appointment` route remains a local placeholder and is not the external API booking path.

## Required deployment environment

```env
BOOKING_CREATE_API_URL=http://15.252.235.83:2053/booking/createBooking
BOOKING_API_TIMEOUT_SECONDS=15
BOOKING_VAT_PERCENTAGE=5
```

Do not store or copy customer examples into environment or source files. No live booking request was sent during development.

## View booking API

The backend exposes `GET /api/v1/bookings/{booking_id}` and forwards the request to `BOOKING_VIEW_API_URL/{booking_id}` (default `http://15.252.235.83:2053/booking/viewBooking`). Configure the optional `BOOKING_VIEW_API_URL` environment variable to override it. The route requires `x-auth-language`, `x-user-type`, and `x-auth-token-user`, forwards only those headers, and performs no retries. The Bookly API is relied on to validate the token and enforce booking ownership because this application does not currently verify Bookly JWTs itself.

The response is filtered to booking/order identifiers, booking/payment statuses, date/time/type, salon name, service names/durations/prices, totals and a small contact subset. Completion codes, email addresses, phone numbers, raw tokens and unneeded upstream fields are not returned. Upstream authentication/authorization/not-found HTTP statuses are surfaced to the caller; API-level errors and malformed responses are rejected. Never place a Bookly token in source code or logs.

The frontend does not currently have a verified authenticated-token source, so this API is available for a signed-in client that can securely supply the documented headers; the chat UI is not yet wired to call it. Local database `bookly_staging.bookings` is not used as a fallback because it may not be the external API's source of truth. Tests mock the upstream call and do not contact Bookly.
