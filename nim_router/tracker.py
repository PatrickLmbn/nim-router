import os
import time
import sqlite3
import threading
from typing import Optional, Dict, List, Any

class UsageTracker:
    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = db_path
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_dir = os.path.join(base_dir, "config")
            os.makedirs(config_dir, exist_ok=True)
            self.db_path = os.path.join(config_dir, "usage.db")
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS request_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        provider TEXT NOT NULL,
                        model TEXT NOT NULL,
                        api_key_masked TEXT NOT NULL,
                        status_code INTEGER NOT NULL,
                        latency_ms REAL NOT NULL,
                        stream INTEGER NOT NULL,
                        prompt_tokens INTEGER NOT NULL,
                        completion_tokens INTEGER NOT NULL,
                        total_tokens INTEGER NOT NULL,
                        is_estimated INTEGER NOT NULL DEFAULT 0
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON request_logs(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_provider ON request_logs(provider)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_model ON request_logs(model)")
                conn.commit()

    def record_request(
        self,
        provider: str,
        model: str,
        api_key_masked: str,
        status_code: int,
        latency_ms: float,
        stream: bool,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        is_estimated: bool = False,
        timestamp: Optional[float] = None
    ):
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO request_logs (
                        timestamp, provider, model, api_key_masked,
                        status_code, latency_ms, stream,
                        prompt_tokens, completion_tokens, total_tokens,
                        is_estimated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ts,
                    provider or "Unknown",
                    model or "unknown",
                    api_key_masked or "",
                    int(status_code),
                    round(float(latency_ms), 2),
                    1 if stream else 0,
                    max(0, int(prompt_tokens)),
                    max(0, int(completion_tokens)),
                    max(0, int(total_tokens)),
                    1 if is_estimated else 0
                ))
                conn.commit()

    def get_analytics(self, time_range: str = "all") -> Dict[str, Any]:
        now = time.time()
        cutoff = 0.0
        if time_range == "24h":
            cutoff = now - 86400.0
        elif time_range == "7d":
            cutoff = now - (7 * 86400.0)
        elif time_range == "30d":
            cutoff = now - (30 * 86400.0)

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT
                        COUNT(*) as total_requests,
                        SUM(CASE WHEN status_code >= 200 AND status_code < 400 THEN 1 ELSE 0 END) as successful_requests,
                        SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as failed_requests,
                        COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens,
                        COALESCE(SUM(completion_tokens), 0) as total_completion_tokens,
                        COALESCE(SUM(total_tokens), 0) as total_tokens,
                        COALESCE(AVG(latency_ms), 0.0) as avg_latency_ms
                    FROM request_logs
                    WHERE timestamp >= ?
                """, (cutoff,))
                row = cursor.fetchone()

                total_reqs = row["total_requests"] or 0
                succ_reqs = row["successful_requests"] or 0
                fail_reqs = row["failed_requests"] or 0
                prompt_toks = row["total_prompt_tokens"] or 0
                comp_toks = row["total_completion_tokens"] or 0
                tot_toks = row["total_tokens"] or 0
                avg_lat = round(row["avg_latency_ms"] or 0.0, 1)
                succ_rate = round((succ_reqs / total_reqs * 100.0), 1) if total_reqs > 0 else 100.0

                summary = {
                    "total_requests": total_reqs,
                    "successful_requests": succ_reqs,
                    "failed_requests": fail_reqs,
                    "success_rate": succ_rate,
                    "total_prompt_tokens": prompt_toks,
                    "total_completion_tokens": comp_toks,
                    "total_tokens": tot_toks,
                    "avg_latency_ms": avg_lat
                }

                cursor.execute("""
                    SELECT
                        provider,
                        COUNT(*) as requests,
                        SUM(CASE WHEN status_code >= 200 AND status_code < 400 THEN 1 ELSE 0 END) as success_count,
                        COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                        COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                        COALESCE(SUM(total_tokens), 0) as total_tokens,
                        COALESCE(AVG(latency_ms), 0.0) as avg_latency_ms
                    FROM request_logs
                    WHERE timestamp >= ?
                    GROUP BY provider
                    ORDER BY total_tokens DESC, requests DESC
                """, (cutoff,))
                p_rows = cursor.fetchall()

                providers = []
                for p in p_rows:
                    p_reqs = p["requests"] or 0
                    p_succ = p["success_count"] or 0
                    p_tot_tok = p["total_tokens"] or 0
                    p_share = round((p_tot_tok / tot_toks * 100.0), 1) if tot_toks > 0 else 0.0
                    p_succ_rate = round((p_succ / p_reqs * 100.0), 1) if p_reqs > 0 else 100.0
                    providers.append({
                        "provider": p["provider"],
                        "requests": p_reqs,
                        "success_rate": p_succ_rate,
                        "prompt_tokens": p["prompt_tokens"] or 0,
                        "completion_tokens": p["completion_tokens"] or 0,
                        "total_tokens": p_tot_tok,
                        "token_percentage": p_share,
                        "avg_latency_ms": round(p["avg_latency_ms"] or 0.0, 1)
                    })

                cursor.execute("""
                    SELECT
                        model,
                        provider,
                        COUNT(*) as requests,
                        SUM(CASE WHEN status_code >= 200 AND status_code < 400 THEN 1 ELSE 0 END) as success_count,
                        COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                        COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                        COALESCE(SUM(total_tokens), 0) as total_tokens,
                        COALESCE(AVG(latency_ms), 0.0) as avg_latency_ms
                    FROM request_logs
                    WHERE timestamp >= ?
                    GROUP BY model, provider
                    ORDER BY total_tokens DESC, requests DESC
                """, (cutoff,))
                m_rows = cursor.fetchall()

                models = []
                for m in m_rows:
                    m_reqs = m["requests"] or 0
                    m_succ = m["success_count"] or 0
                    m_succ_rate = round((m_succ / m_reqs * 100.0), 1) if m_reqs > 0 else 100.0
                    models.append({
                        "model": m["model"],
                        "provider": m["provider"],
                        "requests": m_reqs,
                        "success_rate": m_succ_rate,
                        "prompt_tokens": m["prompt_tokens"] or 0,
                        "completion_tokens": m["completion_tokens"] or 0,
                        "total_tokens": m["total_tokens"] or 0,
                        "avg_latency_ms": round(m["avg_latency_ms"] or 0.0, 1)
                    })

                cursor.execute("""
                    SELECT
                        timestamp,
                        provider,
                        model,
                        status_code,
                        latency_ms,
                        stream,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens
                    FROM request_logs
                    WHERE timestamp >= ?
                    ORDER BY timestamp DESC
                    LIMIT 25
                """, (cutoff,))
                recent_rows = cursor.fetchall()
                recent_activity = [
                    {
                        "timestamp": r["timestamp"],
                        "provider": r["provider"],
                        "model": r["model"],
                        "status_code": r["status_code"],
                        "latency_ms": r["latency_ms"],
                        "stream": bool(r["stream"]),
                        "prompt_tokens": r["prompt_tokens"],
                        "completion_tokens": r["completion_tokens"],
                        "total_tokens": r["total_tokens"]
                    }
                    for r in recent_rows
                ]

        return {
            "time_range": time_range,
            "summary": summary,
            "providers": providers,
            "models": models,
            "recent_activity": recent_activity
        }

    def reset_analytics(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path, timeout=15.0)
            try:
                conn.isolation_level = None
                conn.execute("DELETE FROM request_logs")
                conn.execute("VACUUM")
            finally:
                conn.close()

_global_tracker: Optional[UsageTracker] = None
_global_tracker_lock = threading.Lock()

def get_usage_tracker() -> UsageTracker:
    global _global_tracker
    if _global_tracker is None:
        with _global_tracker_lock:
            if _global_tracker is None:
                _global_tracker = UsageTracker()
    return _global_tracker
