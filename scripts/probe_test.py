import asyncio
import os
import json
import httpx
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(dotenv_path=env_path)
api_key = os.getenv("NVIDIA_API_KEY")

async def test_models():
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            "https://integrate.api.nvidia.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code != 200:
            print(resp.text)
            return

        data = resp.json()
        models = data.get("data", [])
        print(f"Total models returned by API: {len(models)}")

        all_ids = [m.get("id") for m in models if m.get("id")]
        print(f"Sample model IDs: {all_ids[:20]}")

        print("\nTesting chat completions on models...")
        working_models = []
        not_working = []

        semaphore = asyncio.Semaphore(10)

        async def probe(model_id):
            async with semaphore:
                try:
                    r = await client.post(
                        "https://integrate.api.nvidia.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "model": model_id,
                            "messages": [{"role": "user", "content": "hi"}],
                            "max_tokens": 1,
                            "temperature": 0.1
                        },
                        timeout=15.0
                    )
                    if r.status_code == 200:
                        print(f" [200 OK] {model_id}")
                        working_models.append((model_id, 200, "OK"))
                    elif r.status_code == 429:
                        print(f" [429 RATE_LIMIT (valid endpoint)] {model_id}")
                        working_models.append((model_id, 429, "Rate Limited"))
                    else:
                        not_working.append((model_id, r.status_code, r.text[:100]))
                except Exception as e:
                    not_working.append((model_id, "ERR", str(e)))

        tasks = [probe(mid) for mid in all_ids]
        await asyncio.gather(*tasks)

        working_list = sorted([m[0] for m in working_models])
        non_working_list = sorted([m[0] for m in not_working])

        print("\n" + "=" * 70)
        print(f"WORKING / ACCESSIBLE MODELS ({len(working_list)} total)")
        print("=" * 70)
        for m, status, note in sorted(working_models, key=lambda x: x[0]):
            print(f"  - {m:<45} [Status: {status}] ({note})")

        print("\n" + "=" * 70)
        print(f"NON-WORKING / INACCESSIBLE MODELS ({len(non_working_list)} total)")
        print("=" * 70)
        for m, status, note in sorted(not_working, key=lambda x: (str(x[1]), x[0])):
            print(f"  - {m:<45} [Status: {status}]")

        print("\n" + "=" * 70)
        print("PYTHON LIST FORMAT FOR COPY/PASTE OR ROUTER INTEGRATION")
        print("=" * 70)
        print("WORKING_MODELS = [")
        for m in working_list:
            print(f'    "{m}",')
        print("]\n")

        print("NON_WORKING_MODELS = [")
        for m in non_working_list:
            print(f'    "{m}",')
        print("]")

        output_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "models_status.json")
        with open(output_file, "w") as f:
            json.dump({
                "total_models": len(all_ids),
                "working_count": len(working_list),
                "non_working_count": len(non_working_list),
                "working_models": working_list,
                "working_details": [{"id": m, "status": s, "note": n} for m, s, n in working_models],
                "non_working_models": non_working_list,
                "non_working_details": [{"id": m, "status": s, "error": n} for m, s, n in not_working]
            }, f, indent=2)
        print(f"\nSaved full status report to {output_file}")

if __name__ == "__main__":
    asyncio.run(test_models())
