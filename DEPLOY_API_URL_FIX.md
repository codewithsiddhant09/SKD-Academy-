# Deploy API URL Fix - URGENT

## Problem Found ✅
The logs showed: **`[Errno 111] Connection refused`**

The agent server could NOT connect to the old booking API:
- ❌ OLD: `http://15.252.235.83:2053`
- ✅ NEW: `https://test.bookly.ae:2087`

## What Was Changed
Updated `.env` file with new base URL for all booking API endpoints:
```env
BOOKING_CREATE_API_URL=https://test.bookly.ae:2087/booking/createBooking
BOOKING_PAYNOW_API_URL=https://test.bookly.ae:2087/booking/payNowBooking
BOOKING_VIEW_API_URL=https://test.bookly.ae:2087/booking/viewBooking
BOOKING_CANCELLATION_AMOUNT_API_URL=https://test.bookly.ae:2087/booking/getCancellationAmount
BOOKING_CANCEL_API_URL=https://test.bookly.ae:2087/booking/cancelBookingByUser
```

Changed from HTTP to HTTPS and new domain/port.

## Deployment Steps

### 1. SSH into server and pull changes
```bash
ssh ubuntu@172.31.32.142
cd /var/www/a-agent-base
git pull origin fixes
```

### 2. Update .env file on server
The .env file was updated locally, but you need to **manually update it on the server** because .env is typically in .gitignore:

```bash
# Edit .env on server
nano /var/www/a-agent-base/.env

# Find these lines and update them to:
BOOKING_CREATE_API_URL=https://test.bookly.ae:2087/booking/createBooking
BOOKING_PAYNOW_API_URL=https://test.bookly.ae:2087/booking/payNowBooking
BOOKING_VIEW_API_URL=https://test.bookly.ae:2087/booking/viewBooking
BOOKING_CANCELLATION_AMOUNT_API_URL=https://test.bookly.ae:2087/booking/getCancellationAmount
BOOKING_CANCEL_API_URL=https://test.bookly.ae:2087/booking/cancelBookingByUser

# Save: Ctrl+O, Enter, Ctrl+X
```

### 3. Restart the service
```bash
pm2 restart agentserver
```

### 4. Monitor logs
```bash
pm2 logs agentserver --lines 50
```

## Complete Copy-Paste Commands

```bash
ssh ubuntu@172.31.32.142
cd /var/www/a-agent-base
git pull origin fixes

# Update .env - Copy each line individually
sed -i 's|BOOKING_CREATE_API_URL=.*|BOOKING_CREATE_API_URL=https://test.bookly.ae:2087/booking/createBooking|' .env
sed -i 's|BOOKING_PAYNOW_API_URL=.*|BOOKING_PAYNOW_API_URL=https://test.bookly.ae:2087/booking/payNowBooking|' .env
sed -i 's|BOOKING_VIEW_API_URL=.*|BOOKING_VIEW_API_URL=https://test.bookly.ae:2087/booking/viewBooking|' .env
sed -i 's|BOOKING_CANCELLATION_AMOUNT_API_URL=.*|BOOKING_CANCELLATION_AMOUNT_API_URL=https://test.bookly.ae:2087/booking/getCancellationAmount|' .env
sed -i 's|BOOKING_CANCEL_API_URL=.*|BOOKING_CANCEL_API_URL=https://test.bookly.ae:2087/booking/cancelBookingByUser|' .env

# Verify changes
cat .env | grep BOOKING_CREATE

# Restart
pm2 restart agentserver

# Monitor logs
pm2 logs agentserver --lines 50
```

## Verification

### 1. Check .env is updated correctly:
```bash
cat /var/www/a-agent-base/.env | grep BOOKING_
```

Should show:
```
BOOKING_CREATE_API_URL=https://test.bookly.ae:2087/booking/createBooking
BOOKING_PAYNOW_API_URL=https://test.bookly.ae:2087/booking/payNowBooking
...
```

### 2. Test booking flow and check logs:
When user completes booking, logs should now show:
```
INFO BOOKING_PAYLOAD: {...}
INFO Booking created: {'_id': '...', 'orderId': '...', 'paymentUrl': '...'}
```

Instead of:
```
WARNING BOOKING_API_FAILED: [Errno 111] Connection refused
```

### 3. Test API connectivity:
```bash
# From agent server, test new API
curl -v https://test.bookly.ae:2087/booking/createBooking
```

Should NOT get "Connection refused" - should get response (even if it's an error about missing auth, that's fine).

## What This Fixes

✅ **[Errno 111] Connection refused** - Server can now reach booking API
✅ Bookings will be created successfully
✅ Payment links will be returned from API
✅ Users will receive booking confirmation with payment URL

## Expected Result After Deployment

User flow:
1. Completes booking details ✅
2. Provides contact info ✅
3. Confirms booking ✅
4. **API call succeeds** ✅ (was failing before)
5. **Booking created** ✅
6. **Payment link received** ✅
7. User sees payment link in chat ✅

## If Still Not Working

Check these:
1. **Is new API URL correct?** Test: `curl https://test.bookly.ae:2087/`
2. **Is SSL certificate valid?** If getting SSL errors, temporarily set: `BOOKING_API_VERIFY_SSL=false` (not recommended for production)
3. **Check PM2 logs** for any new errors

## Commit Details
```
Commit: f2dbd4d
Message: "Update booking API base URL to https://test.bookly.ae:2087"
Files: .env
```

---
**Status**: Ready to deploy
**Priority**: CRITICAL - Blocks all booking creation
**Impact**: Fixes "Connection refused" error, enables booking creation
