```text
 ________   ___  _____ ______   
|\   ___  \|\  \|\   _ \  _   \  
\ \  \\ \  \ \  \ \  \\\__\ \  \ 
 \ \  \\ \  \ \  \ \  \\|__| \  \ 
  \ \  \\ \  \ \  \ \  \    \ \  \ 
   \ \__\ \__\ \__\ \__\    \ \__\
    \|__| \|__|\|__|\|__|     \|__|
            R O U T E R
```

# Universal Multi-Provider Free Model Router

A lightweight, OpenAI-compatible proxy router that aggregates, load-balances, and fails over across **NVIDIA NIM Free Tier**, **OpenRouter Free Tier**, and **OpenCode API**. It turns free tier AI endpoints into a single, high-availability, ultra-low latency API endpoint with dynamic latency ranking, account key rotation, and zero-downtime cross-provider failover.

---

## Features

- **Universal Free Multi-Provider Support**:
  - **NVIDIA NIM Free Tier** (`NVIDIA_API_KEYS` / `NVIDIA_API_KEY`)
  - **OpenRouter Free Tier** (`OPENROUTER_API_KEY` - automatically pools all `:free` models)
  - **OpenCode API** (`OPENCODE_API_KEY`)
- **Custom Virtual Model Name (`VIRTUAL_MODEL_NAME`)**: Customize your virtual model alias during setup or anytime via `nimrouter name` (e.g. `nim-free`, `my-router`, `free-model`).
- **Primary Model Priority with Free Fallback**: Set any discovered free model as your primary priority model. If it encounters rate limits (`429`), out-of-credits (`402`), or server errors (`5xx`), `nimrouter` automatically fails over to the lowest-latency free models across providers with zero downtime.
- **Unified Virtual Model (`nim-free` / `auto` / Custom)**: Send requests to your custom virtual model identifier that automatically load-balances across all healthy free models ranked by real-time latency, generation speed, and reliability.
- **Maximum Latency Threshold Filtering (`MAX_LATENCY_THRESHOLD=3.0`s)**: Restricts active pool to endpoints responding in under 3.0 seconds, automatically filtering out congested/overloaded server endpoints.
- **Dynamic EMA Reliability Scoring (0.05–1.0)**: Tracks real-time model stability over time using Exponential Moving Average (EMA) scoring to downweight unstable endpoints smoothly.
- **Tokens-Per-Second (TPS) Speed Ranking**: Measures actual text generation throughput (tokens/second) to rank fast-generating endpoints first.
- **Large Context Window Matching**: Automatically detects large prompts (>16,000 tokens) and isolates the pool to 128k+ context models to prevent context-limit errors.
- **Multi-Account API Key Round-Robin**: Automatically rotates requests across multiple configured NVIDIA API keys to multiply rate limits and bypass account throttling.
- **Interactive Model Selection CLI (`nimrouter models`)**: View and set your primary priority free model interactively (with optional live probing scan).
- **Change Virtual Model Name CLI (`nimrouter name`)**: Set custom virtual model alias interactively anytime.
- **Standalone Endpoint Probing CLI (`nimrouter probe`)**: Perform full multi-provider live latency probing scans anytime.
- **Interactive Key Setup CLI (`nimrouter connect`)**: Add or update API keys anytime without editing files manually.
- **Process Management CLI (`nimrouter restart` / `nimrouter stop`)**: Restart or stop background server processes instantly via PM2.
- **Stream Live Server Logs CLI (`nimrouter logs`)**: Stream live PM2 background server logs directly in terminal.
- **CLI Command Help (`nimrouter --help`)**: Comprehensive built-in documentation for all CLI commands.
- **Multimodal & Vision Support**: Automatically isolates and routes image payloads (`image_url`, base64) to vision-capable models.
- **Tool-Calling Compatibility**: Isolates tool-enabled requests to models supporting function calling.
- **Real-Time Token Streaming (SSE)**: Full Server-Sent Events support for streaming responses in interactive applications and AI coding assistants.

---

## Quick Start

### 1. Automated Setup (Recommended)

Run the installation script for your operating system:

**Linux / macOS / WSL:**
```bash
git clone https://github.com/patricklmbn/nim-router.git
cd nim-router
bash install.sh
```

> The installer prompts for your **Custom Virtual Model Name**, **NVIDIA API Keys**, **OpenRouter API Key**, and **OpenCode API Key**.

---

## CLI Usage (`nimrouter`)

### **1. Change Virtual Model Name (`nimrouter name`)**
```bash
nimrouter name
```
- Customizes your virtual model alias (default: `nim-free`).

### **2. Set Primary Priority Model (`nimrouter models`)**
```bash
nimrouter models
```

### **3. Probe Endpoints (`nimrouter probe`)**
```bash
nimrouter probe
```

### **4. Configure API Keys (`nimrouter connect`)**
```bash
nimrouter connect
```

### **5. Restart Server (`nimrouter restart`)**
```bash
nimrouter restart
```

### **6. Stop Server (`nimrouter stop`)**
```bash
nimrouter stop
```

### **7. Stream Server Logs (`nimrouter logs`)**
```bash
nimrouter logs
```

### **8. Command Help (`nimrouter --help`)**
```bash
nimrouter --help
```
