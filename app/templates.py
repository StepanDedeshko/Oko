"""User-editable text templates for OTRS notes and future Redmine tasks."""

from copy import deepcopy
from datetime import datetime
import re


OTRS_GRAPH_CHECK_TEMPLATE_KEY = "otrs_graph_check"
REDMINE_TASK_TEMPLATE_KEY = "redmine_task"

DEFAULT_OTRS_GRAPH_CHECK_TEMPLATE_NAME = "Заметка ОТРС: проверка графиков"
DEFAULT_OTRS_GRAPH_CHECK_TEMPLATE_TEXT = """Проверка выполнена.

Период проверки:
{from_time} — {to_time}

Статистика проверки:
OK: {ok_count}
ALERT: {alert_count}
Ошибки: {error_count}

Обнаружены проблемы:
{active_problems}

Активные триггеры:
{active_triggers}

Связанные графики:
{related_graphs}

Комментарий дежурного:
[заполнить при необходимости]
"""

DEFAULT_REDMINE_TASK_TEMPLATE = {
    "name": "Задача Redmine",
    "create_url": "",
    "subject_template": "Проверка графиков: {checked_at}",
    "description_template": """Скриншоты графиков за последние 3 часа:

{graph_images_collapsed}

Обнаружены проблемы:
{active_problems}
""",
    "tracker_id": "",
    "priority_id": "",
    "project": "",
}

OTRS_VARIABLES = [
    "{checked_at}",
    "{from_time}",
    "{to_time}",
    "{duration_minutes}",
    "{ok_count}",
    "{alert_count}",
    "{error_count}",
    "{active_triggers}",
    "{active_trigger_names}",
    "{active_problems}",
    "{related_graphs}",
    "{related_graph_links}",
    "{trigger_name}",
    "{trigger_status}",
    "{trigger_source_product}",
    "{trigger_source_section}",
]

REDMINE_GRAPH_VARIABLES = [
    "{graph_1_title}",
    "{graph_1_url}",
    "{graph_1_image}",
    "{graph_1_redmine_image}",
    "{graph_1_collapsed}",
    "{graph_2_title}",
    "{graph_2_url}",
    "{graph_2_image}",
    "{graph_2_redmine_image}",
    "{graph_2_collapsed}",
    "{graph_images}",
    "{graph_images_collapsed}",
    "{screenshots_folder}",
]

OTRS_TEMPLATE_EXAMPLE = """Проверка выполнена.

Обнаружены проблемы:
{active_problems}

Активные триггеры:
{active_triggers}

Связанные графики:
{related_graphs}
"""

REDMINE_COLLAPSE_EXAMPLE = """{{collapse(скрыть/показать)
!{graph_1_image}!
}}
"""

REDMINE_ALL_GRAPHS_EXAMPLE = """Скриншоты графиков за последние 3 часа:

{graph_images_collapsed}
"""

_TEMPLATE_TOKEN_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def default_otrs_graph_check_template():
    return {
        "name": DEFAULT_OTRS_GRAPH_CHECK_TEMPLATE_NAME,
        "text": DEFAULT_OTRS_GRAPH_CHECK_TEMPLATE_TEXT,
    }


def default_redmine_task_template():
    return deepcopy(DEFAULT_REDMINE_TASK_TEMPLATE)


def ensure_templates_defaults(config):
    """Ensure safe, credential-free template settings exist in the app config."""
    templates = config.setdefault("templates", {})

    otrs = templates.setdefault(OTRS_GRAPH_CHECK_TEMPLATE_KEY, {})
    otrs_defaults = default_otrs_graph_check_template()
    otrs.setdefault("name", otrs_defaults["name"])
    otrs.setdefault("text", otrs_defaults["text"])

    redmine = templates.setdefault(REDMINE_TASK_TEMPLATE_KEY, {})
    for key, value in default_redmine_task_template().items():
        redmine.setdefault(key, value)

    return templates


def get_otrs_graph_check_template(config):
    templates = ensure_templates_defaults(config)
    template = templates.get(OTRS_GRAPH_CHECK_TEMPLATE_KEY) or {}
    text = str(template.get("text") or "").strip()
    if not text:
        text = DEFAULT_OTRS_GRAPH_CHECK_TEMPLATE_TEXT
    return {
        "name": str(template.get("name") or DEFAULT_OTRS_GRAPH_CHECK_TEMPLATE_NAME),
        "text": text,
    }


def reset_otrs_graph_check_template(config):
    templates = config.setdefault("templates", {})
    templates[OTRS_GRAPH_CHECK_TEMPLATE_KEY] = default_otrs_graph_check_template()
    return templates[OTRS_GRAPH_CHECK_TEMPLATE_KEY]


def reset_redmine_task_template(config):
    templates = config.setdefault("templates", {})
    templates[REDMINE_TASK_TEMPLATE_KEY] = default_redmine_task_template()
    return templates[REDMINE_TASK_TEMPLATE_KEY]


def render_template(template_text, context):
    """Render a template without raising on unknown placeholders."""
    safe_context = {str(key): "" if value is None else str(value) for key, value in (context or {}).items()}

    def replace(match):
        return safe_context.get(match.group(1), "")

    return _TEMPLATE_TOKEN_RE.sub(replace, str(template_text or ""))


def format_numbered_lines(items, empty_text="Не обнаружены"):
    values = [str(item).strip() for item in (items or []) if str(item or "").strip()]
    if not values:
        return empty_text
    return "\n".join(f"{index}. {value}" for index, value in enumerate(values, start=1))


def format_dt(value):
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M:%S")
    return str(value or "")
