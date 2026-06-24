"""User-editable text templates for OTRS notes and future Redmine tasks."""

from copy import deepcopy
from datetime import datetime
import re


OTRS_GRAPH_CHECK_TEMPLATE_KEY = "otrs_graph_check"
REDMINE_TASK_TEMPLATE_KEY = "redmine_task"
REDMINE_SPECIAL_TASK_TEMPLATE_KEY = "redmine_special_task"
OTRS_SERVICE_CHECK_TEMPLATE_KEY = "otrs_service_check"

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

DEFAULT_OTRS_SERVICE_CHECK_TEMPLATE_NAME = "ОТРС: Проверка сервисов"
DEFAULT_OTRS_SERVICE_CHECK_TEMPLATE_TEXT = """Проверка сервисов выполнена.

Время проверки:
{checked_at}

Результат:
Всего сервисов: {services_total_count}
OK: {services_ok_count}
Ошибки: {services_error_count}
Таймауты: {services_timeout_count}
Неизвестно: {services_unknown_count}

Сервисы:
{services_results}

Ошибки:
{services_errors}

Комментарий дежурного:
[заполнить при необходимости]
"""

DEFAULT_REDMINE_SPECIAL_TASK_TEMPLATE = {
    "name": "Задача Redmine: специальные триггеры с графиками",
    "create_url": "",
    "subject_template": "Проверка графиков: {trigger_name} — {checked_at}",
    "description_template": """Сработал специальный триггер: {trigger_name}
Статус: {trigger_status}

Ссылки на графики для ручной проверки:
{special_graph_links}

Обнаружены проблемы:
{active_problems}
""",
    "tracker_id": "",
    "priority_id": "",
    "project": "",
}

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

OTRS_VARIABLE_DETAILS = [
    {
        "group": "Общие",
        "name": "{checked_at}",
        "description": "дата и время выполнения проверки",
        "example": "03.06.2026 12:30:15",
    },
    {
        "group": "Проверка",
        "name": "{from_time}",
        "description": "начало периода проверки",
        "example": "03.06.2026 09:30:15",
    },
    {
        "group": "Проверка",
        "name": "{to_time}",
        "description": "конец периода проверки",
        "example": "03.06.2026 12:30:15",
    },
    {
        "group": "Проверка",
        "name": "{duration_minutes}",
        "description": "длительность проверяемого периода в минутах",
        "example": "180",
    },
    {
        "group": "Проверка",
        "name": "{ok_count}",
        "description": "количество триггеров со статусом OK",
        "example": "4",
    },
    {
        "group": "Проверка",
        "name": "{alert_count}",
        "description": "количество активных/проблемных триггеров",
        "example": "2",
    },
    {
        "group": "Проверка",
        "name": "{error_count}",
        "description": "количество ошибок при проверке",
        "example": "0",
    },
    {
        "group": "Триггеры",
        "name": "{active_triggers}",
        "description": "подробный список активных триггеров",
        "example": "1. Проверка поступления сработок — ALERT\n2. Высокая нагрузка CPU — ALERT",
    },
    {
        "group": "Триггеры",
        "name": "{active_trigger_names}",
        "description": "только названия активных триггеров",
        "example": "Проверка поступления сработок, Высокая нагрузка CPU",
    },
    {
        "group": "Триггеры",
        "name": "{active_problems}",
        "description": "готовый текстовый блок “Обнаружены проблемы”",
        "example": "1. По графику “Сфера 1: Сработки” наблюдается отклонение.\n2. Активен триггер: Проверка поступления сработок.",
    },
    {
        "group": "Графики",
        "name": "{related_graphs}",
        "description": "список связанных графиков",
        "example": "1. Сфера 1 / Zabbix: Общее количество сработок\n2. Сфера 2 / Zabbix: Общее количество сработок",
    },
    {
        "group": "Графики",
        "name": "{related_graph_links}",
        "description": "список ссылок на связанные графики",
        "example": "1. https://zabbix.example/chart.php?graphid=101\n2. https://zabbix.example/chart.php?graphid=102",
    },
    {
        "group": "Триггеры",
        "name": "{trigger_name}",
        "description": "название текущего триггера",
        "example": "Проверка поступления сработок",
    },
    {
        "group": "Триггеры",
        "name": "{trigger_status}",
        "description": "статус текущего триггера",
        "example": "ALERT",
    },
    {
        "group": "Триггеры",
        "name": "{trigger_source_product}",
        "description": "продукт-источник триггера",
        "example": "Сфера 1",
    },
    {
        "group": "Триггеры",
        "name": "{trigger_source_section}",
        "description": "раздел-источник триггера",
        "example": "Zabbix-графики",
    },
]


SERVICE_CHECK_VARIABLE_DETAILS = [
    {"group": "Проверка сервисов", "name": "{checked_at}", "description": "дата и время проверки сервисов", "example": "2026-06-10 13:30"},
    {"group": "Проверка сервисов", "name": "{services_total_count}", "description": "всего сервисов", "example": "14"},
    {"group": "Проверка сервисов", "name": "{services_ok_count}", "description": "количество сервисов со статусом ОК", "example": "12"},
    {"group": "Проверка сервисов", "name": "{services_error_count}", "description": "количество ошибок", "example": "1"},
    {"group": "Проверка сервисов", "name": "{services_timeout_count}", "description": "количество таймаутов", "example": "1"},
    {"group": "Проверка сервисов", "name": "{services_unknown_count}", "description": "количество неизвестных результатов", "example": "0"},
    {"group": "Проверка сервисов", "name": "{services_results}", "description": "нумерованный список результатов", "example": "1. FacePay — ОК"},
    {"group": "Проверка сервисов", "name": "{services_errors}", "description": "подробности ошибок", "example": "Биометрик: Ошибка: Access denied"},
]

REDMINE_GRAPH_VARIABLE_DETAILS = []
for graph_index in range(1, 5):
    REDMINE_GRAPH_VARIABLE_DETAILS.extend([
        {
            "group": "Графики",
            "name": f"{{graph_{graph_index}_title}}",
            "description": f"название {graph_index}-го связанного графика",
            "example": "Общее количество сработок за опер. сутки",
        },
        {
            "group": "Графики",
            "name": f"{{graph_{graph_index}_url}}",
            "description": f"ссылка на {graph_index}-й связанный график",
            "example": "https://zabbix.example/chart.php?graphid=101",
        },
        {
            "group": "Redmine-изображения",
            "name": f"{{graph_{graph_index}_image}}",
            "description": f"имя файла скриншота {graph_index}-го графика",
            "example": f"graph_{graph_index}.png",
        },
        {
            "group": "Redmine-изображения",
            "name": f"{{graph_{graph_index}_redmine_image}}",
            "description": "готовая вставка изображения Redmine вида !filename.png!",
            "example": f"!graph_{graph_index}.png!",
        },
        {
            "group": "Redmine-изображения",
            "name": f"{{graph_{graph_index}_collapsed}}",
            "description": f"готовый collapse-блок Redmine для {graph_index}-го графика",
            "example": f"{{{{collapse(График {graph_index})\n!graph_{graph_index}.png!\n}}}}",
        },
    ])

REDMINE_GRAPH_VARIABLE_DETAILS.extend([
    {
        "group": "Redmine-изображения",
        "name": "{graph_images}",
        "description": "список всех изображений графиков в Redmine-разметке",
        "example": "!graph_1.png!\n!graph_2.png!",
    },
    {
        "group": "Redmine-изображения",
        "name": "{graph_images_collapsed}",
        "description": "список всех изображений графиков в collapse-блоках",
        "example": "{{collapse(График 1)\n!graph_1.png!\n}}\n{{collapse(График 2)\n!graph_2.png!\n}}",
    },
    {
        "group": "Redmine-изображения",
        "name": "{screenshots_folder}",
        "description": "папка, куда сохранены скриншоты графиков",
        "example": "/home/user/oko/screenshots/2026-06-03_123015",
    },
])

OTRS_VARIABLES = [item["name"] for item in OTRS_VARIABLE_DETAILS]
REDMINE_GRAPH_VARIABLES = [item["name"] for item in REDMINE_GRAPH_VARIABLE_DETAILS]

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


def default_redmine_special_task_template():
    return deepcopy(DEFAULT_REDMINE_SPECIAL_TASK_TEMPLATE)


def ensure_templates_defaults(config):
    """Ensure safe, credential-free template settings exist in the app config."""
    templates = config.setdefault("templates", {})

    otrs = templates.setdefault(OTRS_GRAPH_CHECK_TEMPLATE_KEY, {})
    otrs_defaults = default_otrs_graph_check_template()
    otrs.setdefault("name", otrs_defaults["name"])
    otrs.setdefault("text", otrs_defaults["text"])

    service = templates.setdefault(OTRS_SERVICE_CHECK_TEMPLATE_KEY, {})
    service.setdefault("name", DEFAULT_OTRS_SERVICE_CHECK_TEMPLATE_NAME)
    service.setdefault("text", DEFAULT_OTRS_SERVICE_CHECK_TEMPLATE_TEXT.strip())

    redmine = templates.setdefault(REDMINE_TASK_TEMPLATE_KEY, {})
    for key, value in default_redmine_task_template().items():
        redmine.setdefault(key, value)

    redmine_special = templates.setdefault(REDMINE_SPECIAL_TASK_TEMPLATE_KEY, {})
    for key, value in default_redmine_special_task_template().items():
        redmine_special.setdefault(key, value)

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


def get_otrs_service_check_template(config):
    templates = ensure_templates_defaults(config)
    template = templates.get(OTRS_SERVICE_CHECK_TEMPLATE_KEY) or {}
    text = str(template.get("text") or "").strip()
    if not text:
        text = DEFAULT_OTRS_SERVICE_CHECK_TEMPLATE_TEXT
    return {
        "name": str(template.get("name") or DEFAULT_OTRS_SERVICE_CHECK_TEMPLATE_NAME),
        "text": text,
    }


def reset_otrs_service_check_template(config):
    templates = config.setdefault("templates", {})
    templates[OTRS_SERVICE_CHECK_TEMPLATE_KEY] = {
        "name": DEFAULT_OTRS_SERVICE_CHECK_TEMPLATE_NAME,
        "text": DEFAULT_OTRS_SERVICE_CHECK_TEMPLATE_TEXT.strip(),
    }
    return templates[OTRS_SERVICE_CHECK_TEMPLATE_KEY]


def reset_otrs_graph_check_template(config):
    templates = config.setdefault("templates", {})
    templates[OTRS_GRAPH_CHECK_TEMPLATE_KEY] = default_otrs_graph_check_template()
    return templates[OTRS_GRAPH_CHECK_TEMPLATE_KEY]


def reset_redmine_task_template(config):
    templates = config.setdefault("templates", {})
    templates[REDMINE_TASK_TEMPLATE_KEY] = default_redmine_task_template()
    return templates[REDMINE_TASK_TEMPLATE_KEY]


def reset_redmine_special_task_template(config):
    templates = config.setdefault("templates", {})
    templates[REDMINE_SPECIAL_TASK_TEMPLATE_KEY] = default_redmine_special_task_template()
    return templates[REDMINE_SPECIAL_TASK_TEMPLATE_KEY]


def get_redmine_task_template(config, special=False):
    templates = ensure_templates_defaults(config)
    key = REDMINE_SPECIAL_TASK_TEMPLATE_KEY if special else REDMINE_TASK_TEMPLATE_KEY
    defaults = default_redmine_special_task_template() if special else default_redmine_task_template()
    template = templates.get(key) or {}
    return {key_: template.get(key_, value) for key_, value in defaults.items()}


def render_template(template_text, context):
    """Render a template without raising on unknown placeholders."""
    safe_context = {str(key): "" if value is None else str(value) for key, value in (context or {}).items()}

    def replace(match):
        return safe_context.get(match.group(1), "")

    return _TEMPLATE_TOKEN_RE.sub(replace, str(template_text or ""))



def sample_otrs_preview_context():
    return {
        "checked_at": "2026-06-05 12:00",
        "from_time": "2026-06-05 09:00",
        "to_time": "2026-06-05 12:00",
        "duration_minutes": "180",
        "ok_count": "5",
        "alert_count": "2",
        "error_count": "0",
        "active_triggers": "1. Проверка поступления сработок — ALERT",
        "active_trigger_names": "Проверка поступления сработок",
        "active_problems": "1. По графику “Общее количество сработок” наблюдается отклонение.",
        "related_graphs": "1. (Сфера 1) detects-history-search: Общее количество сработок за опер. сутки",
        "related_graph_links": "1. https://zabbix.example.local/chart.php?graphid=101",
        "trigger_name": "Проверка поступления сработок",
        "trigger_status": "ALERT",
        "trigger_source_product": "Сфера 1",
        "trigger_source_section": "Zabbix-графики",
    }


def sample_redmine_preview_context():
    return {
        **sample_otrs_preview_context(),
        "trigger_name": "Проверка поступления сработок",
        "trigger_status": "ALERT",
        "graph_1_title": "(Сфера 1) detects-history-search: Общее количество сработок за опер. сутки",
        "graph_1_url": "https://zabbix.example.local/chart.php?graphid=101",
        "graph_1_image": "graph_1.png",
        "graph_1_redmine_image": "!graph_1.png!",
        "graph_1_collapsed": "{{collapse(скрыть/показать)\n!graph_1.png!\n}}",
        "graph_2_title": "(Сфера 2) detects-history-search: Общее количество сработок за опер. сутки",
        "graph_2_url": "https://zabbix.example.local/chart.php?graphid=102",
        "graph_2_image": "graph_2.png",
        "graph_2_redmine_image": "!graph_2.png!",
        "graph_2_collapsed": "{{collapse(скрыть/показать)\n!graph_2.png!\n}}",
        "graph_images": "!graph_1.png!\n!graph_2.png!",
        "graph_images_collapsed": "{{collapse(скрыть/показать)\n!graph_1.png!\n!graph_2.png!\n}}",
        "screenshots_folder": "/tmp/oko_screenshots/example",
        "special_graph_links": "1. https://zabbix.example.local/chart.php?graphid=101\n2. https://zabbix.example.local/chart.php?graphid=102",
    }


def preview_otrs_template(template_text):
    return render_template(template_text, sample_otrs_preview_context())


def preview_redmine_template(subject_template, description_template):
    context = sample_redmine_preview_context()
    subject = render_template(subject_template, context)
    description = render_template(description_template, context)
    return f"Тема:\n{subject}\n\nОписание:\n{description}"


def variable_details_text(details):
    """Format grouped variable help for read-only template editor panels."""
    grouped = {}
    for item in details or []:
        grouped.setdefault(item.get("group", "Прочее"), []).append(item)

    lines = [
        "Переменные можно вставлять в текст шаблона. "
        "При создании заметки или задачи они будут автоматически заменены на реальные значения."
    ]
    for group, items in grouped.items():
        lines.append("")
        lines.append(f"[{group}]")
        for item in items:
            lines.append(item.get("name", ""))
            lines.append(f"Описание: {item.get('description', '')}")
            example = item.get("example", "")
            if example:
                lines.append(f"Пример: {example}")
            lines.append("")
    return "\n".join(lines).strip()


def format_numbered_lines(items, empty_text="Не обнаружены"):
    values = [str(item).strip() for item in (items or []) if str(item or "").strip()]
    if not values:
        return empty_text
    return "\n".join(f"{index}. {value}" for index, value in enumerate(values, start=1))


def format_dt(value):
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M:%S")
    return str(value or "")
