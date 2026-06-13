# Installation Guide — Controva Intelligence Platform

Complete walkthrough to install this platform on a brand-new VPS.

---

## Prerequisites

### Server Requirements
- Ubuntu 22.04, 24.04, or 26.04 LTS
- Minimum 4 GB RAM, 50 GB disk
- Recommended 16 GB RAM (Hostinger KVM 4)
- Root SSH access
- Public IPv4 address

### Tools You Need On Your Local Machine
- SSH client (Terminal on Mac/Linux, PowerShell on Windows)
- SCP for file upload (or use SFTP client like FileZilla)
- Web browser

### API Keys You Need to Collect
| Service | Required | Get It Here | Free Tier |
|---|---|---|---|
| Google Cloud (Places + Geocoding) | YES | console.cloud.google.com | $300 credits |
| Serper.dev | YES | serper.dev | 2,500 free searches |
| Google Gemini | YES | aistudio.google.com/app/apikey | Generous free tier |
| Anthropic Claude | YES | console.anthropic.com | Pay-as-you-go |
| Replicate | Optional | replicate.com/account/api-tokens | Pay per image |
| imagine.art | Optional | imagine.art/dev | Pay per image |
| Oxylabs AI Studio | Optional | aistudio.oxylabs.io | Pay per scrape |
| Resend.com | YES (for email send) | resend.com | 3,000 emails/month free |

---

## Step-by-Step Installation

### Step 1 — Provision a VPS

Pick any provider. Recommended:
- Hostinger KVM 4 (€10/mo, 16 GB RAM)
- DigitalOcean Premium (4 GB RAM, $24/mo)
- Hetzner CX22 (€5/mo, 4 GB RAM)

Choose **Ubuntu 24.04 LTS** during setup. Save the IP address.

### Step 2 — Upload This Kit

From your local machine:

```bash
# Replace YOUR_IP with your server's IP
scp -r LeadGen_Platform_Complete root@YOUR_IP:/root/
```

Or use FileZilla:
- Host: `YOUR_IP`, User: `root`, Port: `22`
- Drag the `LeadGen_Platform_Complete` folder to `/root/`

### Step 3 — Run the Installer

SSH into the server:

```bash
ssh root@YOUR_IP
```

Run the installer:

```bash
cd /root/LeadGen_Platform_Complete/server
chmod +x setup.sh
sudo ./setup.sh
```

This takes 3-5 minutes. The script will:
1. Update Ubuntu
2. Install Docker + Python + dependencies
3. Create directories
4. Open firewall ports
5. Copy config files
6. Start PostgreSQL + Redis + Crawl4AI containers
7. Wait for database initialization
8. Start the API + dashboard service

Expected output ends with:
```
SETUP COMPLETE
Dashboard URL: http://YOUR_IP:8080/
Default login: admin / ChangeMe_2026!
```

### Step 4 — Add Your Real API Keys

Edit the config file:

```bash
nano /opt/leadgen/config.json
```

Replace the placeholder values with your real keys. Save with `Ctrl+X`, then `Y`, then `Enter`.

Restart to apply:

```bash
systemctl restart leadgen-api
```

### Step 5 — Open the Dashboard

In your browser: `http://YOUR_IP:8080/`

Log in with `admin` / `ChangeMe_2026!`

### Step 6 — Change Default Passwords (CRITICAL)

#### Dashboard Password
SSH into the server:

```bash
nano /opt/leadgen/leads_api.py
```

Find the line:
```python
AUTH_USERS = {
    "admin": {"salt": "controva2026salt", "hash": _h_hashlib.sha256(("ChangeMe_2026!" + "controva2026salt").encode()).hexdigest()}
}
```

Replace `ChangeMe_2026!` with your new password. Save, then restart:

```bash
systemctl restart leadgen-api
```

#### Database Password (optional but recommended)

```bash
nano /opt/leadgen/docker-compose.yml
```

Change all instances of `LeadGen_Secure_2024!` and `Redis_Secure_2024!` to your new passwords.

Also update them in `/opt/leadgen/leads_api.py` (look for `DB = dict(...)` line).

Then:

```bash
cd /opt/leadgen
docker compose down -v   # WARNING: deletes existing data
docker compose up -d
systemctl restart leadgen-api
```

---

## Verifying The Installation

### Test 1 — Health Check
```bash
curl http://localhost:8080/health
```

Expected:
```json
{"status":"ok","version":"5.0","modules":[...],"providers":{...}}
```

### Test 2 — Database Connection
```bash
docker exec leadgen_postgres psql -U leadgen -d leadgen_db -c "SELECT COUNT(*) FROM leads;"
```

Expected: `count` of 0 (new install).

### Test 3 — Dashboard Loads
Open `http://YOUR_IP:8080/` in browser. You should see the login screen.

### Test 4 — Run Your First Search
1. Log in
2. Go to "Search" page
3. Type: `barber shops in Manchester UK`
4. Click Search
5. Wait 15-30 seconds
6. Should see parsed query + 5-50 results

---

## Common Installation Issues

### Issue: PostgreSQL won't start
```
Error: chown: /opt/leadgen/postgres/data: permission denied
```

Fix:
```bash
chown -R 70:70 /opt/leadgen/postgres
cd /opt/leadgen && docker compose restart postgres
```

### Issue: Crawl4AI keeps restarting
Check available RAM:
```bash
free -h
```

Crawl4AI needs at least 2 GB free. If you only have 4 GB total, you may need to reduce other services or upgrade.

### Issue: API service won't start
```bash
journalctl -u leadgen-api -n 50 --no-pager
```

Common causes:
- Missing Python packages → `pip3 install --break-system-packages psycopg2-binary oxylabs-ai-studio`
- Syntax error in config.json → validate at jsonlint.com
- PostgreSQL not ready yet → wait 60 seconds and retry

### Issue: Dashboard shows blank page
Hard-refresh browser (Ctrl+Shift+R or Cmd+Shift+R).
If still blank, check the browser console (F12) for red errors.

### Issue: Search returns 0 leads always
Most common cause: Google Places API key not enabled.
1. Go to console.cloud.google.com
2. APIs & Services → Library
3. Search "Places API (New)" → ENABLE
4. Search "Geocoding API" → ENABLE
5. Make sure billing is enabled (required for free tier too)

### Issue: Connection refused on port 8080
Check service status:
```bash
systemctl status leadgen-api
```

Check firewall:
```bash
ufw status
```

Should show `8080/tcp ALLOW Anywhere`.

---

## Optional: HTTPS Setup (Recommended for Production)

To replace the "Not secure" browser warning with HTTPS:

### Option A — Caddy (Easiest)

```bash
apt install -y caddy
nano /etc/caddy/Caddyfile
```

Add:
```
your-domain.com {
    reverse_proxy localhost:8080
}
```

Save, then:
```bash
systemctl restart caddy
```

Point your domain's DNS A record to your server IP. Caddy auto-fetches a Let's Encrypt certificate.

### Option B — Nginx + Certbot

```bash
apt install -y nginx certbot python3-certbot-nginx

# Create nginx config
nano /etc/nginx/sites-available/leadgen
```

Add:
```nginx
server {
    listen 80;
    server_name your-domain.com;
    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Enable + get SSL:
```bash
ln -s /etc/nginx/sites-available/leadgen /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d your-domain.com
```

---

## Backup Strategy

### Manual Database Backup

```bash
docker exec leadgen_postgres pg_dump -U leadgen leadgen_db > /opt/leadgen/backups/backup_$(date +%Y%m%d_%H%M%S).sql
```

### Automated Daily Backup (Cron)

```bash
crontab -e
```

Add:
```
0 3 * * * docker exec leadgen_postgres pg_dump -U leadgen leadgen_db > /opt/leadgen/backups/backup_$(date +\%Y\%m\%d).sql 2>&1
```

### Restore from Backup

```bash
cat /opt/leadgen/backups/backup_20260603.sql | docker exec -i leadgen_postgres psql -U leadgen -d leadgen_db
```

---

## Upgrading to a New Version

When updates are released:

```bash
# 1. Backup database
docker exec leadgen_postgres pg_dump -U leadgen leadgen_db > /opt/leadgen/backups/pre_upgrade.sql

# 2. Replace the two main files (keep config.json untouched)
cp NEW_VERSION/leads_api.py /opt/leadgen/leads_api.py
cp NEW_VERSION/dashboard.html /opt/leadgen/dashboard.html

# 3. Apply schema migrations if init.sql changed (manual review needed)

# 4. Restart
systemctl restart leadgen-api
```

---

## Uninstalling

To completely remove the platform:

```bash
systemctl stop leadgen-api
systemctl disable leadgen-api
rm /etc/systemd/system/leadgen-api.service
cd /opt/leadgen
docker compose down -v        # Removes all data
rm -rf /opt/leadgen
ufw delete allow 8080/tcp
ufw delete allow 5432/tcp
ufw delete allow 6379/tcp
ufw delete allow 11235/tcp
```

---

## What Gets Installed Where

```
/opt/leadgen/
├── docker-compose.yml        # Docker services config
├── leads_api.py              # Main Python API server
├── dashboard.html            # React dashboard
├── config.json               # API keys + settings (YOU EDIT THIS)
├── postgres/
│   ├── data/                 # PostgreSQL data files
│   └── init.sql              # Schema (runs once on first start)
├── redis/data/               # Redis persistence
├── crawl4ai/                 # Crawl4AI working dir
├── mockups/                  # Generated mockup images
├── logs/                     # Application logs
└── backups/                  # SQL backups

/etc/systemd/system/
└── leadgen-api.service       # Systemd unit to auto-start API
```

---

## Next Steps After Installation

1. Read **2_USER_GUIDE.docx** to learn how to use the dashboard
2. Read **3_DEVELOPER_GUIDE.docx** if you want to modify the code
3. Read **4_API_REFERENCE.md** if you want to integrate with other tools
4. Change all default passwords
5. Set up automated backups
6. (Optional) Add HTTPS via Caddy or Nginx
7. (Optional) Buy a domain and point it to the server

You're now ready to use the platform. Open `http://YOUR_IP:8080/` and start finding leads.
