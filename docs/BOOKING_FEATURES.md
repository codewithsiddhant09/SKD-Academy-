# Bookly Booking Features Implementation

This document describes the complete booking features implemented in the a-agent-base project, matching the specifications from the Node.js backend.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Features](#features)
4. [Environment Variables](#environment-variables)
5. [API Endpoints](#api-endpoints)
6. [Utilities](#utilities)
7. [Workflows](#workflows)

---

## Overview

The booking system supports:
- **Multiple payment options**: PayNow (Ziina), PayAtStore, and legacy flow
- **WhatsApp bookings**: With phone normalization and guest user matching
- **Cancellation policy**: 2-hour rule with automatic refund processing
- **Payment holds**: Automatic timeout handling for unpaid bookings
- **Multi-channel notifications**: Push, email, WhatsApp
- **Localization**: English and Arabic support

---

## Architecture

### File Structure

```
app/
├── api/routes/
│   ├── booking.py         # Booking endpoints
│   └── payment.py         # Payment result page and confirmation
├── services/
│   ├── booking_service.py # Main booking logic
│   ├── booking_cron.py    # Payment hold expiry handler
│   └── notification_service.py # Multi-channel notifications
├── utils/
│   ├── booking_payment.py      # Payment logic and Ziina integration
│   ├── cancellation_policy.py  # 2-hour rule and fee calculation
│   ├── timezone.py             # Slot/date parsing in booking timezone
│   └── guest_booking_link.py   # Phone-based user matching
└── locales/
    ├── en.json            # English messages
    └── ar.json            # Arabic messages
```

---

## Features

### 1. createBooking — POST /booking/book-appointment

#### Caller Detection (in order)

| Caller | Condition | userId | vendorId |
|--------|-----------|--------|----------|
| WhatsApp bot | `body.mode === "whatsapp"` | Registered user matched by phone, else null | Resolved (see §3) |
| Registered user matched by phone, else null | Resolved (see §3) |
| Customer app | `x-user-type: User` + token | `req.user._id` | `body.vendorId` (required) |
| Salon app | `x-user-type: Vendor` + token | Registered user matched by email/phone, else null | `req.user._id` |

#### Payment Options and Status

```python
payOption = (
    "PayAtStore" if (is_whatsapp or is_vendor) and not body.get("payOption")
    else body.get("payOption")
)

bookingStatus = (
    "Approved" if (payOption == "PayAtStore" or is_vendor)
    else "Pending"
)
```

| payOption | Status | Visible to salon | Then |
|-----------|--------|------------------|------|
| PayNow | Pending / paymentStatus: Pending | No, until paid | Pay via Ziina within 10 min |
| PayAtStore | Approved (+ tracking "Appointment Confirmed") | Yes | Paid at the salon on completion |
| (missing): old app | Pending | Yes | Salon accepts within 30 min, then pay within 10 min |

#### Amount Calculation

```
subtotal (service prices) 
→ minus coupon (capped at subtotal) 
→ plus active VAT % 
→ finalAmount
```

All amounts stored on the booking and returned.

#### Notifications

| Case | Notify |
|------|--------|
| PayAtStore (User / WhatsApp) | User: booking confirmed notification |
| PayNow | None until payment is confirmed |
| Old flow (User) | User: "Booking Created", Salon: "New Booking Received" + email + WhatsApp |
| Salon-created | Salon: push + customer WhatsApp/email |

### 2. Cancellation Policy

#### Rule — `get_cancellation_terms(booking, now)`

Appointment time = `booking.date + slot start`, built with `get_scheduled_moment(date, slotStart, DEFAULT_IANA_TIMEZONE)`.

| When | Result |
|------|--------|
| now ≥ appointment start | Not allowed: "Booking cannot be cancelled after the appointment start time" |
| within 2 h before start (FREE_CANCELLATION_HOURS) | Fee = CANCELLATION_FEE_AED (default 10), or CANCELLATION_FEE_PERCENTAGE% if set; capped at paid amount |
| more than 2 h before | Free, full refund |
| unpaid booking | Fee always 0 |
| date/slot unreadable | Allowed, fee 0 (logged) |

#### Accepted Slot Formats

- "02:20 PM"
- "2:20 pm"
- "02:20PM"
- "14:20"
- "02:20 PM - 02:50 PM"

#### Timezone

Comes from `BOOKING_TIMEZONE`, default `Asia/Dubai`.

**⚠️ Important**: Never build slot times with `new Date() + setHours`. Always use timezone-aware parsing.

#### Preview Endpoint

```
GET /booking/bookings/{order_id}/cancellation-quote
```

Returns:
- `paidAmount`
- `cancellationFee`
- `refundAmount`
- `isLateCancellation`
- `appointmentAt`
- `allowed`
- `reason`

#### Cancellation Endpoint

```
PUT /booking/bookings/cancel
```

Body:
```json
{
  "bookingId": "...",
  "cancelledReason": "...",
  "additionalNotes": "..."
}
```

**Process:**

1. Booking must belong to `req.user`; Cancelled/Completed → error
2. Unpaid PayNow hold → atomic cancel, notify user, return (no policy check, no refund)
3. Policy not allowed → error
4. Paid booking:
   - Needs a Successful Transaction
   - Existing Refund Transaction is reused (never refund twice)
   - `refund = paid - fee`. Calculate fee split before calling Ziina
   - Ziina refund:
     - `ZIINA_REFUND_MOCK=true` → skip the API
     - Otherwise: GET payment intent (must be completed), POST /refund with amount in fils, capped at intent amount
     - If Ziina errors: save RefundError doc, return 500, do NOT cancel booking
   - Write these Transactions:
     - Original "Booking Payment": `status → Refunded`
     - New "Refund": `amount = grossAmount = netAmount = refund, status: Refunded`
     - New "Cancellation Fee" (if fee > 0): `vendorId = salon, grossAmount = fee, commissionAmount = admin %, amount = salon share, status: Successful`
   - Booking: `paymentStatus: Pending, paymentUrl: null, ziinaPaymentId: null`
5. Unpaid PayAtStore / old flow → allowed while Pending/Approved. No refund
6. Booking → `Cancelled, cancelledReason, cancelledAt, cancelledBy: "User"`
7. Notify:
   - User: in-app + push + WhatsApp + email (includes refund and fee)
   - Salon: push + email + WhatsApp
   - New refund: refund email/WhatsApp with amounts at 2 decimals

**Fee Split Example** (paid 100, late cancel, admin 20%):
- Refund: 90
- Fee: 10
- Admin: 2
- Salon: 8

The salon's 8 is a Successful Transaction with its `vendorId`, counting in earnings automatically.

### 3. WhatsApp Booking

Same endpoint: `POST /booking/book-appointment` with `mode: "whatsapp"`, no user token.

| Step | Rule |
|------|------|
| Auth | Header `x-whatsapp-booking-key` must equal `WHATSAPP_BOOKING_SECRET` (timing-safe). Else 401. |
| Phone | Required. `normalize_whatsapp_phone`: 971501234567 → 501234567 + +971. Known codes 971, 91; default 971; leading zeros stripped; needs ≥ 7 digits. |
| User match | `find_registered_user_by_contact({ phoneNumber, countryCode })`, phone only, never email (typed email must not attach to another account). No match → `userId: null`. |
| Later linking | `link_guest_bookings_to_user` (called after OTP login/signup) sets userId on matching `userId: null` bookings via Contact email/phone. |
| Salon | `vendorId` → `salonId` → exact case-insensitive `salonName` / `vendorName` on `businessName` / `fullName` / `name` → first `serviceId`'s `vendorId`. None → "Vendor / Salon is required". |
| payOption | Defaults to `PayAtStore`. |
| PayNow | `create_ziina_payment_intent(booking, "web")`. Response adds `paymentRequired, paymentHoldMinutes: 10, paymentId, paymentUrl`. If link creation fails → booking Cancelled ("Payment link failed", cancelledBy: System) and 500. |
| Redirect | Ziina returns to `PAYMENT_RESULT_BASE_URL?result=success` |
| Result page | `GET /payment/paymentResult` renders HTML. On success calls `confirmIfPaidOnZiina`; paid state always from Ziina, never from query string. |

### 4. Payment Confirmation

**Always use `confirm_online_booking_payment(order_id, payment_id, amount)`:**

- Atomic and idempotent
- App verify, cron, and WhatsApp result page can all call it
- Sets `Paid / Ziina` and moves `Pending → Approved`
- Restores a "Payment Timeout" cancellation and clears `cancelledAt / cancelledBy`
- Creates exactly one "Booking Payment" Transaction (`grossAmount, commissionAmount = admin %, amount = netAmount = salon share`)

### 5. Payment Hold (Cron)

PayNow unpaid 10 min after create (old flow: 10 min after approval):

1. Ask Ziina first: `completed` → confirm. `pending / requires_user_action` → wait up to 5 more min.
2. Otherwise → Cancelled, `cancelledReason: "Payment Timeout", cancelledBy: "System"`
3. A PayNow hold is cancelled silently (no notification)
4. Ziina unreachable → skip and retry next minute. **Never cancel an unverified payment.**

### 6. Visibility

- `listUserBookings`: hides unpaid PayNow bookings and every "Payment Timeout" booking
- `vendorListBookings`: hides unpaid PayNow bookings and PayNow "Payment Timeout" bookings, except bookings the salon created itself

---

## Environment Variables

Add these to your `.env` file:

```bash
# Booking timezone for slot/date parsing (used in cancellation policy)
BOOKING_TIMEZONE=Asia/Dubai

# Cancellation policy
FREE_CANCELLATION_HOURS=2
CANCELLATION_FEE_AED=10
CANCELLATION_FEE_PERCENTAGE=0

# Ziina payment integration
ZIINA_BASE_URL=https://api.ziina.com/v1
ZIINA_API_KEY=your-ziina-api-key
ZIINA_TEST_MODE=false
ZIINA_REFUND_MOCK=false

# Payment settings
PAYMENT_RESULT_BASE_URL=http://localhost:8000/payment/paymentResult
PAYMENT_HOLD_MINUTES=10
WHATSAPP_REFUND_PROCESSING_TIME=24-48 hours

# WhatsApp booking
WHATSAPP_BOOKING_SECRET=your-whatsapp-booking-secret
```

---

## API Endpoints

### Booking Endpoints

#### Create Booking
```
POST /api/v1/booking/book-appointment
```

Headers:
- `x-auth-language`: English or Arabic
- `x-user-type`: User or Vendor
- `x-auth-token`: Authentication token
- `x-whatsapp-booking-key`: For WhatsApp bookings

Body:
```json
{
  "mode": "whatsapp",  // Optional: for WhatsApp bookings
  "phoneNumber": "971501234567",
  "vendorId": "...",
  "serviceId": ["..."],
  "date": "2024-01-15",
  "slot": "02:20 PM",
  "payOption": "PayNow",  // PayNow, PayAtStore, or null
  "email": "user@example.com"
}
```

Response:
```json
{
  "booking": {
    "_id": "...",
    "orderId": "BKLY-15012024-ABC",
    "bookingStatus": "Pending",
    "paymentStatus": "Pending",
    "paymentUrl": "https://pay.ziina.com/...",
    "paymentId": "pi_..."
  }
}
```

#### View Booking
```
GET /api/v1/booking/bookings/{booking_id}
```

#### Get Cancellation Quote
```
GET /api/v1/booking/bookings/{order_id}/cancellation-quote
```

Response:
```json
{
  "cancellation": {
    "allowed": true,
    "paidAmount": 100.0,
    "cancellationFee": 10.0,
    "refundAmount": 90.0,
    "isLateCancellation": true,
    "appointmentAt": "2024-01-15T14:20:00+04:00"
  }
}
```

#### Cancel Booking
```
PUT /api/v1/booking/bookings/cancel
```

Body:
```json
{
  "bookingId": "...",
  "cancelledReason": "Customer request",
  "additionalNotes": "Changed plans"
}
```

### Payment Endpoints

#### Payment Result Page
```
GET /api/v1/payment/paymentResult?result=success&orderId=...&payment_intent=pi_...
```

Returns HTML page showing payment result.

#### Manual Payment Confirmation
```
POST /api/v1/payment/confirm-booking-payment
```

Body:
```json
{
  "order_id": "BKLY-15012024-ABC",
  "payment_intent_id": "pi_..."
}
```

---

## Utilities

### booking_payment.py

Functions:
- `determine_pay_option()`: Validate and determine payment option
- `calculate_booking_status()`: Calculate initial booking status
- `calculate_booking_amounts()`: Calculate subtotal, VAT, final amount
- `calculate_commission()`: Split commission
- `create_ziina_payment_intent()`: Create Ziina payment link
- `verify_ziina_payment()`: Verify payment with Ziina
- `refund_ziina_payment()`: Process refund via Ziina
- `is_payment_hold_expired()`: Check if hold expired

### cancellation_policy.py

Functions:
- `get_cancellation_terms()`: Calculate cancellation fee and refund
- `calculate_fee_split()`: Split cancellation fee between admin and salon

### timezone.py

Functions:
- `get_scheduled_moment()`: Parse booking date and slot in timezone
- `parse_slot_start()`: Extract start time from slot range
- `is_valid_slot_format()`: Validate slot format

### guest_booking_link.py

Functions:
- `normalize_whatsapp_phone()`: Normalize WhatsApp phone numbers
- `find_registered_user_by_contact()`: Find user by phone
- `link_guest_bookings_to_user()`: Link guest bookings after signup
- `extract_salon_info()`: Resolve salon from various sources

---

## Workflows

### PayNow Booking Flow

```
1. User creates booking with payOption: "PayNow"
   ↓
2. System creates booking with status: "Pending"
   ↓
3. Create Ziina payment intent
   ↓
4. Return payment URL to user
   ↓
5. User completes payment on Ziina
   ↓
6. Ziina redirects to payment result page
   ↓
7. Page verifies payment with Ziina
   ↓
8. Confirm booking payment (atomic, idempotent)
   ↓
9. Update booking: status → "Approved", paymentStatus → "Paid"
   ↓
10. Send confirmation notifications
```

### PayAtStore Booking Flow

```
1. User creates booking with payOption: "PayAtStore"
   ↓
2. System creates booking with status: "Approved"
   ↓
3. Send confirmation notifications immediately
   ↓
4. User pays at salon on completion
```

### Cancellation with Refund Flow

```
1. User requests cancellation
   ↓
2. Check cancellation policy (2-hour rule)
   ↓
3. If within 2 hours → calculate fee
   ↓
4. If paid booking → process Ziina refund
   ↓
5. Create refund transaction
   ↓
6. Create cancellation fee transaction (if applicable)
   ↓
7. Update booking: status → "Cancelled"
   ↓
8. Send cancellation notifications with refund details
```

### Payment Hold Expiry Flow (Cron)

```
1. Cron runs every minute
   ↓
2. Find PayNow bookings unpaid > 10 min
   ↓
3. For each expired booking:
   ├─ Verify with Ziina
   ├─ If completed → confirm payment
   ├─ If pending and < 15 min → wait (grace period)
   └─ Otherwise → cancel with "Payment Timeout"
   ↓
4. Cancelled silently (no notification)
```

---

## Must-Keep Rules

1. **Responses**: Go through `success()` / `error()` with `req.language`. Every new message must be added to both `locales/en.json` and `locales/ar.json`.

2. **Race Conditions**: Use atomic updates with expected current state in filter for payment vs cancel vs cron.

3. **Notifications**: Use `notify()` wrapped so a failure can't break the main action.

4. **Service Restart**: After changing common utilities, restart the service manually.

5. **Never Cancel Unverified Payments**: If Ziina is unreachable, skip and retry - never cancel.

6. **Idempotent Payment Confirmation**: Safe to call multiple times, won't duplicate transactions.

7. **WhatsApp Phone Matching**: Phone only, never email for WhatsApp bookings.

8. **Timezone-Aware Parsing**: Always use `get_scheduled_moment()` for appointment times.

---

## Testing

### Test PayNow Flow

```bash
# Create booking with PayNow
curl -X POST http://localhost:8000/api/v1/booking/book-appointment \
  -H "Content-Type: application/json" \
  -H "x-auth-token: YOUR_TOKEN" \
  -d '{
    "vendorId": "...",
    "serviceId": ["..."],
    "date": "2024-01-20",
    "slot": "02:00 PM",
    "payOption": "PayNow",
    "phoneNumber": "501234567",
    "email": "test@example.com"
  }'

# Response includes paymentUrl - visit it to complete payment
```

### Test Cancellation

```bash
# Get cancellation quote
curl -X GET http://localhost:8000/api/v1/booking/bookings/BKLY-15012024-ABC/cancellation-quote \
  -H "x-auth-token: YOUR_TOKEN"

# Cancel booking
curl -X PUT http://localhost:8000/api/v1/booking/bookings/cancel \
  -H "Content-Type: application/json" \
  -H "x-auth-token: YOUR_TOKEN" \
  -d '{
    "bookingId": "...",
    "cancelledReason": "Test cancellation"
  }'
```

### Test WhatsApp Booking

```bash
curl -X POST http://localhost:8000/api/v1/booking/book-appointment \
  -H "Content-Type: application/json" \
  -H "x-whatsapp-booking-key: YOUR_SECRET" \
  -d '{
    "mode": "whatsapp",
    "phoneNumber": "971501234567",
    "vendorId": "...",
    "serviceId": ["..."],
    "date": "2024-01-20",
    "slot": "02:00 PM",
    "payOption": "PayAtStore"
  }'
```

---

## Support

For issues or questions:
1. Check the logs for detailed error messages
2. Verify all environment variables are set correctly
3. Test with `ZIINA_REFUND_MOCK=true` in development
4. Check Ziina dashboard for payment status

---

**Last Updated**: 2024-01-15
**Version**: 1.0.0
