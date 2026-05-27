from pathlib import Path
from PySide6.QtWebEngineCore import QWebEngineProfile

PROFILE_DIR = Path.home() / ".zabbix_duty_panel" / "profiles"


def create_profile(zabbix_id: str) -> QWebEngineProfile:
    """
    Создает отдельный браузерный профиль на каждый Zabbix.
    Так cookies разных Zabbix не мешаются.
    """
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    profile = QWebEngineProfile(f"profile_{zabbix_id}")
    profile_path = PROFILE_DIR / zabbix_id
    cache_path = profile_path / "cache"

    profile.setPersistentStoragePath(str(profile_path))
    profile.setCachePath(str(cache_path))

    return profile
