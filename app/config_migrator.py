import json
from copy import deepcopy
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"


def deep_merge_missing(current, defaults):
    if isinstance(current, dict) and isinstance(defaults, dict):
        for key, default_value in defaults.items():
            if key not in current:
                current[key] = deepcopy(default_value)
            else:
                current[key] = deep_merge_missing(current[key], default_value)
        return current
    return current


def ensure_runtime_defaults(config):
    config.setdefault("settings", {})
    settings = config["settings"]

    settings.setdefault("theme", "mass_effect")
    settings.setdefault("graph_columns", 1)
    settings.setdefault("vertical_graphs_only", True)
    settings.setdefault("graph_card_min_height", 420)
    settings.setdefault("allow_save_password", True)
    settings.setdefault("graph_refresh_seconds", 300)
    settings.setdefault("problems_refresh_seconds", 60)
    settings.setdefault("web_zoom_factor", 0.85)
    settings.setdefault("fit_graphs_to_window", True)

    loading_defaults = {
        "_comment": "Заставка после входа. Видео и музыка встроены в assets/loading.",
        "enabled": True,
        "show_after_login": True,
        "show_until_problem_counter_ready": False,
        "show_on_problems_open": False,
        "duration_ms": 7000,
        "max_wait_ms": 30000,
        "min_show_ms": 1500,
        "auto_detect_media": True,
        "video_path": "assets/loading/loading.mp4",
        "music_path": "assets/loading/loading_music.mp3",
        "music_volume": 35,
        "loop_video": True,
        "loop_music": True
    }
    config["loading_screen"] = deep_merge_missing(config.get("loading_screen", {}), loading_defaults)
    config["loading_screen"]["show_after_login"] = True
    config["loading_screen"]["show_until_problem_counter_ready"] = False
    config["loading_screen"]["show_on_problems_open"] = False

    for product in config.get("products", []):
        for dashboard in product.get("dashboards", []):
            # Счётчик проблем убран. Страницу проблем оставляем как обычную страницу Zabbix.
            dashboard.pop("problem_counter", None)
            if dashboard.get("type") == "problems_page":
                dashboard["type"] = "problems_page"

            if dashboard.get("type") == "mode_pages":
                dashboard.setdefault("modes", [
                    {"name": "Режим 1", "url": ""},
                    {"name": "Режим 2", "url": ""}
                ])

            if dashboard.get("type") == "graphs_grid":
                dashboard.setdefault("columns", 1)
                dashboard.setdefault("layout", "vertical")
                for graph in dashboard.get("graphs", []):
                    graph.setdefault("open_url", graph.get("zabbix_url", graph.get("external_url", "")))

    config.pop("otrs", None)
    config.pop("fp_connect", None)

    return config


def patch_config_file(config_path=CONFIG_PATH):
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"config.json не найден: {config_path}")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    config = ensure_runtime_defaults(config)

    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return config
