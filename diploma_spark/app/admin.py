import os
import sys
import json
import platform
import importlib.metadata
from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.config_manager import (
    load_api_keys, save_api_keys, load_settings, save_settings,
    load_system_prompt, save_system_prompt, load_specialties, save_specialties,
    load_admin_password, save_admin_password,
)
from app.file_storage import (
    load_stats, load_error_logs, clear_logs, export_logs_csv,
    get_disk_usage, clear_cache,
)
from app.ai_engine import AIEngine

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

SESSION_COOKIE = "ds_admin_auth"
PROVIDERS = ["openai", "anthropic", "google", "mistral"]
PROVIDER_NAMES = {
    "openai": "OpenAI (GPT)",
    "anthropic": "Anthropic (Claude)",
    "google": "Google Gemini",
    "mistral": "Mistral AI",
}


# ── Auth helpers ──────────────────────────────────────────────────────────────

def is_authenticated(request: Request) -> bool:
    return request.cookies.get(SESSION_COOKIE) == "authenticated"


def require_auth(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})


# ── Login ─────────────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def admin_login_form(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/admin/dashboard", status_code=302)
    return templates.TemplateResponse("admin_login.html", {"request": request, "error": None})


@router.post("/login")
async def admin_login(request: Request, password: str = Form(...)):
    correct = load_admin_password()
    if password == correct:
        response = RedirectResponse("/admin/dashboard", status_code=302)
        response.set_cookie(SESSION_COOKIE, "authenticated", httponly=True, samesite="lax")
        return response
    return templates.TemplateResponse("admin_login.html", {
        "request": request,
        "error": "Неверный пароль",
    })


@router.get("/logout")
async def admin_logout():
    response = RedirectResponse("/admin/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    stats = load_stats()
    keys = load_api_keys()
    settings = load_settings()
    enabled_count = sum(1 for k in keys.values() if k.get("enabled") and k.get("key"))
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "stats": stats,
        "settings": settings,
        "enabled_count": enabled_count,
        "provider_names": PROVIDER_NAMES,
    })


# ── API Keys ──────────────────────────────────────────────────────────────────

@router.get("/keys", response_class=HTMLResponse)
async def admin_keys_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    keys = load_api_keys()
    settings = load_settings()
    return templates.TemplateResponse("admin_keys.html", {
        "request": request,
        "keys": keys,
        "providers": PROVIDERS,
        "provider_names": PROVIDER_NAMES,
        "provider_order": settings.get("provider_order", PROVIDERS),
        "success": request.query_params.get("saved"),
    })


@router.post("/keys/save")
async def admin_keys_save(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    keys = load_api_keys()

    for provider in PROVIDERS:
        new_key = form.get(f"{provider}_key", "").strip()
        if new_key:
            keys.setdefault(provider, {})["key"] = new_key
        elif provider not in keys:
            keys[provider] = {"key": "", "enabled": False}

        keys[provider]["enabled"] = f"{provider}_enabled" in form

    # Handle custom providers
    new_providers = {}
    for field_name, value in form.items():
        if field_name.startswith("custom_name_"):
            idx = field_name.replace("custom_name_", "")
            name = value.strip().lower().replace(" ", "_")
            key_val = form.get(f"custom_key_{idx}", "").strip()
            if name and key_val:
                new_providers[name] = {"key": key_val, "enabled": True}

    keys.update(new_providers)

    # Update provider order
    order_raw = form.get("provider_order", "")
    if order_raw:
        order = [p.strip() for p in order_raw.split(",") if p.strip()]
        settings = load_settings()
        settings["provider_order"] = order
        save_settings(settings)

    save_api_keys(keys)
    return RedirectResponse("/admin/keys?saved=1", status_code=302)


@router.post("/keys/verify")
async def admin_keys_verify(request: Request):
    if not is_authenticated(request):
        return JSONResponse({"ok": False, "message": "Не авторизован"}, status_code=401)
    body = await request.json()
    provider = body.get("provider", "")
    api_key = body.get("key", "")
    engine = AIEngine()
    result = await engine.verify_key(provider, api_key)
    return JSONResponse(result)


# ── Settings ──────────────────────────────────────────────────────────────────

@router.get("/settings", response_class=HTMLResponse)
async def admin_settings_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    settings = load_settings()
    return templates.TemplateResponse("admin_settings.html", {
        "request": request,
        "settings": settings,
        "success": request.query_params.get("saved"),
    })


@router.post("/settings/save")
async def admin_settings_save(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    settings = load_settings()

    settings["default_model"] = form.get("default_model", settings["default_model"]).strip()
    settings["max_topics_per_request"] = int(form.get("max_topics_per_request", 5))
    settings["temperature"] = float(form.get("temperature", 0.7))
    settings["timeout_seconds"] = int(form.get("timeout_seconds", 30))
    settings["rate_limit_per_ip_per_hour"] = int(form.get("rate_limit_per_ip_per_hour", 10))
    settings["save_all_requests"] = "save_all_requests" in form
    settings["enable_pdf_export"] = "enable_pdf_export" in form

    save_settings(settings)
    return RedirectResponse("/admin/settings?saved=1", status_code=302)


@router.post("/settings/change_password")
async def admin_change_password(request: Request,
                                 current_password: str = Form(...),
                                 new_password: str = Form(...)):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    if current_password != load_admin_password():
        settings = load_settings()
        return templates.TemplateResponse("admin_settings.html", {
            "request": request,
            "settings": settings,
            "pw_error": "Текущий пароль неверный",
        })
    save_admin_password(new_password)
    return RedirectResponse("/admin/settings?saved=1", status_code=302)


# ── Specialties ───────────────────────────────────────────────────────────────

@router.get("/specialties", response_class=HTMLResponse)
async def admin_specialties_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    specialties = load_specialties()
    return templates.TemplateResponse("admin_settings.html", {
        "request": request,
        "settings": load_settings(),
        "specialties": specialties,
        "success": request.query_params.get("saved"),
    })


@router.post("/specialties/save")
async def admin_specialties_save(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    raw = form.get("specialties_text", "")
    specialties = [line.strip() for line in raw.splitlines() if line.strip()]
    save_specialties(specialties)
    return RedirectResponse("/admin/settings?saved=1", status_code=302)


# ── Statistics ────────────────────────────────────────────────────────────────

@router.get("/stats", response_class=HTMLResponse)
async def admin_stats_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    stats = load_stats()
    errors = load_error_logs(limit=50)

    # Top-10 specialties
    top_specialties = sorted(
        stats.get("specialty_counter", {}).items(), key=lambda x: x[1], reverse=True
    )[:10]

    # Top-20 keywords
    top_keywords = sorted(
        stats.get("keywords_counter", {}).items(), key=lambda x: x[1], reverse=True
    )[:20]

    # Daily chart data (last 30 days)
    import datetime
    daily = stats.get("daily_counter", {})
    today = datetime.date.today()
    chart_labels = []
    chart_data = []
    for i in range(29, -1, -1):
        day = (today - datetime.timedelta(days=i)).isoformat()
        chart_labels.append(day[5:])  # MM-DD
        chart_data.append(daily.get(day, 0))

    return templates.TemplateResponse("admin_stats.html", {
        "request": request,
        "stats": stats,
        "errors": errors,
        "top_specialties": top_specialties,
        "top_keywords": top_keywords,
        "chart_labels": json.dumps(chart_labels),
        "chart_data": json.dumps(chart_data),
    })


@router.post("/clear_logs")
async def admin_clear_logs(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    clear_logs()
    return RedirectResponse("/admin/stats", status_code=302)


@router.get("/download_logs")
async def admin_download_logs(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    csv_data = export_logs_csv()
    return PlainTextResponse(
        csv_data,
        headers={"Content-Disposition": "attachment; filename=requests_log.csv"},
        media_type="text/csv",
    )


# ── Prompt Editor ─────────────────────────────────────────────────────────────

@router.get("/prompts", response_class=HTMLResponse)
async def admin_prompts_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    prompt = load_system_prompt()
    return templates.TemplateResponse("admin_prompts.html", {
        "request": request,
        "prompt": prompt,
        "success": request.query_params.get("saved"),
    })


@router.post("/prompts/save")
async def admin_prompts_save(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    text = form.get("prompt_text", "").strip()
    save_system_prompt(text)
    return RedirectResponse("/admin/prompts?saved=1", status_code=302)


# ── System Info ───────────────────────────────────────────────────────────────

@router.get("/system", response_class=HTMLResponse)
async def admin_system_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    disk = get_disk_usage()

    # Installed packages
    try:
        packages = sorted(
            [(d.metadata["Name"], d.version) for d in importlib.metadata.distributions()],
            key=lambda x: x[0].lower()
        )
    except Exception:
        packages = []

    return templates.TemplateResponse("admin_system.html", {
        "request": request,
        "python_version": sys.version,
        "platform": platform.platform(),
        "disk": disk,
        "packages": packages,
    })


@router.post("/clear_cache")
async def admin_clear_cache(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    clear_cache()
    return RedirectResponse("/admin/system", status_code=302)
