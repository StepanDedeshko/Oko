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
    "success_selectors": [],
    "error_selectors": [],
    "timeout_seconds": 15,
    "post_login_delay_ms": 1500,
    "allow_insecure_ssl": False,
    "allow_http_error_load": False,
    "visible_window_close_on_success": True,
    "visible_window_close_on_error": False,
    "visible_window_close_delay_seconds": 3,
    "logout_menu_selector": "",
    "logout_button_selector": "",
    "logout_success_selectors": [],
    "logout_success_texts": [],
    "logout_wait_seconds": 10,
    "logout_menu_wait_seconds": 5,
}



def visible_service_start_diagnostics(service):
    service = service or {}
    return {
        "service_id": service.get("id", ""),
        "auth_type": service.get("auth_type", ""),
        "has_url": bool(service.get("url")),
        "has_login_selector": bool(service.get("login_selector")),
        "has_password_selector": bool(service.get("password_selector")),
        "has_submit_selector": bool(service.get("submit_selector")),
    }


def visible_html_form_should_start_autofill_wait(service):
    diagnostics = visible_service_start_diagnostics(service)
    return all([
        diagnostics["has_url"],
        diagnostics["has_login_selector"],
        diagnostics["has_password_selector"],
        diagnostics["has_submit_selector"],
    ])


def can_open_next_visible_service_after_cleanup(cleanup_completed, current_dialog_active=False):
    return bool(cleanup_completed) and not bool(current_dialog_active)

def default_service_checks_config():
    return deepcopy(DEFAULT_SERVICE_CHECKS)


def default_service_item(item_id=""):
    item = deepcopy(DEFAULT_SERVICE_ITEM)
    item["id"] = normalize_service_id(item_id or item["name"])
    return item


def _dedupe_markers(raw_items):
    result = []
    seen = set()
    for item in raw_items:
        text = str(item or "").strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def parse_text_markers(value):
    """Parse semicolon-separated success/error text markers, preserving order."""
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").split(";")
    return _dedupe_markers(raw_items)


def parse_selector_markers(value):
    """Parse semicolon/newline-separated CSS selectors, preserving order."""
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[;\n]+", str(value or ""))
    return _dedupe_markers(raw_items)


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
        merged["allow_http_error_load"] = bool(merged.get("allow_http_error_load", False))
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
        merged["success_selectors"] = parse_selector_markers(merged.get("success_selectors", []))
        merged["error_selectors"] = parse_selector_markers(merged.get("error_selectors", []))
        merged["logout_success_selectors"] = parse_selector_markers(merged.get("logout_success_selectors", []))
        merged["logout_success_texts"] = parse_text_markers(merged.get("logout_success_texts", []))
        try:
            merged["logout_wait_seconds"] = max(1, int(merged.get("logout_wait_seconds", 10)))
        except Exception:
            merged["logout_wait_seconds"] = 10
        try:
            merged["logout_menu_wait_seconds"] = max(1, int(merged.get("logout_menu_wait_seconds", 5)))
        except Exception:
            merged["logout_menu_wait_seconds"] = 5
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
    """Build a synchronous autofill script returning a JSON string for Qt WebEngine."""
    login_selector = json.dumps(service.get("login_selector", ""))
    password_selector = json.dumps(service.get("password_selector", ""))
    submit_selector = json.dumps(service.get("submit_selector", ""))
    login_value = json.dumps(credentials.get("login", ""))
    password_value = json.dumps(credentials.get("password", ""))
    blur_line = 'element.dispatchEvent(new Event("blur", { bubbles: true }));' if blur_fields else ""
    return f"""
(function () {{
  function safeText(value) {{
    return String(value || "").replace(/[\\r\\n\\t]+/g, " ").replace(/\\s+/g, " ").trim().slice(0, 120);
  }}
  function safeLocationHref() {{
    try {{
      return String(window.location.origin || "") + String(window.location.pathname || "");
    }} catch (error) {{
      return "";
    }}
  }}
  function selectorSummary(element) {{
    if (!element) return "";
    const tag = String(element.tagName || "").toLowerCase();
    const type = element.getAttribute && element.getAttribute("type");
    const id = element.getAttribute && element.getAttribute("id");
    const className = element.getAttribute && element.getAttribute("class");
    const placeholder = element.getAttribute && element.getAttribute("placeholder");
    const ariaLabel = element.getAttribute && element.getAttribute("aria-label");
    const name = element.getAttribute && element.getAttribute("name");
    const text = tag === "button" ? safeText(element.innerText || element.textContent || "") : "";
    const span = tag === "button" && element.querySelector ? safeText((element.querySelector("span") || {{}}).innerText || "") : "";
    const parts = [tag];
    if (type) parts.push("type=" + safeText(type));
    if (id) parts.push("id=" + safeText(id));
    if (className) parts.push("class=" + safeText(className));
    if (placeholder) parts.push("placeholder=" + safeText(placeholder));
    if (ariaLabel) parts.push("aria-label=" + safeText(ariaLabel));
    if (name) parts.push("name=" + safeText(name));
    if (text) parts.push("text=" + text);
    if (span && span !== text) parts.push("span=" + span);
    return parts.join(" ");
  }}
  function diagnostics(login, password, submit) {{
    const textInputs = Array.from(document.querySelectorAll('input[type="text"], input:not([type]), input[type="email"], input[type="tel"], textarea')).slice(0, 12).map(selectorSummary);
    const passwordInputs = Array.from(document.querySelectorAll('input[type="password"]')).slice(0, 12).map(selectorSummary);
    const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"]')).slice(0, 12).map(selectorSummary);
    const textInputCount = document.querySelectorAll('input[type="text"], input:not([type]), input[type="email"], input[type="tel"], textarea').length;
    return {{
      login_found: !!login,
      password_found: !!password,
      submit_found: !!submit,
      ready_state: document.readyState || "",
      location_href: safeLocationHref(),
      iframe_count: document.querySelectorAll("iframe").length,
      input_text_count: textInputCount,
      text_input_count: textInputCount,
      input_password_count: document.querySelectorAll('input[type="password"]').length,
      password_input_count: document.querySelectorAll('input[type="password"]').length,
      button_count: document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"]').length,
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
      return JSON.stringify({{
        ok: false,
        error: "missing_form_elements",
        missing: missing,
        login_found: info.login_found,
        password_found: info.password_found,
        submit_found: info.submit_found,
        diagnostics: info
      }});
    }}
    login.focus();
    setNativeValue(login, {login_value});
    password.focus();
    setNativeValue(password, {password_value});
    window.setTimeout(function () {{ clickElement(submit); }}, 100);
    return JSON.stringify({{
      ok: true,
      clicked: true,
      login_found: info.login_found,
      password_found: info.password_found,
      submit_found: info.submit_found,
      diagnostics: info
    }});
  }} catch (error) {{
    const fallbackDiagnostics = diagnostics(null, null, null);
    return JSON.stringify({{
      ok: false,
      error: "autofill_failed",
      message: String(error && error.message ? error.message : error),
      diagnostics: fallbackDiagnostics
    }});
  }}
}})()
""".strip()



def build_auth_form_presence_js(service):
    """Build a synchronous script that checks auth form presence and returns JSON diagnostics."""
    login_selector = json.dumps(service.get("login_selector", ""))
    password_selector = json.dumps(service.get("password_selector", ""))
    submit_selector = json.dumps(service.get("submit_selector", ""))
    return f"""
(function () {{
  function safeText(value) {{
    return String(value || "").replace(/[\\r\\n\\t]+/g, " ").replace(/\\s+/g, " ").trim().slice(0, 120);
  }}
  function safeLocationHref() {{
    try {{
      return String(window.location.origin || "") + String(window.location.pathname || "");
    }} catch (error) {{
      return "";
    }}
  }}
  function selectorSummary(element) {{
    if (!element) return "";
    const tag = String(element.tagName || "").toLowerCase();
    const type = element.getAttribute && element.getAttribute("type");
    const id = element.getAttribute && element.getAttribute("id");
    const className = element.getAttribute && element.getAttribute("class");
    const placeholder = element.getAttribute && element.getAttribute("placeholder");
    const ariaLabel = element.getAttribute && element.getAttribute("aria-label");
    const name = element.getAttribute && element.getAttribute("name");
    const text = tag === "button" ? safeText(element.innerText || element.textContent || "") : "";
    const span = tag === "button" && element.querySelector ? safeText((element.querySelector("span") || {{}}).innerText || "") : "";
    const parts = [tag];
    if (type) parts.push("type=" + safeText(type));
    if (id) parts.push("id=" + safeText(id));
    if (className) parts.push("class=" + safeText(className));
    if (placeholder) parts.push("placeholder=" + safeText(placeholder));
    if (ariaLabel) parts.push("aria-label=" + safeText(ariaLabel));
    if (name) parts.push("name=" + safeText(name));
    if (text) parts.push("text=" + text);
    if (span && span !== text) parts.push("span=" + span);
    return parts.join(" ");
  }}
  function diagnostics(login, password, submit) {{
    const textInputs = Array.from(document.querySelectorAll('input[type="text"], input:not([type]), input[type="email"], input[type="tel"], textarea')).slice(0, 12).map(selectorSummary);
    const passwordInputs = Array.from(document.querySelectorAll('input[type="password"]')).slice(0, 12).map(selectorSummary);
    const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"]')).slice(0, 12).map(selectorSummary);
    const textInputCount = document.querySelectorAll('input[type="text"], input:not([type]), input[type="email"], input[type="tel"], textarea').length;
    return {{
      login_found: !!login,
      password_found: !!password,
      submit_found: !!submit,
      ready_state: document.readyState || "",
      location_href: safeLocationHref(),
      iframe_count: document.querySelectorAll("iframe").length,
      input_text_count: textInputCount,
      text_input_count: textInputCount,
      input_password_count: document.querySelectorAll('input[type="password"]').length,
      password_input_count: document.querySelectorAll('input[type="password"]').length,
      button_count: document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"]').length,
      found_inputs: textInputs.concat(passwordInputs),
      found_buttons: buttons
    }};
  }}
  try {{
    const login = document.querySelector({login_selector});
    const password = document.querySelector({password_selector});
    const submit = document.querySelector({submit_selector});
    const info = diagnostics(login, password, submit);
    const missing = [];
    if (!login) missing.push("login");
    if (!password) missing.push("password");
    if (!submit) missing.push("submit");
    return JSON.stringify({{
      ok: missing.length === 0,
      error: missing.length ? "missing_form_elements" : "",
      missing: missing,
      login_found: info.login_found,
      password_found: info.password_found,
      submit_found: info.submit_found,
      diagnostics: info
    }});
  }} catch (error) {{
    return JSON.stringify({{
      ok: false,
      error: "autofill_wait_failed",
      message: String(error && error.message ? error.message : error),
      diagnostics: {{
        ready_state: document.readyState || "",
        location_href: safeLocationHref(),
        iframe_count: document.querySelectorAll("iframe").length,
        input_text_count: document.querySelectorAll('input[type="text"], input:not([type]), input[type="email"], input[type="tel"], textarea').length,
        input_password_count: document.querySelectorAll('input[type="password"]').length,
        button_count: document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"]').length,
        login_found: false,
        password_found: false,
        submit_found: false,
        found_inputs: [],
        found_buttons: []
      }}
    }});
  }}
}})()
""".strip()


def build_load_false_diagnostics_js(service):
    """Build safe diagnostics for pages where QtWebEngine reports loadFinished(False)."""
    login_selector = json.dumps(service.get("login_selector", ""))
    password_selector = json.dumps(service.get("password_selector", ""))
    submit_selector = json.dumps(service.get("submit_selector", ""))
    success_selectors = json.dumps(parse_selector_markers(service.get("success_selectors", [])), ensure_ascii=False)
    error_selectors = json.dumps(parse_selector_markers(service.get("error_selectors", [])), ensure_ascii=False)
    return f"""
(function () {{
  function safeText(value) {{
    return String(value || "").replace(/[\\r\\n\\t]+/g, " ").replace(/\\s+/g, " ").trim().slice(0, 120);
  }}
  function summary(element) {{
    if (!element) return "";
    const tag = String(element.tagName || "").toLowerCase();
    const id = element.getAttribute && element.getAttribute("id");
    const className = element.getAttribute && element.getAttribute("class");
    const ariaLabel = element.getAttribute && element.getAttribute("aria-label");
    const name = element.getAttribute && element.getAttribute("name");
    const text = tag === "input" || tag === "textarea" ? "" : safeText(element.innerText || element.textContent || "");
    const parts = [tag];
    if (id) parts.push("id=" + safeText(id));
    if (className) parts.push("class=" + safeText(className));
    if (ariaLabel) parts.push("aria-label=" + safeText(ariaLabel));
    if (name) parts.push("name=" + safeText(name));
    if (text) parts.push("text=" + text);
    return parts.join(" ");
  }}
  function check(selector) {{
    if (!selector) return {{ found: false, summary: "", error: "" }};
    try {{
      const element = document.querySelector(selector);
      return {{ found: !!element, summary: summary(element), error: "" }};
    }} catch (error) {{
      return {{ found: false, summary: "", error: String(error && error.message ? error.message : error) }};
    }}
  }}
  function firstMatch(selectors) {{
    const results = selectors.map(function(selector) {{
      const item = check(selector);
      item.selector = selector;
      return item;
    }});
    return results.find(function(item) {{ return item.found; }}) || null;
  }}
  function sanitizeUrl(value) {{
    try {{
      const url = new URL(String(value || ""), window.location.href);
      return String(url.protocol || "") + "//" + String(url.host || "") + String(url.pathname || "");
    }} catch (error) {{
      return "";
    }}
  }}
  function iframeDiagnostics() {{
    try {{
      return Array.from(document.querySelectorAll("iframe, frame")).slice(0, 10).map(function(frame) {{
        try {{
          return sanitizeUrl(frame.getAttribute("src") || frame.src || "");
        }} catch (error) {{
          return "";
        }}
      }}).filter(function(src) {{ return !!src; }});
    }} catch (error) {{
      return [];
    }}
  }}
  try {{
    const login = check({login_selector});
    const password = check({password_selector});
    const submit = check({submit_selector});
    const successMatch = firstMatch({success_selectors});
    const errorMatch = firstMatch({error_selectors});
    return JSON.stringify({{
      ok: true,
      body_found: !!document.body,
      ready_state: document.readyState || "",
      title: safeText(document.title || ""),
      location_protocol: String(window.location.protocol || ""),
      location_host: String(window.location.host || ""),
      location_pathname: String(window.location.pathname || ""),
      iframe_count: document.querySelectorAll("iframe, frame").length,
      iframe_srcs: iframeDiagnostics(),
      login_found: !!login.found,
      password_found: !!password.found,
      submit_found: !!submit.found,
      success_found: !!successMatch,
      error_found: !!errorMatch,
      matched_success_selector: successMatch ? successMatch.selector : "",
      matched_error_selector: errorMatch ? errorMatch.selector : "",
      login_summary: login.summary,
      password_summary: password.summary,
      submit_summary: submit.summary,
      success_summary: successMatch ? successMatch.summary : "",
      error_summary: errorMatch ? errorMatch.summary : ""
    }});
  }} catch (error) {{
    return JSON.stringify({{
      ok: false,
      error: "load_false_diagnostics_failed",
      message: String(error && error.message ? error.message : error),
      body_found: !!document.body,
      ready_state: document.readyState || "",
      title: safeText(document.title || ""),
      location_protocol: String(window.location.protocol || ""),
      location_host: String(window.location.host || ""),
      location_pathname: String(window.location.pathname || ""),
      iframe_count: document.querySelectorAll("iframe, frame").length,
      iframe_srcs: iframeDiagnostics()
    }});
  }}
}})()
""".strip()


def load_false_diagnostics_log_parts(diagnostics):
    diagnostics = diagnostics or {}
    return {
        "body_found": bool(diagnostics.get("body_found")),
        "ready_state": str(diagnostics.get("ready_state", "")),
        "title": str(diagnostics.get("title", ""))[:120],
        "location": f"{diagnostics.get('location_protocol', '')}//{diagnostics.get('location_host', '')}{diagnostics.get('location_pathname', '')}",
        "iframe_count": int(diagnostics.get("iframe_count") or 0),
        "iframe_srcs": [str(src) for src in (diagnostics.get("iframe_srcs") or [])][:10],
        "login_found": bool(diagnostics.get("login_found")),
        "password_found": bool(diagnostics.get("password_found")),
        "submit_found": bool(diagnostics.get("submit_found")),
        "success_found": bool(diagnostics.get("success_found")),
        "error_found": bool(diagnostics.get("error_found")),
    }


def load_false_auth_form_available(diagnostics):
    diagnostics = diagnostics or {}
    return bool(diagnostics.get("login_found")) and bool(diagnostics.get("password_found")) and bool(diagnostics.get("submit_found"))


def should_continue_after_http_error_load(service, diagnostics):
    if not bool((service or {}).get("allow_http_error_load", False)):
        return False
    diagnostics = diagnostics or {}
    return load_false_auth_form_available(diagnostics) or bool(diagnostics.get("success_found")) or bool(diagnostics.get("error_found"))


def load_false_continuation_action(service, diagnostics):
    """Return the next action for loadFinished(False) diagnostics."""
    if not bool((service or {}).get("allow_http_error_load", False)):
        return "load_error"
    diagnostics = diagnostics or {}
    if load_false_auth_form_available(diagnostics):
        return "autofill"
    if bool(diagnostics.get("error_found")):
        return "error_selector"
    if bool(diagnostics.get("success_found")):
        return "result_selector"
    return "wait"




def build_click_selector_js(selector):
    selector_json = json.dumps(str(selector or ""))
    return f"""
(function () {{
  function safeText(value) {{
    return String(value || "").replace(/[\\r\\n\\t]+/g, " ").replace(/\\s+/g, " ").trim().slice(0, 120);
  }}
  function summary(element) {{
    if (!element) return "";
    const tag = String(element.tagName || "").toLowerCase();
    const id = element.getAttribute && element.getAttribute("id");
    const cls = element.getAttribute && element.getAttribute("class");
    const text = tag === "input" || tag === "textarea" ? "" : safeText(element.innerText || element.textContent || "");
    const parts = [tag];
    if (id) parts.push("id=" + safeText(id));
    if (cls) parts.push("class=" + safeText(cls));
    if (text) parts.push("text=" + text);
    return parts.join(" ");
  }}
  try {{
    const selector = {selector_json};
    const element = document.querySelector(selector);
    if (!element) {{
      return JSON.stringify({{ ok: false, found: false, clicked: false, selector: selector, error: "not_found", summary: "" }});
    }}
    element.dispatchEvent(new MouseEvent("mousedown", {{ bubbles: true, cancelable: true, view: window }}));
    element.dispatchEvent(new MouseEvent("mouseup", {{ bubbles: true, cancelable: true, view: window }}));
    element.dispatchEvent(new MouseEvent("click", {{ bubbles: true, cancelable: true, view: window }}));
    return JSON.stringify({{ ok: true, found: true, clicked: true, selector: selector, error: "", summary: summary(element) }});
  }} catch (error) {{
    return JSON.stringify({{ ok: false, found: false, clicked: false, selector: {selector_json}, error: "invalid_selector", message: String(error && error.message ? error.message : error), summary: "" }});
  }}
}})()
""".strip()


def build_wait_selector_js(selectors):
    selectors_json = json.dumps(parse_selector_markers(selectors), ensure_ascii=False)
    return f"""
(function () {{
  function safeText(value) {{
    return String(value || "").replace(/[\\r\\n\\t]+/g, " ").replace(/\\s+/g, " ").trim().slice(0, 120);
  }}
  function summary(element) {{
    if (!element) return "";
    const tag = String(element.tagName || "").toLowerCase();
    const id = element.getAttribute && element.getAttribute("id");
    const cls = element.getAttribute && element.getAttribute("class");
    const text = tag === "input" || tag === "textarea" ? "" : safeText(element.innerText || element.textContent || "");
    const parts = [tag];
    if (id) parts.push("id=" + safeText(id));
    if (cls) parts.push("class=" + safeText(cls));
    if (text) parts.push("text=" + text);
    return parts.join(" ");
  }}
  const selectors = {selectors_json};
  const results = selectors.map(function(selector) {{
    try {{
      const element = document.querySelector(selector);
      return {{ selector: selector, found: !!element, summary: summary(element), error: "" }};
    }} catch (error) {{
      return {{ selector: selector, found: false, summary: "", error: "invalid_selector", message: String(error && error.message ? error.message : error) }};
    }}
  }});
  const match = results.find(function(item) {{ return item.found; }}) || null;
  return JSON.stringify({{ ok: true, found: !!match, matched_selector: match ? match.selector : "", matched_summary: match ? match.summary : "", invalid_selectors: results.filter(function(item) {{ return !!item.error; }}), results: results }});
}})()
""".strip()

def build_result_selector_check_js(service):
    """Build a script that checks success/error CSS selectors and returns JSON."""
    success_selectors = json.dumps(parse_selector_markers(service.get("success_selectors", [])), ensure_ascii=False)
    error_selectors = json.dumps(parse_selector_markers(service.get("error_selectors", [])), ensure_ascii=False)
    return f"""
(function () {{
  function safeText(value) {{
    return String(value || "").replace(/[\\r\\n\\t]+/g, " ").replace(/\\s+/g, " ").trim().slice(0, 120);
  }}
  function elementSummary(element) {{
    if (!element) return "";
    const tag = String(element.tagName || "").toLowerCase();
    const type = element.getAttribute && element.getAttribute("type");
    const id = element.getAttribute && element.getAttribute("id");
    const className = element.getAttribute && element.getAttribute("class");
    const ariaLabel = element.getAttribute && element.getAttribute("aria-label");
    const name = element.getAttribute && element.getAttribute("name");
    const text = tag === "input" || tag === "textarea" ? "" : safeText(element.innerText || element.textContent || "");
    const parts = [tag];
    if (type) parts.push("type=" + safeText(type));
    if (id) parts.push("id=" + safeText(id));
    if (className) parts.push("class=" + safeText(className));
    if (ariaLabel) parts.push("aria-label=" + safeText(ariaLabel));
    if (name) parts.push("name=" + safeText(name));
    if (text) parts.push("text=" + text);
    return parts.join(" ");
  }}
  function checkSelector(kind, selector) {{
    try {{
      const element = document.querySelector(selector);
      return {{
        kind: kind,
        selector: selector,
        found: !!element,
        summary: elementSummary(element),
        error: ""
      }};
    }} catch (error) {{
      return {{
        kind: kind,
        selector: selector,
        found: false,
        summary: "",
        error: String(error && error.message ? error.message : error)
      }};
    }}
  }}
  const successSelectors = {success_selectors};
  const errorSelectors = {error_selectors};
  const success = successSelectors.map(function (selector) {{ return checkSelector("success", selector); }});
  const errors = errorSelectors.map(function (selector) {{ return checkSelector("error", selector); }});
  const successMatch = success.find(function (item) {{ return item.found; }}) || null;
  const errorMatch = errors.find(function (item) {{ return item.found; }}) || null;
  const invalidSuccess = success.filter(function (item) {{ return !!item.error; }});
  const invalidErrors = errors.filter(function (item) {{ return !!item.error; }});
  return JSON.stringify({{
    ok: true,
    success_found: !!successMatch,
    error_found: !!errorMatch,
    matched_success_selector: successMatch ? successMatch.selector : "",
    matched_error_selector: errorMatch ? errorMatch.selector : "",
    matched_success_summary: successMatch ? successMatch.summary : "",
    matched_error_summary: errorMatch ? errorMatch.summary : "",
    invalid_success_selectors: invalidSuccess,
    invalid_error_selectors: invalidErrors,
    success_results: success,
    error_results: errors
  }});
}})()
""".strip()


def parse_autofill_callback_result(result):
    if isinstance(result, dict):
        return result, None
    if isinstance(result, str):
        if not result.strip():
            return None, {"error": "empty_string_result", "message": "JS автозаполнения вернул пустую строку вместо JSON."}
        try:
            parsed = json.loads(result)
        except Exception as exc:
            return None, {"error": "invalid_json", "message": "JS автозаполнения вернул невалидный JSON.", "details": str(exc)}
        if not isinstance(parsed, dict):
            return None, {"error": "invalid_json_type", "message": "JS автозаполнения вернул JSON неверного типа.", "json_type": type(parsed).__name__}
        return parsed, None
    return None, {"error": "invalid_result", "message": "Ошибка автозаполнения формы: JS автозаполнения не вернул корректный результат."}

def _autofill_diagnostics_lines(result):
    if not isinstance(result, dict):
        return []
    diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else result
    input_text_count = diagnostics.get("input_text_count", diagnostics.get("text_input_count", 0))
    input_password_count = diagnostics.get("input_password_count", diagnostics.get("password_input_count", 0))
    lines = [
        f"readyState={diagnostics.get('ready_state', '')}",
        f"location={diagnostics.get('location_href', '')}",
        f"iframe_count={diagnostics.get('iframe_count', 0)}",
        f"input_text_count={input_text_count}",
        f"input_password_count={input_password_count}",
        f"button_count={diagnostics.get('button_count', 0)}",
        f"login_found={bool(diagnostics.get('login_found', False))}",
        f"password_found={bool(diagnostics.get('password_found', False))}",
        f"submit_found={bool(diagnostics.get('submit_found', False))}",
    ]
    found_inputs = [str(item) for item in (diagnostics.get("found_inputs") or []) if str(item).strip()]
    found_buttons = [str(item) for item in (diagnostics.get("found_buttons") or []) if str(item).strip()]
    if found_inputs:
        lines.append("found_inputs=" + "; ".join(found_inputs))
    if found_buttons:
        lines.append("found_buttons=" + "; ".join(found_buttons))
    if int(diagnostics.get("iframe_count") or 0) > 0 and not all([
        diagnostics.get("login_found"),
        diagnostics.get("password_found"),
        diagnostics.get("submit_found"),
    ]):
        lines.append("Возможно, форма авторизации находится внутри iframe. Текущая проверка ищет элементы в основном document.")
    return lines


def build_autofill_error_message(service, result):
    if result is None:
        return "JS автозаполнения не вернул результат. Возможно, QtWebEngine получил undefined из runJavaScript."
    if isinstance(result, str) and not result.strip():
        return "JS автозаполнения вернул пустую строку вместо JSON."
    if not isinstance(result, dict):
        return "Ошибка автозаполнения формы: JS автозаполнения не вернул корректный результат."
    if result.get("error") == "empty_string_result":
        return "JS автозаполнения вернул пустую строку вместо JSON."
    if result.get("error") == "invalid_json":
        return "JS автозаполнения вернул невалидный JSON."
    if result.get("error") == "invalid_json_type":
        return "JS автозаполнения вернул JSON неверного типа."
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



def safe_autofill_script_preview(script, credentials=None, size=180):
    text = str(script or "")
    for value in (credentials or {}).values():
        value = str(value or "")
        if not value:
            continue
        text = text.replace(json.dumps(value), '"<redacted>"')
        if len(value) >= 4:
            text = text.replace(value, "<redacted>")
    redacted = re.sub(r'(const\s+(?:login_value|password_value)\s*=\s*)"(?:\\.|[^"\\])*"', r'\1"<redacted>"', text)
    compact = " ".join(redacted.split())
    return compact[:size], compact[-size:] if len(compact) > size else compact

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

def evaluate_service_check_page(service, page_text, loaded=True, timed_out=False, error="", selector_result=None):
    if timed_out:
        return "timeout", "", "", error or "Истёк таймаут проверки"
    if not loaded:
        return "load_error", "", "", error or "Страница не загрузилась"

    selector_result = selector_result if isinstance(selector_result, dict) else {}
    invalid_error = (selector_result.get("invalid_error_selectors") or [])
    if invalid_error:
        selector = str(invalid_error[0].get("selector", ""))
        return "error", "", selector, f"Некорректный CSS selector признака ошибки: {selector}"
    invalid_success = (selector_result.get("invalid_success_selectors") or [])
    if invalid_success:
        selector = str(invalid_success[0].get("selector", ""))
        return "error", selector, "", f"Некорректный CSS selector признака успеха: {selector}"

    if selector_result.get("error_found"):
        selector = str(selector_result.get("matched_error_selector") or "")
        summary = str(selector_result.get("matched_error_summary") or "")
        detail = f"Ошибочный признак найден по CSS selector: {selector}"
        if summary:
            detail += f" ({summary})"
        return "error", "", selector, detail

    text = str(page_text or "")
    lowered = text.casefold()
    for marker in parse_text_markers(service.get("error_texts", [])):
        if marker.casefold() in lowered:
            return "auth_error", "", marker, f"найден текст “{marker}”"

    if selector_result.get("success_found"):
        selector = str(selector_result.get("matched_success_selector") or "")
        summary = str(selector_result.get("matched_success_summary") or "")
        detail = f"Успешный признак найден по CSS selector: {selector}"
        if summary:
            detail += f" ({summary})"
        return "ok", selector, "", detail

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
