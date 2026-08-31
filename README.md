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

## Quick Start (Recommended Installation)

Run the single-line command for your operating system / terminal:

### **Linux / macOS / Git Bash / WSL (Recommended)**:
```bash
git clone https://github.com/PatrickLmbn/nim-router.git && cd nim-router && bash install.sh
```

### **Windows Command Prompt (`cmd.exe`)**:
```cmd
git clone https://github.com/PatrickLmbn/nim-router.git && cd nim-router && install.bat
```

### **Windows PowerShell**:
```powershell
git clone https://github.com/PatrickLmbn/nim-router.git; cd nim-router; .\install.bat
```

> **Note**: The installer interactively prompts for your **NVIDIA API Keys**, **OpenRouter API Key**, and **OpenCode API Key**.

---

## Features

- **Universal Free Multi-Provider Support**:
  - **NVIDIA NIM Free Tier** (`NVIDIA_API_KEYS` / `NVIDIA_API_KEY`)
  - **OpenRouter Free Tier** (`OPENROUTER_API_KEY` - automatically pools all `:free` models)
  - **OpenCode API** (`OPENCODE_API_KEY`)
- **Primary Model Priority with Free Fallback**: Set any discovered free model as your primary priority model. If it encounters rate limits (`429`), out-of-credits (`402`), or server errors (`5xx`), `nim` automatically fails over to the lowest-latency free models across providers with zero downtime.
- **Unified Virtual Model (`nim-free` / `auto`)**: Send requests to `nim-free` or `auto` that automatically load-balances across all healthy free models ranked by real-time latency, generation speed, and reliability.
- **Maximum Latency Threshold Filtering (`MAX_LATENCY_THRESHOLD=3.0`s)**: Restricts active pool to endpoints responding in under 3.0 seconds, automatically filtering out congested/overloaded server endpoints.
- **Dynamic EMA Reliability Scoring (0.05–1.0)**: Tracks real-time model stability over time using Exponential Moving Average (EMA) scoring to downweight unstable endpoints smoothly.
- **Tokens-Per-Second (TPS) Speed Ranking**: Measures actual text generation throughput (tokens/second) to rank fast-generating endpoints first.
- **Large Context Window Matching**: Automatically detects large prompts (>16,000 tokens) and isolates the pool to 128k+ context models to prevent context-limit errors.
- **Multi-Account API Key Round-Robin**: Automatically rotates requests across multiple configured NVIDIA API keys to multiply rate limits and bypass account throttling.
- **Interactive Model Selection CLI (`nim models`)**: View and set your primary priority free model interactively (with optional live probing scan).
- **Standalone Endpoint Probing CLI (`nim probe`)**: Perform full multi-provider live latency probing scans anytime.
- **Interactive Key Setup CLI (`nim connect`)**: Add or update API keys anytime without editing files manually.
- **Process Management CLI (`nim restart` / `nim stop`)**: Restart or stop background server processes instantly via PM2.
- **Stream Live Server Logs CLI (`nim logs`)**: Stream live PM2 background server logs directly in terminal.
- **CLI Command Help (`nim --help`)**: Comprehensive built-in documentation for all CLI commands.
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
               (Combined Latency + TPS Speed + EMA Reliability + <3.0s Threshold)
```

---

## CLI Usage (`nim`)

### **1. Set Primary Priority Model (`nim models`)**
```bash
nim models
```

### **2. Probe Endpoints (`nim probe`)**
```bash
nim probe
```

### **3. Configure API Keys (`nim connect`)**
```bash
nim connect
```

### **4. Restart Server (`nim restart`)**
```bash
nim restart
```

### **5. Stop Server (`nim stop`)**
```bash
nim stop
```

### **6. Stream Server Logs (`nim logs`)**
```bash
nim logs
```

### **7. Command Help (`nim --help`)**
```bash
nim --help
```
