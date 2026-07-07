#!/usr/bin/env bash
# =============================================================================
#  migrate_db.sh — Export seen_jobs from Railway Postgres → Oracle Postgres
#
#  Run this ONCE on the Oracle VM after setup_oracle.sh completes.
#
#  Prerequisites:
#    - Railway DATABASE_URL (export RAILWAY_DB_URL before running)
#    - Oracle Postgres already running (setup_oracle.sh done)
#
#  Usage:
#    export RAILWAY_DB_URL="postgresql://user:pass@host:port/dbname"
#    bash migrate_db.sh
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Check deps ────────────────────────────────────────────────────────────────
command -v pg_dump  &>/dev/null || error "pg_dump not found. Install postgresql-client."
command -v psql     &>/dev/null || error "psql not found. Install postgresql-client."

# ── Validate inputs ───────────────────────────────────────────────────────────
if [ -z "${RAILWAY_DB_URL:-}" ]; then
    error "Set RAILWAY_DB_URL first:\n  export RAILWAY_DB_URL='postgresql://user:pass@host:port/dbname'"
fi

# Load Oracle DATABASE_URL from .env
APP_DIR="/home/ubuntu/hiringradar"
ENV_FILE="$APP_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    source <(grep -E '^DATABASE_URL=' "$ENV_FILE" | sed 's/^/export /')
fi

if [ -z "${DATABASE_URL:-}" ]; then
    error "DATABASE_URL not set. Make sure $ENV_FILE has DATABASE_URL."
fi

DUMP_FILE="/tmp/seen_jobs_railway.sql"

# ── Step 1: Dump from Railway ─────────────────────────────────────────────────
info "Exporting seen_jobs table from Railway..."
pg_dump "$RAILWAY_DB_URL" \
    --table=seen_jobs \
    --data-only \
    --no-owner \
    --no-privileges \
    -f "$DUMP_FILE" \
    && info "  Dump written to $DUMP_FILE" \
    || error "pg_dump failed — check RAILWAY_DB_URL"

ROWS=$(grep -c "^INSERT\|^COPY" "$DUMP_FILE" 2>/dev/null || echo "?")
info "  Rows in dump: $ROWS"

# ── Step 2: Ensure table exists on Oracle ────────────────────────────────────
info "Ensuring seen_jobs table exists on Oracle Postgres..."
psql "$DATABASE_URL" -c \
    "CREATE TABLE IF NOT EXISTS seen_jobs (url TEXT PRIMARY KEY);" \
    >/dev/null

# ── Step 3: Import into Oracle ────────────────────────────────────────────────
info "Importing into Oracle Postgres..."
psql "$DATABASE_URL" -f "$DUMP_FILE" >/dev/null \
    && info "  Import complete!" \
    || warn "  Some rows may have been skipped (duplicates OK)"

# ── Step 4: Verify ────────────────────────────────────────────────────────────
COUNT=$(psql "$DATABASE_URL" -t -c "SELECT COUNT(*) FROM seen_jobs;" | tr -d ' ')
info "  seen_jobs rows on Oracle: $COUNT"

rm -f "$DUMP_FILE"
echo ""
echo -e "${GREEN}✅ Migration complete — $COUNT seen_jobs transferred from Railway → Oracle${NC}"
echo "   The bot will NOT re-alert users on jobs it has already seen."
echo ""
