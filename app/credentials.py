import base64
import json
import os
from datetime import datetime
from pathlib import Path


CREDENTIALS_DIR = Path.home() / ".config" / "zabbix_duty_panel"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"


OTRS_CREDENTIALS_KEY = "otrs"
LEGACY_OTRS_CREDENTIALS_KEY = "__otrs__"
SERVICE_CREDENTIALS_PREFIX = "service_check::"
SERVICE_GROUP_CREDENTIALS_PREFIX = "service_group::"
PROFILE_EXPORT_TYPE = "oko_profile_credentials"
PROFILE_EXPORT_VERSION = 1


def load_otrs_credentials(config=None) -> dict:
    """Load OTRS credentials from the shared credentials store.

    Older builds stored OTRS login/password in ``config["duty_mode"]``.
    Those values are used only as a compatibility fallback so existing users
    still see their credentials in Profile and autologin keeps working until
    they save them into the credentials file.
    """
    credentials = load_saved_credentials()
    saved = credentials.get(OTRS_CREDENTIALS_KEY) or credentials.get(LEGACY_OTRS_CREDENTIALS_KEY, {})
    login = saved.get("login", "")
    password = saved.get("password", "")

    if (login or password) or not config:
        return {"login": login, "password": password}

    duty = config.get("duty_mode", {}) if isinstance(config, dict) else {}
    return {
        "login": str(duty.get("otrs_login", "") or ""),
        "password": str(duty.get("otrs_password", "") or ""),
    }


def save_otrs_credentials(login: str, password: str):
    credentials = load_saved_credentials()
    credentials.pop(LEGACY_OTRS_CREDENTIALS_KEY, None)
    credentials[OTRS_CREDENTIALS_KEY] = {
        "login": login or "",
        "password": password or "",
    }
    save_credentials(credentials)


def load_service_credentials(service_id: str) -> dict:
    credentials = load_saved_credentials()
    return credentials.get(f"{SERVICE_CREDENTIALS_PREFIX}{service_id}", {"login": "", "password": ""})


def save_service_credentials(service_id: str, login: str, password: str):
    credentials = load_saved_credentials()
    credentials[f"{SERVICE_CREDENTIALS_PREFIX}{service_id}"] = {
        "login": login or "",
        "password": password or "",
    }
    save_credentials(credentials)


def load_service_group_credentials(group_id: str) -> dict:
    credentials = load_saved_credentials()
    return credentials.get(f"{SERVICE_GROUP_CREDENTIALS_PREFIX}{group_id}", {"login": "", "password": ""})


def save_service_group_credentials(group_id: str, login: str, password: str):
    credentials = load_saved_credentials()
    credentials[f"{SERVICE_GROUP_CREDENTIALS_PREFIX}{group_id}"] = {
        "login": login or "",
        "password": password or "",
    }
    save_credentials(credentials)


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


def default_profile_export_filename():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"oko_profile_{timestamp}.oko-profile.json"


def make_profile_credentials_export(credentials=None) -> dict:
    credentials = load_saved_credentials() if credentials is None else credentials
    raw_credentials = {}

    for key, data in sorted((credentials or {}).items()):
        if not isinstance(data, dict):
            continue

        raw_credentials[str(key)] = {
            "login": _encode(data.get("login", "")),
            "password": _encode(data.get("password", "")),
        }

    return {
        "type": PROFILE_EXPORT_TYPE,
        "version": PROFILE_EXPORT_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "credentials": raw_credentials,
    }


def load_profile_credentials_export(source_path) -> dict:
    path = Path(source_path)

    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, dict):
        raise ValueError("Invalid profile export payload")

    if payload.get("type") != PROFILE_EXPORT_TYPE:
        raise ValueError("Unsupported profile export type")

    credentials = payload.get("credentials")
    if not isinstance(credentials, dict):
        raise ValueError("Invalid profile credentials payload")

    result = {}

    for key, data in credentials.items():
        if not isinstance(data, dict):
            continue

        result[str(key)] = {
            "login": _decode(data.get("login", "")),
            "password": _decode(data.get("password", "")),
        }

    return result


def export_profile_credentials_file(destination_path, credentials=None):
    path = Path(destination_path)
    payload = make_profile_credentials_export(credentials)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    try:
        os.chmod(path, 0o600)
    except Exception:
        pass

    return path


def import_profile_credentials_file(source_path):
    imported_credentials = load_profile_credentials_export(source_path)
    credentials = load_saved_credentials()
    credentials.update(imported_credentials)
    save_credentials(credentials)
    return len(imported_credentials)


def clear_saved_credentials():
    try:
        if CREDENTIALS_FILE.exists():
            CREDENTIALS_FILE.unlink()
    except Exception:
        pass
