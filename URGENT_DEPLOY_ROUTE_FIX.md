# URGENT: Fix Frontend Route Mismatch

## Problem
Frontend is calling: `http://15.252.235.83:5000/chat`
But server expects: `http://15.252.235.83:5000/api/v1/chat`

Result: **404 Not Found** → Frontend shows "System Error"

## Root Cause
`app/api/router.py` had:
```python
api_router = APIRouter(prefix="/api/v1")  # ← This added /api/v1 to all routes
```

## Solution ✅
Removed the prefix so routes are at root level:
```python
api_router = APIRouter()  # ← No prefix
```

Now routes are:
- ✅ `/chat` (was `/api/v1/chat`)
- ✅ `/health` (was `/api/v1/health`)
- ✅ `/booking` (was `/api/v1/booking`)
- etc.

## Deployment Commands

```bash
ssh ubuntu@172.31.32.142
cd /var/www/a-agent-base

# Pull latest code
git pull origin fixes

# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null

# Update .env with new backend API URL (if not done already)
sed -i 's|BOOKING_CREATE_API_URL=.*|BOOKING_CREATE_API_URL=https://test.bookly.ae:2087/booking/createBooking|' .env
sed -i 's|BOOKING_PAYNOW_API_URL=.*|BOOKING_PAYNOW_API_URL=https://test.bookly.ae:2087/booking/payNowBooking|' .env
sed -i 's|BOOKING_VIEW_API_URL=.*|BOOKING_VIEW_API_URL=https://test.bookly.ae:2087/booking/viewBooking|' .env
sed -i 's|BOOKING_CANCELLATION_AMOUNT_API_URL=.*|BOOKING_CANCELLATION_AMOUNT_API_URL=https://test.bookly.ae:2087/booking/getCancellationAmount|' .env
sed -i 's|BOOKING_CANCEL_API_URL=.*|BOOKING_CANCEL_API_URL=https://test.bookly.ae:2087/booking/cancelBookingByUser|' .env

# Verify .env
echo "=== Backend API URLs ==="
cat .env | grep BOOKING_CREATE

# Restart PM2
pm2 restart agentserver

# Monitor logs
pm2 logs agentserver --lines 50
```

## Verification

### 1. Test /chat endpoint:
```bash
curl -X POST http://15.252.235.83:5000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test123","message":"hello"}'
```

Should return JSON response (not 404).

### 2. Test /health endpoint:
```bash
curl http://15.252.235.83:5000/health
```

Should return: `{"status":"ok","rag_ready":true,"categories_cached":true}`

### 3. Check logs for successful booking:
```bash
pm2 logs agentserver | grep -E "CONFIRM_BOOKING|Booking created"
```

Should see:
```
INFO === CONFIRM_BOOKING CALLED ===
INFO BOOKING_PAYLOAD: {...}
INFO Booking created: {'_id': '...', 'orderId': 'BKLY-...', 'paymentUrl': '...'}
```

## All Fixes Included in This Deployment

1. ✅ **Route prefix removed** - Frontend can call `/chat` directly
2. ✅ **Comprehensive logging** - Can debug any issues
3. ✅ **Contact info collection** - AI asks for all required fields
4. ✅ **Backend API URL updated** - Points to `https://test.bookly.ae:2087`
5. ✅ **Individual/Group booking** - Feature implemented
6. ✅ **Home/Salon location** - Feature implemented
7. ✅ **Payment flow** - Immediate confirmation, no approval wait

## Expected Result

User journey:
1. User sends message ✅
2. AI responds (no "System Error") ✅
3. User completes booking flow ✅
4. User provides contact info ✅
5. AI saves contact info ✅
6. AI creates booking ✅
7. **Payment link shown** ✅

## Recent Commits

```
2608643 - Remove /api/v1 prefix - frontend calls /chat directly
f2dbd4d - Update booking API base URL to https://test.bookly.ae:2087
a28b3c2 - Add comprehensive logging and fix contact validation
a72bcc7 - Add save_booking_contact tool
5322964 - Fix syntax error: longitude missing .longitude attribute
```

## If Still Getting Errors After Deployment

### Check 1: Is server running on correct IP?
```bash
pm2 status
# Should show agentserver running
```

### Check 2: Is frontend calling correct URL?
Frontend must call: `http://15.252.235.83:5000/chat`
NOT: `http://15.252.235.83:5000/api/v1/chat`

### Check 3: Check PM2 logs for errors
```bash
pm2 logs agentserver --lines 100
```

Look for:
- Connection errors
- 404 errors (should be gone now)
- API failures
- Missing fields errors

### Check 4: Test direct API call
```bash
# From your local machine
curl -X POST http://15.252.235.83:5000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session",
    "message": "hello",
    "platform": "app"
  }'
```

Should get response like:
```json
{
  "reply": "Hello! ...",
  "intent": "general_conversation",
  ...
}
```

---

**Status**: CRITICAL FIX - Ready to deploy immediately
**Priority**: P0 - Blocks all functionality
**Impact**: Fixes "System Error" in app, enables all booking features
