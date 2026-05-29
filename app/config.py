import json
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from app.logger import get_logger

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
        },
        "duty_triggers": default_duty_triggers_config(),
        "app": {"name": "Око"},
    }


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
