import asyncio
import os
import sys
import httpx

from nim_router.config import get_nvidia_keys, get_openrouter_key, get_opencode_key, get_primary_model
from nim_router.engine import ModelRouter

async def interactive_model_selector():
    nvidia_keys = get_nvidia_keys()
    openrouter_key = get_openrouter_key()
    opencode_key = get_opencode_key()

    print("\033[1;36m===================================================\033[0m")
    print("\033[1;37m   NVIDIA NIM Router - Model Priority Selector      \033[0m")
    print("\033[1;36m===================================================\033[0m\n")

    current_primary = get_primary_model()
    print(f"Current Primary Model: \033[1;32m{current_primary}\033[0m\n")

    print("\033[90mDiscovering available models across configured providers...\033[0m")
    router = ModelRouter(api_key=nvidia_keys, openrouter_key=openrouter_key, opencode_key=opencode_key)
    models = await router._discover_models()

    if not models:
        print("\033[91mNo models found. Please check your API keys in .env.\033[0m")
        return

    model_ids = [m.get("id") for m in models if m.get("id")]
    print("\n\033[1;33mAvailable Models:\033[0m")
    print("  \033[1;32m[0]\033[0m nim-free (Auto-rotate across all free models by lowest latency)")
    for i, mid in enumerate(model_ids, 1):
        prefix = "★ " if mid == current_primary else "  "
        print(f"{prefix}\033[1;37m[{i}]\033[0m {mid}")

    try:
        choice = input("\n\033[1;36mSelect primary priority model number (0 to reset): \033[0m").strip()
        if not choice:
            return
        idx = int(choice)
        if idx == 0:
            selected_model = "nim-free"
        elif 1 <= idx <= len(model_ids):
            selected_model = model_ids[idx - 1]
        else:
            print("\033[91mInvalid selection.\033[0m")
            return
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
                print("\033[1;32m[✓] Live nim-router server refreshed successfully.\033[0m")
    except Exception:
        pass

def main():
    asyncio.run(interactive_model_selector())
