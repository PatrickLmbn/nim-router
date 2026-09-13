import json
import os
import shutil
import time
from nim_router.logger import logger

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
_COMBOS_FILE = os.path.join(_BASE_DIR, "config", "combos.json")
_COMBOS_EXAMPLE = os.path.join(_BASE_DIR, "config", "combos.example.json")


def load_combos() -> list[dict]:
    if not os.path.exists(_COMBOS_FILE) and os.path.exists(_COMBOS_EXAMPLE):
        try:
            os.makedirs(os.path.dirname(_COMBOS_FILE), exist_ok=True)
            shutil.copy(_COMBOS_EXAMPLE, _COMBOS_FILE)
        except Exception:
            pass
    if not os.path.exists(_COMBOS_FILE):
        return []
    try:
        with open(_COMBOS_FILE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"Failed to load combos: {e}")
        return []


def save_combos(combos: list[dict]):
    os.makedirs(os.path.dirname(_COMBOS_FILE), exist_ok=True)
    try:
        with open(_COMBOS_FILE, "w") as f:
            json.dump(combos, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save combos: {e}")


def get_combo(name: str) -> dict | None:
    name_lower = name.strip().lower()
    for c in load_combos():
        if c.get("name", "").lower() == name_lower:
            return c
    return None


def create_combo(name: str, strategy: str, models: list[str]) -> dict:
    name = name.strip().lower().replace(" ", "-")
    combos = load_combos()
    if any(c.get("name", "").lower() == name for c in combos):
        raise ValueError(f"Combo '{name}' already exists.")
    combo = {
        "name": name,
        "strategy": strategy,
        "models": [m.strip() for m in models if m.strip()],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    combos.append(combo)
    save_combos(combos)
    return combo


def update_combo(name: str, strategy: str, models: list[str]) -> dict:
    name = name.strip().lower()
    combos = load_combos()
    for i, c in enumerate(combos):
        if c.get("name", "").lower() == name:
            combos[i]["strategy"] = strategy
            combos[i]["models"] = [m.strip() for m in models if m.strip()]
            save_combos(combos)
            return combos[i]
    raise ValueError(f"Combo '{name}' not found.")


def delete_combo(name: str) -> bool:
    name = name.strip().lower()
    combos = load_combos()
    new_combos = [c for c in combos if c.get("name", "").lower() != name]
    if len(new_combos) == len(combos):
        return False
    save_combos(new_combos)
    return True
