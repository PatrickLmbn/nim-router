# 🎬 Promotional Video Script: NVIDIA NIM Free Model Router

**Estimated Runtime:** ~2 Minutes 45 Seconds – 3 Minutes  
**Tone:** Fast-paced, punchy, developer-centric (Tech Showcase / Fireship style)  
**Target Audience:** AI Engineers, Autonomous Agent Builders (Hermes, Cline, Aider, Continue.dev, LangChain), and Open-Source Developers

---

## ⏱️ Video & Audio Timeline Breakdown

### **[0:00 - 0:25] THE HOOK: The Free AI Dilemma**
| Time | Visual / On-Screen Action (B-Roll) | Voiceover / Spoken Dialogue |
| :--- | :--- | :--- |
| **0:00** | Dramatic zoom-in on [build.nvidia.com](https://build.nvidia.com) showcasing 80+ state-of-the-art models (Llama 3.2, Nemotron, Gemma, DeepSeek, Minimax). | *"NVIDIA offers access to dozens of state-of-the-art foundation models on their NIM platform completely free. We’re talking high-parameter open-weights models, vision models, and reasoning engines."* |
| **0:10** | Quick montage of terminal error codes: `HTTP 429 Too Many Requests`, `500 Server Error`, broken agent loops, and stalled coding assistants. | *"But if you’ve ever plugged them into an AI agent, coding assistant, or production script, you know the pain: **Rate limits. Sudden 429s. Unpredictable latencies. And random endpoint outages that kill your workflow mid-task.**"* |
| **0:18** | Screen freezes on an error, then transitions with a glitch / swipe effect into a clean terminal. | *"What if you could turn that entire free model fleet into a **single, invincible, ultra-low-latency endpoint** that never goes down?"* |

---

### **[0:25 - 0:55] THE REVEAL: What is NIM Router?**
| Time | Visual / On-Screen Action (B-Roll) | Voiceover / Spoken Dialogue |
| :--- | :--- | :--- |
| **0:25** | Sleek animated title card: **NVIDIA NIM Free Model Router (`nim-router`)**.<br>Subtitle: *Intelligent Reverse Proxy & Load Balancer*. | *"Meet the **NVIDIA NIM Free Model Router** — an intelligent, lightweight, OpenAI-compatible local reverse proxy designed to harness the full power of NVIDIA’s free tier."* |
| **0:38** | Clean architectural diagram animation: <br>`Client Request (model: "nim-free")` ➔ `NIM Router (Discovery & Latency Ranking)` ➔ `Healthy NIM Model Pool` ➔ `Auto-Failover Loop`. | *"Instead of hardcoding a single model and praying it doesn’t get throttled, you point your applications to `localhost:11435` with one virtual model name: `nim-free`.*<br><br>*Behind the scenes, NIM Router discovers all available endpoints, probes their health, and automatically load-balances across the entire catalog."* |

---

### **[0:55 - 1:50] CORE ADVANTAGES: Why It’s a Game Changer**
| Time | Visual / On-Screen Action (B-Roll) | Voiceover / Spoken Dialogue |
| :--- | :--- | :--- |

| **0:55** | Terminal showing startup probe progress bar: `Probing models: [====] 100%` and ranking the **Top-3 Priority Models**. | *"Here is why this completely transforms your local AI workflow:*<br><br>*First: **Real-Time Latency Routing**. When you boot it up, it probes all active endpoints and calculates dynamic Exponential Moving Average (EMA) latency scores. Your prompt is continuously routed to the fastest responding models first."* |
| **1:15** | Terminal screen recording: An artificial 429 rate limit triggers on a model; the router catches it, displays a warning, instantly switches to the next model, and returns a 200 OK stream seamlessly. | *"Second: **Zero-Downtime Multi-Tier Failover**. Hit a `429 Rate Limit` or a `500 Server Error`? NIM Router instantly catches the failure, temporarily puts that model in cooldown, and routes your exact request to the next fastest standby model without dropping your connection."* |
| **1:32** | Split-screen demo: An image input triggers automatic routing to **Llama 3.2 90B Vision**, while a function-calling request routes to tool-capable models. | *"Third: **Smart Payload Routing**. If you send an image payload or base64 data URI, NIM Router automatically detects it and routes to multimodal vision models. If your agent uses tool calling, it isolates models with structured function support."* |
| **1:44** | Code snippet highlighting empty message and reasoning token sanitization. | *"Plus, it features **built-in message normalization**, cleaning reasoning-only blocks and empty assistant frames so strict schemas never crash."* |

---

### **[1:50 - 2:30] INTEGRATION & SPEED: Plug & Play Everywhere**
| Time | Visual / On-Screen Action (B-Roll) | Voiceover / Spoken Dialogue |
| :--- | :--- | :--- |
| **1:50** | Screen recording configuring **Hermes Agent** via `hermes model`, then showing **Cline / Aider / Continue.dev** JSON configs. | *"Because it’s 100% OpenAI-compatible, it drops seamlessly into whatever you already use:*<br>• *Autonomous agents like **Hermes Agent**,*<br>• *Coding harness tools like **Cline, Aider, and Continue.dev**,*<br>• *Or standard Python and TypeScript OpenAI SDKs."* |
| **2:08** | Quick demo of interactive token streaming (SSE) via Python script or cURL streaming response. | *"Full Server-Sent Events (SSE) streaming support means zero perceived delay for interactive chats and coding completions."* |
| **2:18** | Terminal running `pm2 start ecosystem.config.js` and showing `pm2 logs nim-router` running in the background. | *"And privacy? Your real NVIDIA API key stays safe in your local `.env`. Client tools only talk to `localhost`, and with PM2 support, you can keep it running 24/7 as a background service."* |

---

### **[2:30 - 2:55] OUTRO & CALL TO ACTION**
| Time | Visual / On-Screen Action (B-Roll) | Voiceover / Spoken Dialogue |
| :--- | :--- | :--- |
| **2:30** | Showing the GitHub repository and 1-click install command: `bash install.sh` / `install.bat`. | *"Setup takes less than 60 seconds:*<br>1. *Clone the repo,*<br>2. *Run `install.sh` or `install.bat`,*<br>3. *Add your free API key from [build.nvidia.com](https://build.nvidia.com), and launch!"* |
| **2:45** | Logo animation with repo link and summary text: **High Availability. Zero Rate-Limit Frustration. Unlimited Potential.** | *"Stop letting rate limits throttle your AI agents. Upgrade your developer stack with **NVIDIA NIM Free Model Router** today. Check out the link in the description to get started!"* |

---

## 📌 Summary Cheat Sheet

| Dimension | Details |
| :--- | :--- |
| **What It Is** | An OpenAI-compatible reverse proxy router aggregating all free NVIDIA NIM endpoints into one virtual model (`nim-free`). |
| **The Core Purpose** | Eliminates rate limit (`429`) interruptions, latency bottlenecks, and endpoint downtime when using free foundation models. |
| **Key Advantage #1** | **Adaptive Latency Routing (EMA)**: Continually routes to the top fastest responding models. |
| **Key Advantage #2** | **Multi-Tier Auto Failover**: Retries failed/throttled calls across candidate models with zero client drop. |
| **Key Advantage #3** | **Multimodal & Agent Intelligence**: Automatic vision routing for images, tool filtering, and message normalization. |
| **Key Advantage #4** | **100% Local & Free**: Runs locally (`pm2`/`uvicorn`), keeps keys secure, and costs nothing to operate. |
