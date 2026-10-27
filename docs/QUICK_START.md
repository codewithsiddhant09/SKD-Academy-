# Quick Start Guide - Booking Features

## Installation

1. **Install dependencies**:
```bash
pip install -r requirements.txt
```

2. **Configure environment variables**:
```bash
cp .env.example .env
```

Edit `.env` and add:
```bash
# Required
ZIINA_API_KEY=your_ziina_api_key_here
WHATSAPP_BOOKING_SECRET=your_secret_here
BOOKLY_API_TOKEN=your_bookly_token_here

# Optional (defaults shown)
BOOKING_TIMEZONE=Asia/Dubai
FREE_CANCELLATION_HOURS=2
CANCELLATION_FEE_AED=10
PAYMENT_HOLD_MINUTES=10
```

3. **Start the server**:
```bash
uvicorn app.main:app --reload --port 8000
```

## Quick Test

### 1. Test PayAtStore Booking

```bash
curl -X POST http://localhost:8000/api/v1/booking/book-appointment \
  -H "Content-Type: application/json" \
  -H "x-auth-token: YOUR_TOKEN" \
  -d '{
    "vendorId": "VENDOR_ID",
    "serviceId": ["SERVICE_ID"],
    "date": "2024-01-25",
    "slot": "02:00 PM",
    "payOption": "PayAtStore"
  }'
```

### 2. Test Cancellation Quote

```bash
curl http://localhost:8000/api/v1/booking/bookings/ORDER_ID/cancellation-quote \
  -H "x-auth-token: YOUR_TOKEN"
```

### 3. Test WhatsApp Booking

```bash
curl -X POST http://localhost:8000/api/v1/booking/book-appointment \
  -H "Content-Type: application/json" \
  -H "x-whatsapp-booking-key: YOUR_SECRET" \
  -d '{
    "mode": "whatsapp",
    "phoneNumber": "971501234567",
    "vendorId": "VENDOR_ID",
    "serviceId": ["SERVICE_ID"],
    "date": "2024-01-25",
    "slot": "02:00 PM"
  }'
```

## Features Checklist

- ✅ PayNow with Ziina integration
- ✅ PayAtStore immediate approval
- ✅ WhatsApp bookings with phone normalization
- ✅ 2-hour cancellation policy
- ✅ Automatic refund processing
- ✅ Payment hold expiry (cron)
- ✅ Multi-channel notifications
- ✅ English/Arabic localization
- ✅ Timezone-aware appointment parsing

## API Documentation

Visit http://localhost:8000/docs for interactive API documentation.

## Troubleshooting

### Payment link creation fails
- Check `ZIINA_API_KEY` is set correctly
- Verify `ZIINA_TEST_MODE` matches your API key type
- Check logs for detailed error message

### Cancellation fails with refund error
- Set `ZIINA_REFUND_MOCK=true` for development/testing
- In production, verify payment was completed before refunding
- Check Ziina dashboard for payment status

### WhatsApp booking returns 401
- Verify `WHATSAPP_BOOKING_SECRET` in .env
- Check header: `x-whatsapp-booking-key` matches secret

### Phone number format invalid
- Supported formats: 971501234567, +971501234567, 501234567
- System auto-detects country code (971, 91) or defaults to 971
- Leading zeros are stripped automatically

## Next Steps

- See [BOOKING_FEATURES.md](./BOOKING_FEATURES.md) for complete documentation
- Configure MongoDB for production user matching
- Set up actual notification services (FCM, SendGrid, WhatsApp Business API)
- Enable cron service for payment hold expiry
- Add transaction history endpoints

## Support

Check logs at: `./logs/` (configure LOG_LEVEL in .env)

For detailed workflows and specifications, refer to the main documentation.
