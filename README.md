# Bookly AI Appointment Chatbot

A production-grade conversational AI assistant for booking salon and beauty appointments with **complete payment integration**, built with FastAPI, LangChain, and OpenAI.

## ✨ Features

### 🎯 Complete Booking System
- **Multiple Payment Options**: PayNow (Ziina), PayAtStore, Legacy flow
- **WhatsApp Integration**: Direct bookings via WhatsApp with phone matching
- **Smart Cancellation**: 2-hour policy with automatic refund processing
- **Payment Management**: Automatic payment holds, verification, and refunds
- **Multi-channel Notifications**: Push, Email, WhatsApp, SMS (English & Arabic)

### 💳 Payment Features
- Ziina payment gateway integration
- Automatic payment link generation
- Payment verification and confirmation
- Refund processing with fee calculation
- Payment hold expiry (10-minute automatic cancellation)
- Beautiful payment result page

### 📱 WhatsApp Booking
- Phone number normalization (971, 91 country codes)
- Automatic user matching
- Guest booking creation
- Secure authentication
- Later booking linking after signup

### 🔄 Cancellation Policy
- 2-hour free cancellation window
- Automatic fee calculation (flat or percentage)
- Timezone-aware appointment parsing
- Automatic refund processing
- Fee split between admin and salon

### 🤖 AI Features
- Natural language booking assistant
- Salon recommendations
- Service discovery
- RAG-powered knowledge base
- Context-aware conversations

---

## 🚀 Quick Deployment

### Option 1: Docker (Recommended)

```bash
# Configure environment
cp .env.production.example .env.production
# Edit with your API keys

# Deploy full stack
docker-compose up -d

# Verify
curl http://localhost:8000/api/v1/health
```

### Option 2: Manual Server

```bash
# Deploy with one command
chmod +x deploy.sh
sudo ./deploy.sh production
```

---

## 📚 Documentation

- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Complete deployment instructions
- **[PRE_DEPLOYMENT_CHECKLIST.md](PRE_DEPLOYMENT_CHECKLIST.md)** - Pre-deployment checklist
- **[docs/BOOKING_FEATURES.md](docs/BOOKING_FEATURES.md)** - Complete feature documentation
- **[docs/QUICK_START.md](docs/QUICK_START.md)** - Local development guide
- **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** - Technical implementation details

---

## ⚙️ Configuration

Essential environment variables:

```bash
# Payment Gateway
ZIINA_API_KEY=pk_prod_your_key_here
ZIINA_TEST_MODE=false

# WhatsApp Integration
WHATSAPP_BOOKING_SECRET=your_32_char_secret

# Bookly Backend
BOOKLY_API_TOKEN=your_token_here

# Domain
PAYMENT_RESULT_BASE_URL=https://your-domain.com/payment/paymentResult

# Database
MONGODB_URI=mongodb://localhost:27017/bookly

# Timezone
BOOKING_TIMEZONE=Asia/Dubai
```

See `.env.production.example` for complete configuration.

---

## 🧪 Testing

```bash
# Health check
curl http://localhost:8000/api/v1/health

# API documentation
http://localhost:8000/docs

# Create test booking
curl -X POST http://localhost:8000/api/v1/booking/book-appointment \
  -H "Content-Type: application/json" \
  -H "x-auth-token: YOUR_TOKEN" \
  -d '{"vendorId":"...","serviceId":["..."],"date":"2024-02-01","slot":"02:00 PM","payOption":"PayAtStore"}'
```

---

## 🏗️ Architecture

```
app/
├── api/routes/          # API endpoints
│   ├── booking.py       # Booking endpoints
│   ├── payment.py       # Payment result & confirmation
│   └── ...
├── services/            # Business logic
│   ├── booking_service.py      # Main booking service
│   ├── booking_cron.py         # Payment hold expiry
│   └── notification_service.py # Multi-channel notifications
├── utils/               # Helper utilities
│   ├── booking_payment.py      # Ziina integration
│   ├── cancellation_policy.py  # 2-hour rule
│   ├── timezone.py             # Timezone handling
│   └── guest_booking_link.py   # WhatsApp user matching
└── locales/             # Translations (en, ar)
```

---

## 📊 API Endpoints

### Booking
- `POST /api/v1/booking/book-appointment` - Create booking
- `GET /api/v1/booking/bookings/{booking_id}` - View booking
- `GET /api/v1/booking/bookings/{order_id}/cancellation-quote` - Get cancellation quote
- `PUT /api/v1/booking/bookings/cancel` - Cancel booking with refund

### Payment
- `GET /api/v1/payment/paymentResult` - Payment result page (HTML)
- `POST /api/v1/payment/confirm-booking-payment` - Confirm payment

### AI Chat
- `POST /api/v1/chat` - Conversational booking assistant

---

## 🔐 Security

- ✅ Timing-safe secret comparison
- ✅ Atomic operations (race-condition safe)
- ✅ Idempotent payment confirmation
- ✅ Input validation with Pydantic
- ✅ HTTPS ready
- ✅ Rate limiting (Nginx)
- ✅ Non-root Docker containers

---

## 📈 Monitoring

### Health Checks
```bash
curl http://localhost:8000/api/v1/health
```

### Logs
```bash
# Systemd
sudo journalctl -u bookly-agent -f

# Docker
docker-compose logs -f bookly-agent
```

### Metrics to Monitor
- Payment success rate
- Refund processing time
- Cancellation rate
- Payment hold cancellations
- API response times

---

## 🛠️ Technology Stack

- **Framework**: FastAPI (async Python)
- **AI**: OpenAI GPT-4, LangChain
- **Database**: MongoDB
- **Vector Store**: ChromaDB
- **Payment**: Ziina Payment Gateway
- **Deployment**: Docker, Nginx
- **Language**: Python 3.10+

---

## 📦 Requirements

- Python 3.10+
- MongoDB 6.0+
- Docker & Docker Compose (for containerized deployment)
- Ziina API account
- OpenAI API key (for AI features)

---

## 🤝 Support

- Check logs: `sudo journalctl -u bookly-agent -f`
- Review documentation in `docs/`
- Test mode: Set `ZIINA_REFUND_MOCK=true` for development

---

## 📄 License

Copyright © 2024 Bookly. All rights reserved.

---

## 🎉 Status

✅ **Production Ready**  
✅ All booking features implemented  
✅ Payment integration complete  
✅ Docker deployment ready  
✅ Comprehensive documentation  
✅ Security hardened  

**Version**: 1.0.0  
**Last Updated**: January 2024

---

For detailed deployment instructions, see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
