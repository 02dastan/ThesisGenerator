import json
import csv
import time
import datetime
from pathlib import Path
from typing import Dict, List, Any

from app.config_manager import LOGS_DIR

REQUESTS_LOG = LOGS_DIR / "requests.log"
ERRORS_LOG = LOGS_DIR / "errors.log"
STATS_FILE = LOGS_DIR / "stats.json"
IP_LIMITS_FILE = LOGS_DIR / "ip_limits.json"


# ── Logging ───────────────────────────────────────────────────────────────────

def log_request(ip: str, specialty: str, interests: str, topics_count: int,
                duration_sec: float, model_used: str):
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "ip": ip,
        "specialty": specialty,
        "interests": interests,
        "generated_count": topics_count,
        "duration_sec": round(duration_sec, 2),
        "model_used": model_used,
    }
    with open(REQUESTS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _update_stats(specialty, interests)


def log_error(provider: str, error: str):
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "provider": provider,
        "error": error,
    }
    with open(ERRORS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _update_stats(specialty: str, interests: str):
    stats = load_stats()
    stats["total_requests"] = stats.get("total_requests", 0) + 1

    sc = stats.setdefault("specialty_counter", {})
    sc[specialty] = sc.get(specialty, 0) + 1

    kc = stats.setdefault("keywords_counter", {})
    for kw in [k.strip().lower() for k in interests.split(",") if k.strip()]:
        kc[kw] = kc.get(kw, 0) + 1

    day = datetime.date.today().isoformat()
    dc = stats.setdefault("daily_counter", {})
    dc[day] = dc.get(day, 0) + 1

    _save_stats(stats)


def load_stats() -> Dict:
    if STATS_FILE.exists():
        with open(STATS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"total_requests": 0, "specialty_counter": {}, "keywords_counter": {}, "daily_counter": {}}


def _save_stats(stats: Dict):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)


def load_error_logs(limit: int = 100) -> List[Dict]:
    if not ERRORS_LOG.exists():
        return []
    entries = []
    with open(ERRORS_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
    return entries[-limit:]


def clear_logs():
    for p in [REQUESTS_LOG, ERRORS_LOG]:
        if p.exists():
            p.unlink()


def export_logs_csv() -> str:
    rows = []
    if REQUESTS_LOG.exists():
        with open(REQUESTS_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
    if not rows:
        return ""
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


# ── IP Rate Limiting ──────────────────────────────────────────────────────────

def _load_ip_limits() -> Dict:
    if IP_LIMITS_FILE.exists():
        with open(IP_LIMITS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_ip_limits(data: Dict):
    with open(IP_LIMITS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def check_rate_limit(ip: str, limit_per_hour: int) -> bool:
    """Returns True if request is allowed, False if rate limit exceeded."""
    now = time.time()
    hour_ago = now - 3600
    data = _load_ip_limits()

    timestamps = [t for t in data.get(ip, []) if t > hour_ago]
    if len(timestamps) >= limit_per_hour:
        data[ip] = timestamps
        _save_ip_limits(data)
        return False

    timestamps.append(now)
    data[ip] = timestamps
    _save_ip_limits(data)
    return True


# ── Disk Usage ────────────────────────────────────────────────────────────────

def get_disk_usage() -> Dict:
    from app.config_manager import DATA_DIR
    total = 0
    file_count = 0
    if DATA_DIR.exists():
        for p in DATA_DIR.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
                file_count += 1
    return {"bytes": total, "human": _human_size(total), "files": file_count}


def _human_size(b: int) -> str:
    for unit in ["Б", "КБ", "МБ", "ГБ"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} ТБ"


def clear_cache():
    from app.config_manager import CACHE_DIR
    if CACHE_DIR.exists():
        import shutil
        shutil.rmtree(CACHE_DIR)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
