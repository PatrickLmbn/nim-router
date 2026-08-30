# NVIDIA NIM Free Model Router

A lightweight, OpenAI-compatible proxy router that aggregates and load-balances across all free NVIDIA NIM endpoints. It transforms NVIDIA's free model tier into a single, high-availability, low-latency API endpoint with dynamic latency-based routing and automatic multi-tier failover.

---

## Why NIM Router?

NVIDIA offers powerful free models on [build.nvidia.com](https://build.nvidia.com), but using them directly in production or agentic workflows introduces challenges:
- **Rate Limits (`429`)**: Individual free models quickly run out of request quota during heavy use.
- **Inconsistent Availability**: Endpoints can change, become deprecated (`404`), or experience temporary server outages (`5xx`).
- **Variable Latencies**: Response times vary significantly across models depending on server load.

**NIM Router solves this** by acting as an intelligent reverse proxy. Point your agents, coding assistants, or applications to `http://localhost:11435/v1` with model `nim-free`, and the router handles model discovery, latency ranking, load distribution, and multi-tier failover automatically.

---

## How It Works

```text
Client Request (model: "nim-free")
        │
        ▼
[Discover models from NVIDIA API]
        │
        ▼
[Minimal-scale probe to verify healthy endpoints]
        │
        ▼
[Rank by latency & select Top-3 priority tier]
        │
        ▼
[Route request to lowest-latency model] ──► Forward to NVIDIA NIM
        │
        ▼
     ┌──────┴──────┐
     ▼             ▼
  200 OK       400/422/429/5xx Error
     │             │
     ▼             ▼
[Return stream] [Failover to next fastest model]
                    (up to 3 attempts)
```

---

## Core Capabilities

- **Unified Virtual Model (`nim-free`)**: Send requests to a single model identifier that automatically rotates across all healthy free models.
- **Lowest-Latency Priority Routing**: Continuously measures and ranks model response times, prioritizing the 3 fastest responding models for incoming requests.
- **Adaptive Real-Time Latency Tracking (EMA)**: Dynamically recalculates moving average latency scores on live requests to adapt to changing server loads.
- **Zero-Downtime Automatic Failover**: Instantly catches HTTP `400`, `422`, `429`, and `5xx` errors and retries the request across alternate healthy models without dropping the connection.
- **Real-Time Token Streaming (SSE)**: Full Server-Sent Events support for streaming responses in interactive applications and agent interfaces.
- **Agent & Tool-Calling Compatibility**: Automatically isolates and routes tool-enabled requests to models with structured function-calling capabilities.
- **Message Normalization**: Automatically sanitizes empty or reasoning-only assistant message contents to prevent schema validation errors.

---

## Comparison to Alternatives

| Solution | Model Selection | Failover | Scope | Setup |
| :--- | :--- | :--- | :--- | :--- |
| **NIM Free Router** | **Lowest-Latency (Top-3 Tier)** | **Automatic (Multi-tier)** | NVIDIA NIM Free Tier | Local proxy (`python` / `pm2`) |
| OpenRouter `openrouter/free` | Remote load balancing | Automatic | 20+ hosted providers | Third-party cloud service |
| Manual model switching | Manual | None | Single model | Config change per model failure |

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
*(Or simply double-click `install.bat` in File Explorer)*


### 2. Manual Installation
If you prefer manual setup:
```bash
pip install -r requirements.txt
cp .env.example .env
```
Configure your settings in `.env`:
```env
NVIDIA_API_KEY=your_api_key
PORT=11435
MODEL=nim-free
```
> Obtain a free API key directly from [build.nvidia.com](https://build.nvidia.com/).

### 3. Starting the Server

**Option A: Foreground Execution**
```bash
python nim-router.py
```

**Option B: Background Execution via PM2**
```bash
pm2 start ecosystem.config.js
pm2 logs nim-router     # View live logs
pm2 stop nim-router     # Stop server
pm2 restart nim-router  # Restart server
```

---

## Connecting to AI Agents & Harnesses

The router exposes a standard OpenAI-compatible API base URL (`http://localhost:11435/v1`).

Because your real `NVIDIA_API_KEY` is loaded securely by the router from `.env`, your client applications only connect locally to the router and do not need your real key. You can use `"local"` as the API key in all client configurations.

### 1. Hermes Agent
Add the provider to `~/.hermes/config.yaml`:
```yaml
providers:
  nim-router:
    base_url: "http://localhost:11435/v1"
    model: "nim-free"
    api_key: "local"
```

### 2. Coding Harnesses (OpenCode, Aider, Cline, Continue.dev)
Configure your assistant or harness to use local custom OpenAI endpoints:
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

### 4. cURL
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

---

## Configuration Options

| Variable | Default | Description |
| :--- | :--- | :--- |
| `NVIDIA_API_KEY` | *(Required)* | Your NVIDIA NIM API key from build.nvidia.com |
| `PORT` | `11435` | Local port the proxy server listens on |
| `MODEL` | `nim-free` | Default virtual model alias for automatic routing |

---

## API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/v1/chat/completions` | `POST` | OpenAI-compatible chat completion endpoint (supports streaming) |
| `/v1/models` | `GET` | Returns list of currently active models in the healthy pool |
| `/health` | `GET` | Health check endpoint reporting pool size and server status |
| `/refresh` | `POST` | Triggers immediate re-discovery and probing of model endpoints |

---

## Diagnostics & Testing

- **Full Model Diagnostics**: Test all 80+ endpoints and generate a status report:
  ```bash
  python tests/probe_test.py
  ```
- **Benchmark Round-Robin**: Test completion responses and failover behavior:
  ```bash
  python tests/benchmark.py
  ```
