# TimerFreak Deployment Guide

Complete instructions for deploying TimerFreak to production with proper security configuration.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Server Setup](#server-setup)
3. [Application Installation](#application-installation)
4. [Environment Configuration](#environment-configuration)
5. [OAuth Provider Setup](#oauth-provider-setup)
6. [Database Initialization](#database-initialization)
7. [Systemd Service Configuration](#systemd-service-configuration)
8. [Nginx Reverse Proxy](#nginx-reverse-proxy-optional)
9. [SSL/TLS with Let's Encrypt](#ssltls-with-lets-encrypt)
10. [Security Checklist](#security-checklist)
11. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Hardware Requirements
- **Minimum:** 1 CPU core, 1GB RAM, 10GB storage
- **Recommended:** 2 CPU cores, 2GB RAM, 20GB storage

### Software Requirements
- Ubuntu 20.04+ or Debian 11+ server
- Python 3.8+ installed
- Root or sudo access
- Domain name pointing to your server

---

## Server Setup

### 1. Update System Packages

```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Install Required Dependencies

```bash
sudo apt install -y python3 python3-pip python3-venv python3-dev \
                    nginx certbot python3-certbot-nginx \
                    build-essential libssl-dev libffi-dev \
                    sqlite3 git curl
```

### 3. Create Application User (Recommended)

```bash
sudo useradd -r -m -s /bin/bash timerfreak
```

### 4. Create Application Directory

```bash
sudo mkdir -p /var/www/timerfreak
sudo chown timerfreak:timerfreak /var/www/timerfreak
```

---

## Application Installation

### 1. Clone or Upload Application

```bash
# Navigate to directory
cd /var/www/timerfreak

# Option A: Clone from Git repository
git clone https://github.com/yourusername/timerfreak.git .

# Option B: Upload via SCP/rsync
# From your local machine:
# rsync -avz . timerfreak@yourserver:/var/www/timerfreak/
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Set Directory Permissions

```bash
# Create instance directory for database
sudo mkdir -p /var/www/timerfreak/instance
sudo chown -R www-data:www-data /var/www/timerfreak/instance
sudo chmod 755 /var/www/timerfreak
sudo chmod 755 /var/www/timerfreak/instance
```

---

## Environment Configuration

### 1. Generate Secure Keys

```bash
# Generate FLASK_SECRET_KEY
FLASK_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "FLASK_SECRET_KEY: $FLASK_SECRET"

# Generate ADMIN_STATS_TOKEN
ADMIN_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "ADMIN_STATS_TOKEN: $ADMIN_TOKEN"

# Save securely (you'll need these later)
sudo tee /root/timerfreak-secrets.txt > /dev/null <<EOF
FLASK_SECRET_KEY=$FLASK_SECRET
ADMIN_STATS_TOKEN=$ADMIN_TOKEN
EOF
sudo chmod 600 /root/timerfreak-secrets.txt
```

### 2. Create .env File (Development Only)

```bash
# Copy example file
cp .env.example .env

# Edit with your values (for development only)
nano .env
```

**For production, use systemd environment variables instead (see below).**

---

## OAuth Provider Setup

### Google OAuth

1. **Go to** [Google Cloud Console](https://console.cloud.google.com/)
2. **Create** a new project or select existing
3. **Enable** "Google+ API"
4. **Navigate to** Credentials → Create Credentials → OAuth 2.0 Client ID
5. **Application type:** Web application
6. **Authorized redirect URIs:**
   ```
   https://yourdomain.com/auth/oauth/google/callback
   ```
7. **Copy** Client ID and Client Secret

### GitHub OAuth

1. **Go to** [GitHub OAuth Apps](https://github.com/settings/developers)
2. **Click** "New OAuth App"
3. **Application name:** TimerFreak
4. **Homepage URL:** `https://yourdomain.com`
5. **Authorization callback URL:**
   ```
   https://yourdomain.com/auth/oauth/github/callback
   ```
6. **Copy** Client ID and generate Client Secret

### Store OAuth Credentials

Save all OAuth credentials securely:
```bash
sudo tee -a /root/timerfreak-secrets.txt <<EOF

# Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret

# GitHub OAuth
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
EOF
```

> **Note:** Apple Sign In support is available in the code but commented out by default as it requires an Apple Developer Program membership ($99/year). To enable it, uncomment the Apple OAuth sections in `auth/__init__.py` and the templates, then add your Apple credentials to the environment.

---

## Database Initialization

### 1. Activate Virtual Environment

```bash
cd /var/www/timerfreak
source venv/bin/activate
```

### 2. Run Database Migrations

```bash
# Initialize database schema
flask db upgrade
```

### 3. Verify Database

```bash
# Check database was created
ls -la /var/www/timerfreak/instance/

# Should see: timerfreak.db
```

### 4. (Optional) Create Initial Admin User

```bash
# You can create a script or use Flask shell
flask shell

>>> from models import db, User
>>> from werkzeug.security import generate_password_hash
>>> admin = User(email='admin@yourdomain.com', username='admin', 
...              password_hash=generate_password_hash('your-secure-password'),
...              is_verified=True)
>>> db.session.add(admin)
>>> db.session.commit()
>>> exit()
```

---

## Systemd Service Configuration

### 1. Create Service File

```bash
# Load your secrets
source /root/timerfreak-secrets.txt

# Create systemd service
sudo tee /etc/systemd/system/timerfreak.service > /dev/null <<EOF
[Unit]
Description=TimerFreak Flask Application
Documentation=https://github.com/yourusername/timerfreak
After=network.target

[Service]
# Run as web server user
User=www-data
Group=www-data

# Application directory
WorkingDirectory=/var/www/timerfreak

# Environment variables
Environment="FLASK_SECRET_KEY=${FLASK_SECRET}"
Environment="ADMIN_STATS_TOKEN=${ADMIN_TOKEN}"
Environment="FLASK_DEBUG=false"
Environment="LOG_LEVEL=INFO"
Environment="FLASK_ENV=production"

# OAuth credentials
Environment="GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}"
Environment="GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}"
Environment="GITHUB_CLIENT_ID=${GITHUB_CLIENT_ID}"
Environment="GITHUB_CLIENT_SECRET=${GITHUB_CLIENT_SECRET}"

# Apple Sign In (uncomment when Apple Developer account is available)
# Environment="APPLE_CLIENT_ID=${APPLE_CLIENT_ID}"
# Environment="APPLE_CLIENT_SECRET=${APPLE_CLIENT_SECRET}"
# Environment="APPLE_TEAM_ID=${APPLE_TEAM_ID}"

# Virtual environment path
Environment="PATH=/var/www/timerfreak/venv/bin"

# Run gunicorn with 4 workers (adjust based on CPU cores)
ExecStart=/var/www/timerfreak/venv/bin/gunicorn \
    --workers 4 \
    --bind 127.0.0.1:5001 \
    --timeout 120 \
    --access-logfile /var/log/timerfreak/access.log \
    --error-logfile /var/log/timerfreak/error.log \
    wsgi:application

# Restart policy
Restart=always
RestartSec=10

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/www/timerfreak/instance

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=timerfreak

[Install]
WantedBy=multi-user.target
EOF
```

### 2. Create Log Directory

```bash
sudo mkdir -p /var/log/timerfreak
sudo chown www-data:www-data /var/log/timerfreak
sudo chmod 755 /var/log/timerfreak
```

### 3. Enable and Start Service

```bash
# Reload systemd to recognize new service
sudo systemctl daemon-reload

# Enable to start on boot
sudo systemctl enable timerfreak

# Start the service
sudo systemctl start timerfreak

# Check status
sudo systemctl status timerfreak
```

### 4. Verify Service is Running

```bash
# Check if active
sudo systemctl is-active timerfreak

# View logs
sudo journalctl -u timerfreak -f --no-pager

# Test locally
curl http://127.0.0.1:5001
```

---

## Nginx Reverse Proxy (Optional)

### 1. Create Nginx Configuration

```bash
sudo tee /etc/nginx/sites-available/timerfreak > /dev/null <<EOF
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=31536000" always;

    # Static files
    location /static {
        alias /var/www/timerfreak/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Proxy to Flask application
    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Script-Name /;
        
        # Timeouts
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
        
        # Buffering
        proxy_buffering off;
    }

    # Deny access to hidden files
    location ~ /\. {
        deny all;
    }

    # Logs
    access_log /var/log/nginx/timerfreak-access.log;
    error_log /var/log/nginx/timerfreak-error.log;
}
EOF
```

### 2. Enable Site

```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/timerfreak /etc/nginx/sites-enabled/

# Remove default site (optional)
sudo rm /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

---

## SSL/TLS with Let's Encrypt

### 1. Obtain SSL Certificate

```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

### 2. Auto-Renewal Setup

Certbot sets up automatic renewal. Verify it works:

```bash
sudo certbot renew --dry-run
```

### 3. Force HTTPS (Recommended)

Edit `/etc/nginx/sites-available/timerfreak`:

```nginx
# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;
    
    # SSL configuration (auto-added by certbot)
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    
    # ... rest of configuration
}
```

Then reload:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## Security Checklist

### Application Security

| Feature | Status | Verification |
|---------|--------|--------------|
| CSRF Protection | ✅ Built-in | Check forms have `csrf_token` |
| Secret Key | ⚠️ **You must set** | Check systemd service file |
| Admin Token | ⚠️ **You must set** | Check systemd service file |
| Debug Mode | ✅ Disabled | `FLASK_DEBUG=false` |
| Rate Limiting | ✅ Built-in | 100 req/min on `/log_activity` |
| Input Validation | ✅ Built-in | Sound filenames validated |
| SQL Injection Prevention | ✅ Built-in | SQLAlchemy ORM |
| Error Handling | ✅ Built-in | Custom error pages |

### Server Security

- [ ] **Firewall configured** (ufw recommended)
  ```bash
  sudo ufw allow OpenSSH
  sudo ufw allow 'Nginx Full'
  sudo ufw enable
  sudo ufw status
  ```

- [ ] **Automatic security updates enabled**
  ```bash
  sudo apt install -y unattended-upgrades
  sudo dpkg-reconfigure --priority=low unattended-upgrades
  ```

- [ ] **File permissions restricted**
  ```bash
  sudo chmod 600 /root/timerfreak-secrets.txt
  sudo chown -R www-data:www-data /var/www/timerfreak/instance
  ```

- [ ] **Database backed up regularly**
  ```bash
  # Add to crontab for daily backups at 2 AM
  sudo crontab -e
  
  # Add this line:
  0 2 * * * cp /var/www/timerfreak/instance/timerfreak.db /backup/timerfreak-$(date +\%Y\%m\%d).db && find /backup -name "timerfreak-*.db" -mtime +30 -delete
  ```

- [ ] **SSL certificate auto-renewal tested**
  ```bash
  sudo certbot renew --dry-run
  ```

- [ ] **Admin stats URL secured**
  - Save `ADMIN_STATS_TOKEN` in a password manager
  - Do not share the `/admin/stats?token=...` URL

- [ ] **Log rotation configured**
  ```bash
  sudo tee /etc/logrotate.d/timerfreak <<EOF
  /var/log/timerfreak/*.log {
      daily
      missingok
      rotate 14
      compress
      delaycompress
      notifempty
      create 0640 www-data www-data
      sharedscripts
      postrotate
          systemctl reload timerfreak
      endscript
  }
  EOF
  ```

---

## Troubleshooting

### Service Won't Start

```bash
# Check service status
sudo systemctl status timerfreak

# View detailed logs
sudo journalctl -u timerfreak -n 100 --no-pager

# Check for port conflicts
sudo lsof -i :5001

# Test configuration manually
cd /var/www/timerfreak
source venv/bin/activate
gunicorn --workers 1 --bind 127.0.0.1:5001 wsgi:application
```

### Environment Variables Not Set

```bash
# Check what systemd sees
sudo systemctl show timerfreak | grep Environment

# Verify service file
sudo cat /etc/systemd/system/timerfreak.service
```

### Database Errors

```bash
# Check database exists
ls -la /var/www/timerfreak/instance/

# Run migrations
cd /var/www/timerfreak
source venv/bin/activate
flask db upgrade

# Check database integrity
sqlite3 /var/www/timerfreak/instance/timerfreak.db ".tables"
```

### Nginx Proxy Issues

```bash
# Test nginx configuration
sudo nginx -t

# Check nginx error log
sudo tail -f /var/log/nginx/error.log

# Test backend directly
curl http://127.0.0.1:5001

# Test through proxy
curl https://yourdomain.com
```

### Permission Denied Errors

```bash
# Fix ownership
sudo chown -R www-data:www-data /var/www/timerfreak
sudo chown -R www-data:www-data /var/www/timerfreak/instance

# Fix permissions
sudo chmod 755 /var/www/timerfreak
sudo chmod 755 /var/www/timerfreak/instance
sudo chmod 644 /var/www/timerfreak/instance/timerfreak.db
```

### OAuth Login Not Working

```bash
# Check OAuth credentials are set
sudo systemctl show timerfreak | grep -E 'CLIENT_ID|CLIENT_SECRET'

# Check logs for OAuth errors
sudo journalctl -u timerfreak -f | grep -i oauth

# Verify redirect URLs match in provider settings
# Google: https://console.cloud.google.com/apis/credentials
# GitHub: https://github.com/settings/developers
# Apple: https://developer.apple.com/account/resources/identifiers/list
```

### Quick Health Check Script

```bash
#!/bin/bash
echo "=== TimerFreak Health Check ==="
echo ""
echo "Service Status:"
sudo systemctl is-active timerfreak
echo ""
echo "Nginx Status:"
sudo systemctl is-active nginx
echo ""
echo "Recent Logs:"
sudo journalctl -u timerfreak -n 10 --no-pager
echo ""
echo "Port 5001:"
sudo lsof -i :5001 | head -5
echo ""
echo "Disk Space:"
df -h /var/www/timerfreak
echo ""
echo "Database Size:"
ls -lh /var/www/timerfreak/instance/timerfreak.db
```

---

## Quick Reference

### Commands

| Action | Command |
|--------|---------|
| Start service | `sudo systemctl start timerfreak` |
| Stop service | `sudo systemctl stop timerfreak` |
| Restart service | `sudo systemctl restart timerfreak` |
| Check status | `sudo systemctl status timerfreak` |
| View logs | `sudo journalctl -u timerfreak -f` |
| Enable on boot | `sudo systemctl enable timerfreak` |
| Disable on boot | `sudo systemctl disable timerfreak` |
| Reload systemd | `sudo systemctl daemon-reload` |

### Important Files

| File | Purpose |
|------|---------|
| `/etc/systemd/system/timerfreak.service` | Systemd service configuration |
| `/var/www/timerfreak/` | Application directory |
| `/var/www/timerfreak/instance/timerfreak.db` | SQLite database |
| `/root/timerfreak-secrets.txt` | Saved secret keys (secure!) |
| `/etc/nginx/sites-available/timerfreak` | Nginx configuration |
| `/var/log/timerfreak/` | Application logs |
| `/var/log/nginx/` | Nginx logs |

### Important URLs

| URL | Purpose |
|-----|---------|
| `https://yourdomain.com/` | Main application |
| `https://yourdomain.com/admin/stats?token=YOUR_TOKEN` | Admin statistics |
| `https://yourdomain.com/about` | About page |
| `https://yourdomain.com/auth/login` | User login |
| `https://yourdomain.com/auth/register` | User registration |

---

## Post-Deployment Verification

### 1. Test Basic Functionality

- [ ] Home page loads
- [ ] Create a new timer sequence
- [ ] Timer runs correctly
- [ ] Audio alarms work

### 2. Test Authentication

- [ ] User registration works
- [ ] Email login works
- [ ] Google OAuth login works
- [ ] GitHub OAuth login works
- [ ] Apple Sign In works (if configured)
- [ ] Logout works
- [ ] Password reset works

### 3. Test User Features

- [ ] Dashboard displays correctly
- [ ] Profile page works
- [ ] Settings page works
- [ ] Timer sharing works
- [ ] QR code displays
- [ ] Social sharing buttons work

### 4. Test Admin Features

- [ ] Admin stats page accessible with token
- [ ] Statistics display correctly

### 5. Performance Check

```bash
# Check response times
curl -w "@curl-format.txt" -o /dev/null -s https://yourdomain.com

# curl-format.txt content:
# time_namelookup:  %{time_namelookup}\n
# time_connect:     %{time_connect}\n
# time_appconnect:  %{time_appconnect}\n
# time_pretransfer: %{time_pretransfer}\n
# time_redirect:    %{time_redirect}\n
# time_starttransfer: %{time_starttransfer}\n
# ----------\n
# time_total:       %{time_total}\n
```

---

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review application logs: `sudo journalctl -u timerfreak -f`
3. Check the GitHub repository for updates
4. Review DEPLOYMENT.md for configuration details
