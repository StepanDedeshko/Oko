import json
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from app.logger import get_logger
from app.service_checks import default_service_checks_config
from app.redmine_triggers import default_special_redmine_triggers_config, ensure_special_redmine_triggers_defaults
from app.trigger_model import default_trigger_catalog_config, ensure_trigger_catalog_defaults
from app.live_zabbix import default_live_monitor_config, ensure_live_monitor_defaults
from app.permissions import ensure_duty_links, build_user_settings_export, import_user_settings_payload

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
    settings.setdefault("duty_zabbix_task_id", str(settings.get("current_ticket_id") or ""))
    settings.setdefault("duty_zabbix_task_url", str(settings.get("current_ticket_url") or ""))
    settings.setdefault("duty_service_checks_task_number", "")
    settings.setdefault("duty_service_checks_task_id", "")
    settings.setdefault("duty_service_checks_task_url", "")
    settings.setdefault("duty_service_checks_enabled", False)
    settings.setdefault("check_services_enabled", bool(settings.get("duty_service_checks_enabled", False)))
    settings.setdefault("check_zabbix_enabled", True)
    settings.setdefault("last_service_check_note", "")
    settings.setdefault("last_zabbix_check_note", "")
    settings.setdefault("last_service_check_time", "")
    settings.setdefault("last_zabbix_check_time", "")
    settings.setdefault("manual_duty_note", "")
    settings.setdefault("zabbix_problem_keywords", [])
    settings.setdefault("zabbix_problem_exclude_keywords", [])
    legacy_expected_title = (
        settings.get("duty_zabbix_expected_task_title")
        or settings.get("expected_task_title")
        or settings.get("duty_expected_task_title")
        or settings.get("expected_ticket_title")
        or settings.get("duty_ticket_title")
        or settings.get("expected_ticket_subject")
        or "Дежурная проверка Zabbix / графиков"
    )
    settings.setdefault("duty_zabbix_expected_task_title", str(legacy_expected_title or "Дежурная проверка Zabbix / графиков"))
    settings.setdefault("duty_service_checks_expected_task_title", str(settings.get("expected_service_checks_ticket_subject") or "Дежурная проверка сервисов"))
    settings.setdefault("expected_ticket_subject", settings.get("duty_zabbix_expected_task_title", "Дежурная проверка Zabbix / графиков"))
    settings.setdefault("expected_service_checks_ticket_subject", settings.get("duty_service_checks_expected_task_title", "Дежурная проверка сервисов"))
    settings.setdefault("otrs_login_enabled", False)
    settings.setdefault("otrs_login", "")
    settings.setdefault("otrs_password", "")
    settings.setdefault("otrs_auto_submit_login", False)
    settings.setdefault("graph_ids", [])
    ensure_trigger_catalog_defaults(config)
    ensure_special_redmine_triggers_defaults(config)
    ensure_live_monitor_defaults(config)
    ensure_duty_links(config)
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
            "expected_ticket_subject": "Дежурная проверка Zabbix / графиков",
            "duty_zabbix_expected_task_title": "Дежурная проверка Zabbix / графиков",
            "duty_service_checks_expected_task_title": "Дежурная проверка сервисов",
            "duty_service_checks_enabled": False,
            "check_services_enabled": False,
            "check_zabbix_enabled": True,
            "last_service_check_note": "",
            "last_zabbix_check_note": "",
            "last_service_check_time": "",
            "last_zabbix_check_time": "",
            "manual_duty_note": "",
            "zabbix_problem_keywords": [],
            "zabbix_problem_exclude_keywords": [],
            "duty_zabbix_task_number": "",
            "duty_zabbix_task_id": "",
            "duty_zabbix_task_url": "",
            "duty_service_checks_task_number": "",
            "duty_service_checks_task_id": "",
            "duty_service_checks_task_url": "",
            "expected_service_checks_ticket_subject": "Дежурная проверка сервисов",
        },
        "duty_triggers": default_duty_triggers_config(),
        "zabbix_trigger_definitions": default_trigger_catalog_config(),
        "special_redmine_triggers": default_special_redmine_triggers_config(),
        "live_zabbix_monitor": default_live_monitor_config(),
        "service_checks": default_service_checks_config(),
        "duty_links": {},
        "zabbix_trigger_catalog": {"version": 1, "triggers": []},
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
    "special_redmine_triggers",
    "service_checks",
    "templates",
    "zabbix_trigger_catalog",
    "duty_links",
    "app",
)


def default_settings_export_filename(now=None):
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return f"oko_settings_export_{timestamp}.json"


def _is_secret_key(key):
    lowered = str(key or "").lower()
    if lowered in {"credential_groups", "credential_group_id"}:
        return False
    return any(part in lowered for part in SECRET_KEY_PARTS)


SERVICE_CHECK_EXPORT_SAFE_SECRET_KEYS = {
    "auth_type",
    "login_selector",
    "password_selector",
    "submit_selector",
    "post_login_actions",
    "post_login_mini_test_enabled",
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
            if _is_service_check_path(path) and key_text in SERVICE_CHECK_EXPORT_SAFE_SECRET_KEYS:
                sanitized[key] = _sanitize_export_data(item, path + (key_text,))
                continue
            if _is_secret_key(key_text):
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

    current = {}
    if config_path.exists():
        try:
            current = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    if isinstance(imported_settings, dict) and imported_settings.get("format") == "oko_user_settings_export":
        safe_settings = import_user_settings_payload(current, imported_settings, keep_passwords=True)
    else:
        safe_settings = sanitize_export_data(imported_settings)
    with config_path.open("w", encoding="utf-8") as file:
        json.dump(safe_settings, file, ensure_ascii=False, indent=2)

    catalog = safe_settings.get("zabbix_trigger_catalog")
    if isinstance(catalog, dict):
        try:
            data_dir = config_path.parent / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            (data_dir / "zabbix_trigger_catalog.json").write_text(
                json.dumps(catalog, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            get_logger().exception("Не удалось восстановить zabbix_trigger_catalog.json из экспорта настроек")
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
