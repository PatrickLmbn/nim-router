import asyncio
import getpass
import json
import os
import shutil
import subprocess
import sys
import httpx

from nim_router.config import get_nvidia_keys, get_openrouter_key, get_opencode_key, get_primary_model
from nim_router.engine import ModelRouter

def get_rainbow_banner() -> str:
    banner_lines = [
        r" ________   ___  _____ ______   ",
        r"|\   ___  \|\  \|\   _ \  _   \  ",
        r"\ \  \\ \  \ \  \ \  \\\__\ \  \ ",
        r" \ \  \\ \  \ \  \ \  \\|__| \  \\",
        r"  \ \  \\ \  \ \  \ \  \    \ \  \\",
        r"   \ \__\ \__\ \__\ \__\    \ \__\\",
        r"    \|__| \|__|\|__|\|__|     \|__|",
        r"            R O U T E R"
    ]
    colors = [
        "\033[38;5;196m",
        "\033[38;5;208m",
        "\033[38;5;220m",
        "\033[38;5;118m",
        "\033[38;5;45m",
        "\033[38;5;129m",
        "\033[38;5;201m",
        "\033[1;37m",
    ]
    lines = [f"{c}{line}\033[0m" for c, line in zip(colors, banner_lines)]
    return "\n".join(lines) + "\n"

def get_provider_name(m_obj: dict | str) -> str:
    if isinstance(m_obj, dict):
        if "provider" in m_obj:
            return m_obj["provider"]
        mid = m_obj.get("id", "").lower()
    else:
        mid = str(m_obj).lower()

    if mid.endswith(":free") or "openrouter/" in mid or mid.startswith("openrouter"):
        return "OpenRouter"
    elif mid.startswith("opencode/") or "opencode" in mid or mid.endswith("-free") or any(k in mid for k in ("claude-", "gpt-", "gemini-", "codestral")):
        return "OpenCode"
    else:
        return "NVIDIA"

def save_working_models(model_ids: list[str]):
    base_dir = os.path.dirname(os.path.dirname(__file__))
    config_dir = os.path.join(base_dir, "config")
    os.makedirs(config_dir, exist_ok=True)
    status_path = os.path.join(config_dir, "models_status.json")
    try:
        with open(status_path, "w") as f:
            json.dump({"working_models": model_ids}, f, indent=2)
    except Exception:
        pass

def show_help():
    print(get_rainbow_banner())
    print("\033[1;33mUsage:\033[0m nimrouter [command]\n")
    print("\033[1;33mAvailable Commands:\033[0m")
    print("  \033[1;32mmodels, list, select\033[0m   Interactively choose primary priority model.")
    print("  \033[1;32mprobe, scan\033[0m            Run live probing scan across all enabled providers.")
    print("  \033[1;32mconnect, keys, config\033[0m  Interactively add or update provider API keys.")
    print("  \033[1;32mrestart, reload\033[0m        Restart background server process via PM2.")
    print("  \033[1;32mstop\033[0m                   Stop background server process via PM2.")
    print("  \033[1;32mlogs, log\033[0m              Stream live nimrouter server logs.")
    print("  \033[1;32mhelp, -h, --help\033[0m       Show CLI help documentation and exit.\n")
    print("\033[1;33mDefault (no argument):\033[0m")
    print("  Starts the nimrouter OpenAI-compatible proxy server (Port 11435).\n")
    print("\033[1;33mExamples:\033[0m")
    print("  nimrouter models       Select primary model priority")
    print("  nimrouter probe        Probe endpoints and refresh active model pool")
    print("  nimrouter connect      Set or update API credentials")
    print("  nimrouter restart      Restart background server process")
    print("  nimrouter stop         Stop background server process")
    print("  nimrouter logs         View live background server logs")
    print("  nimrouter --help       Show help documentation\n")

def show_logs():
    print(get_rainbow_banner())
    pm2_bin = shutil.which("pm2")
    if pm2_bin:
        try:
            os.execvp(pm2_bin, [pm2_bin, "logs", "nim-router"])
        except Exception:
            subprocess.run([pm2_bin, "logs", "nim-router"])
    else:
        print("\033[91mPM2 is not installed on this system. Install PM2 via 'npm install -g pm2'.\033[0m")

def restart_server():
    print(get_rainbow_banner())
    pm2_bin = shutil.which("pm2")
    if pm2_bin:
        res = subprocess.run([pm2_bin, "restart", "nim-router", "--update-env"])
        if res.returncode == 0:
            print("\n\033[1;32m[✓] Live nimrouter server process restarted via PM2!\033[0m")
        else:
            print("\n\033[91mFailed to restart nimrouter via PM2. Please check if process is running in PM2.\033[0m")
    else:
        print("\033[91mPM2 is not installed on this system.\033[0m")

def stop_server():
    print(get_rainbow_banner())
    pm2_bin = shutil.which("pm2")
    if pm2_bin:
        res = subprocess.run([pm2_bin, "stop", "nim-router"])
        if res.returncode == 0:
            print("\n\033[1;32m[✓] Stopped nimrouter server process via PM2.\033[0m")
        else:
            print("\n\033[91mFailed to stop nimrouter via PM2. Please check if process is running in PM2.\033[0m")
    else:
        print("\033[91mPM2 is not installed on this system.\033[0m")

async def async_probe_models():
    nvidia_keys = get_nvidia_keys()
    openrouter_key = get_openrouter_key()
    opencode_key = get_opencode_key()

    print(get_rainbow_banner())
    print("\033[1;37m   Endpoint Probing Scan       \033[0m\n")

    print("\033[90mStarting live multi-provider endpoint probing scan...\033[0m")
    router = ModelRouter(api_key=nvidia_keys, openrouter_key=openrouter_key, opencode_key=opencode_key)
    models = await router._discover_models()

    if not models:
        print("\033[91mNo working models discovered. Please check your API keys via 'nimrouter connect'.\033[0m")
        return

    model_ids = [m.get("id") for m in models if m.get("id")]
    save_working_models(model_ids)

    print(f"\n\033[1;32m[✓] Probing scan complete! Discovered {len(model_ids)} active working models.\033[0m")

    try:
        port = int(os.getenv("PORT", 11435))
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.post(f"http://127.0.0.1:{port}/refresh")
            if r.status_code == 200:
                print("\033[1;32m[✓] Live nimrouter server refreshed with new active pool.\033[0m")
    except Exception:
        pass

async def interactive_model_selector():
    nvidia_keys = get_nvidia_keys()
    openrouter_key = get_openrouter_key()
    opencode_key = get_opencode_key()

    print(get_rainbow_banner())
    print("\033[1;37m   Model Priority Selector      \033[0m\n")

    current_primary = get_primary_model()
    print(f"Current Primary Model: \033[1;32m{current_primary}\033[0m\n")

    try:
        scan_choice = input("\033[1;36mDo you want to probe/scan endpoints for active working models? [Y/n] (Recommended): \033[0m").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\n\033[90mOperation cancelled.\033[0m")
        sys.exit(0)

    should_probe = scan_choice not in ("n", "no")

    router = ModelRouter(api_key=nvidia_keys, openrouter_key=openrouter_key, opencode_key=opencode_key)

    if should_probe:
        print("\n\033[90mDiscovering and probing models across configured providers...\033[0m")
        models = await router._discover_models()
        if models:
            save_working_models([m.get("id") for m in models if m.get("id")])
    else:
        print("\n\033[90mLoading saved working models pool...\033[0m")
        models = router._load_fallback_models()

    if not models:
        print("\033[91mNo models found. Please check your API keys in .env.\033[0m")
        return

    nvidia_models = [m.get("id") for m in models if m.get("id") and get_provider_name(m) == "NVIDIA"]
    openrouter_models = [m.get("id") for m in models if m.get("id") and get_provider_name(m) == "OpenRouter"]
    opencode_models = [m.get("id") for m in models if m.get("id") and get_provider_name(m) == "OpenCode"]

    all_ordered = []
    counter = 1

    print("\n\033[1;33mAvailable Models:\033[0m\n")
    print("  \033[1;32m[0]\033[0m nim-free (Auto-rotate across all free models by lowest latency)\n")

    if nvidia_models:
        print("\033[1;36m--- NVIDIA NIM Models ---\033[0m")
        for mid in nvidia_models:
            all_ordered.append(mid)
            prefix = "★ " if mid == current_primary else "  "
            print(f"{prefix}\033[1;37m[{counter}]\033[0m {mid}")
            counter += 1
        print()

    if openrouter_models:
        print("\033[1;36m--- OpenRouter Free Models ---\033[0m")
        for mid in openrouter_models:
            all_ordered.append(mid)
            prefix = "★ " if mid == current_primary else "  "
            print(f"{prefix}\033[1;37m[{counter}]\033[0m {mid}")
            counter += 1
        print()

    if opencode_models:
        print("\033[1;36m--- OpenCode Models ---\033[0m")
        for mid in opencode_models:
            all_ordered.append(mid)
            prefix = "★ " if mid == current_primary else "  "
            print(f"{prefix}\033[1;37m[{counter}]\033[0m {mid}")
            counter += 1
        print()

    try:
        choice = input("\033[1;36mSelect primary priority model number (0 to reset): \033[0m").strip()
        if not choice:
            return
        idx = int(choice)
        if idx == 0:
            selected_model = "nim-free"
        elif 1 <= idx <= len(all_ordered):
            selected_model = all_ordered[idx - 1]
        else:
            print("\033[91mInvalid selection.\033[0m")
            return
    except (KeyboardInterrupt, EOFError):
        print("\n\033[90mOperation cancelled.\033[0m")
        sys.exit(0)
    except ValueError:
        print("\033[91mInvalid input.\033[0m")
        return

    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
        updated = False
        new_lines = []
        for line in lines:
            if line.startswith("PRIMARY_MODEL=") or line.startswith("MODEL="):
                new_lines.append(f"PRIMARY_MODEL={selected_model}\n")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"PRIMARY_MODEL={selected_model}\n")
        with open(env_path, "w") as f:
            f.writelines(new_lines)
    else:
        with open(env_path, "w") as f:
            f.write(f"PRIMARY_MODEL={selected_model}\n")

    print(f"\n\033[1;32m[✓] Primary model updated to: {selected_model}\033[0m")

    try:
        port = int(os.getenv("PORT", 11435))
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.post(f"http://127.0.0.1:{port}/refresh")
            if r.status_code == 200:
                print("\033[1;32m[✓] Live nimrouter server refreshed successfully.\033[0m")
    except Exception:
        pass

async def async_connect_api_keys():
    print(get_rainbow_banner())
    print("\033[1;37m   Multi-Provider Key Config   \033[0m\n")

    current_nvidia = get_nvidia_keys()
    current_or = get_openrouter_key()
    current_oc = get_opencode_key()

    def mask(k: str) -> str:
        return f"{k[:8]}...{k[-4:]}" if len(k) > 12 else ("(Set)" if k else "(Not set)")

    nv_disp = ", ".join([mask(k) for k in current_nvidia]) if current_nvidia else "(Not set)"
    print(f"Current NVIDIA Keys:    \033[1;33m{nv_disp}\033[0m")
    print(f"Current OpenRouter Key: \033[1;33m{mask(current_or)}\033[0m")
    print(f"Current OpenCode Key:   \033[1;33m{mask(current_oc)}\033[0m\n")

    print("\033[90mEnter new API keys (inputs hidden, press Enter to keep current value):\033[0m\n")
    try:
        k1 = getpass.getpass("Primary NVIDIA API Key #1: ").strip()
        k2 = getpass.getpass("Secondary NVIDIA API Key #2 (Optional): ").strip()
        or_key = getpass.getpass("OpenRouter API Key (Optional): ").strip()
        oc_key = getpass.getpass("OpenCode API Key (Optional): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\033[90mOperation cancelled.\033[0m")
        sys.exit(0)

    keys_combined = []
    if k1:
        keys_combined.append(k1)
    elif current_nvidia:
        keys_combined.append(current_nvidia[0])

    if k2:
        keys_combined.append(k2)
    elif len(current_nvidia) > 1:
        keys_combined.append(current_nvidia[1])

    final_nvidia = ",".join(keys_combined)
    final_or = or_key if or_key else current_or
    final_oc = oc_key if oc_key else current_oc

    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    parts = line.split("=", 1)
                    env_vars[parts[0].strip()] = parts[1].strip()

    if final_nvidia:
        env_vars["NVIDIA_API_KEYS"] = final_nvidia
    if final_or:
        env_vars["OPENROUTER_API_KEY"] = final_or
    if final_oc:
        env_vars["OPENCODE_API_KEY"] = final_oc

    if "PORT" not in env_vars:
        env_vars["PORT"] = "11435"
    if "PRIMARY_MODEL" not in env_vars and "MODEL" not in env_vars:
        env_vars["PRIMARY_MODEL"] = "nim-free"

    with open(env_path, "w") as f:
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")

    print("\n\033[1;32m[✓] Saved API keys to .env file!\033[0m")

    try:
        port = int(env_vars.get("PORT", 11435))
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.post(f"http://127.0.0.1:{port}/refresh")
            if r.status_code == 200:
                print("\033[1;32m[✓] Live nimrouter server refreshed with new keys.\033[0m")
    except Exception:
        pass

def safe_run(coro):
    try:
        asyncio.run(coro)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n\033[90mOperation cancelled.\033[0m")
        sys.exit(0)

def select_primary_model():
    safe_run(interactive_model_selector())

def probe_active_models():
    safe_run(async_probe_models())

def connect_api_keys():
    safe_run(async_connect_api_keys())

def main():
    safe_run(interactive_model_selector())
