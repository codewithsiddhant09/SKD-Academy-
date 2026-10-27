# ✅ Pre-Deployment Checklist

Use this checklist before deploying to production.

## 📋 Quick Checklist

### 1. Environment Configuration
- [ ] Copy `.env.production.example` to `.env.production`
- [ ] Set `ZIINA_API_KEY` (production key)
- [ ] Set `WHATSAPP_BOOKING_SECRET` (strong random string)
- [ ] Set `BOOKLY_API_TOKEN` (production token)
- [ ] Set `OPENAI_API_KEY` (if using AI features)
- [ ] Set `MONGODB_URI` (production database)
- [ ] Update `PAYMENT_RESULT_BASE_URL` to your domain
- [ ] Verify `BOOKING_TIMEZONE=Asia/Dubai`
- [ ] Set `ZIINA_TEST_MODE=false`
- [ ] Set `ZIINA_REFUND_MOCK=false`
- [ ] Set `LOG_LEVEL=INFO`

### 2. Security
- [ ] Generated strong `WHATSAPP_BOOKING_SECRET` (32+ characters)
- [ ] All secrets stored securely (not in Git)
- [ ] `.env.production` added to `.gitignore`
- [ ] SSL certificate ready for HTTPS
- [ ] Firewall rules configured

### 3. External Services
- [ ] Ziina account created and verified
- [ ] Ziina production API key obtained
- [ ] Bookly backend API accessible from server
- [ ] MongoDB production instance ready
- [ ] Domain name pointed to server

### 4. Code Quality
- [ ] All tests passing
- [ ] No critical errors in logs
- [ ] Code reviewed
- [ ] Dependencies up to date
- [ ] Git committed and pushed

### 5. Testing
- [ ] Tested PayAtStore booking locally
- [ ] Tested PayNow booking locally (with test mode)
- [ ] Tested WhatsApp booking locally
- [ ] Tested cancellation flow
- [ ] Tested refund process (mock mode)
- [ ] Verified payment result page renders

---

## 🚀 Quick Start Deployment

### Option 1: Docker (Fastest)

```bash
# 1. Ensure .env.production is configured
cp .env.production.example .env.production
nano .env.production  # Edit with your values

# 2. Build and run
docker-compose up -d

# 3. Check status
docker-compose ps
docker-compose logs -f bookly-agent

# 4. Test
curl http://localhost:8000/api/v1/health
```

### Option 2: Manual Server

```bash
# 1. On your server
git clone <your-repo> /opt/bookly-agent
cd /opt/bookly-agent

# 2. Setup environment
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.production.example .env.production
nano .env.production  # Edit with your values

# 4. Run deployment script
chmod +x deploy.sh
sudo ./deploy.sh production

# 5. Verify
sudo systemctl status bookly-agent
curl http://localhost:8000/api/v1/health
```

---

## 📝 Essential Environment Variables

**Must Configure (No Defaults):**
```bash
ZIINA_API_KEY=pk_prod_xxxxxxxxxxxxx
WHATSAPP_BOOKING_SECRET=your_random_32_char_secret_here
BOOKLY_API_TOKEN=your_bookly_production_token
OPENAI_API_KEY=sk-xxxxxxxxxxxxx  # If using AI
MONGODB_URI=mongodb://user:pass@host:27017/bookly
PAYMENT_RESULT_BASE_URL=https://your-domain.com/payment/paymentResult
```

**Important Settings:**
```bash
BOOKING_TIMEZONE=Asia/Dubai
ZIINA_TEST_MODE=false
ZIINA_REFUND_MOCK=false
FREE_CANCELLATION_HOURS=2
CANCELLATION_FEE_AED=10
PAYMENT_HOLD_MINUTES=10
LOG_LEVEL=INFO
```

---

## 🧪 Quick Test Commands

After deployment, test these endpoints:

### 1. Health Check
```bash
curl https://your-domain.com/api/v1/health
# Should return: {"status": "healthy"}
```

### 2. API Documentation
```bash
curl https://your-domain.com/docs
# Should return HTML with API docs
```

### 3. Payment Result Page
```bash
curl https://your-domain.com/payment/paymentResult?result=success
# Should return HTML payment result page
```

### 4. Create Test Booking (PayAtStore)
```bash
curl -X POST https://your-domain.com/api/v1/booking/book-appointment \
  -H "Content-Type: application/json" \
  -H "x-auth-token: YOUR_TOKEN" \
  -d '{
    "vendorId": "TEST_VENDOR",
    "serviceId": ["TEST_SERVICE"],
    "date": "2024-02-01",
    "slot": "02:00 PM",
    "payOption": "PayAtStore"
  }'
```

---

## 🔍 Post-Deployment Verification

### Check Service Status
```bash
# With systemd
sudo systemctl status bookly-agent

# With Docker
docker-compose ps
```

### Check Logs
```bash
# With systemd
sudo journalctl -u bookly-agent -f

# With Docker
docker-compose logs -f bookly-agent
```

### Monitor Resources
```bash
# CPU and Memory
htop

# Disk space
df -h

# Network connections
netstat -tulpn | grep 8000
```

---

## ⚠️ Common Issues

### Issue: Service won't start
**Check:**
- Missing environment variables
- Port 8000 already in use
- Database connection failed
- Python version < 3.10

**Fix:**
```bash
# Check logs
sudo journalctl -u bookly-agent -n 50

# Verify environment
source venv/bin/activate
python --version  # Should be 3.10+
```

### Issue: Payment link creation fails
**Check:**
- `ZIINA_API_KEY` is production key (not test)
- `ZIINA_TEST_MODE=false`
- Ziina API accessible from server

**Fix:**
```bash
# Test Ziina connectivity
curl -H "Authorization: Bearer $ZIINA_API_KEY" https://api.ziina.com/v1/ping
```

### Issue: WhatsApp booking returns 401
**Check:**
- `WHATSAPP_BOOKING_SECRET` is set
- Header `x-whatsapp-booking-key` matches secret

**Fix:**
```bash
# Verify secret is set
grep WHATSAPP_BOOKING_SECRET .env.production
```

---

## 📊 Monitoring Setup

### 1. Setup Log Alerts
```bash
# Add to crontab
*/5 * * * * grep "ERROR" /var/log/bookly-agent/app.log | tail -n 1 | mail -s "App Error" admin@example.com
```

### 2. Setup Health Check Monitoring
```bash
# Add to crontab
*/5 * * * * curl -f https://your-domain.com/api/v1/health || echo "Service down!" | mail -s "Alert: Service Down" admin@example.com
```

### 3. Monitor Payment Success Rate
```bash
# Daily report at 9 AM
0 9 * * * grep "Payment" /var/log/bookly-agent/app.log | grep -c "success"
```

---

## 🔐 Security Hardening

### 1. Firewall Setup
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

### 2. SSL Certificate
```bash
sudo certbot --nginx -d your-domain.com
```

### 3. Fail2ban (Brute Force Protection)
```bash
sudo apt-get install fail2ban
sudo systemctl enable fail2ban
```

---

## 📞 Support Contacts

- **Ziina Support**: support@ziina.com
- **Bookly Backend**: backend-team@bookly.ae
- **Emergency**: your-emergency-contact

---

## ✅ Deployment Complete

When all checks pass:

✅ Service running  
✅ Health check returns 200  
✅ API docs accessible  
✅ Test booking successful  
✅ Logs show no errors  
✅ SSL certificate valid  
✅ Monitoring enabled  

**🎉 Ready for production!**

---

**Deployment Date**: __________  
**Deployed By**: __________  
**Server**: __________  
**Version**: 1.0.0

---

For detailed deployment guide, see `DEPLOYMENT_GUIDE.md`  
For feature documentation, see `docs/BOOKING_FEATURES.md`
