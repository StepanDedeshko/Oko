"""Helpers for duty task UX and ticket binding state."""

from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from urllib.parse import parse_qs, urlparse
import re
import uuid

TASK_ZABBIX = "zabbix"
TASK_SERVICES = "service_checks"
TASK_TYPES = (TASK_ZABBIX, TASK_SERVICES)

TASK_LABELS = {
    TASK_ZABBIX: "Проверка Zabbix / графиков",
    TASK_SERVICES: "Проверка сервисов",
}
TASK_SHORT_LABELS = {
    TASK_ZABBIX: "ZABBIX / ГРАФИКИ",
    TASK_SERVICES: "СЕРВИСЫ",
}


DUTY_SESSION_FIELDS = (
    "duty_session_id",
    "duty_started_at",
    "duty_finished_at",
    "duty_zabbix_task_session_id",
    "duty_service_checks_task_session_id",
)

DUTY_ACTIVE_BINDING_FIELDS = (
    "current_ticket_number",
    "current_ticket_id",
    "current_ticket_url",
    "duty_zabbix_task_number",
    "duty_zabbix_task_id",
    "duty_zabbix_task_url",
    "duty_zabbix_task_system",
    "duty_zabbix_task_status",
    "duty_zabbix_task_linked_at",
    "duty_zabbix_task_session_id",
    "duty_service_checks_task_number",
    "duty_service_checks_task_id",
    "duty_service_checks_task_url",
    "duty_service_checks_task_system",
    "duty_service_checks_task_status",
    "duty_service_checks_task_linked_at",
    "duty_service_checks_task_session_id",
    "last_zabbix_check_note",
    "last_zabbix_check_time",
    "last_service_check_note",
    "last_service_check_time",
)

DUTY_NOTE_DISABLED_MESSAGE = "Дежурство не включено. Начните новое дежурство и привяжите задачу."
DUTY_NOTE_UNBOUND_MESSAGE = "Задача текущего дежурства не привязана. Начните новое дежурство и привяжите задачу."


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def start_duty_session(settings: dict) -> str:
    if settings is None:
        settings = {}
    session_id = uuid.uuid4().hex
    for field in DUTY_ACTIVE_BINDING_FIELDS:
        settings[field] = ""
    settings["enabled"] = True
    settings["duty_session_id"] = session_id
    settings["duty_started_at"] = _utc_now_iso()
    settings["duty_finished_at"] = ""
    return session_id


def finish_duty_session(settings: dict) -> None:
    if settings is None:
        settings = {}
    settings["enabled"] = False
    settings["duty_finished_at"] = _utc_now_iso()


def extract_ticket_id_from_url(url: str) -> str:
    match = re.search(r"[?;]TicketID=([^;&?#]+)", str(url or ""))
    if match:
        return match.group(1).strip()
    return ""


def duty_note_guard(settings: dict, task_type: str) -> tuple[bool, str]:
    settings = settings or {}
    if not bool(settings.get("enabled", False)):
        return False, DUTY_NOTE_DISABLED_MESSAGE
    session_id = str(settings.get("duty_session_id", "") or "").strip()
    if not session_id:
        return False, DUTY_NOTE_UNBOUND_MESSAGE
    if task_type == TASK_SERVICES:
        task_session_id = str(settings.get("duty_service_checks_task_session_id", "") or "").strip()
        task_id = str(settings.get("duty_service_checks_task_id", "") or "").strip()
        task_url = str(settings.get("duty_service_checks_task_url", "") or "").strip()
    else:
        task_session_id = str(settings.get("duty_zabbix_task_session_id", "") or "").strip()
        task_id = str(settings.get("duty_zabbix_task_id", "") or settings.get("current_ticket_id", "") or "").strip()
        task_url = str(settings.get("duty_zabbix_task_url", "") or settings.get("current_ticket_url", "") or "").strip()
    has_task = bool(task_id or extract_ticket_id_from_url(task_url))
    if task_session_id != session_id or not has_task:
        return False, DUTY_NOTE_UNBOUND_MESSAGE
    return True, ""


def parse_ticket_number_from_html(html_text: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", str(html_text or "")))
    h1_matches = re.findall(r"<h1[^>]*>(.*?)</h1>", str(html_text or ""), flags=re.IGNORECASE | re.DOTALL)
    for source in h1_matches + [text]:
        plain = unescape(re.sub(r"<[^>]+>", " ", source))
        match = re.search(r"(?:Заявка|Задача)\s*#\s*(\d{5,})", plain, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    title_match = re.search(r"<title[^>]*>\s*(\d{5,})\s*-\s*Подробно\s*-\s*Заявки\s*-\s*Service Desk", str(html_text or ""), flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        return title_match.group(1)
    return ""


def selected_task_types(settings: dict) -> list[str]:
    settings = settings or {}
    result = []
    if bool(settings.get("check_zabbix_enabled", True)):
        result.append(TASK_ZABBIX)
    if bool(settings.get("check_services_enabled", settings.get("duty_service_checks_enabled", False))):
        result.append(TASK_SERVICES)
    return result


def duty_tasks_button_enabled(settings: dict) -> bool:
    return bool(selected_task_types(settings))


def smart_action_text(values: dict, task_types: list[str] | tuple[str, ...]) -> str:
    visible = list(task_types or [])
    filled = [bool(str((values or {}).get(task_type, "") or "").strip()) for task_type in visible]
    if not visible:
        return "Нет выбранных проверок"
    if all(not item for item in filled):
        return "Создать оба тикета" if len(visible) > 1 else "Создать тикет"
    if all(filled):
        return "Привязать оба тикета" if len(visible) > 1 else "Привязать тикет"
    return "Применить"


def planned_actions(values: dict, task_types: list[str] | tuple[str, ...]) -> dict[str, str]:
    return {
        task_type: ("link" if str((values or {}).get(task_type, "") or "").strip() else "create")
        for task_type in (task_types or [])
    }


def parse_ticket_url(value: str) -> dict:
    raw = str(value or "").strip()
    if not raw:
        return {"system": "", "id": "", "url": "", "number": ""}

    parsed = urlparse(raw)
    host_path = f"{parsed.netloc} {parsed.path}".casefold()
    query = parsed.query or ""
    if parsed.params:
        query = f"{query}&{parsed.params}" if query else parsed.params
    params = parse_qs(query.replace(";", "&"), keep_blank_values=True)

    def first(*names):
        lowered = {key.casefold(): values for key, values in params.items()}
        for name in names:
            values = lowered.get(name.casefold())
            if values:
                return str(values[0]).strip()
        return ""

    ticket_id = first("TicketID", "ticket_id")
    if ticket_id:
        return {"system": "otrs", "id": ticket_id, "url": raw, "number": ""}

    redmine_match = re.search(r"/(?:issues|tickets)/(\d+)(?:\D|$)", parsed.path or "", re.IGNORECASE)
    if redmine_match:
        issue_id = redmine_match.group(1)
        return {"system": "redmine", "id": issue_id, "url": raw, "number": issue_id}

    issue_id = first("issue_id", "id") if "redmine" in host_path else ""
    if issue_id and issue_id.isdigit():
        return {"system": "redmine", "id": issue_id, "url": raw, "number": issue_id}

    if raw.isdigit():
        return {"system": "", "id": raw, "url": raw, "number": raw}

    return {"system": "", "id": "", "url": raw, "number": ""}


def current_task_binding(settings: dict, task_type: str) -> dict:
    settings = settings or {}
    if task_type == TASK_SERVICES:
        return {
            "url": str(settings.get("duty_service_checks_task_url", "") or "").strip(),
            "id": str(settings.get("duty_service_checks_task_id", "") or "").strip(),
            "number": str(settings.get("duty_service_checks_task_number", "") or "").strip(),
            "system": str(settings.get("duty_service_checks_task_system", "") or "").strip(),
        }
    return {
        "url": str(settings.get("duty_zabbix_task_url") or settings.get("current_ticket_url") or "").strip(),
        "id": str(settings.get("duty_zabbix_task_id") or settings.get("current_ticket_id") or "").strip(),
        "number": str(settings.get("duty_zabbix_task_number") or settings.get("current_ticket_number") or "").strip(),
        "system": str(settings.get("duty_zabbix_task_system", "") or "").strip(),
    }


def has_current_task(settings: dict, task_type: str) -> bool:
    binding = current_task_binding(settings, task_type)
    return bool(binding.get("url") or binding.get("id") or binding.get("number"))


def save_task_binding(settings: dict, task_type: str, parsed: dict, status: str = "linked") -> dict:
    parsed = parsed or {}
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    system = str(parsed.get("system", "") or "").strip()
    ticket_id = str(parsed.get("id", "") or "").strip()
    number = str(parsed.get("number", "") or "").strip()
    url = str(parsed.get("url", "") or "").strip()
    prefix = "duty_service_checks_task" if task_type == TASK_SERVICES else "duty_zabbix_task"
    if system:
        settings[f"{prefix}_system"] = system
    if ticket_id:
        settings[f"{prefix}_id"] = ticket_id
    if number:
        settings[f"{prefix}_number"] = number
    if url:
        settings[f"{prefix}_url"] = url
    settings[f"{prefix}_status"] = status
    settings[f"{prefix}_linked_at"] = now
    settings[f"{prefix}_session_id"] = str(settings.get("duty_session_id", "") or "").strip()
    settings.pop(f"{prefix}_error", None)
    if task_type == TASK_ZABBIX:
        if ticket_id:
            settings["current_ticket_id"] = ticket_id
        if number:
            settings["current_ticket_number"] = number
        if url:
            settings["current_ticket_url"] = url
    return settings
