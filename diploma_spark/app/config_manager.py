import json
import base64
import secrets
import os
from pathlib import Path
from typing import Dict, Any, List

DATA_DIR = Path("app/data")
CONFIG_DIR = DATA_DIR / "config"
LOGS_DIR = DATA_DIR / "logs"
CACHE_DIR = DATA_DIR / "cache"

DEFAULT_SYSTEM_PROMPT = """Ты — эксперт по академическим исследованиям и научному руководству дипломных работ.
Твоя задача — генерировать оригинальные, актуальные и выполнимые темы дипломных работ.
Будь конкретным, практичным и оригинальным. Учитывай уровень студента, его интересы и доступные ресурсы.
Всегда возвращай ТОЛЬКО валидный JSON без markdown-обёртки."""

DEFAULT_SPECIALTIES = [
    "Прикладная информатика",
    "Программная инженерия",
    "Информационные системы",
    "Экономика",
    "Менеджмент",
    "Психология",
    "Дизайн",
    "Биология",
    "Машиностроение",
    "Филология",
    "Юриспруденция",
    "Педагогика",
    "Социология",
    "Медицина",
    "Физика",
    "Математика",
    "Химия",
    "Архитектура",
    "Другое",
]


def init_data_dirs():
    for d in [DATA_DIR, CONFIG_DIR, LOGS_DIR, CACHE_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    _ensure_settings()
    _ensure_api_keys()
    _ensure_stats()
    _ensure_system_prompt()
    _ensure_specialties()
    _ensure_admin_credentials()


def _ensure_settings():
    path = CONFIG_DIR / "settings.json"
    if not path.exists():
        default = {
            "default_model": "gpt-4-turbo",
            "max_topics_per_request": 5,
            "temperature": 0.7,
            "timeout_seconds": 30,
            "rate_limit_per_ip_per_hour": 10,
            "save_all_requests": True,
            "enable_pdf_export": True,
            "provider_order": ["openai", "anthropic", "google", "mistral"],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2, ensure_ascii=False)


def _ensure_api_keys():
    path = CONFIG_DIR / "api_keys.json"
    if not path.exists():
        default = {
            "openai": {"key": "", "enabled": False},
            "anthropic": {"key": "", "enabled": False},
            "google": {"key": "", "enabled": False},
            "mistral": {"key": "", "enabled": False},
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2, ensure_ascii=False)


def _ensure_stats():
    path = LOGS_DIR / "stats.json"
    if not path.exists():
        default = {
            "total_requests": 0,
            "last_reset": "",
            "specialty_counter": {},
            "keywords_counter": {},
            "daily_counter": {},
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2, ensure_ascii=False)


def _ensure_system_prompt():
    path = CONFIG_DIR / "system_prompt.txt"
    if not path.exists():
        with open(path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_SYSTEM_PROMPT)


def _ensure_specialties():
    path = CONFIG_DIR / "specialties.txt"
    if not path.exists():
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(DEFAULT_SPECIALTIES))


def _ensure_admin_credentials():
    path = CONFIG_DIR / "admin_credentials.json"
    if not path.exists():
        password = os.getenv("ADMIN_PASSWORD", secrets.token_urlsafe(12))
        creds = {"password": password}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(creds, f, indent=2)
        print(f"\n{'='*50}")
        print(f"  ADMIN PASSWORD: {password}")
        print(f"  Login at: http://localhost:8000/admin/login")
        print(f"{'='*50}\n")


# ── Settings ──────────────────────────────────────────────────────────────────

def load_settings() -> Dict:
    with open(CONFIG_DIR / "settings.json", encoding="utf-8") as f:
        return json.load(f)


def save_settings(settings: Dict):
    with open(CONFIG_DIR / "settings.json", "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


# ── API Keys ──────────────────────────────────────────────────────────────────

def _encode_key(key: str) -> str:
    return base64.b64encode(key.encode()).decode() if key else ""


def _decode_key(encoded: str) -> str:
    try:
        return base64.b64decode(encoded.encode()).decode() if encoded else ""
    except Exception:
        return encoded  # already plaintext (legacy)


def load_api_keys() -> Dict:
    with open(CONFIG_DIR / "api_keys.json", encoding="utf-8") as f:
        raw = json.load(f)
    # decode keys transparently
    decoded = {}
    for provider, info in raw.items():
        decoded[provider] = {
            "key": _decode_key(info.get("key", "")),
            "enabled": info.get("enabled", False),
        }
    return decoded


def save_api_keys(keys: Dict):
    encoded = {}
    for provider, info in keys.items():
        encoded[provider] = {
            "key": _encode_key(info.get("key", "")),
            "enabled": info.get("enabled", False),
        }
    with open(CONFIG_DIR / "api_keys.json", "w", encoding="utf-8") as f:
        json.dump(encoded, f, indent=2, ensure_ascii=False)


# ── System Prompt ─────────────────────────────────────────────────────────────

def load_system_prompt() -> str:
    with open(CONFIG_DIR / "system_prompt.txt", encoding="utf-8") as f:
        return f.read()


def save_system_prompt(text: str):
    with open(CONFIG_DIR / "system_prompt.txt", "w", encoding="utf-8") as f:
        f.write(text)


# ── Specialties ───────────────────────────────────────────────────────────────

def load_specialties() -> List[str]:
    with open(CONFIG_DIR / "specialties.txt", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def save_specialties(specialties: List[str]):
    with open(CONFIG_DIR / "specialties.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(specialties))


# ── Admin Credentials ─────────────────────────────────────────────────────────

def load_admin_password() -> str:
    env_pass = os.getenv("ADMIN_PASSWORD")
    if env_pass:
        return env_pass
    path = CONFIG_DIR / "admin_credentials.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("password", "admin123")
    return "admin123"


def save_admin_password(new_password: str):
    path = CONFIG_DIR / "admin_credentials.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"password": new_password}, f, indent=2)
