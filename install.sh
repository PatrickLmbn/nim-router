#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "Installing Python dependencies..."
if command -v pip3 &> /dev/null; then
    pip3 install -r requirements.txt
elif command -v pip &> /dev/null; then
    pip install -r requirements.txt
else
    echo "[ERROR] pip is not installed. Please install Python and pip first."
    exit 1
fi

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "Created .env from .env.example. Please remember to add your NVIDIA_API_KEY."
    fi
fi

if command -v pm2 &> /dev/null; then
    echo "PM2 is already installed on your system."
    read -r -p "Do you want to start nim-router in the background with PM2 now? (y/N): " start_pm2
    if [[ "$start_pm2" =~ ^[Yy]$ ]]; then
        if [ -f ecosystem.config.js ]; then
            pm2 start ecosystem.config.js
        else
            pm2 start nim-router.py --name nim-router --interpreter python3
        fi
        echo "nim-router started in background with PM2."
        echo "Use 'pm2 logs nim-router' to view logs or 'pm2 stop nim-router' to stop."
    else
        echo "Setup complete. You can start the server anytime with: python nim-router.py"
    fi
else
    echo ""
    read -r -p "Do you want to install PM2 to run nim-router in the background? (y/N): " install_pm2
    if [[ "$install_pm2" =~ ^[Yy]$ ]]; then
        if command -v npm &> /dev/null; then
            echo "Installing PM2 via npm..."
            npm install -g pm2 || sudo npm install -g pm2
            
            read -r -p "Do you want to start nim-router with PM2 now? (y/N): " start_now
            if [[ "$start_now" =~ ^[Yy]$ ]]; then
                if [ -f ecosystem.config.js ]; then
                    pm2 start ecosystem.config.js
                else
                    pm2 start nim-router.py --name nim-router --interpreter python3
                fi
                echo "nim-router started in background with PM2."
                echo "Use 'pm2 logs nim-router' to view logs."
            fi
        else
            echo "[WARNING] npm was not found. Please install Node.js / npm first to install PM2."
            echo "You can still run the router directly with: python nim-router.py"
        fi
    else
        echo "Setup complete. You can start the router with: python nim-router.py"
    fi
fi
