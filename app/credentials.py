import base64
import json
import os
from pathlib import Path


CREDENTIALS_DIR = Path.home() / ".config" / "zabbix_duty_panel"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"


def _encode(value: str) -> str:
    """
    Это не полноценное шифрование, а простое скрытие от случайного просмотра.
    Файл дополнительно создается с правами 600.
    """
    if value is None:
        value = ""
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _decode(value: str) -> str:
    try:
        return base64.b64decode(value.encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def load_saved_credentials() -> dict:
    if not CREDENTIALS_FILE.exists():
        return {}

    try:
        with CREDENTIALS_FILE.open("r", encoding="utf-8") as file:
            raw = json.load(file)
    except Exception:
        return {}

    result = {}

    for zabbix_id, data in raw.items():
        result[zabbix_id] = {
            "login": _decode(data.get("login", "")),
            "password": _decode(data.get("password", ""))
        }

    return result


def save_credentials(credentials: dict):
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)

    raw = {}

    for zabbix_id, data in credentials.items():
        raw[zabbix_id] = {
            "login": _encode(data.get("login", "")),
            "password": _encode(data.get("password", ""))
        }

    with CREDENTIALS_FILE.open("w", encoding="utf-8") as file:
        json.dump(raw, file, ensure_ascii=False, indent=2)

    try:
        os.chmod(CREDENTIALS_FILE, 0o600)
    except Exception:
        pass


def clear_saved_credentials():
    try:
        if CREDENTIALS_FILE.exists():
            CREDENTIALS_FILE.unlink()
    except Exception:
        pass
