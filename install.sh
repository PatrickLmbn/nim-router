#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
CYAN="\033[1;36m"
RED="\033[0;31m"
NC="\033[0m"

echo -e "${CYAN}"
echo " ________   ___  _____ ______   "
echo "|\   ___  \|\  \|\   _ \  _   \  "
echo "\ \  \\\\ \  \ \  \ \  \\\\\__\ \  \ "
echo " \ \  \\\\ \  \ \  \ \  \\|__| \  \ "
echo "  \ \  \\\\ \  \ \  \ \  \    \ \  \ "
echo "   \ \__\ \__\ \__\ \__\    \ \__\\"
echo "    \|__| \|__|\|__|\|__|     \|__|"
echo "            R O U T E R"
echo -e "${NC}\n"
echo -e "${BOLD}=== Universal Multi-Provider Free Model Router ===${NC}\n"

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

echo ""
echo "Installing Python dependencies..."
INSTALL_SUCCESS=false

if $PYTHON_BIN -m pip install -r requirements.txt 2>/dev/null; then
    INSTALL_SUCCESS=true
elif command -v pip3 &> /dev/null && pip3 install -r requirements.txt 2>/dev/null; then
    INSTALL_SUCCESS=true
elif command -v pip &> /dev/null && pip install -r requirements.txt 2>/dev/null; then
    INSTALL_SUCCESS=true
fi

if [ "$INSTALL_SUCCESS" = false ]; then
    echo -e "${YELLOW}[!] Direct pip install failed (e.g. system-managed environment). Setting up virtual environment (.venv)...${NC}"
    
    if [ ! -d ".venv" ]; then
        $PYTHON_BIN -m venv .venv || {
            echo -e "${RED}[ERROR] Failed to create virtual environment. Ensure python3-venv is installed.${NC}"
            echo "Run: sudo apt install -y python3-venv (Debian/Ubuntu)"
            exit 1
        }
    fi
    
    # shellcheck disable=SC1091
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    python -m pip install -e . 2>/dev/null || true
    INSTALL_SUCCESS=true
    echo -e "${GREEN}[✓] Dependencies installed in virtual environment (.venv).${NC}"
else
    $PYTHON_BIN -m pip install -e . 2>/dev/null || true
    echo -e "${GREEN}[✓] Dependencies installed successfully.${NC}"
fi

echo ""
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${GREEN}[✓] Created .env from .env.example.${NC}"
        
        echo -e "${BOLD}=== Multi-Provider API Key & Virtual Model Setup ===${NC}"
        read -r -p "Enter custom virtual model name (Press Enter for default: nim-free): " v_model_input
        echo ""
        read -r -s -p "Enter Primary NVIDIA API Key #1 (Recommended): " key1
        echo ""
        read -r -s -p "Enter Secondary NVIDIA API Key #2 (Optional - press Enter to skip): " key2
        echo ""
        read -r -s -p "Enter OpenRouter API Key (Optional - press Enter to skip): " or_key
        echo ""
        read -r -s -p "Enter OpenCode API Key (Optional - press Enter to skip): " opencode_key
        echo ""

        [ -z "$v_model_input" ] && v_model_input="nim-free"
        if grep -q "VIRTUAL_MODEL_NAME=" .env; then
            sed -i "s/^VIRTUAL_MODEL_NAME=.*/VIRTUAL_MODEL_NAME=$v_model_input/" .env
        else
            echo "VIRTUAL_MODEL_NAME=$v_model_input" >> .env
        fi

        keys_combined=""
        [ -n "$key1" ] && keys_combined="$key1"
        if [ -n "$key2" ]; then
            [ -n "$keys_combined" ] && keys_combined="$keys_combined,$key2" || keys_combined="$key2"
        fi

        if [ -n "$keys_combined" ]; then
            if grep -q "NVIDIA_API_KEYS=" .env; then
                sed -i "s/^NVIDIA_API_KEYS=.*/NVIDIA_API_KEYS=$keys_combined/" .env
            else
                echo "NVIDIA_API_KEYS=$keys_combined" >> .env
            fi
        fi

        if [ -n "$or_key" ]; then
            if grep -q "OPENROUTER_API_KEY=" .env; then
                sed -i "s/^OPENROUTER_API_KEY=.*/OPENROUTER_API_KEY=$or_key/" .env
            else
                echo "OPENROUTER_API_KEY=$or_key" >> .env
            fi
        fi

        if [ -n "$opencode_key" ]; then
            if grep -q "OPENCODE_API_KEY=" .env; then
                sed -i "s/^OPENCODE_API_KEY=.*/OPENCODE_API_KEY=$opencode_key/" .env
            else
                echo "OPENCODE_API_KEY=$opencode_key" >> .env
            fi
        fi

        echo -e "${GREEN}[✓] Saved configured virtual model name and API key(s) to .env${NC}"
    fi
else
    echo -e "${GREEN}[✓] .env file already exists.${NC}"
fi

echo ""
mkdir -p "$HOME/.local/bin"
cat << EOF > "$HOME/.local/bin/nim"
#!/usr/bin/env bash
cd "$DIR" || exit 1
if [ -f "$DIR/.venv/bin/python" ]; then
    exec "$DIR/.venv/bin/python" "$DIR/nim-router.py" "\$@"
else
    exec python3 "$DIR/nim-router.py" "\$@"
fi
EOF
cp "$HOME/.local/bin/nim" "$HOME/.local/bin/nimrouter"
cp "$HOME/.local/bin/nim" "$HOME/.local/bin/nim-router"
chmod +x "$DIR/nim-router.py" "$HOME/.local/bin/nim" "$HOME/.local/bin/nimrouter" "$HOME/.local/bin/nim-router" 2>/dev/null || true

if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    export PATH="$HOME/.local/bin:$PATH"
    if [ -f "$HOME/.zshrc" ] && ! grep -q '\.local/bin' "$HOME/.zshrc'; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
    fi
    if [ -f "$HOME/.bashrc" ] && ! grep -q '\.local/bin' "$HOME/.bashrc"; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    fi
fi

echo -e "${GREEN}[✓] Installed 'nim' CLI command to ~/.local/bin/nim.${NC}"

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
        echo "Use 'nim logs' to view logs or 'nim stop' to stop."
    else
        echo -e "${GREEN}Setup complete!${NC} You can start the server anytime with: nim"
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
                echo "Use 'nim logs' to view logs."
            fi
        else
            echo -e "${YELLOW}[WARNING] npm was not found. Please install Node.js / npm first to install PM2.${NC}"
            echo "You can still run the router directly with: nim"
        fi
    else
        echo -e "${GREEN}Setup complete!${NC} You can start the router with: nim"
    fi
fi
