#!/bin/bash
# ============================================================
#  Controva Intelligence Platform - One-Click Installer
#  Tested on: Ubuntu 22.04 / 24.04 / 26.04
#
#  Usage:
#    1. Upload this folder to /root/LeadGen on your VPS
#    2. cd /root/LeadGen
#    3. chmod +x setup.sh
#    4. sudo ./setup.sh
#    5. Edit /opt/leadgen/config.json with your real API keys
#    6. systemctl restart leadgen-api
#    7. Open http://YOUR_SERVER_IP:8080/
# ============================================================

set -e
echo ""
echo "════════════════════════════════════════════════════════"
echo "  CONTROVA INTELLIGENCE PLATFORM - Installer"
echo "════════════════════════════════════════════════════════"
echo ""

# Verify we're root
if [ "$EUID" -ne 0 ]; then
  echo "ERROR: Please run as root (sudo ./setup.sh)"
  exit 1
fi

# Verify kit files are present
required=(docker-compose.yml init.sql leads_api.py dashboard.html leadgen-api.service config.json.template)
for f in "${required[@]}"; do
  if [ ! -f "./$f" ]; then
    echo "ERROR: Missing file: $f"
    echo "Run this script from inside the server/ folder of the kit."
    exit 1
  fi
done

# Step 1: Update + dependencies
echo "[1/9] Installing system dependencies..."
apt-get update -y
apt-get install -y curl git wget unzip htop ufw python3 python3-pip python3-psycopg2 dnsutils

# Step 2: Docker
echo ""
echo "[2/9] Installing Docker..."
if ! command -v docker &> /dev/null; then
  curl -fsSL https://get.docker.com | bash
  systemctl enable docker && systemctl start docker
fi
apt-get install -y docker-compose-plugin 2>/dev/null || true

# Step 3: Install Python packages
echo ""
echo "[3/9] Installing Python packages..."
pip3 install --break-system-packages psycopg2-binary oxylabs-ai-studio 2>&1 | tail -3

# Step 4: Create directory structure
echo ""
echo "[4/9] Creating /opt/leadgen directories..."
mkdir -p /opt/leadgen/{postgres/data,redis/data,crawl4ai,logs,backups,mockups}
chown -R 70:70 /opt/leadgen/postgres
chmod -R 755 /opt/leadgen

# Step 5: Configure firewall
echo ""
echo "[5/9] Configuring firewall..."
ufw --force enable
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8080/tcp comment 'LeadGen Dashboard + API'
ufw allow 5432/tcp comment 'PostgreSQL'
ufw allow 6379/tcp comment 'Redis'
ufw allow 11235/tcp comment 'Crawl4AI'

# Step 6: Install configuration files
echo ""
echo "[6/9] Installing configuration files..."
cp ./docker-compose.yml      /opt/leadgen/docker-compose.yml
cp ./init.sql                /opt/leadgen/postgres/init.sql
cp ./leads_api.py            /opt/leadgen/leads_api.py
cp ./dashboard.html          /opt/leadgen/dashboard.html
cp ./config.json.template    /opt/leadgen/config.json
cp ./leadgen-api.service     /etc/systemd/system/leadgen-api.service
chmod +x /opt/leadgen/leads_api.py

# Step 7: Start Docker services
echo ""
echo "[7/9] Starting Docker services (PostgreSQL, Redis, Crawl4AI)..."
cd /opt/leadgen
docker compose up -d
echo "Waiting 45 seconds for PostgreSQL initialization..."
sleep 45

# Step 8: Verify services
echo ""
echo "[8/9] Verifying Docker services..."
docker compose ps
docker exec leadgen_postgres psql -U leadgen -d leadgen_db -c "SELECT 1" >/dev/null 2>&1 && echo "PostgreSQL: OK" || echo "PostgreSQL: FAILED"
docker exec leadgen_redis redis-cli -a "Redis_Secure_2024!" ping 2>&1 | grep -q "PONG" && echo "Redis: OK" || echo "Redis: FAILED"
curl -s http://localhost:11235/health 2>&1 | grep -q "ok" && echo "Crawl4AI: OK" || echo "Crawl4AI: Still starting"

# Step 9: Start API + dashboard service
echo ""
echo "[9/9] Starting LeadGen API service..."
systemctl daemon-reload
systemctl enable leadgen-api
systemctl start leadgen-api
sleep 5

if systemctl is-active leadgen-api >/dev/null; then
  echo "API service: ACTIVE"
else
  echo "API service: FAILED (check: journalctl -u leadgen-api)"
fi

PUBLIC_IP=$(curl -s ifconfig.me || echo "YOUR_SERVER_IP")
echo ""
echo "════════════════════════════════════════════════════════"
echo "  SETUP COMPLETE"
echo "════════════════════════════════════════════════════════"
echo ""
echo "  IMPORTANT - You MUST do these final 2 steps:"
echo ""
echo "  1. Edit /opt/leadgen/config.json and add YOUR real API keys"
echo "     nano /opt/leadgen/config.json"
echo ""
echo "  2. Restart the service after updating keys:"
echo "     systemctl restart leadgen-api"
echo ""
echo "  Dashboard URL: http://$PUBLIC_IP:8080/"
echo "  Default login: admin / ChangeMe_2026!"
echo ""
echo "  Useful commands:"
echo "    systemctl status leadgen-api    - Check API status"
echo "    journalctl -u leadgen-api -f    - Watch live logs"
echo "    docker compose ps                - Check Docker services"
echo "    docker compose restart           - Restart all services"
echo ""
