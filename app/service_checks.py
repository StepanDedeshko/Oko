"""Pure logic and defaults for service/product checks in duty mode."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
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
    "autofill_error": "Ошибка автозаполнения формы",
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



def build_auth_form_js(service, credentials, blur_fields=True):
    """Build a synchronous autofill script returning a plain object for Qt WebEngine."""
    login_selector = json.dumps(service.get("login_selector", ""))
    password_selector = json.dumps(service.get("password_selector", ""))
    submit_selector = json.dumps(service.get("submit_selector", ""))
    login_value = json.dumps(credentials.get("login", ""))
    password_value = json.dumps(credentials.get("password", ""))
    blur_line = 'element.dispatchEvent(new Event("blur", { bubbles: true }));' if blur_fields else ""
    return f"""
(function () {{
  function selectorSummary(element) {{
    if (!element) return "";
    const parts = [String(element.tagName || "").toLowerCase()];
    const type = element.getAttribute && element.getAttribute("type");
    const id = element.getAttribute && element.getAttribute("id");
    const className = element.getAttribute && element.getAttribute("class");
    if (type) parts.push("[type=" + type + "]");
    if (id) parts.push("#" + id);
    if (className) parts.push("." + String(className).trim().split(/\\s+/).filter(Boolean).join("."));
    return parts.join("");
  }}
  function diagnostics(login, password, submit) {{
    const textInputs = Array.from(document.querySelectorAll('input[type="text"], input:not([type]), textarea')).slice(0, 8).map(selectorSummary);
    const passwordInputs = Array.from(document.querySelectorAll('input[type="password"]')).slice(0, 8).map(selectorSummary);
    const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"]')).slice(0, 8).map(selectorSummary);
    return {{
      login_found: !!login,
      password_found: !!password,
      submit_found: !!submit,
      ready_state: document.readyState || "",
      iframe_count: document.querySelectorAll("iframe").length,
      text_input_count: document.querySelectorAll('input[type="text"], input:not([type]), textarea').length,
      password_input_count: document.querySelectorAll('input[type="password"]').length,
      button_count: document.querySelectorAll('button, input[type="submit"], input[type="button"]').length,
      found_inputs: textInputs.concat(passwordInputs),
      found_buttons: buttons
    }};
  }}
  function setNativeValue(element, value) {{
    const prototype = Object.getPrototypeOf(element);
    const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
    if (descriptor && descriptor.set) {{
      descriptor.set.call(element, value);
    }} else {{
      element.value = value;
    }}
    element.dispatchEvent(new Event("input", {{ bubbles: true }}));
    element.dispatchEvent(new Event("change", {{ bubbles: true }}));
    {blur_line}
  }}
  function clickElement(element) {{
    element.dispatchEvent(new MouseEvent("mousedown", {{ bubbles: true, cancelable: true, view: window }}));
    element.dispatchEvent(new MouseEvent("mouseup", {{ bubbles: true, cancelable: true, view: window }}));
    element.dispatchEvent(new MouseEvent("click", {{ bubbles: true, cancelable: true, view: window }}));
  }}
  try {{
    const loginSelector = {login_selector};
    const passwordSelector = {password_selector};
    const submitSelector = {submit_selector};
    const login = document.querySelector(loginSelector);
    const password = document.querySelector(passwordSelector);
    const submit = document.querySelector(submitSelector);
    const info = diagnostics(login, password, submit);
    const missing = [];
    if (!login) missing.push("login");
    if (!password) missing.push("password");
    if (!submit) missing.push("submit");
    if (missing.length) {{
      return Object.assign({{ ok: false, error: "missing_form_elements", missing: missing }}, info);
    }}
    login.focus();
    setNativeValue(login, {login_value});
    password.focus();
    setNativeValue(password, {password_value});
    window.setTimeout(function () {{ clickElement(submit); }}, 0);
    return Object.assign({{ ok: true, clicked: true }}, info);
  }} catch (error) {{
    return {{
      ok: false,
      error: "autofill_failed",
      message: String(error && error.message ? error.message : error),
      ready_state: document.readyState || "",
      iframe_count: document.querySelectorAll("iframe").length,
      text_input_count: document.querySelectorAll('input[type="text"], input:not([type]), textarea').length,
      password_input_count: document.querySelectorAll('input[type="password"]').length,
      button_count: document.querySelectorAll('button, input[type="submit"], input[type="button"]').length
    }};
  }}
}})()
"""


def _autofill_diagnostics_lines(result):
    if not isinstance(result, dict):
        return []
    lines = [
        f"document.readyState: {result.get('ready_state', '')}",
        f"iframe на странице: {result.get('iframe_count', 0)}",
        f"input[type=text]/textarea: {result.get('text_input_count', 0)}",
        f"input[type=password]: {result.get('password_input_count', 0)}",
        f"button/input submit: {result.get('button_count', 0)}",
    ]
    found_inputs = [str(item) for item in (result.get("found_inputs") or []) if str(item).strip()]
    found_buttons = [str(item) for item in (result.get("found_buttons") or []) if str(item).strip()]
    if found_inputs:
        lines.append("Найдены input: " + ", ".join(found_inputs))
    if found_buttons:
        lines.append("Найдены button: " + ", ".join(found_buttons))
    return lines


def build_autofill_error_message(service, result):
    if result is None:
        return "JS автозаполнения не вернул результат. Возможно, QtWebEngine получил undefined из runJavaScript."
    if not isinstance(result, dict):
        return "Ошибка автозаполнения формы: JS автозаполнения не вернул корректный результат."
    if result.get("error") == "missing_form_elements":
        missing = set(result.get("missing") or [])
        lines = ["Не найдены элементы формы авторизации:"]
        if "login" in missing:
            lines.append(f"- поле логина: {service.get('login_selector', '')}")
        if "password" in missing:
            lines.append(f"- поле пароля: {service.get('password_selector', '')}")
        if "submit" in missing:
            lines.append(f"- кнопка входа: {service.get('submit_selector', '')}")
        lines.extend(_autofill_diagnostics_lines(result))
        return "\n".join(lines)
    if result.get("error") == "autofill_failed":
        lines = ["Ошибка автозаполнения формы: " + str(result.get("message") or "неизвестная ошибка")]
        lines.extend(_autofill_diagnostics_lines(result))
        return "\n".join(lines)
    lines = ["Ошибка автозаполнения формы: JS автозаполнения не вернул корректный результат."]
    lines.extend(_autofill_diagnostics_lines(result))
    return "\n".join(lines)


def safe_autofill_result_repr(result, max_length=800):
    text = repr(result)
    for marker in ("password", "passwd", "token", "cookie", "session", "credential", "secret"):
        text = re.sub(marker + r"[^,;}\n]*", marker + "=<redacted>", text, flags=re.IGNORECASE)
    if len(text) > max_length:
        text = text[:max_length] + "…"
    return text


def service_result_display_label(result):
    status = result.get("status") if isinstance(result, dict) else str(result or "")
    if isinstance(result, dict) and result.get("manual"):
        details = str(result.get("details") or "")
        if status == "ok":
            return "ОК — подтверждено вручную"
        if status == "error":
            return "Ошибка — подтверждена вручную"
        if status == "unknown" and "пропущ" in details.casefold():
            return "Пропущено вручную"
    return service_status_label(status)

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


def make_service_result(service, status="not_checked", error="", matched_success_text="", matched_error_text="", page_excerpt="", duration_ms=0, checked_at=None, warning="", manual=False, details=""):
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
        "manual": bool(manual),
        "details": details or "",
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
        status_label = service_result_display_label(result)
        lines.append(f"{index}. {result.get('name') or result.get('service_id') or 'Сервис'} — {status_label}")
        details = []
        if result.get("error"):
            details.append(f"Ошибка: {result.get('error')}")
        if result.get("details"):
            details.append(f"Детали: {result.get('details')}")
        if result.get("warning"):
            details.append(f"Предупреждение: {result.get('warning')}")
        if result.get("url"):
            details.append(f"URL: {result.get('url')}")
        if details:
            if result.get("status") != "ok" or result.get("warning") or result.get("details"):
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
