# Universal Multi-Provider Free Model Router

A lightweight, OpenAI-compatible proxy router that aggregates, load-balances, and fails over across **NVIDIA NIM**, **OpenRouter Free Tier**, and **OpenCode API**. It turns free and paid AI endpoints into a single, high-availability, ultra-low latency API endpoint with dynamic latency ranking, account key rotation, and zero-downtime cross-provider failover.

---

## Features

- **Universal Multi-Provider Support**:
  - **NVIDIA NIM Free Tier** (`NVIDIA_API_KEYS` / `NVIDIA_API_KEY`)
  - **OpenRouter Free Tier** (`OPENROUTER_API_KEY` - automatically pools all `:free` models)
  - **OpenCode API** (`OPENCODE_API_KEY`)
- **Primary Model Priority with Free Fallback**: Set any model (free or paid) as your primary priority model. If it encounters rate limits (`429`), out-of-credits (`402`), or server errors (`5xx`), `nim-router` automatically fails over to the lowest-latency free models across providers with zero downtime.
- **Unified Virtual Model (`nim-free` / `auto`)**: Send requests to a single model identifier that automatically load-balances across all healthy free models ranked by real-time latency.
- **Interactive Model Selection CLI (`nim-router models`)**: Easily view and set your primary priority model interactively from any terminal.
- **Multi-Account API Key Rotation**: Rotate up to 3 NVIDIA API keys to multiply rate limits and bypass account-level throttling.
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
   ├── YES ──► Try Primary Model (e.g., anthropic/claude-3.5-sonnet, meta/llama-3.3-70b-instruct)
   │               │
   │               ├── 200 OK ──► Return Stream / Response
   │               └── 402/429/5xx ──► [Failover to Free Pool]
   │
   └── NO / Fallback ──► [Discover & Rank Healthy Models]
                            (NVIDIA NIM + OpenRouter Free + OpenCode)
                                       │
                                       ▼
                       [Route to Lowest-Latency Model]
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

### **Set Primary Priority Model**
```bash
nim-router models
```
- Scans all configured providers.
- Displays a clean numbered terminal menu of active models.
- Select your primary model or select `[0] nim-free` for automatic free pool rotation.
- Automatically updates `.env` and refreshes the live router server.

---

## Quick API Example

### 1. Standard Request (Auto Free Pool Rotation)
```bash
curl -X POST http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local" \
  -d '{
    "model": "nim-free",
    "messages": [{"role": "user", "content": "Hello!"}],
    "temperature": 0.7
  }'
```

### 2. Direct Custom Model Request (With Free Fallback)
```bash
curl -X POST http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local" \
  -d '{
    "model": "anthropic/claude-3.5-sonnet",
    "messages": [{"role": "user", "content": "Write a python script"}],
    "stream": true
  }'
```

---

## Connecting to AI Agents & Harnesses

The router exposes a standard OpenAI-compatible API base URL (`http://localhost:11435/v1`).

### 1. Hermes Agent
```yaml
providers:
  nim-router:
    base_url: "http://localhost:11435/v1"
    model: "nim-free"
    api_key: "local"
```

### 2. Coding Harnesses (Aider, Cline, Continue.dev)
```json
{
  "api_base": "http://localhost:11435/v1",
  "api_key": "local",
  "model": "nim-free",
  "stream": true
}
```

### 3. OpenAI Python SDK
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11435/v1",
    api_key="local"
)

response = client.chat.completions.create(
    model="nim-free",
    messages=[
        {"role": "user", "content": "Explain binary search in Python."}
    ],
    stream=True
)

for chunk in response:
    content = chunk.choices[0].delta.content
    if content:
        print(content, end="", flush=True)
print()
```

---

## Environment Configuration (`.env`)

| Variable | Description | Default |
| :--- | :--- | :--- |
| `NVIDIA_API_KEYS` | Comma-separated list of NVIDIA NIM API keys (up to 3 for rotation) | `""` |
| `OPENROUTER_API_KEY` | OpenRouter API key for `:free` models | `""` |
| `OPENCODE_API_KEY` | OpenCode API key | `""` |
| `PRIMARY_MODEL` | Primary model preference (e.g. `anthropic/claude-3.5-sonnet`, `meta/llama-3.3-70b-instruct`) | `nim-free` |
| `PORT` | Local port for proxy server | `11435` |

---

## API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/v1/chat/completions` | `POST` | OpenAI-compatible chat completion endpoint (supports streaming) |
| `/v1/models` | `GET` | Returns list of currently active models across all providers |
| `/health` | `GET` | Health check endpoint reporting active pool size |
| `/refresh` | `POST` | Triggers immediate re-discovery and probing of model endpoints |

---

## Diagnostics & Testing

Run unit test suite:
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```
