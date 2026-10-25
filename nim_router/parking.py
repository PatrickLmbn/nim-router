import json
import os
import threading
import time

_LOCK = threading.Lock()
_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "provider_parking.json")
_CACHE = {"path": "", "data": {}, "stamp": 0.0}
_CACHE_TTL = 2.0


def _load() -> dict:
    try:
        with open(_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        tmp_path = f"{_PATH}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
        os.replace(tmp_path, _PATH)
    except Exception:
        pass


def _cached_load() -> dict:
    now = time.time()
    if _CACHE["path"] == _PATH and now - _CACHE["stamp"] < _CACHE_TTL:
        return dict(_CACHE["data"])
    data = _load()
    _CACHE.update({"path": _PATH, "data": data, "stamp": now})
    return dict(data)


def _store(data: dict) -> None:
    _CACHE.update({"path": _PATH, "data": data, "stamp": time.time()})
    _save(data)


def _until_of(entry) -> float:
    if isinstance(entry, (int, float)):
        return float(entry)
    if isinstance(entry, dict):
        try:
            return float(entry.get("until") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _prune(data: dict) -> dict:
    now = time.time()
    kept: dict = {}
    for key, entry in data.items():
        until = _until_of(entry)
        if until:
            if until > now:
                kept[key] = entry
            continue
        last = 0.0
        if isinstance(entry, dict):
            try:
                last = float(entry.get("last") or entry.get("first") or 0.0)
            except (TypeError, ValueError):
                last = 0.0
        if last and now - last > 86400:
            continue
        kept[key] = entry
    return kept


def parked_until(key: str) -> float:
    with _LOCK:
        data = _cached_load()
        until = _until_of(data.get(key))
        if until and until <= time.time():
            data = _prune(data)
            _store(data)
            return 0.0
        return until


def is_parked(key: str) -> bool:
    return parked_until(key) > time.time()


def note_success(key: str) -> None:
    with _LOCK:
        data = _cached_load()
        if key in data:
            data.pop(key, None)
            _store(data)


def note_failure(key: str, seconds: float, reason: str = "", threshold: int = 1) -> bool:
    now = time.time()
    with _LOCK:
        data = _prune(_cached_load())
        entry = data.get(key)
        if not isinstance(entry, dict):
            entry = {"count": 0, "first": now}
        entry["count"] = int(entry.get("count") or 0) + 1
        entry["reason"] = reason
        entry["last"] = now
        if entry["count"] >= max(1, threshold):
            entry["until"] = now + max(1.0, float(seconds))
        data[key] = entry
        _store(data)
        return entry["count"] >= max(1, threshold)


def clear(key: str) -> None:
    with _LOCK:
        data = _cached_load()
        if data.pop(key, None) is not None:
            _store(data)


def clear_prefix(prefix: str) -> None:
    with _LOCK:
        data = _cached_load()
        updated = {key: value for key, value in data.items() if not key.startswith(prefix)}
        if updated != data:
            _store(updated)


def prune() -> None:
    with _LOCK:
        _store(_prune(_cached_load()))
