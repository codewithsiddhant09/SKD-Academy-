# 🔍 Detailed API Call Logging - Deploy Karo!

## Kya Change Kiya Maine

**File:** `app/services/booking_service.py`

**Location:** Exactly jahan backend API call hoti hai (line ~135)

### Before API Call:
```
================================================================================
🚀 CALLING BOOKING API
================================================================================
📍 URL: https://test.bookly.ae:2087/booking/createBooking
📦 PAYLOAD: {vendorId, serviceId, payOption, ...}
🔐 AUTH HEADERS PROVIDED: True/False
🔑 AUTH HEADERS KEYS: ['x-auth-token', 'x-auth-language', 'x-user-type']
   x-auth-language: English
   x-user-type: User
   x-auth-token: eyJhbGciOiJIUzI1NiIsI... (length=234)
================================================================================
```

### After API Response:
```
📥 RESPONSE RECEIVED
   Status Code: 401
   Response: {"error":true,"error_code":401,"message":"Access Denied..."}
❌ BOOKING API HTTP ERROR
   Status: 401
   Response: {"error":true,"error_code":401,"message":"Access Denied..."}
================================================================================
```

---

## 🚀 Deploy Commands

### Option 1: Manual Copy (Server pe seedha file update karo)

```bash
# 1. Server pe login
ssh ubuntu@172.31.32.142

# 2. Backup le lo pehle
cd /var/www/a-agent-base
cp app/services/booking_service.py app/services/booking_service.py.backup

# 3. Edit karo
nano app/services/booking_service.py

# Line 135 ke aas paas dekho aur ye code replace karo
# (Full modified code neeche diya hai)

# 4. Save karke restart
pm2 restart agentserver

# 5. Logs dekho
pm2 logs agentserver --lines 0
```

### Option 2: Git Pull (Agar commit push ho gaya)

```bash
ssh ubuntu@172.31.32.142
cd /var/www/a-agent-base
git pull origin fixes
pm2 restart agentserver
pm2 logs agentserver
```

---

## 📊 Ab Kya Dikhega Logs Mein

### ✅ Agar Token SAHI Hai:
```
================================================================================
🚀 CALLING BOOKING API
================================================================================
📍 URL: https://test.bookly.ae:2087/booking/createBooking
📦 PAYLOAD: {...}
🔐 AUTH HEADERS PROVIDED: True           ← Headers mil gaye!
🔑 AUTH HEADERS KEYS: ['x-auth-token', 'x-auth-language', 'x-user-type']
   x-auth-language: English
   x-user-type: User
   x-auth-token: eyJhbGciOiJIUzI1NiIsI... (length=234)  ← Token hai!
================================================================================
📥 RESPONSE RECEIVED
   Status Code: 200                      ← SUCCESS!
   Response: {"error":false,"results":{"booking":{...}}}
✅ BOOKING API SUCCESS
```

### ❌ Agar Token MISSING Hai:
```
================================================================================
🚀 CALLING BOOKING API
================================================================================
📍 URL: https://test.bookly.ae:2087/booking/createBooking
📦 PAYLOAD: {...}
🔐 AUTH HEADERS PROVIDED: False          ← Headers nahi mile!
❌ NO AUTH HEADERS! API will return 401  ← Clear warning!
================================================================================
📥 RESPONSE RECEIVED
   Status Code: 401
   Response: {"error":true,"message":"Access Denied. No token provided."}
❌ BOOKING API HTTP ERROR
```

---

## 💯 Is Se Kya Pata Chalega

1. **Auth headers mil rahe hain ya nahi?**
   - `🔐 AUTH HEADERS PROVIDED: True/False`

2. **Agar mil rahe hain toh keys kya hain?**
   - `🔑 AUTH HEADERS KEYS: [...]`

3. **Token ka value kya hai?**
   - `x-auth-token: eyJxxx... (length=234)`

4. **Backend API ka response kya hai?**
   - `📥 RESPONSE RECEIVED`
   - `Status Code: 401/200`
   - Full response text

5. **Exactly kaunsa error aaya?**
   - `❌ BOOKING API HTTP ERROR`
   - Complete details

---

## 🎯 Test Kaise Karein

```bash
# 1. Server pe code deploy karo
ssh ubuntu@172.31.32.142
cd /var/www/a-agent-base
git pull origin fixes  # Ya manual copy karo
pm2 restart agentserver

# 2. Logs start karo (Real-time)
pm2 logs agentserver --lines 0

# 3. App mein booking karo
# - Login karo
# - Service select karo
# - Pay Now tak jao
# - Confirm karo

# 4. Logs mein turant dikhega:
# 🚀 CALLING BOOKING API
# 🔐 AUTH HEADERS PROVIDED: ???
# ❌ ya ✅
```

---

## 🔧 Modified Code (Manual Copy Ke Liye)

File: `app/services/booking_service.py`
Location: Line ~135

```python
# Make the API call
logger.info("=" * 80)
logger.info("🚀 CALLING BOOKING API")
logger.info("=" * 80)
logger.info("📍 URL: %s", settings.booking_create_api_url)
logger.info("📦 PAYLOAD: %s", payload)
logger.info("🔐 AUTH HEADERS PROVIDED: %s", bool(auth_headers))
if auth_headers:
    logger.info("🔑 AUTH HEADERS KEYS: %s", list(auth_headers.keys()))
    for key, value in auth_headers.items():
        if key == "x-auth-token" and value:
            logger.info("   %s: %s... (length=%d)", key, value[:20] if len(value) > 20 else value, len(value))
        else:
            logger.info("   %s: %s", key, value)
else:
    logger.error("❌ NO AUTH HEADERS! API will return 401")
logger.info("=" * 80)

try:
    with httpx.Client(timeout=settings.booking_api_timeout_seconds, verify=settings.booking_api_verify_ssl) as client:
        response = client.post(settings.booking_create_api_url, json=payload, headers=auth_headers or {})
        
        logger.info("📥 RESPONSE RECEIVED")
        logger.info("   Status Code: %s", response.status_code)
        logger.info("   Response: %s", response.text[:500])
        
        response.raise_for_status()
        result = response.json()
        
        logger.info("✅ BOOKING API SUCCESS")
        logger.info("=" * 80)
except httpx.TimeoutException as exc:
    logger.error("⏱️ BOOKING API TIMEOUT")
    logger.error("=" * 80)
    raise RuntimeError("Booking request timed out; verify booking status before retrying.") from exc
except httpx.HTTPStatusError as exc:
    logger.error("❌ BOOKING API HTTP ERROR")
    logger.error("   Status: %s", exc.response.status_code)
    logger.error("   Response: %s", exc.response.text[:500])
    logger.error("=" * 80)
    raise RuntimeError(f"Booking API returned HTTP {exc.response.status_code}: {exc.response.text[:500]}") from exc
except httpx.RequestError as exc:
    logger.error("❌ BOOKING API REQUEST ERROR")
    logger.error("   Error: %s", str(exc))
    logger.error("=" * 80)
    raise RuntimeError(f"Booking API request failed: {exc}") from exc
except ValueError as exc:
    logger.error("❌ BOOKING API INVALID JSON")
    logger.error("=" * 80)
    raise RuntimeError("Booking API returned invalid JSON.") from exc
```

---

## ✅ Success Criteria

After deployment, ek booking test karne ke baad logs mein **pakka dikhna chahiye:**

1. `🚀 CALLING BOOKING API` - API call start hua
2. `🔐 AUTH HEADERS PROVIDED: True/False` - Headers status
3. `🔑 AUTH HEADERS KEYS: [...]` - Exactly kaunsi keys hai
4. `x-auth-token: xxx... (length=N)` - Token ka value aur length
5. `📥 RESPONSE RECEIVED` - Response aaya
6. `Status Code: 401/200` - Exact status code

**Isse 100% confirm ho jayega ki token aa raha hai ya nahi!** 🎯

---

**Deploy karo aur ek test booking karo - logs clear answer denge!** 💯
