import asyncio
import time
import httpx

ROUTER_URL = "http://127.0.0.1:11435"

async def test_router():
    async with httpx.AsyncClient(timeout=60) as client:
        print("1. Checking Router Health...", flush=True)
        try:
            r = await client.get(f"{ROUTER_URL}/health")
            print(f"   Status: {r.status_code}, Response: {r.json()}", flush=True)
        except Exception as e:
            print(f"   [ERROR] Failed to reach router: {e}", flush=True)
            return

        print("\n2. Fetching Model Catalog from /v1/models...", flush=True)
        try:
            r = await client.get(f"{ROUTER_URL}/v1/models")
            data = r.json()
            models = [m["id"] for m in data.get("data", [])]
            print(f"   Total models available: {len(models)}", flush=True)
            print(f"   Discovered models: {models}", flush=True)
        except Exception as e:
            print(f"   [ERROR] Failed to fetch models: {e}", flush=True)
            return

        print("\n3. Testing Round-Robin Chat Completions (Sending 6 requests with model='nim-free')...", flush=True)
        for i in range(1, 7):
            prompt = f"Say hello and count to {i}"
            t0 = time.time()
            try:
                resp = await client.post(
                    f"{ROUTER_URL}/v1/chat/completions",
                    json={
                        "model": "nim-free",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 15,
                        "temperature": 0.2
                    }
                )
                elapsed = round(time.time() - t0, 2)
                if resp.status_code == 200:
                    resp_json = resp.json()
                    used_model = resp_json.get("model", "unknown")
                    msg = resp_json.get("choices", [{}])[0].get("message", {})
                    content = msg.get("content") or msg.get("reasoning") or str(msg)
                    if not content or content == "None":
                        content = "(response returned)"
                    print(f"   [Request #{i}] Status: 200 OK ({elapsed}s) | Model: {used_model} | Output: {str(content).strip()[:55]}", flush=True)
                else:
                    print(f"   [Request #{i}] Status: {resp.status_code} ({elapsed}s) | Error: {resp.text[:100]}", flush=True)
            except Exception as e:
                print(f"   [Request #{i}] Exception ({round(time.time()-t0, 2)}s): {e}", flush=True)

if __name__ == "__main__":
    asyncio.run(test_router())
