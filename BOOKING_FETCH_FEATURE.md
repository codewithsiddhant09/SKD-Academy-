# Fetch Booking Details by Order ID Feature

## 🎯 Problem
When users want to modify or view their bookings, the bot cannot fetch booking details by order ID (e.g., BKLY-04112026-009). The old system only fetched "booking requests" from the chatbot database, not actual Bookly bookings created via the API.

## ✅ Solution
Added `get_bookly_booking` tool to fetch booking details from the Bookly API using order ID.

---

## 📝 Changes Made

### 1. New Tool: `get_bookly_booking`

**File:** `app/agent/tools.py`

```python
class get_bookly_booking(BaseModel):
    """WHAT: Fetches a Bookly booking by its order ID (e.g. BKLY-04112026-009) from the booking system.
    Returns salon, service, date, time, payment status, and booking status.
    WHY: Use when the customer asks about or wants to modify a booking they created (not old chatbot requests).
    For old chatbot requests from before the API integration, use get_booking_request instead."""

    order_id: str = Field(description="Booking order ID, e.g. 'BKLY-04112026-009'.")
```

### 2. Handler Function

**File:** `app/agent/tools.py`

```python
def run_get_bookly_booking(ctx: ToolContext, args: get_bookly_booking) -> dict:
    """Fetch a Bookly booking by order ID."""
    token = ctx.session.jwt_token or ctx.session.auth_token or get_settings().bookly_api_token
    if not token:
        return {"error": "Authentication required. Please log in."}
    
    auth_headers = {
        "x-auth-language": "English",
        "x-user-type": "User",
        "x-auth-token-user": token
    }
    
    try:
        # Try to fetch booking using the order ID
        booking = ctx.bookings.view_external_booking(args.order_id, auth_headers)
        
        # Extract and format booking details
        return {
            "order_id": booking.get("orderId"),
            "booking_id": booking.get("_id") or booking.get("bookingId"),
            "salon": salon_name,
            "services": service_names,
            "date": booking_date,
            "time": booking.get("slot"),
            "booking_status": booking.get("bookingStatus", "Unknown"),
            "payment_status": booking.get("paymentStatus", "Unknown"),
            "payment_option": booking.get("payOption"),
            "booking_place": booking.get("BookingAppointment") or booking.get("bookingPlace"),
            "final_amount": booking.get("finalAmount"),
            "can_cancel": booking.get("bookingStatus") not in ["Cancelled", "Completed", "Rejected"],
        }
    except RuntimeError as exc:
        # Fallback: try old chatbot request system
        req = ctx.bookings.find_request(args.order_id)
        if req:
            return run_get_booking_request(ctx, get_booking_request(request_id=args.order_id))
        return {"error": f"Booking {args.order_id} not found. {str(exc)}"}
```

### 3. Tool Registration

**File:** `app/agent/tools.py`

```python
TOOLS: dict[str, tuple[type[BaseModel], ToolHandler]] = {
    # ... other tools ...
    "get_bookly_booking": (get_bookly_booking, run_get_bookly_booking),
    "get_booking_request": (get_booking_request, run_get_booking_request),
    # ... rest of tools ...
}
```

### 4. Updated Assistant Prompt

**File:** `app/agent/assistant.py`

```python
Existing booking requests (IDs like BKLY-09102026-004):
- When the customer gives an order ID or asks about an existing booking, call get_bookly_booking first
  to fetch the current booking details (salon, service, date, time, payment status, booking status).
- For old chatbot requests (before API integration), use get_booking_request instead.
- Bookings from the Bookly API can be viewed but not modified through the chatbot. If the customer wants
  to change a confirmed booking, explain they need to cancel it and create a new one, or contact the salon directly.
```

---

## 🔄 How It Works

1. **User asks:** "Show me my booking BKLY-04112026-009"
2. **Bot calls:** `get_bookly_booking(order_id="BKLY-04112026-009")`
3. **Backend:**
   - Uses user's auth token (`x-auth-token-user`)
   - Calls `view_external_booking` API
   - Returns booking details including:
     - Order ID
     - Salon name
     - Service name(s)
     - Date & time
     - Booking status (Pending/Confirmed/Cancelled)
     - Payment status (Pending/Paid/Failed)
     - Total amount
     - Whether it can be cancelled
4. **Bot displays:** Full booking details to user

### Fallback Behavior

If the booking is not found in the Bookly API (might be an old chatbot request), the system automatically falls back to the old `get_booking_request` method.

---

## 📋 Example Conversation

**User:** "I want to see my booking BKLY-04112026-009"

**Bot calls tool:**
```json
{
  "tool": "get_bookly_booking",
  "args": {
    "order_id": "BKLY-04112026-009"
  }
}
```

**Tool returns:**
```json
{
  "order_id": "BKLY-04112026-009",
  "booking_id": "6aeaeabf45ecb752aea15d64",
  "salon": "Singh salon",
  "services": ["Iron man body massage"],
  "date": "2026-11-06",
  "time": "04:00 PM",
  "booking_status": "Confirmed",
  "payment_status": "Paid",
  "payment_option": "PayNow",
  "booking_place": "Salon",
  "final_amount": 628.95,
  "can_cancel": true
}
```

**Bot responds:**
"Here are your booking details:

**Order ID:** BKLY-04112026-009  
**Salon:** Singh salon  
**Service:** Iron man body massage  
**Date & Time:** November 6th, 2026 at 4:00 PM  
**Location:** At the salon  
**Payment:** Paid (AED 628.95)  
**Status:** Confirmed ✓

Would you like to cancel this booking?"

---

## 🚀 Deployment

### Files Changed:
- `app/agent/tools.py` - Added tool class, handler, and registration
- `app/agent/assistant.py` - Updated system prompt

### Deploy Command:
```bash
ssh root@178.128.102.23
cd /var/www/a-agent-base
git pull origin fixes
pm2 restart agentserver
pm2 logs agentserver --lines 50
```

---

## ✅ Testing

After deployment, test with:

1. **View existing booking:**
   - User: "Show me booking BKLY-04112026-009"
   - Expected: Bot fetches and displays all booking details

2. **View with wrong ID:**
   - User: "Show booking BKLY-99999999-999"
   - Expected: "Booking BKLY-99999999-999 not found"

3. **Modify booking request:**
   - User: "I want to change my booking BKLY-04112026-009"
   - Expected: Bot shows details, explains bookings cannot be modified directly, offers to cancel and rebook

---

## 📊 Before vs After

### Before:
- ❌ User: "Show my booking BKLY-04112026-009"
- ❌ Bot: "No booking request found with ID BKLY-04112026-009"

### After:
- ✅ User: "Show my booking BKLY-04112026-009"
- ✅ Bot: Displays complete booking details (salon, service, date, time, payment status, etc.)

---

## 🔐 Security

- Uses user's authentication token (`x-auth-token-user`)
- Only shows bookings that belong to the authenticated user
- Backend API validates ownership before returning booking details

---

**Created:** 2026-11-04  
**Status:** Ready for deployment
