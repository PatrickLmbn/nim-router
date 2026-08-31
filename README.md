# Universal Multi-Provider Free Model Router

A lightweight, OpenAI-compatible proxy router that aggregates, load-balances, and fails over across **NVIDIA NIM Free Tier**, **OpenRouter Free Tier**, and **OpenCode API**. It turns free tier AI endpoints into a single, high-availability, ultra-low latency API endpoint with dynamic latency ranking, account key rotation, and zero-downtime cross-provider failover.

> **Note**: `nim-router` is designed specifically for free-tier model aggregation across providers. It automatically discovers, probes, and load-balances working free models.

---

## Features

- **Universal Free Multi-Provider Support**:
  - **NVIDIA NIM Free Tier** (`NVIDIA_API_KEYS` / `NVIDIA_API_KEY`)
  - **OpenRouter Free Tier** (`OPENROUTER_API_KEY` - automatically pools all `:free` models)
  - **OpenCode API** (`OPENCODE_API_KEY`)
- **Primary Model Priority with Free Fallback**: Set any discovered free model as your primary priority model. If it encounters rate limits (`429`), out-of-credits (`402`), or server errors (`5xx`), `nim-router` automatically fails over to the lowest-latency free models across providers with zero downtime.
- **Unified Virtual Model (`nim-free` / `auto`)**: Send requests to a single model identifier that automatically load-balances across all healthy free models ranked by real-time latency, generation speed, and reliability.
- **Dynamic EMA Reliability Scoring (0.05–1.0)**: Tracks real-time model stability over time using Exponential Moving Average (EMA) scoring to downweight unstable endpoints smoothly.
- **Tokens-Per-Second (TPS) Speed Ranking**: Measures actual text generation throughput (tokens/second) to rank fast-generating endpoints first.
- **Large Context Window Matching**: Automatically detects large prompts (>16,000 tokens) and isolates the pool to 128k+ context models to prevent context-limit errors.
- **Multi-Account API Key Round-Robin**: Automatically rotates requests across multiple configured NVIDIA API keys to multiply rate limits and bypass account throttling.
- **Interactive Model Selection CLI (`nim-router models`)**: View and set your primary priority free model interactively (with optional live probing scan).
- **Standalone Endpoint Probing CLI (`nim-router probe`)**: Perform full multi-provider live latency probing scans anytime.
- **Interactive Key Setup CLI (`nim-router connect`)**: Add or update API keys anytime without editing files manually.
- **Process Management CLI (`nim-router restart` / `nim-router stop`)**: Restart or stop background server processes instantly via PM2.
- **Stream Live Server Logs CLI (`nim-router logs`)**: Stream live PM2 background server logs directly in terminal.
- **CLI Command Help (`nim-router --help`)**: Comprehensive built-in documentation for all CLI commands.
- **Multimodal & Vision Support**: Automatically isolates and routes image payloads (`image_url`, base64) to vision-capable models.
- **Tool-Calling Compatibility**: Isolates tool-enabled requests to models supporting function calling.
- **Real-Time Token Streaming (SSE)**: Full Server-Sent Events support for streaming responses in interactive applications and AI coding assistants.

---

## Core Architecture

```text
Client Request (model: "nim-free" or "auto")
        │
        ▼
[Primary Model Configured?]
   ├── YES ──► Try Primary Free Model (e.g., openai/gpt-oss-120b, meta/llama-3.3-70b-instruct)
   │               │
   │               ├── 200 OK ──► Return Stream / Response
   │               └── 402/429/5xx ──► [Failover to Free Pool]
   │
   └── NO / Fallback ──► [Discover & Rank Healthy Free Models]
                            (NVIDIA NIM + OpenRouter Free + OpenCode)
                                       │
                                       ▼
                       [Route to Highest Ranked Free Model]
               (Combined Latency + TPS Speed + EMA Reliability)
```

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

**Windows (Command Prompt / PowerShell):**
```cmd
git clone https://github.com/patricklmbn/nim-router.git
cd nim-router
install.bat
```

> The installer interactively prompts for your **NVIDIA API Keys**, **OpenRouter API Key**, and **OpenCode API Key**.

---

## CLI Usage (`nim-router`)

You can control `nim-router` directly from your terminal:

### **1. Set Primary Priority Model (`nim-router models`)**
```bash
nim-router models
```
- Asks user whether to run live probing scan first (Recommended, optional).
- Displays provider-categorized terminal menu (`--- NVIDIA NIM Models ---`, `--- OpenRouter Free Models ---`, `--- OpenCode Models ---`).
- Select your primary model or choose `[0] nim-free` for auto free pool rotation.

### **2. Probe Endpoints (`nim-router probe`)**
```bash
nim-router probe
```
- Performs a live probing scan across all configured provider endpoints (NVIDIA, OpenRouter, OpenCode).
- Saves discovered working models to `config/models_status.json`.
- Refreshes the active pool of the live running `nim-router` server process.

### **3. Configure API Keys (`nim-router connect`)**
```bash
nim-router connect
```
- Interactive step-by-step prompts for NVIDIA, OpenRouter, and OpenCode API keys.
- Shows masked current key status.
- Automatically saves to `.env` and refreshes the live router server.

### **4. Restart Server (`nim-router restart`)**
```bash
nim-router restart
```
- Restarts the background `nim-router` server process via PM2.

### **5. Stop Server (`nim-router stop`)**
```bash
nim-router stop
```
- Stops the background `nim-router` server process via PM2.

### **6. Stream Server Logs (`nim-router logs`)**
```bash
nim-router logs
```
- Streams live background server logs from PM2 directly in terminal.

### **7. Command Help (`nim-router --help`)**
```bash
nim-router --help
```
- Displays built-in CLI command menu and usage examples.

---

## Quick API Example

### 1. Standard Request (Auto Free Pool Rotation)
```bash
curl -X POST http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local" \
  -d '{
    "model": "nim-free",
    "messages": [{"role": "user", "content": "Explain quantum computing in one sentence."}]
  }'
```
