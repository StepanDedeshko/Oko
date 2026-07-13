from __future__ import annotations

from typing import Iterable

from app.critical_triggers import CRITICAL_TRIGGER_KIND, is_critical_trigger_name


CRITICAL_SELECTION_MESSAGE = "Критический триггер необходимо обработать отдельно. Выберите одну критическую строку."

REDMINE_ACTION = "redmine"
MM_OTRS_ACTION = "mm_otrs"
OBSERVED_ACTION = "observed"
NO_ACTION_REQUIRED_ACTION = "no_action_required"
COPY_TASK_COMMENT_ACTION = "copy_task_comment"

CRITICAL_FORBIDDEN_ACTIONS = {
    MM_OTRS_ACTION,
    OBSERVED_ACTION,
    NO_ACTION_REQUIRED_ACTION,
    COPY_TASK_COMMENT_ACTION,
}


def _get_value(item, name: str, default=""):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def is_critical_problem_item(item) -> bool:
    """Return True for Live Zabbix rows that must use the critical Redmine flow."""
    kind = str(_get_value(item, "trigger_kind", "") or "").casefold()
    if kind == CRITICAL_TRIGGER_KIND:
        return True
    return is_critical_trigger_name(str(_get_value(item, "trigger_name", "") or ""))


def split_critical_selection(items: Iterable) -> tuple[list, list]:
    critical = []
    normal = []
    for item in items or []:
        if is_critical_problem_item(item):
            critical.append(item)
        else:
            normal.append(item)
    return critical, normal


def critical_selection_error(items: Iterable) -> str:
    """Validate critical selection rules. Empty string means the selection is OK."""
    items = list(items or [])
    critical, normal = split_critical_selection(items)
    if not critical:
        return ""
    if len(items) != 1 or normal:
        return CRITICAL_SELECTION_MESSAGE
    return ""


def can_use_processing_action(action: str, items: Iterable) -> tuple[bool, str]:
    """Shared guard for state-changing Live Zabbix actions."""
    items = list(items or [])
    error = critical_selection_error(items)
    if error:
        return False, error
    if any(is_critical_problem_item(item) for item in items) and action in CRITICAL_FORBIDDEN_ACTIONS:
        return False, "Критический триггер можно обработать только через создание задачи Redmine."
    return True, ""


def should_offer_same_host_expansion(items: Iterable) -> bool:
    items = list(items or [])
    return len(items) == 1 and not any(is_critical_problem_item(item) for item in items)


def critical_auto_ack_required(items: Iterable) -> bool:
    return any(is_critical_problem_item(item) for item in items or [])


def redmine_auto_ack_enabled_for_items(items: Iterable, settings: dict | None) -> bool:
    if critical_auto_ack_required(items):
        return True
    settings = settings or {}
    return bool(settings.get("auto_ack_after_task_enabled", False) and settings.get("auto_ack_after_redmine_enabled", False))
