from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALID_EQUALIZER_MODES = {"auto", "real", "decorative"}


def normalize_bar_count(count):
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 24
    return max(4, min(96, count))


def normalize_fps(fps):
    try:
        fps = int(fps)
    except (TypeError, ValueError):
        fps = 24
    return max(6, min(60, fps))


def normalize_mode(mode):
    return mode if mode in VALID_EQUALIZER_MODES else "auto"


def default_music_widget_config():
    return {
        "enabled": True, "visible": True, "collapsed": False, "active_provider": "yandex_music",
        "width": 420, "height": 220, "show_in_header": True,
        "visualizer_enabled": True, "visualizer_mode": "auto", "visualizer_bar_count": 24,
        "visualizer_fps": 24, "visualizer_decorative_when_idle": True,
        "providers": [
            {"id": "yandex_music", "name": "Яндекс Музыка", "url": "https://music.yandex.ru/", "enabled": True, "profile_dir": "web_profiles/music/yandex_music", "cache_dir": "web_profiles/music/yandex_music_cache", "open_external_if_failed": True},
            {"id": "spotify", "name": "Spotify", "url": "https://open.spotify.com/", "enabled": True, "profile_dir": "web_profiles/music/spotify", "cache_dir": "web_profiles/music/spotify_cache", "open_external_if_failed": True},
            {"id": "custom", "name": "Свой плеер", "url": "", "enabled": False, "profile_dir": "web_profiles/music/custom", "cache_dir": "web_profiles/music/custom_cache", "open_external_if_failed": True},
        ],
    }


def enabled_providers(settings):
    return [p for p in settings.get("providers", []) if isinstance(p, dict) and p.get("enabled", True)]


def find_provider(settings, provider_id):
    for provider in enabled_providers(settings):
        if provider.get("id") == provider_id:
            return provider
    return None


def first_enabled_provider(settings):
    providers = enabled_providers(settings)
    return providers[0] if providers else None


def ensure_music_widget_defaults(config):
    defaults = default_music_widget_config()
    settings = config.setdefault("music_widget", {})
    for key, value in defaults.items():
        if key != "providers":
            settings.setdefault(key, deepcopy(value))
    by_id = {p.get("id"): p for p in settings.setdefault("providers", []) if isinstance(p, dict)}
    for provider_default in defaults["providers"]:
        provider = by_id.get(provider_default["id"])
        if provider is None:
            settings["providers"].append(deepcopy(provider_default))
        else:
            for key, value in provider_default.items():
                provider.setdefault(key, deepcopy(value))
    settings["visualizer_mode"] = normalize_mode(settings.get("visualizer_mode"))
    settings["visualizer_bar_count"] = normalize_bar_count(settings.get("visualizer_bar_count"))
    settings["visualizer_fps"] = normalize_fps(settings.get("visualizer_fps"))
    settings["width"] = max(260, min(900, int(settings.get("width") or 420)))
    settings["height"] = max(120, min(700, int(settings.get("height") or 220)))
    if not find_provider(settings, settings.get("active_provider")):
        fallback = first_enabled_provider(settings)
        settings["active_provider"] = (fallback or {}).get("id", "yandex_music")
    return settings


def provider_paths(provider, root=None):
    root = Path(root or PROJECT_ROOT)
    profile = Path(provider.get("profile_dir") or "")
    cache = Path(provider.get("cache_dir") or "")
    return (profile if profile.is_absolute() else root / profile, cache if cache.is_absolute() else root / cache)
