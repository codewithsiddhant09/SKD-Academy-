# Setup Checklist - Booking Features

Use this checklist to ensure all booking features are properly configured and working.

## ✅ Installation

- [ ] Python 3.10+ installed
- [ ] Virtual environment created (`python -m venv venv`)
- [ ] Virtual environment activated
- [ ] Dependencies installed (`pip install -r requirements.txt`)

## ✅ Configuration

### Environment Variables (.env)

Copy `.env.example` to `.env` and configure:

#### Required Variables
- [ ] `OPENAI_API_KEY` - For AI chatbot (if using)
- [ ] `ZIINA_API_KEY` - For payment processing (get from Ziina dashboard)
- [ ] `WHATSAPP_BOOKING_SECRET` - Secret for WhatsApp booking authentication
- [ ] `BOOKLY_API_TOKEN` - Token for Bookly backend API

#### Optional Variables (with defaults)
- [ ] `BOOKING_TIMEZONE` (default: Asia/Dubai)
- [ ] `FREE_CANCELLATION_HOURS` (default: 2)
- [ ] `CANCELLATION_FEE_AED` (default: 10)
- [ ] `CANCELLATION_FEE_PERCENTAGE` (default: 0)
- [ ] `PAYMENT_HOLD_MINUTES` (default: 10)
- [ ] `PAYMENT_RESULT_BASE_URL` (default: http://localhost:8000/payment/paymentResult)

#### Development/Testing
- [ ] `ZIINA_TEST_MODE` - Set to `true` for testing
- [ ] `ZIINA_REFUND_MOCK` - Set to `true` to mock refunds in dev
- [ ] `LOG_LEVEL` - Set to `DEBUG` for detailed logs

## ✅ Files Created

### Utility Modules (app/utils/)
- [ ] `cancellation_policy.py` - 2-hour rule implementation
- [ ] `guest_booking_link.py` - WhatsApp phone matching
- [ ] `timezone.py` - Timezone-aware slot parsing
- [ ] `booking_payment.py` - Ziina payment integration

### Service Modules (app/services/)
- [ ] `booking_cron.py` - Payment hold expiry handler
- [ ] `notification_service.py` - Multi-channel notifications

### API Routes (app/api/routes/)
- [ ] `payment.py` - Payment result page and confirmation

### Localization (app/locales/)
- [ ] `en.json` - English messages
- [ ] `ar.json` - Arabic messages

### Documentation (docs/)
- [ ] `BOOKING_FEATURES.md` - Complete feature documentation
- [ ] `QUICK_START.md` - Quick setup guide

## ✅ Files Modified

- [ ] `app/core/config.py` - Added booking configuration
- [ ] `app/services/booking_service.py` - Enhanced with new features
- [ ] `app/api/routes/booking.py` - Made async, added validations
- [ ] `app/api/router.py` - Registered payment routes
- [ ] `.env.example` - Added new environment variables
- [ ] `requirements.txt` - Added tzdata for timezone support

## ✅ Testing

### Basic Functionality
- [ ] Server starts without errors (`uvicorn app.main:app --reload`)
- [ ] API docs accessible at http://localhost:8000/docs
- [ ] Payment result page accessible at http://localhost:8000/payment/paymentResult

### PayAtStore Booking
- [ ] Can create PayAtStore booking
- [ ] Booking status is "Approved" immediately
- [ ] No payment link generated

### PayNow Booking
- [ ] Can create PayNow booking
- [ ] Booking status is "Pending"
- [ ] Payment link generated successfully
- [ ] Payment link redirects to Ziina (or test page)

### Cancellation
- [ ] Can get cancellation quote
- [ ] Quote shows correct fee based on time
- [ ] Free cancellation > 2 hours before appointment
- [ ] Fee applied < 2 hours before appointment
- [ ] Cannot cancel after appointment start

### WhatsApp Booking
- [ ] Can create WhatsApp booking with secret
- [ ] 401 error without correct secret
- [ ] Phone number normalized correctly
- [ ] Guest booking created if user not found

### Payment Confirmation
- [ ] Payment result page shows success message
- [ ] Payment confirmation updates booking status
- [ ] Idempotent (can call multiple times safely)

### Refund Processing
- [ ] Cancellation processes refund for paid bookings
- [ ] Refund amount correct (paid - fee)
- [ ] Cancellation fee transaction created
- [ ] Mock mode works in development

## ✅ Integration

### External Services
- [ ] Ziina API credentials configured
- [ ] Ziina test mode working
- [ ] Bookly backend API accessible

### Notifications (Optional)
- [ ] Push notification service configured (FCM)
- [ ] Email service configured (SendGrid/SES)
- [ ] WhatsApp Business API configured
- [ ] SMS service configured (Twilio/SNS)

### Database (Optional)
- [ ] MongoDB configured for user matching
- [ ] Booking repository methods implemented
- [ ] Transaction tracking set up

### Cron Service (Optional)
- [ ] BookingCronService started on app startup
- [ ] Payment hold expiry running every minute
- [ ] Old unpaid bookings being cancelled

## ✅ Production Readiness

### Security
- [ ] WHATSAPP_BOOKING_SECRET is strong and secure
- [ ] ZIINA_API_KEY is production key (not test)
- [ ] API tokens rotated regularly
- [ ] HTTPS enabled
- [ ] CORS configured correctly

### Configuration
- [ ] BOOKING_TIMEZONE set to production timezone (Asia/Dubai)
- [ ] ZIINA_TEST_MODE set to `false`
- [ ] ZIINA_REFUND_MOCK set to `false`
- [ ] PAYMENT_RESULT_BASE_URL set to production URL
- [ ] LOG_LEVEL set to `INFO` or `WARNING`

### Monitoring
- [ ] Logging configured
- [ ] Error tracking set up (Sentry)
- [ ] Payment tracking dashboard
- [ ] Refund monitoring
- [ ] Cron job monitoring

### Documentation
- [ ] Team trained on new features
- [ ] API documentation shared
- [ ] Support procedures documented
- [ ] Rollback plan prepared

## ✅ Deployment

### Pre-Deployment
- [ ] All tests passing
- [ ] Code reviewed
- [ ] Environment variables configured in production
- [ ] Database migrations run (if applicable)
- [ ] Backup procedures verified

### Deployment
- [ ] Application deployed
- [ ] Health checks passing
- [ ] Payment endpoints accessible
- [ ] Ziina webhook configured (if applicable)
- [ ] Cron service running

### Post-Deployment
- [ ] Test booking created successfully
- [ ] Test cancellation processed successfully
- [ ] Payment flow tested end-to-end
- [ ] Refund tested (in test mode first)
- [ ] Monitoring dashboards showing data
- [ ] No errors in logs

## ✅ Documentation Review

- [ ] Read `BOOKING_FEATURES.md` completely
- [ ] Understand all workflows
- [ ] Know how to test each feature
- [ ] Understand must-keep rules
- [ ] Know troubleshooting steps

## 🚀 Ready for Production

Once all items are checked:

1. ✅ All features implemented
2. ✅ All tests passing
3. ✅ All configurations correct
4. ✅ Production environment ready
5. ✅ Team trained
6. ✅ Monitoring in place

---

## Quick Commands Reference

### Start Server
```bash
uvicorn app.main:app --reload --port 8000
```

### Test PayAtStore Booking
```bash
curl -X POST http://localhost:8000/api/v1/booking/book-appointment \
  -H "Content-Type: application/json" \
  -H "x-auth-token: YOUR_TOKEN" \
  -d '{"vendorId":"...","serviceId":["..."],"date":"2024-01-25","slot":"02:00 PM","payOption":"PayAtStore"}'
```

### Test Cancellation Quote
```bash
curl http://localhost:8000/api/v1/booking/bookings/ORDER_ID/cancellation-quote \
  -H "x-auth-token: YOUR_TOKEN"
```

### Check API Docs
```
http://localhost:8000/docs
```

---

**Last Updated**: January 2024
**Version**: 1.0.0

For support, refer to `docs/BOOKING_FEATURES.md` and `docs/QUICK_START.md`
