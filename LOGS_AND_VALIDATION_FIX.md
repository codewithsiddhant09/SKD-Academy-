# Logs and Validation Fix

## Root Cause Analysis

### The Problem
User reported: "Again and again it will ask for address and zip code after i will confirm that it again ask. Why it can not will give payment link, unfortunetly my booking was not created."

### Investigation Results

When user provides partial contact info like: **"P4 1203 prateek grand noida 208013"**

The AI calls `save_booking_contact` and saves:
- ✅ address = "P4 1203 prateek grand noida"
- ✅ zip_code = "208013"
- ❌ **Missing: email, phone, country_code**

Then when AI calls `confirm_booking`, the validation at **lines 789-799** checks:

```python
# For app bookings: ALWAYS REQUIRED
required = {
    "contact_name": contact_name,
    "email": email,              # ❌ Not saved
    "country code": country_code, # ❌ Not saved
    "phone number": phone,        # ❌ Not saved
    "address": address,           # ✅ Saved
}
```

**Result**: Validation fails → Error returned → Booking NOT created

### Why This Happens

1. **User profile may not have email/phone** - The code tries to read from `profile.email`, `profile.phone_number`, `profile.country_code` (line 764-767), but if user's profile is incomplete, these return `None`

2. **AI only saves partial info** - When user says "P4 1203 prateek grand noida 208013", the AI only extracts address and zip, not realizing email/phone/country_code are also required

3. **No clear error message** - The error says "Before submitting, please provide: email, country code, phone number" but doesn't mention the save_booking_contact tool

## Solution Implemented

### 1. Added Comprehensive Logging

**In `confirm_booking` function (starting line 695):**
```python
logger.info("=== CONFIRM_BOOKING CALLED ===")
logger.info("Session booking_contact: %s", session.booking_contact)
logger.info("Session booking_type: %s", session.booking_type)
logger.info("Session payment_option: %s", session.payment_option)
logger.info("Session booking_platform: %s", session.booking_platform)
```

**When validation fails (line 801):**
```python
logger.warning("MISSING_CONTACT_INFO: %s", missing_contact)
logger.info("Contact values: name=%s, email=%s, country_code=%s, phone=%s, address=%s, city=%s, zip=%s", 
           contact_name, email, country_code, phone, address, city, zip_code)
```

**Before API call (line 823):**
```python
logger.info("BOOKING_PAYLOAD: %s", booking_payload)
```

**In `save_booking_contact` function (line 633):**
```python
logger.info("=== SAVE_BOOKING_CONTACT CALLED ===")
logger.info("Args: address=%s, city=%s, zip_code=%s, contact_name=%s, email=%s, phone=%s, country_code=%s", 
           args.address, args.city, args.zip_code, args.contact_name, args.email, args.phone_number, args.country_code)
logger.info("SAVED contact fields: %s", list(updates.keys()))
logger.info("Session booking_contact after save: %s", session.booking_contact)
```

### 2. Updated System Prompt (assistant.py)

**OLD prompt:**
```
After payment option is selected, collect contact information:
- For Salon Visit: name, email, phone, country code, address
- For Home Service: name, email, phone, country code, address, city, zip code

When customer provides contact details in the conversation, immediately call save_booking_contact
to save them before calling confirm_booking.
```

**NEW prompt:**
```
After payment option is selected, collect contact information:
- For BOTH Salon Visit and Home Service, ALWAYS ask for and save:
  * Full name
  * Email address
  * Phone number with country code (e.g., +971 for UAE)
  * Address
- For Home Service ONLY, also ask for:
  * City
  * Zip code / Postal code

When customer provides contact details in the conversation:
1. Parse all information from their message (name, email, phone, country code, address, city, zip)
2. Immediately call save_booking_contact with ALL provided information
3. Check which fields are still missing
4. Ask for any missing required fields
5. Only call confirm_booking after ALL required fields are collected

IMPORTANT: Do NOT assume contact info from user profile. Always ask explicitly if not provided.
```

### 3. Updated Error Message

**Changed in tools.py line 803:**
```python
# OLD:
return {"error": "Before submitting, please provide: " + ", ".join(missing_contact) + ". Save these using PATCH /session/{session_id}/booking-contact, then explicitly confirm the booking again."}

# NEW:
return {"error": "Before submitting, please provide: " + ", ".join(missing_contact) + ". Save these using save_booking_contact tool, then explicitly confirm the booking again."}
```

## Expected Behavior After Fix

### Test Scenario 1: Salon Visit (User with no profile data)
1. User selects service, time
2. AI asks: "Salon or Home?"
3. User: "Salon"
4. AI asks: "Individual or Group?"
5. User: "Individual"
6. AI asks: "Pay Now or Pay at Store?"
7. User: "Pay Now"
8. **AI asks: "Please provide your full name, email, phone (with country code), and address"**
9. User: "John Doe, john@example.com, +971 50 123 4567, P4 1203 prateek grand noida"
10. **AI calls: `save_booking_contact(contact_name="John Doe", email="john@example.com", country_code="+971", phone_number="50 123 4567", address="P4 1203 prateek grand noida")`**
11. ✅ All required fields saved
12. AI calls `confirm_booking`
13. ✅ Validation passes
14. ✅ Booking created
15. ✅ Payment link shown

### Test Scenario 2: Home Service (User provides partial info)
1. User selects service, time
2. AI asks: "Salon or Home?"
3. User: "Home Service"
4. AI asks: "Individual or Group?"
5. User: "Individual"
6. AI asks: "Pay Now or Pay at Store?"
7. User: "Pay at Store"
8. **AI asks: "Please provide your full name, email, phone (with country code), full address, city, and zip code"**
9. User: "P4 1203 prateek grand noida 208013"
10. **AI calls: `save_booking_contact(address="P4 1203 prateek grand", city="noida", zip_code="208013")`**
11. **AI checks what's missing: name, email, phone, country_code**
12. **AI asks: "Thank you! I still need your full name, email address, and phone number with country code"**
13. User: "Raj Kumar, raj@gmail.com, +971 55 999 8888"
14. **AI calls: `save_booking_contact(contact_name="Raj Kumar", email="raj@gmail.com", country_code="+971", phone_number="55 999 8888")`**
15. ✅ All required fields saved
16. AI calls `confirm_booking`
17. ✅ Validation passes
18. ✅ Booking created immediately

## Log Patterns to Look For

### Successful Flow:
```
INFO === SAVE_BOOKING_CONTACT CALLED ===
INFO Args: address=P4 1203, city=noida, zip_code=208013, contact_name=John, email=john@example.com, phone=50123456, country_code=+971
INFO SAVED contact fields: ['address', 'city', 'zip_code', 'contact_name', 'email', 'phone_number', 'country_code']
INFO Session booking_contact after save: {'address': 'P4 1203', 'city': 'noida', 'zip_code': '208013', 'contact_name': 'John', 'email': 'john@example.com', 'phone_number': '50123456', 'country_code': '+971', 'booking_appointment': 'Home'}
INFO === CONFIRM_BOOKING CALLED ===
INFO Session booking_contact: {'address': 'P4 1203', ...}
INFO Session booking_type: Individual
INFO Session payment_option: Pay Now
INFO BOOKING_PAYLOAD: {'vendorId': '...', 'serviceId': [...], 'payOption': 'PayNow', ...}
INFO Booking created: {'_id': '...', 'orderId': '...', 'paymentUrl': '...'}
```

### Failed Validation (Missing Fields):
```
INFO === CONFIRM_BOOKING CALLED ===
INFO Session booking_contact: {'address': 'P4 1203', 'zip_code': '208013'}
WARNING MISSING_CONTACT_INFO: ['contact name', 'email', 'country code', 'phone number']
INFO Contact values: name=None, email=None, country_code=None, phone=None, address=P4 1203, city=None, zip=208013
```

### API Call Failure:
```
INFO BOOKING_PAYLOAD: {...}
WARNING BOOKING_API_FAILED: Connection error / Timeout / Invalid response
```

## Files Modified

1. **app/agent/tools.py**
   - Added logging to `run_confirm_booking` (lines 695-701)
   - Added logging to contact validation (lines 801-804)
   - Added logging before API call (line 823)
   - Added logging to `run_save_booking_contact` (lines 633-636, 658-659)
   - Updated error message to mention `save_booking_contact` tool (line 803)

2. **app/agent/assistant.py**
   - Updated system prompt to clarify ALL required fields for Salon vs Home
   - Added step-by-step instructions for AI to collect contact info
   - Added instruction to NOT assume from profile, always ask explicitly

## Deployment Instructions

### 1. Commit and Push
```bash
cd a-agent-base
git add app/agent/tools.py app/agent/assistant.py
git commit -m "Add comprehensive logging and fix contact info validation flow"
git push origin fixes
```

### 2. Deploy on Server
```bash
ssh ubuntu@172.31.32.142
cd /var/www/a-agent-base
git pull origin fixes
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
pm2 restart agentserver
```

### 3. Monitor Logs
```bash
# Real-time logs
pm2 logs agentserver --lines 100

# Filter for contact info flow
pm2 logs agentserver | grep -E "SAVE_BOOKING_CONTACT|CONFIRM_BOOKING|MISSING_CONTACT"

# Check for API failures
pm2 logs agentserver | grep "BOOKING_API_FAILED"
```

### 4. Test Flow
Open the app and test:
1. Start booking
2. Choose "Home Service"
3. Choose "Individual"
4. Choose "Pay Now"
5. Provide partial info: "P4 1203 prateek grand noida 208013"
6. **Check logs** - should see save_booking_contact called
7. AI should ask for remaining info (name, email, phone)
8. Provide: "John Doe, john@test.com, +971 50 123 4567"
9. **Check logs** - should see second save_booking_contact call
10. **Check logs** - should see CONFIRM_BOOKING without MISSING_CONTACT_INFO warning
11. ✅ Booking should be created with payment link

## Troubleshooting Guide

### Issue: AI still asks repeatedly for same info
**Check logs for:**
```bash
pm2 logs agentserver | grep "SAVE_BOOKING_CONTACT"
```
- If tool is NOT being called → AI prompt issue
- If tool IS being called but fields empty → Parsing issue

### Issue: Booking fails with "missing contact"
**Check logs for:**
```bash
pm2 logs agentserver | grep "MISSING_CONTACT_INFO"
```
Look at the contact values line to see which specific fields are None

### Issue: API call fails
**Check logs for:**
```bash
pm2 logs agentserver | grep -A5 "BOOKING_PAYLOAD"
```
Verify the payload has all required fields properly formatted

---

**Created**: 2024-10-27
**Status**: Ready for deployment
**Priority**: HIGH - Blocks booking creation
