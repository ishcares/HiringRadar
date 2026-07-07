#!/usr/bin/env bash
# =============================================================================
#  HiringRadar — Oracle Cloud Always Free VM Setup Script
#  Tested on: Ubuntu 22.04 LTS (Ampere A1 ARM64 & AMD E2.1.Micro x86_64)
#
#  Usage (on the Oracle VM, after uploading your project files):
#    chmod +x setup_oracle.sh && sudo bash setup_oracle.sh
# =============================================================================
set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Config ────────────────────────────────────────────────────────────────────
APP_DIR="/home/ubuntu/hiringradar"
DB_NAME="hiringradar"
DB_USER="hiringradar"
DB_PASS="$(openssl rand -base64 24)"   # auto-generated; printed at the end
SERVICE_NAME="hiringradar"
PYTHON_BIN="python3"

# ── Must run as root ──────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "Please run with: sudo bash setup_oracle.sh"

info "=== HiringRadar Oracle Cloud Setup ==="
echo ""

# ── 1. System update ──────────────────────────────────────────────────────────
info "Step 1/9 — Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    git curl wget unzip build-essential \
    python3 python3-pip python3-venv python3-dev \
    libpq-dev ca-certificates gnupg lsb-release openssl

# ── 2. Swap space ─────────────────────────────────────────────────────────────
# Critical for AMD E2.1.Micro (1 GB RAM): sentence-transformers loads ~700 MB model
info "Step 2/9 — Configuring 2 GB swap space..."
if ! swapon --show | grep -q /swapfile; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    sysctl vm.swappiness=10
    echo 'vm.swappiness=10' >> /etc/sysctl.conf
    info "  2 GB swap enabled (swappiness=10)"
else
    info "  Swap already configured — skipping"
fi

# ── 3. PostgreSQL 15 ──────────────────────────────────────────────────────────
info "Step 3/9 — Installing PostgreSQL 15..."
if ! command -v psql &>/dev/null; then
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg
    echo "deb [signed-by=/etc/apt/trusted.gpg.d/postgresql.gpg] \
https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list
    apt-get update -qq
    apt-get install -y -qq postgresql-15
fi

systemctl enable postgresql
systemctl start postgresql

# Create DB user and database (idempotent)
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null \
    || warn "  User '$DB_USER' already exists"
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null \
    || warn "  Database '$DB_NAME' already exists"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 2>/dev/null || true

# Lock Postgres to localhost only
PG_CONF=$(find /etc/postgresql -name "postgresql.conf" 2>/dev/null | head -1)
if [ -n "$PG_CONF" ]; then
    sed -i "s/#listen_addresses = 'localhost'/listen_addresses = 'localhost'/" "$PG_CONF" || true
fi
systemctl restart postgresql
info "  PostgreSQL 15 ready — DB: $DB_NAME, User: $DB_USER"

# ── 4. App directory ──────────────────────────────────────────────────────────
info "Step 4/9 — Preparing application directory at $APP_DIR..."
mkdir -p "$APP_DIR"
chown ubuntu:ubuntu "$APP_DIR"

# ── 5. Python venv & pip deps ─────────────────────────────────────────────────
info "Step 5/9 — Creating Python virtual environment and installing deps..."
sudo -u ubuntu bash <<PYEOF
set -e
cd "$APP_DIR"
$PYTHON_BIN -m venv venv
source venv/bin/activate
pip install --upgrade pip --quiet

if [ -f requirements.txt ]; then
    pip install --no-cache-dir -r requirements.txt --quiet
    echo "  Python packages installed from requirements.txt"
else
    echo "  WARNING: requirements.txt not found — copy project files first, then re-run this script."
fi
PYEOF

# ── 6. Playwright Chromium ────────────────────────────────────────────────────
info "Step 6/9 — Installing Playwright system dependencies and Chromium..."
apt-get install -y -qq \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    libatspi2.0-0 2>/dev/null || true

sudo -u ubuntu bash <<PWEOF
source "$APP_DIR/venv/bin/activate"
playwright install chromium 2>/dev/null \
    && echo "  Playwright Chromium installed" \
    || echo "  Playwright install skipped (requirements not installed yet)"
PWEOF

# ── 7. .env file ──────────────────────────────────────────────────────────────
info "Step 7/9 — Writing .env template..."
ENV_FILE="$APP_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    warn "  .env already exists — not overwriting. Update it manually."
else
    cat > "$ENV_FILE" <<ENVEOF
# ── Telegram ──────────────────────────────────────────────────────────────────
BOT_TOKEN=PASTE_YOUR_BOT_TOKEN_HERE
ADMIN_CHAT_ID=PASTE_YOUR_ADMIN_CHAT_ID_HERE

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL=PASTE_YOUR_SUPABASE_URL_HERE
SUPABASE_KEY=PASTE_YOUR_SUPABASE_KEY_HERE

# ── Local PostgreSQL (seen_jobs deduplication) ────────────────────────────────
DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}
ENVEOF
    chown ubuntu:ubuntu "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    info "  .env written — fill in BOT_TOKEN, ADMIN_CHAT_ID, SUPABASE_URL, SUPABASE_KEY"
fi

# ── 8. systemd service ────────────────────────────────────────────────────────
info "Step 8/9 — Installing systemd service..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<SVCEOF
[Unit]
Description=HiringRadar Telegram Bot
After=network-online.target postgresql.service
Wants=network-online.target postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/python bot.py
Restart=always
RestartSec=15
# Give sentence-transformers time to download model on first run
TimeoutStartSec=180

# Resource limits (conservative for 1 GB AMD VM)
MemoryMax=900M

# Logging — view with: journalctl -u hiringradar -f --since today
StandardOutput=journal
StandardError=journal
SyslogIdentifier=hiringradar

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
info "  systemd service '$SERVICE_NAME' installed and enabled on boot"

# ── 9. Firewall (UFW) ─────────────────────────────────────────────────────────
info "Step 9/9 — Configuring firewall..."
if command -v ufw &>/dev/null; then
    ufw --force reset      >/dev/null
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp comment 'SSH'
    ufw --force enable     >/dev/null
    info "  UFW active — only port 22 (SSH) open inbound"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅  Oracle Cloud VM setup complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${YELLOW}⚠️  Save this DATABASE_URL — it won't be shown again:${NC}"
echo -e "  postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}"
echo ""
echo "  ── Next steps ──────────────────────────────────────────────"
echo ""
echo "  1. Copy your project to the VM (from your local machine):"
echo "     scp -r /path/to/HiringRadar/* ubuntu@<VM_IP>:~/hiringradar/"
echo ""
echo "  2. Fill in missing secrets in $ENV_FILE:"
echo "     nano $ENV_FILE"
echo "     (Add BOT_TOKEN, ADMIN_CHAT_ID, SUPABASE_URL, SUPABASE_KEY)"
echo ""
echo "  3. (Optional) Migrate seen_jobs from Railway:"
echo "     bash $APP_DIR/migrate_db.sh"
echo ""
echo "  4. Start the bot:"
echo "     sudo systemctl start hiringradar"
echo "     sudo journalctl -u hiringradar -f"
echo ""
echo "  ── Useful commands ─────────────────────────────────────────"
echo "  Status:   sudo systemctl status hiringradar"
echo "  Stop:     sudo systemctl stop hiringradar"
echo "  Restart:  sudo systemctl restart hiringradar"
echo "  Logs:     sudo journalctl -u hiringradar -f --since today"
echo ""
