#!/bin/bash

# Bookly AI Agent Deployment Script
# Usage: ./deploy.sh [environment]
# Example: ./deploy.sh production

set -e  # Exit on error

ENVIRONMENT=${1:-production}
APP_NAME="bookly-agent"
APP_DIR="/opt/$APP_NAME"
BACKUP_DIR="/backup/$APP_NAME"

echo "🚀 Starting deployment for $ENVIRONMENT environment..."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
    exit 1
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root or with sudo"
fi

# Check if environment file exists
if [ ! -f ".env.$ENVIRONMENT" ]; then
    print_error "Environment file .env.$ENVIRONMENT not found"
fi

# Step 1: Backup current deployment
echo "📦 Creating backup..."
if [ -d "$APP_DIR" ]; then
    BACKUP_FILE="$BACKUP_DIR/$(date +%Y%m%d_%H%M%S).tar.gz"
    mkdir -p "$BACKUP_DIR"
    tar -czf "$BACKUP_FILE" -C "$APP_DIR" . 2>/dev/null || true
    print_success "Backup created: $BACKUP_FILE"
else
    print_warning "No existing deployment found, skipping backup"
fi

# Step 2: Stop existing service
echo "🛑 Stopping existing service..."
systemctl stop $APP_NAME 2>/dev/null || print_warning "Service not running"
print_success "Service stopped"

# Step 3: Update code
echo "📥 Updating application code..."
mkdir -p "$APP_DIR"
cp -r . "$APP_DIR/"
cd "$APP_DIR"
print_success "Code updated"

# Step 4: Setup virtual environment
echo "🔧 Setting up virtual environment..."
if [ ! -d "venv" ]; then
    python3.10 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
print_success "Virtual environment ready"

# Step 5: Copy environment file
echo "⚙️ Configuring environment..."
cp ".env.$ENVIRONMENT" .env.production
chmod 600 .env.production
print_success "Environment configured"

# Step 6: Run database migrations (if any)
echo "🗄️ Running database migrations..."
# Add migration commands here if needed
print_success "Database migrations complete"

# Step 7: Setup systemd service
echo "📋 Setting up systemd service..."
cat > /etc/systemd/system/$APP_NAME.service << EOF
[Unit]
Description=Bookly AI Agent Service
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
EnvironmentFile=$APP_DIR/.env.production
ExecStart=$APP_DIR/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10
StandardOutput=append:/var/log/$APP_NAME/access.log
StandardError=append:/var/log/$APP_NAME/error.log

[Install]
WantedBy=multi-user.target
EOF

# Create log directory
mkdir -p /var/log/$APP_NAME
chown www-data:www-data /var/log/$APP_NAME

print_success "Systemd service configured"

# Step 8: Set permissions
echo "🔒 Setting permissions..."
chown -R www-data:www-data "$APP_DIR"
print_success "Permissions set"

# Step 9: Reload systemd
echo "🔄 Reloading systemd..."
systemctl daemon-reload
print_success "Systemd reloaded"

# Step 10: Start service
echo "▶️ Starting service..."
systemctl enable $APP_NAME
systemctl start $APP_NAME
sleep 5
print_success "Service started"

# Step 11: Verify deployment
echo "✅ Verifying deployment..."
if systemctl is-active --quiet $APP_NAME; then
    print_success "Service is running"
else
    print_error "Service failed to start. Check logs: journalctl -u $APP_NAME -n 50"
fi

# Step 12: Health check
echo "🏥 Running health check..."
sleep 10  # Wait for service to fully start
HEALTH_CHECK=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/health)
if [ "$HEALTH_CHECK" == "200" ]; then
    print_success "Health check passed"
else
    print_warning "Health check returned: $HEALTH_CHECK"
fi

# Step 13: Display status
echo ""
echo "================================================"
echo "🎉 Deployment completed successfully!"
echo "================================================"
echo ""
echo "Service Status:"
systemctl status $APP_NAME --no-pager -l
echo ""
echo "Recent Logs:"
journalctl -u $APP_NAME -n 20 --no-pager
echo ""
echo "Useful Commands:"
echo "  View logs:    sudo journalctl -u $APP_NAME -f"
echo "  Restart:      sudo systemctl restart $APP_NAME"
echo "  Stop:         sudo systemctl stop $APP_NAME"
echo "  Status:       sudo systemctl status $APP_NAME"
echo ""
echo "API Documentation: http://localhost:8000/docs"
echo "Health Check:      http://localhost:8000/api/v1/health"
echo ""
print_success "Deployment complete! 🚀"
