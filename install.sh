#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Color formatting
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
NC="\033[0m"

echo -e "${BOLD}=== NVIDIA NIM Router Installer ===${NC}\n"

# 1. Check Python installation
PYTHON_BIN=""
if command -v python3 &> /dev/null; then
    PYTHON_BIN="python3"
elif command -v python &> /dev/null; then
    if python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
        PYTHON_BIN="python"
    fi
fi

if [ -z "$PYTHON_BIN" ]; then
    echo -e "${RED}[ERROR] Python 3 is not installed or not in PATH.${NC}"
    echo "Please install Python 3.8+ before running this script."
    echo ""
    echo "Quick install commands:"
    echo "  - Debian/Ubuntu: sudo apt update && sudo apt install -y python3 python3-pip python3-venv"
    echo "  - Fedora/RHEL:   sudo dnf install -y python3 python3-pip"
    echo "  - Arch Linux:    sudo pacman -S python python-pip"
    echo "  - macOS:         brew install python"
    echo ""
    read -r -p "Would you like to attempt automatic installation of Python? (y/N): " install_py
    if [[ "$install_py" =~ ^[Yy]$ ]]; then
        if command -v apt-get &> /dev/null; then
            sudo apt update && sudo apt install -y python3 python3-pip python3-venv
            PYTHON_BIN="python3"
        elif command -v dnf &> /dev/null; then
            sudo dnf install -y python3 python3-pip
            PYTHON_BIN="python3"
        elif command -v pacman &> /dev/null; then
            sudo pacman -S --noconfirm python python-pip
            PYTHON_BIN="python3"
        elif command -v brew &> /dev/null; then
            brew install python
            PYTHON_BIN="python3"
        else
            echo -e "${RED}[ERROR] Package manager not recognized. Please install Python manually.${NC}"
            exit 1
        fi
    else
        exit 1
    fi
fi

echo -e "${GREEN}[✓] Python found:${NC} $($PYTHON_BIN --version)"

# 2. Check and Install pip
PIP_AVAILABLE=false
if $PYTHON_BIN -m pip --version &> /dev/null; then
    PIP_AVAILABLE=true
elif command -v pip3 &> /dev/null; then
    PIP_AVAILABLE=true
elif command -v pip &> /dev/null; then
    PIP_AVAILABLE=true
fi

if [ "$PIP_AVAILABLE" = false ]; then
    echo -e "${YELLOW}[!] pip is not installed.${NC}"
    
    echo "Attempting to bootstrap pip via ensurepip..."
    if $PYTHON_BIN -m ensurepip --default-pip &> /dev/null; then
        PIP_AVAILABLE=true
        echo -e "${GREEN}[✓] pip bootstrapped successfully.${NC}"
    else
        read -r -p "Would you like to install pip using your system package manager? (y/N): " install_pip_pkg
        if [[ "$install_pip_pkg" =~ ^[Yy]$ ]]; then
            if command -v apt-get &> /dev/null; then
                sudo apt update && sudo apt install -y python3-pip python3-venv
                PIP_AVAILABLE=true
            elif command -v dnf &> /dev/null; then
                sudo dnf install -y python3-pip
                PIP_AVAILABLE=true
            elif command -v pacman &> /dev/null; then
                sudo pacman -S --noconfirm python-pip
                PIP_AVAILABLE=true
            elif command -v brew &> /dev/null; then
                brew install python
                PIP_AVAILABLE=true
            else
                echo "Trying to install pip via get-pip.py..."
                if command -v curl &> /dev/null; then
                    curl -sS https://bootstrap.pypa.io/get-pip.py | $PYTHON_BIN
                    PIP_AVAILABLE=true
                elif command -v wget &> /dev/null; then
                    wget -qO- https://bootstrap.pypa.io/get-pip.py | $PYTHON_BIN
                    PIP_AVAILABLE=true
                fi
            fi
        fi
    fi
    
    if [ "$PIP_AVAILABLE" = false ]; then
        echo -e "${RED}[ERROR] pip is not installed. Please install Python and pip first.${NC}"
        echo ""
        echo "Installation commands:"
        echo "  - Debian/Ubuntu: sudo apt install -y python3-pip python3-venv"
        echo "  - Fedora:        sudo dnf install -y python3-pip"
        echo "  - Arch Linux:    sudo pacman -S python-pip"
        echo "  - macOS:         brew install python"
        exit 1
    fi
fi

# 3. Install Python Dependencies
echo ""
echo "Installing Python dependencies..."
INSTALL_SUCCESS=false

# Try standard pip install first
if $PYTHON_BIN -m pip install -r requirements.txt 2>/dev/null; then
    INSTALL_SUCCESS=true
elif command -v pip3 &> /dev/null && pip3 install -r requirements.txt 2>/dev/null; then
    INSTALL_SUCCESS=true
elif command -v pip &> /dev/null && pip install -r requirements.txt 2>/dev/null; then
    INSTALL_SUCCESS=true
fi

# If direct install failed (e.g. externally-managed-environment PEP 668), fallback to virtual environment (.venv)
if [ "$INSTALL_SUCCESS" = false ]; then
    echo -e "${YELLOW}[!] Direct pip install failed (e.g. system-managed environment). Setting up virtual environment (.venv)...${NC}"
    
    if [ ! -d ".venv" ]; then
        $PYTHON_BIN -m venv .venv || {
            echo -e "${RED}[ERROR] Failed to create virtual environment. Ensure python3-venv is installed.${NC}"
            echo "Run: sudo apt install -y python3-venv (Debian/Ubuntu)"
            exit 1
        }
    fi
    
    # Activate virtual environment
    # shellcheck disable=SC1091
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    INSTALL_SUCCESS=true
    echo -e "${GREEN}[✓] Dependencies installed in virtual environment (.venv).${NC}"
else
    echo -e "${GREEN}[✓] Dependencies installed successfully.${NC}"
fi

# 4. Configure .env file
echo ""
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${GREEN}[✓] Created .env from .env.example.${NC}"
        
        read -r -p "Enter your NVIDIA API Key (leave empty to configure later): " user_api_key
        if [ -n "$user_api_key" ]; then
            if grep -q "NVIDIA_API_KEY=" .env; then
                sed -i "s/^NVIDIA_API_KEY=.*/NVIDIA_API_KEY=$user_api_key/" .env
            else
                echo "NVIDIA_API_KEY=$user_api_key" >> .env
            fi
            echo -e "${GREEN}[✓] NVIDIA_API_KEY saved to .env${NC}"
        else
            echo -e "${YELLOW}[!] Please remember to set your NVIDIA_API_KEY in .env before running.${NC}"
        fi
    fi
else
    echo -e "${GREEN}[✓] .env file already exists.${NC}"
fi

# 5. PM2 Setup & Background Execution
echo ""
if command -v pm2 &> /dev/null; then
    echo -e "${GREEN}[✓] PM2 is installed on your system.${NC}"
    read -r -p "Do you want to start nim-router in the background with PM2 now? (y/N): " start_pm2
    if [[ "$start_pm2" =~ ^[Yy]$ ]]; then
        if [ -f ecosystem.config.js ]; then
            pm2 start ecosystem.config.js
        else
            if [ -d ".venv" ]; then
                pm2 start nim-router.py --name nim-router --interpreter .venv/bin/python
            else
                pm2 start nim-router.py --name nim-router --interpreter "$PYTHON_BIN"
            fi
        fi
        echo -e "${GREEN}[✓] nim-router started in background with PM2.${NC}"
        echo "Use 'pm2 logs nim-router' to view logs or 'pm2 stop nim-router' to stop."
    else
        echo -e "${GREEN}Setup complete!${NC} You can start the server anytime with: python nim-router.py"
    fi
else
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
                    if [ -d ".venv" ]; then
                        pm2 start nim-router.py --name nim-router --interpreter .venv/bin/python
                    else
                        pm2 start nim-router.py --name nim-router --interpreter "$PYTHON_BIN"
                    fi
                fi
                echo -e "${GREEN}[✓] nim-router started in background with PM2.${NC}"
                echo "Use 'pm2 logs nim-router' to view logs."
            fi
        else
            echo -e "${YELLOW}[WARNING] npm was not found. Please install Node.js / npm first to install PM2.${NC}"
            echo "You can still run the router directly with: python nim-router.py"
        fi
    else
        echo -e "${GREEN}Setup complete!${NC} You can start the router with: python nim-router.py"
    fi
fi

