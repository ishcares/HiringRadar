#!/bin/bash
# deploy_aws.sh — Automation script to configure and launch HiringRadar on AWS EC2.
# Run this on your Ubuntu 22.04 LTS EC2 instance.

set -e

echo "=== 🚀 Starting HiringRadar Deployment on AWS EC2 ==="

# 1. Update Packages
echo "Updating apt packages..."
sudo apt update && sudo apt upgrade -y

# 2. Install dependencies
echo "Installing Python 3, pip, venv, and git..."
sudo apt install -y python3-pip python3-venv git

# 3. Setup project directory
PROJECT_DIR="/home/ubuntu/hiringradar"
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Cloning repository..."
    git clone https://huggingface.co/spaces/ishitachaurasia/hiringradar "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

# 4. Create Virtual Environment
echo "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# 5. Install Python dependencies
echo "Installing project dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 6. Verify .env existence
if [ ! -f ".env" ]; then
    echo "⚠️ WARNING: .env file is missing!"
    echo "Please create a .env file at $PROJECT_DIR/.env with your configuration:"
    echo "BOT_TOKEN=..."
    echo "SUPABASE_URL=..."
    echo "SUPABASE_KEY=..."
    echo "ADMIN_CHAT_ID=..."
    echo ""
    touch .env
fi

# 7. Configure Systemd Service
echo "Configuring systemd service..."
sudo cp hiringradar.service /etc/systemd/system/hiringradar.service
sudo systemctl daemon-reload
sudo systemctl enable hiringradar

echo "=== 🏁 Setup Completed! ==="
echo "👉 NEXT STEPS:"
echo "1. Edit $PROJECT_DIR/.env and add your Supabase & Bot tokens."
echo "2. Start the bot: sudo systemctl start hiringradar"
echo "3. Monitor logs:  sudo journalctl -u hiringradar -f"
