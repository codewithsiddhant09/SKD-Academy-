# 🚀 Deploy Now - Quick Reference

## Option 1: Docker (Recommended - 3 Commands)

```bash
# 1. Configure
cp .env.production.example .env.production
nano .env.production  # Add: ZIINA_API_KEY, WHATSAPP_BOOKING_SECRET, BOOKLY_API_TOKEN, MONGODB_URI

# 2. Deploy
docker-compose up -d

# 3. Verify
curl http://localhost:8000/api/v1/health
```

**Done! Service is running on port 8000**

---

## Option 2: Manual Server (1 Command)

```bash
# Configure .env.production first, then:
chmod +x deploy.sh && sudo ./deploy.sh production
```

**Done! Service is running as systemd service**

---

## Essential Config (.env.production)

**Must configure these 5:**
```bash
ZIINA_API_KEY=pk_prod_xxxxxxxxxxxxxxxxxxxxxxx
WHATSAPP_BOOKING_SECRET=your_32_char_random_secret_here
BOOKLY_API_TOKEN=your_bookly_token_here
MONGODB_URI=mongodb://user:pass@host:27017/bookly
PAYMENT_RESULT_BASE_URL=https://your-domain.com/payment/paymentResult
```

**Important settings:**
```bash
BOOKING_TIMEZONE=Asia/Dubai
ZIINA_TEST_MODE=false
ZIINA_REFUND_MOCK=false
```

---

## Quick Tests

```bash
# Health check
curl http://localhost:8000/api/v1/health

# API docs
open http://localhost:8000/docs

# Create test booking
curl -X POST http://localhost:8000/api/v1/booking/book-appointment \
  -H "Content-Type: application/json" \
  -H "x-auth-token: YOUR_TOKEN" \
  -d '{"vendorId":"xxx","serviceId":["xxx"],"date":"2024-02-01","slot":"02:00 PM","payOption":"PayAtStore"}'
```

---

## Monitor

**Docker:**
```bash
docker-compose ps
docker-compose logs -f bookly-agent
```

**Systemd:**
```bash
sudo systemctl status bookly-agent
sudo journalctl -u bookly-agent -f
```

---

## Common Issues

❌ **Service won't start** → Check logs, verify .env.production  
❌ **Payment link fails** → Verify ZIINA_API_KEY is production key  
❌ **WhatsApp 401** → Check WHATSAPP_BOOKING_SECRET  

---

## Complete Guides

- **PRE_DEPLOYMENT_CHECKLIST.md** - Full checklist
- **DEPLOYMENT_GUIDE.md** - Complete manual
- **docs/BOOKING_FEATURES.md** - All features

---

✅ **Ready to deploy!**
