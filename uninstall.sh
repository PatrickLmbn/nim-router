#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
NC="\033[0m"

echo -e "${BOLD}=== NIM Router Uninstaller ===${NC}\n"

if command -v pm2 &> /dev/null; then
    if pm2 list | grep -q "nim-router"; then
        echo "Stopping and deleting nim-router from PM2..."
        pm2 stop nim-router 2>/dev/null || true
        pm2 delete nim-router 2>/dev/null || true
        pm2 save 2>/dev/null || true
        echo -e "${GREEN}[✓] PM2 process removed.${NC}"
    else
        echo "No running nim-router PM2 process found."
    fi
fi

if [ -d ".venv" ]; then
    read -r -p "Remove Python virtual environment (.venv)? (y/N): " remove_venv
    if [[ "$remove_venv" =~ ^[Yy]$ ]]; then
        rm -rf .venv
        echo -e "${GREEN}[✓] Removed .venv directory.${NC}"
    fi
fi

echo "Cleaning temporary logs and cache files..."
rm -f *.log
rm -rf __pycache__ tests/__pycache__
echo -e "${GREEN}[✓] Logs and cache cleaned.${NC}"

if [ -f ".env" ]; then
    read -r -p "Delete .env file (containing your NVIDIA_API_KEY)? (y/N): " remove_env
    if [[ "$remove_env" =~ ^[Yy]$ ]]; then
        rm -f .env
        echo -e "${GREEN}[✓] Removed .env file.${NC}"
    else
        echo "Kept .env file."
    fi
fi

echo ""
echo -e "${GREEN}${BOLD}Uninstallation complete!${NC}"
read -r -p "Do you want to delete this entire nim-router project directory ($DIR)? (y/N): " delete_repo
if [[ "$delete_repo" =~ ^[Yy]$ ]]; then
    cd ..
    rm -rf "$DIR"
    echo -e "${GREEN}[✓] nim-router directory deleted.${NC}"
fi

