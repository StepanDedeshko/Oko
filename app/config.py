import json
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from app.logger import get_logger
from app.service_checks import default_service_checks_config

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
CONFIG_EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "config.example.json"


DEFAULT_DUTY_TRIGGERS = {
    "enabled": True,
    "items": [
        {
            "id": "trigger_mode_1",
            "enabled": True,
            "display_name": "Проверка поступления сработок",
            "source_product": "",
            "source_section": "",
            "metric_title": "Кол-во всех сработок (опер. сутки)",
            "target_product": "",
            "target_section": "",
            "target_graph_title": "",
            "mode": "mode_1",
            "ok_text": "Сработки поступают все в пределах нормы",
            "alert_template": "С {from_time} по {to_time} отсутствуют сработки.",
        },
        {
            "id": "trigger_mode_2",
            "enabled": True,
            "display_name": "Проверка поступления сработок",
            "source_product": "",
            "source_section": "",
            "metric_title": "Кол-во всех сработок (опер. сутки)",
            "target_product": "",
            "target_section": "",
            "target_graph_title": "",
            "mode": "mode_2",
            "ok_text": "Сработки поступают все в пределах нормы",
            "alert_template": "С {from_time} по {to_time} отсутствуют сработки.",
        },
    ],
    "day_start": "06:00",
    "day_end": "00:00",
    "day_threshold_minutes": 90,
    "night_threshold_minutes": 180,
    "mode1_night_silence_start": "01:00",
    "mode1_night_silence_end": "05:30",
}


def default_duty_triggers_config():
    return deepcopy(DEFAULT_DUTY_TRIGGERS)


def default_trigger_item(trigger_id="", mode="mode_1"):
    trigger = default_duty_triggers_config()["items"][0]
    trigger["id"] = trigger_id
    trigger["mode"] = mode
    return trigger


def ensure_duty_triggers_defaults(config):
    defaults = default_duty_triggers_config()
    settings = config.setdefault("duty_triggers", {})

    for key, value in defaults.items():
        if key == "items":
            continue
        settings.setdefault(key, deepcopy(value))

    items = settings.setdefault("items", [])
    if not items:
        items.extend(deepcopy(defaults["items"]))
    else:
        valid_modes = {"mode_1", "mode_2"}
        for index, item in enumerate(items):
            mode = item.get("mode") if item.get("mode") in valid_modes else "mode_1"
            item_defaults = default_trigger_item(
                item.get("id") or f"trigger_{index + 1}",
                mode,
            )
            for key, value in item_defaults.items():
                item.setdefault(key, deepcopy(value))

    return settings

def ensure_duty_mode_defaults(config):
    settings = config.setdefault("duty_mode", {})
    legacy_task_number = (
        settings.get("duty_zabbix_task_number")
        or settings.get("current_ticket_number")
        or settings.get("duty_task_number")
        or settings.get("task_number")
        or ""
    )
    settings.setdefault("enabled", False)
    settings.setdefault("hourly_notification", True)
    settings.setdefault("skip_minutes", 5)
    settings.setdefault("sound_path", "")
    settings.setdefault("current_ticket_number", str(legacy_task_number or ""))
    settings.setdefault("current_ticket_id", "")
    settings.setdefault("current_ticket_url", "")
    settings.setdefault("duty_zabbix_task_number", str(legacy_task_number or ""))
    settings.setdefault("duty_service_checks_task_number", "")
    settings.setdefault("duty_service_checks_enabled", False)
    settings.setdefault("expected_ticket_subject", "Проверка Zabbix (Важных IT-сервисов)")
    settings.setdefault("otrs_login_enabled", False)
    settings.setdefault("otrs_login", "")
    settings.setdefault("otrs_password", "")
    settings.setdefault("otrs_auto_submit_login", False)
    settings.setdefault("graph_ids", [])
    settings.setdefault("otrs", {})
    settings["otrs"].setdefault("create_url", "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentNewTicketForm;NewTicketFormID=6")
    settings["otrs"].setdefault("note_url_base", "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketNote;TicketID=")
    settings["otrs"].setdefault("note_url_template", "")
    return settings



def _default_config():
    return {
        "_comment": "Автосозданный минимальный config.json для Око.",
        "settings": {
            "theme": "mass_effect",
            "home_notes": "",
            "default_time_range": "1h",
            "check_updates_on_startup": True,
        },
        "time_ranges": [
            {"title": "1ч", "value": "1h"},
            {"title": "6ч", "value": "6h"},
            {"title": "24ч", "value": "24h"},
        ],
        "zabbix_instances": [],
        "products": [],
        "loading_screen": {
            "enabled": True,
            "show_after_login": True,
            "duration_ms": 7000,
        },
        "duty_mode": {
            "otrs_login_enabled": False,
            "otrs_login": "",
            "otrs_password": "",
            "otrs_auto_submit_login": False,
            "expected_ticket_subject": "Проверка Zabbix (Важных IT-сервисов)",
            "duty_service_checks_enabled": False,
            "duty_zabbix_task_number": "",
            "duty_service_checks_task_number": "",
        },
        "duty_triggers": default_duty_triggers_config(),
        "service_checks": default_service_checks_config(),
        "app": {"name": "Око"},
    }



SETTINGS_EXPORT_FORMAT = "oko_settings_export"
SETTINGS_EXPORT_FORMAT_VERSION = 1
SECRET_KEY_PARTS = (
    "password",
    "passwd",
    "token",
    "cookie",
    "session",
    "auth",
    "credential",
    "secret",
    "login",
    "username",
    "email",
)
EXPORTABLE_CONFIG_KEYS = (
    "settings",
    "time_ranges",
    "zabbix_instances",
    "products",
    "problems_pages",
    "dashboard_pages",
    "mode_pages",
    "duty_mode",
    "duty_triggers",
    "service_checks",
    "templates",
    "app",
)


def default_settings_export_filename(now=None):
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return f"oko_settings_export_{timestamp}.json"


def _is_secret_key(key):
    lowered = str(key or "").lower()
    return any(part in lowered for part in SECRET_KEY_PARTS)


SERVICE_CHECK_EXPORT_SAFE_SECRET_KEYS = {
    "auth_type",
    "login_selector",
    "password_selector",
    "submit_selector",
    "post_login_actions",
    "session_group",
    "session_group_order",
    "session_group_login_owner",
    "session_group_logout_owner",
    "session_group_reuse_webview",
}


def _is_service_check_path(path):
    return "service_checks" in path


def _sanitize_export_data(value, path=()):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_secret_key(key_text) and not (
                _is_service_check_path(path) and key_text in SERVICE_CHECK_EXPORT_SAFE_SECRET_KEYS
            ):
                continue
            sanitized[key] = _sanitize_export_data(item, path + (key_text,))
        return sanitized
    if isinstance(value, list):
        return [_sanitize_export_data(item, path) for item in value]
    return deepcopy(value)


def sanitize_export_data(value):
    """Return a deep copy without credentials, preserving safe service-check selectors."""
    return _sanitize_export_data(value)


def collect_exportable_settings(config):
    """Collect user configuration that is safe to transfer between installations."""
    config = config or {}
    settings = {}
    for key in EXPORTABLE_CONFIG_KEYS:
        if key in config:
            settings[key] = deepcopy(config[key])
    return sanitize_export_data(settings)


def build_settings_export(config, exported_at=None):
    exported_at = exported_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "app": "Око",
        "format": SETTINGS_EXPORT_FORMAT,
        "format_version": SETTINGS_EXPORT_FORMAT_VERSION,
        "exported_at": exported_at,
        "settings": collect_exportable_settings(config),
    }


def export_settings_file(config, destination_path):
    destination_path = Path(destination_path)
    export_data = sanitize_export_data(build_settings_export(config))
    with destination_path.open("w", encoding="utf-8") as file:
        json.dump(export_data, file, ensure_ascii=False, indent=2)
    return destination_path


def load_settings_export(source_path):
    source_path = Path(source_path)
    with source_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("unsupported settings export format")
    if data.get("format") != SETTINGS_EXPORT_FORMAT:
        raise ValueError("unsupported settings export format")
    if data.get("format_version") != SETTINGS_EXPORT_FORMAT_VERSION:
        raise ValueError("unsupported settings export version")
    settings = data.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("settings section is missing")
    return sanitize_export_data(settings)


def import_settings_file(source_path, config_path=None):
    """Import a safe Oko settings export and backup the current config first."""
    config_path = Path(config_path) if config_path is not None else CONFIG_PATH
    imported_settings = load_settings_export(source_path)

    backup_path = None
    if config_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config_path.with_name(f"config.backup_before_import_{timestamp}.json")
        shutil.copy2(config_path, backup_path)

    safe_settings = sanitize_export_data(imported_settings)
    with config_path.open("w", encoding="utf-8") as file:
        json.dump(safe_settings, file, ensure_ascii=False, indent=2)
    return backup_path


def ensure_config_exists():
    if CONFIG_PATH.exists():
        return
    if CONFIG_EXAMPLE_PATH.exists():
        CONFIG_PATH.write_text(CONFIG_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        save_config(_default_config())


def load_config():
    ensure_config_exists()
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_config(config):
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)


def enabled_zabbix_instances(config):
    return [
        instance
        for instance in config.get("zabbix_instances", [])
        if instance.get("enabled", True)
    ]


def import_config_file(source_path):
    """
    Импортирует выбранный пользователем JSON как рабочий config.json.

    Содержимое конфигурации не логируется. Перед заменой текущего config.json
    создаётся backup вида config.json.before_import_YYYYMMDD_HHMMSS.
    """
    logger = get_logger()
    source_path = Path(source_path)

    try:
        with source_path.open("r", encoding="utf-8") as file:
            json.load(file)

        backup_path = None
        if CONFIG_PATH.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = CONFIG_PATH.with_name(f"config.json.before_import_{timestamp}")
            shutil.copy2(CONFIG_PATH, backup_path)

        if source_path.resolve() != CONFIG_PATH.resolve():
            shutil.copy2(source_path, CONFIG_PATH)

        logger.info("config.json импортирован")
        return backup_path
    except Exception:
        logger.exception("Ошибка импорта config.json")
        raise
