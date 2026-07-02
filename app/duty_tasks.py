"""Helpers for duty task UX and ticket binding state."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import parse_qs, urlparse
import re

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


DUTY_TASK_BINDING_FIELDS = [
    "current_ticket_number", "current_ticket_id", "current_ticket_url",
    "duty_zabbix_task_number", "duty_zabbix_task_id", "duty_zabbix_task_url",
    "duty_zabbix_task_system", "duty_zabbix_task_status", "duty_zabbix_task_linked_at",
    "duty_zabbix_task_session_id",
    "duty_service_checks_task_number", "duty_service_checks_task_id", "duty_service_checks_task_url",
    "duty_service_checks_task_system", "duty_service_checks_task_status", "duty_service_checks_task_linked_at",
    "duty_service_checks_task_session_id",
    "last_zabbix_check_note", "last_zabbix_check_time",
    "last_service_check_note", "last_service_check_time",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clear_duty_task_bindings(settings: dict) -> dict:
    settings = {} if settings is None else settings
    for key in DUTY_TASK_BINDING_FIELDS:
        settings[key] = ""
    return settings


def start_new_duty_session(settings: dict) -> dict:
    settings = {} if settings is None else settings
    clear_duty_task_bindings(settings)
    settings["enabled"] = True
    settings["duty_session_id"] = uuid4().hex
    settings["duty_started_at"] = utc_now_iso()
    settings["duty_finished_at"] = ""
    return settings


def finish_duty_session(settings: dict) -> dict:
    settings = {} if settings is None else settings
    settings["enabled"] = False
    settings["duty_finished_at"] = utc_now_iso()
    return settings


def _prefix(task_type: str) -> str:
    return "duty_service_checks_task" if task_type == TASK_SERVICES else "duty_zabbix_task"


def _task_binding_from_settings(settings: dict, task_type: str) -> dict:
    settings = {} if settings is None else settings
    prefix = _prefix(task_type)
    return {
        "url": str(settings.get(f"{prefix}_url", "") or "").strip(),
        "id": str(settings.get(f"{prefix}_id", "") or "").strip(),
        "number": str(settings.get(f"{prefix}_number", "") or "").strip(),
        "system": str(settings.get(f"{prefix}_system", "") or "").strip(),
        "session_id": str(settings.get(f"{prefix}_session_id", "") or "").strip(),
        "status": str(settings.get(f"{prefix}_status", "") or "").strip(),
    }


def is_valid_duty_task_binding(settings: dict, task_type: str) -> bool:
    settings = {} if settings is None else settings
    session_id = str(settings.get("duty_session_id", "") or "").strip()
    binding = _task_binding_from_settings(settings, task_type)
    return bool(
        settings.get("enabled") is True
        and session_id
        and binding["session_id"] == session_id
        and (binding["id"] or binding["url"])
        and binding["status"] == "linked"
    )


def get_active_duty_task(settings: dict, task_type: str) -> dict | None:
    if not is_valid_duty_task_binding(settings, task_type):
        return None
    binding = _task_binding_from_settings(settings, task_type)
    binding["active"] = True
    return binding


def can_send_duty_note(settings: dict, task_type: str) -> tuple[bool, str]:
    settings = {} if settings is None else settings
    if not settings.get("enabled"):
        return False, "Дежурство не включено. Начните новое дежурство и привяжите задачу."
    if get_active_duty_task(settings, task_type) is None:
        return False, "Задача текущего дежурства не привязана. Сначала создайте или выберите задачу для текущего дежурства."
    return True, ""


def bind_duty_task(settings: dict, task_type: str, parsed: dict, status: str = "linked") -> dict:
    settings = {} if settings is None else settings
    parsed = parsed or {}
    prefix = _prefix(task_type)
    number = str(parsed.get("number", "") or "").strip() or str(settings.get(f"{prefix}_number", "") or "").strip()
    ticket_id = str(parsed.get("id", "") or "").strip() or str(settings.get(f"{prefix}_id", "") or "").strip()
    url = str(parsed.get("url", "") or "").strip() or str(settings.get(f"{prefix}_url", "") or "").strip()
    system = str(parsed.get("system", "") or "").strip() or str(settings.get(f"{prefix}_system", "") or "").strip()
    session_id = str(settings.get("duty_session_id", "") or "").strip()
    valid = bool(settings.get("enabled") is True and session_id and (ticket_id or url))

    settings[f"{prefix}_number"] = number
    settings[f"{prefix}_id"] = ticket_id
    settings[f"{prefix}_url"] = url
    settings[f"{prefix}_system"] = system
    settings.pop(f"{prefix}_error", None)

    if valid:
        settings[f"{prefix}_status"] = "linked" if status == "linked" else status
        settings[f"{prefix}_linked_at"] = utc_now_iso()
        settings[f"{prefix}_session_id"] = session_id
        return {"valid": True, "status": settings[f"{prefix}_status"], "reason": ""}

    settings[f"{prefix}_status"] = "incomplete"
    settings[f"{prefix}_linked_at"] = ""
    settings[f"{prefix}_session_id"] = ""
    reason = "Не удалось получить TicketID или URL задачи." if not (ticket_id or url) else "Дежурство не включено. Начните новое дежурство и привяжите задачу."
    return {"valid": False, "status": "incomplete", "reason": reason}


def selected_task_types(settings: dict) -> list[str]:
    settings = {} if settings is None else settings
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



def parse_otrs_task_number(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    patterns = (
        r"(?:Заявка|Задача)\s*[#№]\s*(\d{6,})",
        r"Ticket\s*#\s*(\d{6,})",
        r"^\s*(\d{6,})\s*[-–—]",
    )
    for pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return ""


def parse_otrs_ticket_id(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    patterns = (
        r"[?;]TicketID=([0-9]+)",
        r"\bTicketID=([0-9]+)",
        r'"TicketID"\s*:\s*"([0-9]+)"',
        r"'TicketID'\s*:\s*'([0-9]+)'",
    )
    for pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""

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

    ticket_id = first("TicketID", "ticket_id") or parse_otrs_ticket_id(raw)
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
    settings = {} if settings is None else settings
    if task_type == TASK_SERVICES:
        return {
            "url": str(settings.get("duty_service_checks_task_url", "") or "").strip(),
            "id": str(settings.get("duty_service_checks_task_id", "") or "").strip(),
            "number": str(settings.get("duty_service_checks_task_number", "") or "").strip(),
            "system": str(settings.get("duty_service_checks_task_system", "") or "").strip(),
        }
    return {
        "url": str(settings.get("duty_zabbix_task_url", "") or "").strip(),
        "id": str(settings.get("duty_zabbix_task_id", "") or "").strip(),
        "number": str(settings.get("duty_zabbix_task_number", "") or "").strip(),
        "system": str(settings.get("duty_zabbix_task_system", "") or "").strip(),
    }


def has_current_task(settings: dict, task_type: str) -> bool:
    binding = current_task_binding(settings, task_type)
    return bool(binding.get("url") or binding.get("id") or binding.get("number"))


def save_task_binding(settings: dict, task_type: str, parsed: dict, status: str = "linked") -> dict:
    return bind_duty_task(settings, task_type, parsed, status=status)
