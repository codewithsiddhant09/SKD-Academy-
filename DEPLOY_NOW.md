# Quick Deployment Guide

## What Was Fixed

### Root Problem
AI was NOT collecting **email, phone, and country code** from users, only asking for address and zip. When trying to create booking, validation failed because these fields are ALWAYS required for app bookings.

### Solution
1. ✅ Added comprehensive logging to track exactly what's happening
2. ✅ Updated AI system prompt to ALWAYS ask for: name, email, phone (with country code), address
3. ✅ For Home Service, also ask for: city, zip code
4. ✅ AI must call `save_booking_contact` with ALL information before `confirm_booking`

## Deploy Commands (Copy-Paste)

### SSH into server and deploy:
```bash
ssh ubuntu@172.31.32.142
cd /var/www/a-agent-base
git pull origin fixes
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
pm2 restart agentserver
pm2 logs agentserver --lines 50
```

### Monitor logs in real-time:
```bash
pm2 logs agentserver
```

### Filter for contact info logs:
```bash
pm2 logs agentserver | grep -E "SAVE_BOOKING|CONFIRM_BOOKING|MISSING_CONTACT"
```

## What to Look For in Logs

### ✅ SUCCESS - Contact info saved properly:
```
INFO === SAVE_BOOKING_CONTACT CALLED ===
INFO Args: address=..., city=..., contact_name=John, email=john@example.com, phone=50123456, country_code=+971
INFO SAVED contact fields: ['address', 'city', 'zip_code', 'contact_name', 'email', 'phone_number', 'country_code']
INFO === CONFIRM_BOOKING CALLED ===
INFO BOOKING_PAYLOAD: {...}
INFO Booking created: {'_id': '...', 'orderId': '...'}
```

### ❌ FAIL - Missing contact info:
```
INFO === CONFIRM_BOOKING CALLED ===
WARNING MISSING_CONTACT_INFO: ['email', 'country code', 'phone number']
INFO Contact values: name=None, email=None, country_code=None, phone=None, address=P4 1203
```

## Test After Deployment

### Test Case 1: Salon Visit
1. Start booking, select service & time
2. Choose: **"Visit Salon"**
3. Choose: **"Individual"**
4. Choose: **"Pay Now"**
5. AI should ask: **"Please provide your full name, email, phone number with country code, and address"**
6. Provide: **"John Doe, john@test.com, +971 50 123 4567, P4 1203 prateek grand noida"**
7. ✅ AI should call `save_booking_contact` with ALL info
8. ✅ AI should call `confirm_booking`
9. ✅ Booking created + payment link shown

### Test Case 2: Home Service (Partial info provided)
1. Start booking, select service & time
2. Choose: **"Home Service"**
3. Choose: **"Individual"**
4. Choose: **"Pay Now"**
5. AI should ask: **"Please provide your full name, email, phone (with country code), address, city, and zip code"**
6. User provides only: **"P4 1203 prateek grand noida 208013"** (missing name, email, phone)
7. ✅ AI calls `save_booking_contact(address="P4 1203 prateek grand", city="noida", zip_code="208013")`
8. ✅ AI asks: **"Thank you! I still need your full name, email address, and phone number"**
9. User provides: **"Raj Kumar, raj@gmail.com, +971 55 999 8888"**
10. ✅ AI calls `save_booking_contact(contact_name="Raj Kumar", email="raj@gmail.com", country_code="+971", phone_number="55999888")`
11. ✅ AI calls `confirm_booking`
12. ✅ Booking created + payment link shown

## Commits Included

```
a28b3c2 - Add comprehensive logging and fix contact validation - AI must collect email/phone/name for all bookings
a72bcc7 - Add save_booking_contact tool to fix repeated address/contact asking issue
5322964 - Fix syntax error: longitude missing .longitude attribute
```

## Files Changed

1. **app/agent/tools.py**
   - Added logging in `run_confirm_booking` to show session state
   - Added logging in `run_save_booking_contact` to show what was saved
   - Added logging before API call to show complete payload
   - Updated error message to mention `save_booking_contact` tool

2. **app/agent/assistant.py**
   - Updated system prompt with detailed contact info collection steps
   - Clarified that ALL bookings need: name, email, phone, country code, address
   - Added instruction to NOT assume from profile, ALWAYS ask explicitly

## Quick Check After Deployment

```bash
# Check service is running
pm2 status

# Check latest logs
pm2 logs agentserver --lines 50

# Test API is responding
curl http://localhost:5000/api/v1/health
```

## Rollback (if needed)

```bash
cd /var/www/a-agent-base
git log --oneline -5
git checkout 5322964  # Previous stable commit
pm2 restart agentserver
```

---

**Status**: Ready to deploy
**Priority**: HIGH - Critical fix for booking creation
**Impact**: Fixes repeated asking for contact info and booking creation failure
