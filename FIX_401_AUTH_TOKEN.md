# FIX: 401 Unauthorized - No Token Provided

## Problem Found ✅
```
HTTP 401 Unauthorized
"Access Denied. No token provided."
```

The booking API is rejecting requests because **NO authentication token** is being sent in the headers.

## Root Cause

From logs:
```python
token = session.jwt_token or session.auth_token or get_settings().bookly_api_token
auth_headers = {"x-auth-token": token} if token else None
```

**All three token sources are EMPTY:**
1. `session.jwt_token` - Set from frontend `auth_token` field (EMPTY)
2. `session.auth_token` - Not used (EMPTY)
3. `get_settings().bookly_api_token` - From `.env` `BOOKLY_API_TOKEN` (EMPTY)

## Two Solutions

### Solution 1: Frontend Must Send auth_token (CORRECT)

Frontend should include user's JWT token in the request:

```json
POST /chat
{
  "session_id": "xxx",
  "message": "book a haircut",
  "platform": "app",
  "auth_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",  ← ADD THIS
  "user_id": "user-123"
}
```

The agent will then pass it to booking API:
```python
headers = {"x-auth-token": "eyJhbGciOiJIUz..."}
```

### Solution 2: Use System Token (TEMPORARY WORKAROUND)

If frontend can't send token yet, add a system-level token to `.env`:

```env
BOOKLY_API_TOKEN=your-system-token-here
```

This is a **fallback** for testing, but production should use user tokens.

---

## Changes Made (Commit e91af72)

### 1. Added Logging in `/chat` endpoint

`app/api/routes/chat.py`:
```python
logger.info("=== CHAT REQUEST RECEIVED ===")
logger.info("auth_token present: %s", bool(payload.auth_token))
logger.info("auth_token value: %s", payload.auth_token[:20] + "...")
if not payload.auth_token:
    logger.warning("No auth_token provided!")
```

### 2. Added Validation in `confirm_booking`

`app/agent/tools.py`:
```python
token = session.jwt_token or session.auth_token or get_settings().bookly_api_token
logger.info("AUTH TOKEN CHECK: jwt_token=%s, auth_token=%s, bookly_api_token=%s", ...)
if not token:
    logger.error("NO AUTH TOKEN AVAILABLE!")
    return {"error": "Authentication token is required but not provided. Please ensure you're logged in."}
```

Now we'll see in logs EXACTLY where the token is missing!

---

## Deploy & Test

### 1. Deploy Latest Code
```bash
ssh ubuntu@172.31.32.142
cd /var/www/a-agent-base
git pull origin fixes
pm2 restart agentserver
```

### 2. Test Booking & Check Logs
```bash
pm2 logs agentserver --lines 50
```

**You will now see:**
```
INFO === CHAT REQUEST RECEIVED ===
INFO auth_token present: False    ← Shows if token is sent
INFO No auth_token provided!

... later ...

INFO AUTH TOKEN CHECK: jwt_token=False, auth_token=False, bookly_api_token=False
ERROR NO AUTH TOKEN AVAILABLE!
```

This will confirm if frontend is sending token or not.

---

## Expected Scenarios After Deployment

### Scenario A: Frontend NOT Sending Token
**Logs:**
```
INFO auth_token present: False
WARNING No auth_token provided!
ERROR NO AUTH TOKEN AVAILABLE!
```

**Solution:** Fix frontend to include `auth_token` in request.

### Scenario B: Frontend IS Sending Token
**Logs:**
```
INFO auth_token present: True
INFO auth_token value: eyJhbGciOiJIUz...
INFO Auth token saved to session.jwt_token
INFO Calling booking API with auth headers: {'x-auth-token': 'eyJhbGciOiJIUz...'}
INFO Booking created: {'_id': '...', 'orderId': '...', 'paymentUrl': '...'}
```

**Result:** ✅ Booking created successfully!

---

## Frontend Fix Required

**Current Request (Missing token):**
```json
{
  "session_id": "1793683269306_s1k0t89n",
  "message": "Pay now",
  "platform": "app",
  "user_id": "user-123"
}
```

**Fixed Request (With token):**
```json
{
  "session_id": "1793683269306_s1k0t89n",
  "message": "Pay now",
  "platform": "app",
  "user_id": "user-123",
  "auth_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."  ← ADD THIS
}
```

The token should be the user's JWT from login/authentication.

---

## Alternative: Temporary System Token

If you need to test WITHOUT frontend changes, add this to `.env` on server:

```bash
ssh ubuntu@172.31.32.142
nano /var/www/a-agent-base/.env

# Add this line:
BOOKLY_API_TOKEN=<get-valid-token-from-backend-team>

# Restart
pm2 restart agentserver
```

**⚠️ This is NOT recommended for production** - use user-specific tokens!

---

## Summary

**Problem:** No authentication token → API returns 401
**Root Cause:** Frontend not sending `auth_token` field
**Solution:** 
1. Deploy code with logging (Done ✅)
2. Check logs to confirm token is missing
3. Fix frontend to send `auth_token`
4. OR add temporary `BOOKLY_API_TOKEN` to `.env`

**After fix:** Bookings will be created with payment links! 🎉

---

**Commit:** e91af72 - "Add auth token logging and validation"
**Status:** Ready to deploy + needs frontend fix
