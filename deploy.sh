#!/bin/bash
# deploy.sh — One-command deploy for HiringRadar on the AWS EC2 instance.
#
# Usage (run from your LOCAL machine):
#   ./deploy.sh                    # push + restart bot
#   ./deploy.sh --test-only        # run staged tests on server, don't restart
#   ./deploy.sh --restart-only     # restart bot without pulling new code
#   ./deploy.sh --logs             # tail live logs after deploy
#
# Prerequisites on local machine:
#   - SSH key configured: ssh ubuntu@<EC2_IP> works without password
#   - EC2_HOST set as env var OR edit the EC2_HOST line below
#
# Prerequisites on the EC2 instance (one-time setup via deploy_aws.sh):
#   - /home/ubuntu/hiringradar exists with venv activated
#   - hiringradar.service registered with systemd
#   - .env file present with all secrets

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
EC2_HOST="${EC2_HOST:-}"            # e.g. ubuntu@13.233.xx.xx  (set in your shell or here)
REMOTE_DIR="/home/ubuntu/hiringradar"
SERVICE="hiringradar"
HF_REPO="${HF_REPO:-}"             # e.g. ishitachaurasia/hiringradar (Hugging Face source)

# ── Args ──────────────────────────────────────────────────────────────────────
TEST_ONLY=false
RESTART_ONLY=false
SHOW_LOGS=false

for arg in "$@"; do
    case $arg in
        --test-only)    TEST_ONLY=true ;;
        --restart-only) RESTART_ONLY=true ;;
        --logs)         SHOW_LOGS=true ;;
        --help)
            echo "Usage: ./deploy.sh [--test-only] [--restart-only] [--logs]"
            exit 0 ;;
    esac
done

# ── Validate ──────────────────────────────────────────────────────────────────
if [ -z "$EC2_HOST" ]; then
    echo "❌  EC2_HOST is not set."
    echo "    Set it in your shell:  export EC2_HOST=ubuntu@<your-ec2-ip>"
    echo "    Or edit this script's EC2_HOST line directly."
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  HiringRadar Deploy"
echo "  Target: $EC2_HOST:$REMOTE_DIR"
echo "═══════════════════════════════════════════════════════════════"

# ── Step 1: Run staged tests locally before touching the server ────────────────
if [ "$RESTART_ONLY" = false ] && [ "$TEST_ONLY" = false ]; then
    echo ""
    echo "▶ Step 1/4  Local staged tests (stages 1 & 2 — no DB)..."
    if python stage_test.py --stage 1 2; then
        echo "  ✅ Local tests passed"
    else
        echo "  ❌ Local tests FAILED — aborting deploy"
        echo "     Fix the failures above, then re-run ./deploy.sh"
        exit 1
    fi
fi

# ── Step 2: Push code to remote ────────────────────────────────────────────────
if [ "$RESTART_ONLY" = false ]; then
    echo ""
    echo "▶ Step 2/4  Syncing code to EC2..."

    # Sync all Python files + config (exclude secrets, cache, temp files)
    rsync -avz --progress \
        --exclude='.git' \
        --exclude='.env' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='temp_resumes/' \
        --exclude='*.csv' \
        --exclude='scratch/' \
        --exclude='.pytest_cache' \
        --exclude='venv/' \
        . "$EC2_HOST:$REMOTE_DIR/"

    echo "  ✅ Code synced"

    # Install any new dependencies (in background on server, fast if nothing changed)
    echo ""
    echo "▶ Step 2b   Installing dependencies on server..."
    ssh "$EC2_HOST" "cd $REMOTE_DIR && source venv/bin/activate && pip install -q -r requirements.txt"
    echo "  ✅ Dependencies up to date"
fi

# ── Step 3: Run staged tests on the server (against real DB) ──────────────────
echo ""
echo "▶ Step 3/4  Remote staged tests (stages 3 & 4 — real Supabase)..."
if ssh "$EC2_HOST" "cd $REMOTE_DIR && source venv/bin/activate && python stage_test.py --stage 3 4"; then
    echo "  ✅ Remote DB tests passed"
else
    echo "  ❌ Remote tests FAILED — bot NOT restarted"
    echo "     Check the output above. The old bot is still running."
    if [ "$TEST_ONLY" = true ]; then exit 1; fi
    read -p "  Force restart anyway? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "  Aborted. Old bot still running."
        exit 1
    fi
fi

if [ "$TEST_ONLY" = true ]; then
    echo ""
    echo "  --test-only: skipping restart"
    exit 0
fi

# ── Step 4: Restart the service ───────────────────────────────────────────────
echo ""
echo "▶ Step 4/4  Restarting $SERVICE service..."
ssh "$EC2_HOST" "sudo systemctl restart $SERVICE"
sleep 3  # Give it a moment to start

# Check it actually came up
STATUS=$(ssh "$EC2_HOST" "systemctl is-active $SERVICE" 2>/dev/null || echo "unknown")
if [ "$STATUS" = "active" ]; then
    echo "  ✅ Service is ACTIVE"
else
    echo "  ❌ Service status: $STATUS"
    echo "     Check logs: ssh $EC2_HOST 'sudo journalctl -u $SERVICE -n 50'"
    exit 1
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅  Deploy complete"
echo "═══════════════════════════════════════════════════════════════"
echo "  Service:  $STATUS"
echo "  Logs:     ssh $EC2_HOST 'sudo journalctl -u $SERVICE -f'"
echo "  Status:   ssh $EC2_HOST 'systemctl status $SERVICE'"
echo ""

if [ "$SHOW_LOGS" = true ]; then
    echo "  Tailing logs (Ctrl+C to stop)..."
    ssh "$EC2_HOST" "sudo journalctl -u $SERVICE -f --no-pager"
fi
