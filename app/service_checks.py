"""Pure logic and defaults for service/product checks in duty mode."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re

from app.templates import get_otrs_service_check_template, render_template


AUTH_NONE = "none"
AUTH_HTML_FORM = "html_form"
AUTH_WEBENGINE_SESSION = "webengine_session"
AUTH_EXISTING_SESSION = "existing_session"
AUTH_VISIBLE_HTML_FORM = "visible_html_form"

SERVICE_CHECK_STATUSES = {
    "not_checked": "Не проверено",
    "checking": "Проверяется",
    "ok": "ОК",
    "auth_error": "Ошибка авторизации",
    "load_error": "Ошибка загрузки",
    "timeout": "Таймаут",
    "unknown": "Неизвестно",
    "error": "Ошибка",
    "ssl_error": "Ошибка SSL-сертификата",
    "manual_required": "Требуется ручная проверка",
}

DEFAULT_SERVICE_CHECKS = {
    "otrs_task_url": "",
    "items": [],
}

DEFAULT_SERVICE_ITEM = {
    "id": "",
    "name": "Новый продукт",
    "enabled": True,
    "url": "",
    "auth_type": AUTH_NONE,
    "login_selector": "",
    "password_selector": "",
    "submit_selector": "",
    "success_texts": [],
    "error_texts": [],
    "timeout_seconds": 15,
    "post_login_delay_ms": 1500,
    "allow_insecure_ssl": False,
    "visible_window_close_on_success": True,
    "visible_window_close_on_error": False,
    "visible_window_close_delay_seconds": 3,
}


def default_service_checks_config():
    return deepcopy(DEFAULT_SERVICE_CHECKS)


def default_service_item(item_id=""):
    item = deepcopy(DEFAULT_SERVICE_ITEM)
    item["id"] = normalize_service_id(item_id or item["name"])
    return item


def parse_text_markers(value):
    """Parse semicolon-separated success/error markers, preserving order."""
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").split(";")
    result = []
    seen = set()
    for item in raw_items:
        text = str(item or "").strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def normalize_service_id(value):
    text = str(value or "").strip().casefold()
    translit = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
        "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
        "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
        "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    text = "".join(translit.get(ch, ch) for ch in text)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "service"


def unique_service_id(base_value, items, current_id=""):
    base = normalize_service_id(base_value)
    used = {
        str(item.get("id", ""))
        for item in (items or [])
        if str(item.get("id", "")) and str(item.get("id", "")) != str(current_id or "")
    }
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def ensure_service_checks_defaults(config):
    settings = config.setdefault("service_checks", {})
    settings.setdefault("otrs_task_url", "")
    items = settings.setdefault("items", [])
    normalized = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        merged = deepcopy(DEFAULT_SERVICE_ITEM)
        merged.update(deepcopy(item))
        merged["id"] = unique_service_id(merged.get("id") or merged.get("name") or f"service_{index + 1}", normalized)
        merged["name"] = str(merged.get("name") or merged["id"]).strip() or "Новый продукт"
        merged["enabled"] = bool(merged.get("enabled", True))
        merged["allow_insecure_ssl"] = bool(merged.get("allow_insecure_ssl", False))
        valid_auth_types = {AUTH_NONE, AUTH_HTML_FORM, AUTH_WEBENGINE_SESSION, AUTH_EXISTING_SESSION, AUTH_VISIBLE_HTML_FORM}
        merged["auth_type"] = merged.get("auth_type") if merged.get("auth_type") in valid_auth_types else AUTH_NONE
        merged["visible_window_close_on_success"] = bool(merged.get("visible_window_close_on_success", True))
        merged["visible_window_close_on_error"] = bool(merged.get("visible_window_close_on_error", False))
        try:
            merged["visible_window_close_delay_seconds"] = max(0, int(merged.get("visible_window_close_delay_seconds", 3)))
        except Exception:
            merged["visible_window_close_delay_seconds"] = 3
        merged["success_texts"] = parse_text_markers(merged.get("success_texts", []))
        merged["error_texts"] = parse_text_markers(merged.get("error_texts", []))
        try:
            merged["timeout_seconds"] = max(1, int(merged.get("timeout_seconds", 15)))
        except Exception:
            merged["timeout_seconds"] = 15
        try:
            merged["post_login_delay_ms"] = max(0, int(merged.get("post_login_delay_ms", 1500)))
        except Exception:
            merged["post_login_delay_ms"] = 1500
        normalized.append(merged)
    settings["items"] = normalized
    return settings


def evaluate_service_check_page(service, page_text, loaded=True, timed_out=False, error=""):
    if timed_out:
        return "timeout", "", "", error or "Истёк таймаут проверки"
    if not loaded:
        return "load_error", "", "", error or "Страница не загрузилась"

    text = str(page_text or "")
    lowered = text.casefold()
    for marker in parse_text_markers(service.get("error_texts", [])):
        if marker.casefold() in lowered:
            return "auth_error", "", marker, f"найден текст “{marker}”"
    for marker in parse_text_markers(service.get("success_texts", [])):
        if marker.casefold() in lowered:
            return "ok", marker, "", ""
    return "unknown", "", "", "Не найдены признаки успеха или ошибки"


def make_service_result(service, status="not_checked", error="", matched_success_text="", matched_error_text="", page_excerpt="", duration_ms=0, checked_at=None, warning=""):
    return {
        "service_id": service.get("id", ""),
        "name": service.get("name", ""),
        "url": service.get("url", ""),
        "status": status,
        "checked_at": checked_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "error": error or "",
        "matched_success_text": matched_success_text or "",
        "matched_error_text": matched_error_text or "",
        "page_excerpt": str(page_excerpt or "")[:500],
        "duration_ms": int(duration_ms or 0),
        "warning": warning or "",
    }


def summarize_service_results(results):
    results = list(results or [])
    ok = sum(1 for item in results if item.get("status") == "ok")
    timeout = sum(1 for item in results if item.get("status") == "timeout")
    unknown = sum(1 for item in results if item.get("status") == "unknown")
    errors = sum(1 for item in results if item.get("status") not in {"ok", "unknown", "not_checked", "checking"})
    return {
        "total": len(results),
        "ok": ok,
        "errors": errors,
        "timeouts": timeout,
        "unknown": unknown,
    }


def service_status_label(status):
    return SERVICE_CHECK_STATUSES.get(str(status or ""), SERVICE_CHECK_STATUSES["error"])


def build_service_note_context(results, checked_at=None):
    results = list(results or [])
    stats = summarize_service_results(results)
    checked_at = checked_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    error_lines = []
    for index, result in enumerate(results, start=1):
        status_label = service_status_label(result.get("status"))
        lines.append(f"{index}. {result.get('name') or result.get('service_id') or 'Сервис'} — {status_label}")
        details = []
        if result.get("error"):
            details.append(f"Ошибка: {result.get('error')}")
        if result.get("warning"):
            details.append(f"Предупреждение: {result.get('warning')}")
        if result.get("url"):
            details.append(f"URL: {result.get('url')}")
        if details:
            if result.get("status") != "ok" or result.get("warning"):
                lines.extend(f"   {detail}" for detail in details)
            if result.get("status") != "ok":
                error_lines.append(f"{result.get('name') or result.get('service_id')}: {'; '.join(details)}")
    return {
        "checked_at": checked_at,
        "services_total_count": stats["total"],
        "services_ok_count": stats["ok"],
        "services_error_count": stats["errors"],
        "services_timeout_count": stats["timeouts"],
        "services_unknown_count": stats["unknown"],
        "services_results": "\n".join(lines) if lines else "Нет сервисов для проверки",
        "services_errors": "\n".join(error_lines) if error_lines else "Не обнаружены",
    }


def build_service_check_note_text(config, results, checked_at=None):
    template = get_otrs_service_check_template(config)
    return render_template(template.get("text", ""), build_service_note_context(results, checked_at=checked_at))


def service_credentials_key(service_id):
    return f"service_check::{normalize_service_id(service_id)}"
