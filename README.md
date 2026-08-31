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

A lightweight, OpenAI-compatible proxy router that aggregates, load-balances, and fails over across **NVIDIA NIM Free Tier**, **Groq LPU Free Tier**, **Cerebras Wafer-Scale Free Tier**, **OpenRouter Free Tier**, and **OpenCode API**. It turns free tier AI endpoints into a single, high-availability, ultra-low latency API endpoint with dynamic latency ranking, account key rotation, and zero-downtime cross-provider failover.

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

> **Note**: The installer interactively prompts for your **NVIDIA API Keys**, **Groq API Key**, **Cerebras API Key**, **OpenRouter API Key**, and **OpenCode API Key**.

---

## Features

- **Universal Free Multi-Provider Support**:
  - **NVIDIA NIM Free Tier** (`NVIDIA_API_KEY`)
  - **Groq LPU Free Tier** (`GROQ_API_KEY` - 500+ tokens/sec)
  - **Cerebras Wafer-Scale Free Tier** (`CEREBRAS_API_KEY` - 1800+ tokens/sec)
  - **OpenRouter Free Tier** (`OPENROUTER_API_KEY` - automatically pools all `:free` models)
  - **OpenCode API** (`OPENCODE_API_KEY`)
- **Purpose-Based Virtual Category Models**: Select specialized virtual model categories directly in your agent or harness:
  - **`nim-free`** (Universal lowest-latency auto-balancer across all free models)
  - **`nim-coding`** (Prioritizes code-specialized models: Codestral, DeepSeek Coder, StarCoder, Qwen Coder)
  - **`nim-reasoning`** (Prioritizes complex reasoning & math models: DeepSeek R1, QwQ, Reasoning models)
  - **`nim-vision`** (Prioritizes multimodal / image-capable models)
  - **`nim-moe`** (Prioritizes Mixture-of-Experts architectures)
  - **`nim-chat`** (Prioritizes fast conversational & instruction models)
- **Zero-Downtime Resilience & Routing Rules**:
  - **Payload-Driven Vision Override**: Image payloads (`image_url`, base64) automatically override model selection to vision-capable endpoints, preventing 400/500 errors on text models.
  - **Zero-Downtime Cascading Fallback**: If a targeted model or category model returns `400`, `404`, `429`, or `500`, the router automatically cascades through the remaining healthy models in the `nim-free` pool with zero downtime.
  - **Maximum Latency Threshold Filtering (`MAX_LATENCY_THRESHOLD=3.0`s)**: Restricts active pool to endpoints responding in under 3.0 seconds, automatically filtering out congested/overloaded server endpoints.
  - **Dynamic EMA Reliability Scoring (0.05–1.0)**: Tracks real-time model stability over time using Exponential Moving Average (EMA) scoring to downweight unstable endpoints smoothly.
  - **Tokens-Per-Second (TPS) Speed Ranking**: Measures actual text generation throughput (tokens/second) to rank fast-generating endpoints first.
  - **Multi-Account API Key Round-Robin**: Automatically rotates requests across multiple configured provider API keys to multiply rate limits and bypass account throttling.
  - **Large Context Window Matching**: Automatically detects large prompts (>16,000 tokens) and isolates the pool to 128k+ context models.
  - **Tool-Calling Compatibility**: Isolates tool-enabled requests to models supporting function calling.
  - **Real-Time Token Streaming (SSE)**: Full Server-Sent Events support for streaming responses in interactive applications and AI coding assistants.

---

## Core Architecture & Routing Rules

```text
Client Request (e.g. model: "nim-coding", "nim-reasoning", or "nim-free")
        │
        ▼
[Payload Inspection & Vision Guard]
   ├── Image/Multimodal Payload? ──► Override Target to Vision-Capable Endpoints
   └── Text Payload ───────────────► Continue to Purpose & Category Matching
                                       │
                                       ▼
[Purpose Category & Target Model Filter]
   ├── Purpose Category ("nim-coding") ─► Prioritize Category Models First
   ├── Specific Model Requested ────────► Attempt Targeted Model First
   └── Universal ("nim-free") ──────────► Rank All Healthy Models Across Providers
                                       │
                                       ▼
                       [Route to Highest Ranked Endpoint]
               (Combined Latency + TPS Speed + EMA Reliability + <3.0s Threshold)
                                       │
                                       ├── 200 OK ──► Return Response / Stream
                                       └── 400/429/5xx ──► [Cascading Fallback to Pool]
```

### **Summary of Routing Rules:**
1. **Vision Override Rule**: When an image or multimodal payload is detected in the prompt, `nim-router` automatically isolates candidates to vision-capable endpoints first, preventing unsupported payload errors on text-only models.
2. **Category Prioritization Rule**: Selecting a category (`nim-coding`, `nim-reasoning`, `nim-vision`, `nim-moe`, `nim-chat`) filters and orders candidate models best suited for the task.
3. **Cascading Fallback Rule**: If a requested model or category endpoint encounters rate limits (`429`), out-of-credits (`402`), not found (`404`), or server errors (`500`), `nim-router` automatically fails over to the next candidate model in the pool until a successful response is delivered.
4. **Key Rotation Rule**: Per-provider multi-account key round-robin ensures requests rotate across all configured API keys to maximize request throughput.

---

## Connecting to AI Agents & Harnesses

The router exposes a standard OpenAI-compatible API base URL (`http://localhost:11435/v1`).

Because your real API keys are loaded securely by the router from `.env`, your client applications only connect locally to the router and do not need your real key. You can use `"local"` as the API key in all client configurations.

### 1. Hermes Agent (Recommended)

**Option A: Interactive CLI Setup**
You can configure NIM Router interactively using the `hermes model` command:
```bash
hermes model
```
Choose **Custom Endpoint** and follow the prompts:
- **Base URL**: `http://localhost:11435/v1`
- **Model**: `nim-free`, `nim-coding`, `nim-reasoning`, `nim-vision`, `nim-moe`, or `nim-chat`
- **API Key**: `local` (optional)

**Option B: Manual Configuration (`~/.hermes/config.yaml`)**
Add the provider directly to `~/.hermes/config.yaml`:
```yaml
providers:
  nim-router:
    base_url: "http://localhost:11435/v1"
    model: "nim-coding"
    api_key: "local"
```

### 2. Coding Harnesses (Aider, Cline, Continue.dev)
Configure your assistant or harness to use local custom OpenAI endpoints:
```json
{
  "model": "nim-coding",
  "apiBase": "http://localhost:11435/v1",
  "apiKey": "local"
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
    model="nim-coding",
    messages=[{"role": "user", "content": "Write a python script to parse JSON"}],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()
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

---

## Testing API Endpoints (`curl`)

### **1. Chat Completion with Category Routing (`/v1/chat/completions`)**
```bash
curl http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nim-coding",
    "messages": [
      {"role": "user", "content": "Write a python function to reverse a string."}
    ]
  }'
```

### **2. Real-Time Token Streaming (`stream: true`)**
```bash
curl http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nim-free",
    "stream": true,
    "messages": [
      {"role": "user", "content": "Write a short poem about coding."}
    ]
  }'
```

### **3. List Available Models (`/v1/models`)**
```bash
curl http://localhost:11435/v1/models
```
