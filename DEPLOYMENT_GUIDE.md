# 🚀 Deployment Guide - Bookly Booking System

## Pre-Deployment Checklist

### ✅ Code Ready
- [ ] All code committed to Git
- [ ] All tests passing
- [ ] Code reviewed
- [ ] Documentation complete
- [ ] Dependencies updated

### ✅ Configuration
- [ ] Production `.env` file prepared
- [ ] All API keys obtained (Ziina, Bookly, OpenAI)
- [ ] Secrets generated (WhatsApp booking secret)
- [ ] Database connection tested
- [ ] Timezone verified (Asia/Dubai)

### ✅ External Services
- [ ] Ziina production API key ready
- [ ] Bookly backend API accessible
- [ ] MongoDB production instance ready
- [ ] Domain name configured
- [ ] SSL certificate obtained

---

## Deployment Options

Choose one of these deployment methods:

### Option 1: Docker Deployment (Recommended) ✨
### Option 2: Manual Server Deployment
### Option 3: Cloud Platform (AWS/Azure/GCP)

---

## Option 1: Docker Deployment (Recommended)

### Step 1: Build Docker Image

```bash
cd a-agent-base
docker build -t bookly-agent:latest .
```

### Step 2: Run Container

```bash
docker run -d \
  --name bookly-agent \
  -p 8000:8000 \
  --env-file .env.production \
  --restart unless-stopped \
  bookly-agent:latest
```

### Step 3: Verify Deployment

```bash
# Check container status
docker ps

# Check logs
docker logs bookly-agent

# Test health endpoint
curl http://localhost:8000/api/v1/health
```

### Step 4: Docker Compose (Multiple Services)

```bash
docker-compose up -d
```

---

## Option 2: Manual Server Deployment

### Step 1: Server Setup

```bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Python 3.10+
sudo apt-get install python3.10 python3.10-venv python3-pip -y

# Install nginx (reverse proxy)
sudo apt-get install nginx -y

# Install certbot (SSL)
sudo apt-get install certbot python3-certbot-nginx -y
```

### Step 2: Application Setup

```bash
# Create application directory
sudo mkdir -p /opt/bookly-agent
sudo chown $USER:$USER /opt/bookly-agent
cd /opt/bookly-agent

# Clone repository
git clone <your-repo-url> .

# Create virtual environment
python3.10 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Configure Environment

```bash
# Copy and configure production environment
cp .env.production.example .env.production
nano .env.production

# Set correct values:
# - ZIINA_API_KEY
# - WHATSAPP_BOOKING_SECRET
# - BOOKLY_API_TOKEN
# - MONGODB_URI
# - PAYMENT_RESULT_BASE_URL (your domain)
```

### Step 4: Setup Systemd Service

```bash
sudo nano /etc/systemd/system/bookly-agent.service
```

Paste this content:

```ini
[Unit]
Description=Bookly AI Agent Service
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/bookly-agent
Environment="PATH=/opt/bookly-agent/venv/bin"
EnvironmentFile=/opt/bookly-agent/.env.production
ExecStart=/opt/bookly-agent/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Step 5: Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable bookly-agent

# Start service
sudo systemctl start bookly-agent

# Check status
sudo systemctl status bookly-agent

# View logs
sudo journalctl -u bookly-agent -f
```

### Step 6: Configure Nginx

```bash
sudo nano /etc/nginx/sites-available/bookly-agent
```

Paste this configuration:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
    }

    # Increase max body size for file uploads
    client_max_body_size 10M;
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/bookly-agent /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Step 7: Setup SSL

```bash
sudo certbot --nginx -d your-domain.com
```

### Step 8: Setup Firewall

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## Option 3: Cloud Platform Deployment

### AWS (Elastic Beanstalk)

1. Install AWS CLI and EB CLI
2. Initialize EB application
3. Configure environment variables
4. Deploy

```bash
eb init -p python-3.10 bookly-agent
eb create production-env
eb setenv $(cat .env.production | xargs)
eb deploy
```

### Azure (App Service)

1. Install Azure CLI
2. Create App Service
3. Configure environment
4. Deploy

```bash
az webapp up --name bookly-agent --runtime "PYTHON:3.10"
az webapp config appsettings set --settings @.env.production
```

### Google Cloud (Cloud Run)

1. Build container
2. Push to Container Registry
3. Deploy to Cloud Run

```bash
gcloud builds submit --tag gcr.io/PROJECT-ID/bookly-agent
gcloud run deploy bookly-agent --image gcr.io/PROJECT-ID/bookly-agent --platform managed
```

---

## Post-Deployment Steps

### 1. Verify Deployment

```bash
# Check health endpoint
curl https://your-domain.com/api/v1/health

# Check API documentation
curl https://your-domain.com/docs

# Test payment result page
curl https://your-domain.com/payment/paymentResult?result=success
```

### 2. Test Critical Flows

#### Test PayAtStore Booking
```bash
curl -X POST https://your-domain.com/api/v1/booking/book-appointment \
  -H "Content-Type: application/json" \
  -H "x-auth-token: YOUR_TOKEN" \
  -d '{
    "vendorId": "TEST_VENDOR",
    "serviceId": ["TEST_SERVICE"],
    "date": "2024-01-30",
    "slot": "02:00 PM",
    "payOption": "PayAtStore"
  }'
```

#### Test WhatsApp Booking
```bash
curl -X POST https://your-domain.com/api/v1/booking/book-appointment \
  -H "Content-Type: application/json" \
  -H "x-whatsapp-booking-key: YOUR_SECRET" \
  -d '{
    "mode": "whatsapp",
    "phoneNumber": "971501234567",
    "vendorId": "TEST_VENDOR",
    "serviceId": ["TEST_SERVICE"],
    "date": "2024-01-30",
    "slot": "02:00 PM"
  }'
```

### 3. Setup Monitoring

#### Application Logs
```bash
# View logs
sudo journalctl -u bookly-agent -f

# Or with Docker
docker logs -f bookly-agent
```

#### Setup Log Rotation
```bash
sudo nano /etc/logrotate.d/bookly-agent
```

Content:
```
/var/log/bookly-agent/*.log {
    daily
    missingok
    rotate 14
    compress
    notifempty
    create 0640 www-data www-data
    sharedscripts
}
```

### 4. Setup Cron Job for Payment Holds

The BookingCronService should start automatically with the application. Verify it's running:

```bash
# Check logs for cron activity
grep "payment hold" /var/log/bookly-agent/app.log
```

### 5. Setup Backup

#### Database Backup (MongoDB)
```bash
# Add to crontab
crontab -e

# Backup daily at 2 AM
0 2 * * * mongodump --uri="$MONGODB_URI" --out=/backup/mongodb/$(date +\%Y\%m\%d)
```

#### Application Backup
```bash
# Backup configuration and code
0 3 * * * tar -czf /backup/app/bookly-$(date +\%Y\%m\%d).tar.gz /opt/bookly-agent
```

---

## Monitoring & Maintenance

### Health Checks

Setup automated health checks:

```bash
# Add to crontab
*/5 * * * * curl -f https://your-domain.com/api/v1/health || echo "Service down!" | mail -s "Alert: Bookly Service Down" admin@example.com
```

### Performance Monitoring

1. **Application Metrics**
   - Response times
   - Error rates
   - Active connections
   - Memory usage

2. **Payment Metrics**
   - Payment success rate
   - Refund processing time
   - Payment hold cancellations

3. **Booking Metrics**
   - Bookings created
   - Cancellations
   - WhatsApp bookings

### Log Monitoring

Important log patterns to monitor:

```bash
# Payment errors
grep "Payment.*failed" /var/log/bookly-agent/app.log

# Refund errors
grep "Refund.*failed" /var/log/bookly-agent/app.log

# Ziina API errors
grep "Ziina.*error" /var/log/bookly-agent/app.log

# Cron job activity
grep "payment hold" /var/log/bookly-agent/app.log
```

---

## Scaling

### Horizontal Scaling (Multiple Instances)

1. **Load Balancer Setup**
   - Use Nginx or cloud load balancer
   - Health check endpoint: `/api/v1/health`
   - Session stickiness not required (stateless)

2. **Database Scaling**
   - MongoDB replica set
   - Read replicas for read-heavy operations

3. **Caching**
   - Redis for session data
   - Categories cache (already implemented)

### Vertical Scaling (More Resources)

```bash
# Increase workers in systemd service
ExecStart=/opt/bookly-agent/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 8
```

---

## Rollback Procedure

### Quick Rollback

```bash
# Stop service
sudo systemctl stop bookly-agent

# Restore previous version
cd /opt/bookly-agent
git checkout <previous-commit>

# Restart service
sudo systemctl start bookly-agent
```

### With Docker

```bash
# Stop current container
docker stop bookly-agent
docker rm bookly-agent

# Run previous image
docker run -d \
  --name bookly-agent \
  -p 8000:8000 \
  --env-file .env.production \
  bookly-agent:previous
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check service status
sudo systemctl status bookly-agent

# Check logs
sudo journalctl -u bookly-agent -n 100

# Common issues:
# - Missing environment variables
# - Port already in use
# - Permission issues
# - Database connection failed
```

### Payment Issues

```bash
# Check Ziina configuration
echo $ZIINA_API_KEY
echo $ZIINA_TEST_MODE

# Test Ziina connectivity
curl -H "Authorization: Bearer $ZIINA_API_KEY" https://api.ziina.com/v1/ping

# Check payment logs
grep "Ziina" /var/log/bookly-agent/app.log
```

### High Memory Usage

```bash
# Check memory usage
htop

# Reduce workers
# Edit /etc/systemd/system/bookly-agent.service
# Change --workers from 4 to 2
sudo systemctl daemon-reload
sudo systemctl restart bookly-agent
```

---

## Security Checklist

- [ ] All secrets stored securely (not in Git)
- [ ] HTTPS enabled with valid certificate
- [ ] Firewall configured (only 80/443 open)
- [ ] Database access restricted (internal only)
- [ ] Regular security updates scheduled
- [ ] Backup encryption enabled
- [ ] API rate limiting configured
- [ ] CORS properly configured
- [ ] Environment variables validated
- [ ] Secrets rotated regularly

---

## Support & Maintenance

### Regular Tasks

**Daily:**
- [ ] Check application logs for errors
- [ ] Monitor payment success rate
- [ ] Check disk space

**Weekly:**
- [ ] Review performance metrics
- [ ] Check for failed refunds
- [ ] Review error logs

**Monthly:**
- [ ] Update dependencies
- [ ] Rotate API keys/secrets
- [ ] Review and optimize database
- [ ] Update SSL certificates (if needed)

### Emergency Contacts

- **Ziina Support**: support@ziina.com
- **Bookly Backend**: backend-team@bookly.ae
- **System Admin**: sysadmin@your-company.com

---

## Success Criteria

Your deployment is successful when:

✅ Application responds to health checks  
✅ API documentation accessible at `/docs`  
✅ PayAtStore bookings working  
✅ PayNow bookings create payment links  
✅ Payment result page renders correctly  
✅ Cancellations process refunds  
✅ WhatsApp bookings authenticated properly  
✅ Logs show no critical errors  
✅ Payment cron job running  
✅ SSL certificate valid  

---

## Next Steps After Deployment

1. **Monitor First 24 Hours**
   - Watch logs closely
   - Track payment success rates
   - Monitor error rates

2. **Gradual Rollout**
   - Start with internal testing
   - Beta test with select users
   - Full rollout after validation

3. **Documentation**
   - Update team on new features
   - Share API documentation
   - Train support team

4. **Optimization**
   - Monitor performance
   - Optimize slow queries
   - Adjust worker count as needed

---

**Deployment Date**: _________________  
**Deployed By**: _________________  
**Version**: 1.0.0  
**Status**: ✅ Ready for Production

---

For detailed feature documentation, see `docs/BOOKING_FEATURES.md`  
For troubleshooting, see this guide's Troubleshooting section
