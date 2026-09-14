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

A lightweight, high-performance, OpenAI- and Ollama-compatible proxy router that aggregates, load-balances, and fails over across **NVIDIA NIM Free Tier**, **Groq LPU Free Tier**, **Cerebras Wafer-Scale Free Tier**, **OpenRouter Free Tier**, **OpenCode API**, and **B.AI Free Tier**.

It turns free-tier AI endpoints into a single, high-availability, ultra-low latency API endpoint (`http://localhost:11435/v1`) with dynamic latency ranking, TPS speed benchmarking, Exponential Moving Average (EMA) reliability scoring, account key rotation, custom model combos, and zero-downtime cross-provider failover.

---

## Quick Start (Recommended Installation)

Run the single-line command for your operating system:

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

> **Tip**: The installer interactively prompts for your provider credentials. Use `nim keys` or the built-in Web UI anytime to add multiple keys per provider for automatic key rotation!

---

## Key Features

### 1. Universal Multi-Provider Aggregation
- **NVIDIA NIM Free Tier** (`NVIDIA_API_KEYS` / `NVIDIA_API_KEY`)
- **Groq LPU Free Tier** (`GROQ_API_KEYS` / `GROQ_API_KEY` - 500+ tokens/sec)
- **Cerebras Wafer-Scale Free Tier** (`CEREBRAS_API_KEYS` / `CEREBRAS_API_KEY` - 1800+ tokens/sec)
- **OpenRouter Free Tier** (`OPENROUTER_API_KEY` - auto-pools all `:free` models)
- **OpenCode API** (`OPENCODE_API_KEY`)
- **B.AI Free Tier** (`BAI_API_KEY` - GLM, Qwen, and Hunyuan endpoints)

### 2. Purpose-Based Virtual Category Models
Target high-level capabilities in your agent or application without hardcoding specific model identifiers:
- **`nim-auto`** / **`nim-free`**: Universal lowest-latency auto-balancer across all healthy endpoints in the pool.
- **`nim-coding`**: Prioritizes code-specialized models (Codestral, DeepSeek Coder, StarCoder, Qwen Coder, etc.).
- **`nim-reasoning`**: Prioritizes complex reasoning, math, and logic models (DeepSeek R1, QwQ, etc.).
- **`nim-tools`**: Isolates pool to models verified for function/tool calling (Llama 3.1/3.2/3.3, Qwen 2.5, Mistral, Hermes, etc.).
- **`nim-vision`**: Prioritizes multimodal and image-capable models (Llama 3.2 Vision, Pixtral, etc.).
- **`nim-moe`**: Prioritizes Mixture-of-Experts architectures (Mixtral, DeepSeek V3/V4, DBRX, etc.).
- **`nim-chat`**: Prioritizes fast instruction and conversational models.

### 3. Custom Model Combos
Define custom, named multi-model groups with tailored routing policies:
- Group models by project, team, or speed requirements (e.g. `fast-coder`, `heavy-reasoning`).
- Choose between **`fallback`** (strict priority order with error failover) or **`round_robin`** (load distribution).
- Seamless integration: specify `"model": "your-combo-name"` in any standard OpenAI request.
- Automatic safety net: if all models in a combo fail or rate-limit, the router automatically cascades back to the healthy `nim-auto` pool.

### 4. Zero-Downtime Resilience & Routing Intelligence
- **Payload-Driven Vision Guard**: Inspects incoming messages for image URLs or base64 attachments; automatically routes to vision-capable endpoints to prevent 400/500 errors on text models.
- **Cascading Fallback**: Catches `400`, `402`, `404`, `429`, `500`, `502`, and `503` errors and instantly retries the next best candidate endpoint with sub-millisecond overhead.
- **Per-Key Rotation & Cooldowns**: Cycles requests across multiple comma-separated keys per provider. Parses `Retry-After` headers and applies exponential backoff on rate-limited keys while keeping healthy keys active.
- **Model Family Fallback**: Automatically identifies model families (Qwen, Llama, Nemotron, DeepSeek, Mistral, Gemma, Phi, etc.) and prioritizes fallback to same-family variants.
- **Dynamic EMA Reliability Scoring (0.05–1.0)**: Uses Exponential Moving Averages to dynamically score endpoint stability and downweight unstable models.
- **Throughput (TPS) & Latency Ranking**: Combines live latency benchmarks and tokens-per-second throughput to prioritize the fastest endpoints.
- **Large Context Window Isolation**: Detects prompts exceeding 16,000 tokens and routes exclusively to models supporting large context windows (128k+).
- **Maximum Latency Filtering (`MAX_LATENCY_THRESHOLD=3.0s`)**: Excludes overloaded or congested endpoints from the active routing pool.

### 5. Built-in Web Dashboard (`http://localhost:11435`)
A modern, dark/light Neumorphic dashboard served directly by the router:
- **Featured Route & Live Test**: Test your primary model with real-time latency and TPS calculation.
- **Background Health Prober Dial**: Visual countdown to the next automated probe cycle with active provider badges.
- **Combos Manager**: Create, search, filter, edit, and delete named routing combos with health & latency alerts.
- **Live Server Logs**: Real-time log streaming powered by Server-Sent Events (SSE).
- **Live Key & Settings Management**: Add/remove/clear keys and tune routing parameters without restarting the server.

### 6. Dual API Protocol Compatibility
- **OpenAI Compatible**: `/v1/chat/completions`, `/v1/models`, `/chat/completions`, `/models`
- **Ollama Compatible**: `/api/tags`, `/api/show`, `/api/ps`, `/api/version` (enables seamless use with Open WebUI and Ollama-based harnesses)

---

## Core Architecture & Request Flow

```text
Client Request (e.g. model: "nim-coding", "my-combo", or "nim-auto")
         │
         ▼
[Payload Inspection & Vision Guard]
   ├── Image/Multimodal Payload? ──► Override Target to Vision-Capable Endpoints
   └── Text Payload ───────────────► Continue to Target & Category Matching
                                       │
                                       ▼
[Target Model, Combo, or Category Filter]
   ├── Named Model Combo? ─────────► Route Through Combo Models (Fallback or Round-Robin)
   ├── Purpose Category ("nim-tools") ─► Prioritize Filtered Category Models First
   ├── Specific Model Requested ───► Attempt Requested Model (or Same-Family Fallbacks)
   └── Universal ("nim-auto") ─────► Rank All Healthy Models Across Providers
                                       │
                                       ▼
                     [Score & Rank Active Candidate Pool]
             (Latency + TPS Speed + EMA Reliability + Concurrency Limits)
                                       │
                                       ▼
                     [Route to Highest Ranked Endpoint]
           (Per-Provider Key Rotation with Per-Key Cooldown Tracking)
                                       │
                                       ├── 200 OK ──► Return Response / SSE Stream
                                       └── 400/429/5xx ──► [Cascading Fallback to Next Candidate]
```

---

## Web UI Dashboard

Open your browser to:
```
http://localhost:11435
```

The Web UI allows you to:
1. **Manage API Keys**: Add, delete, and inspect keys for NVIDIA, Groq, Cerebras, OpenRouter, OpenCode, and B.AI in real time.
2. **Configure Combos**: Create custom multi-model combinations with visual health checks for unavailable or high-latency models.
3. **Tune Router Parameters**: Switch routing strategies (`fallback` vs `round_robin`), adjust max latency thresholds, and change probe intervals.
4. **Inspect Live Logs**: Watch request routing, failovers, and key rotations stream in real time.
5. **Quick Test**: Execute single-click completion tests measuring latency and tokens per second.

---

## Connecting to AI Agents & Harnesses

The router exposes a standard OpenAI-compatible API base URL at `http://localhost:11435/v1`. Use `"local"` (or any dummy string) as the API key.

### 1. Hermes Agent (Recommended)

**Interactive CLI Setup:**
```bash
hermes model
```
Choose **Custom Endpoint** and enter:
- **Base URL**: `http://localhost:11435/v1`
- **Model**: `nim-auto`, `nim-coding`, `nim-tools`, `nim-reasoning`, `nim-vision`, or custom combo
- **API Key**: `local`

**Or configure via `~/.hermes/config.yaml`:**
```yaml
providers:
  nim-router:
    base_url: "http://localhost:11435/v1"
    model: "nim-coding"
    api_key: "local"
```

### 2. Coding Assistants (Aider, Cline, Continue.dev, Roo Code)

Configure your harness to connect to the local OpenAI endpoint:
```json
{
  "model": "nim-coding",
  "apiBase": "http://localhost:11435/v1",
  "apiKey": "local"
}
```

### 3. Open WebUI (Ollama or OpenAI Mode)

- **As OpenAI Provider**: Set API URL to `http://localhost:11435/v1` with API Key `local`.
- **As Ollama Provider**: Set Ollama Base URL to `http://localhost:11435`. The router responds to `/api/tags` and `/api/show` automatically.

### 4. OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11435/v1",
    api_key="local"
)

# Streaming Chat Completion
response = client.chat.completions.create(
    model="nim-auto",
    messages=[{"role": "user", "content": "Write an async Python web scraper."}],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()
```

---

## CLI Usage (`nim`)

The `nim` command-line tool provides full control over the router and service lifecycle:

| Command | Alias | Description |
| :--- | :--- | :--- |
| `nim models` | `list`, `select` | Interactively select the primary priority model. |
| `nim keys` | `key` | View, add, delete, or clear multiple API keys per provider. |
| `nim connect` | `config` | Interactively configure primary credentials for each provider. |
| `nim strategy` | `mode` | Select routing strategy (`fallback` or `round_robin`). |
| `nim probe` | `scan` | Run on-demand probing benchmarks across all active endpoints. |
| `nim restart` | `reload` | Restart the background router process via PM2 (supports `--build`). |
| `nim start` | `server` | Start the background router process via PM2. |
| `nim stop` | `kill`, `down` | Stop the background router process. |
| `nim run` | `fg`, `foreground` | Run the server directly in the foreground on port 11435. |
| `nim build` | `ui` | Install frontend dependencies and build production UI assets. |
| `nim logs` | `log` | Stream live server logs in your terminal. |
| `nim --help` | `-h`, `help` | Display CLI help documentation. |

---

## Configuration Reference

### Environment Variables (`.env`)

```env
# Provider Credentials (comma-separated for key rotation)
NVIDIA_API_KEYS="nvapi-key1,nvapi-key2"
GROQ_API_KEYS="gsk_key1,gsk_key2"
CEREBRAS_API_KEYS="csk-key1,csk-key2"
OPENROUTER_API_KEY="sk-or-v1-..."
OPENCODE_API_KEY="your-opencode-key"
BAI_API_KEY="your-bai-key"

# Server Port
PORT=11435

# Default Model Override (optional)
PRIMARY_MODEL="nim-auto"
```

### Settings File (`config/settings.yaml`)

```yaml
primary_model: "nim-auto"
routing_strategy: "fallback"     # 'fallback' or 'round_robin'
max_latency_threshold: 3.0       # Exclude endpoints slower than 3.0s
health_refresh_interval: 180     # Background health probe cycle in seconds
rate_limit_cooldown: 30          # Fallback cooldown in seconds on 429 errors
primary_pool_size: 7             # Number of top models used for round_robin
model_max_rpm: 35                # Maximum requests per minute per endpoint
model_max_concurrency: 4         # Maximum in-flight requests per endpoint
fallback_models: []              # Custom fallback chain overrides
```

---

## API Endpoints Reference

### AI Completion & Model Endpoints
- `POST /v1/chat/completions` (or `/chat/completions`): OpenAI-compatible chat completion (streaming and non-streaming).
- `GET /v1/models` (or `/models`): List virtual categories, custom combos, and discovered healthy models.
  - Supports task filtering: `GET /v1/models?task=coding`, `?task=tools`, `?task=reasoning`, `?task=vision`.
- `GET /v1/models/{model_id}`: Retrieve model details.

### Ollama Compatibility Layer
- `GET /api/tags`: List models in Ollama tag format.
- `POST /api/show`: Model inspection details.
- `GET /api/ps`: Running processes status.
- `GET /api/version`: Gateway version.

### Management & Telemetry Endpoints
- `GET /api/dashboard/stats`: Complete gateway metrics, healthy pools, provider stats, and probe timers.
- `GET /api/keys`: Retrieve configured provider key counts and masked key identifiers.
- `POST /api/keys`: Add, update, remove, or clear API keys per provider in real time.
- `POST /api/settings`: Update router settings dynamically.
- `GET /api/combos`: List configured model combos with health and latency status.
- `POST /api/combos`: Create a new named model combo.
- `PUT /api/combos/{name}`: Update combo models or strategy (`fallback` / `round_robin`).
- `DELETE /api/combos/{name}`: Delete a combo.
- `POST /api/probe`: Trigger an immediate live probe benchmark across all provider endpoints.
- `GET /api/logs/stream`: Real-time Server-Sent Events (SSE) server log feed.
- `GET /api/logs/history`: Retrieve recent in-memory log buffer.
- `POST /api/server/restart`: Reload gateway configuration or restart background process via PM2.
- `GET /health`: Router health check status.

---

## Testing & Verification

### Chat Completion with Category Routing (`curl`)
```bash
curl http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nim-coding",
    "messages": [
      {"role": "user", "content": "Write a Python function to reverse a string."}
    ]
  }'
```

### Real-Time Token Streaming (`curl`)
```bash
curl http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nim-auto",
    "stream": true,
    "messages": [
      {"role": "user", "content": "Write a short haiku about low latency."}
    ]
  }'
```

### Function & Tool Calling (`curl`)
```bash
curl http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nim-tools",
    "messages": [
      {"role": "user", "content": "What is the weather in Tokyo?"}
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_weather",
          "description": "Get current weather for a city",
          "parameters": {
            "type": "object",
            "properties": {
              "city": {"type": "string"}
            },
            "required": ["city"]
          }
        }
      }
    ]
  }'
```

### Run Unit Tests
```bash
pytest
```

---

## License

MIT License. Designed for resilience, developer freedom, and zero-cost LLM orchestration.

