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
ZABBIX_COMMON_CREDENTIALS_KEY = "zabbix"
PROFILE_EXPORT_TYPE = "oko_profile_credentials"
PROFILE_EXPORT_VERSION = 1


def zabbix_credential_key_for_instance(instance: dict) -> str:
    """Return the stable credentials key for a configured Zabbix instance."""
    if not isinstance(instance, dict):
        return ""
    return str(instance.get("id") or "").strip()


def zabbix_profile_credential_targets(instances, live_zabbix_url="", duty_live_zabbix_url="", zabbix_urls=None) -> list[dict]:
    targets = []
    for instance in instances or []:
        key = zabbix_credential_key_for_instance(instance)
        if not key:
            continue
        targets.append({
            "id": key,
            "name": str(instance.get("name") or key),
            "common": False,
        })

    if targets:
        return targets

    if str(live_zabbix_url or "").strip() or str(duty_live_zabbix_url or "").strip():
        name = "Live Zabbix / Дежурный Zabbix"
    else:
        name = "Zabbix"

    return [{"id": ZABBIX_COMMON_CREDENTIALS_KEY, "name": name, "common": True}]


def collect_zabbix_urls(value) -> list[str]:
    urls = []

    def visit(item):
        if isinstance(item, dict):
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)
        elif isinstance(item, str):
            text = item.strip()
            if text.startswith(("http://", "https://")) and "zabbix" in text.lower():
                urls.append(text)

    visit(value)
    return urls


def load_zabbix_profile_credentials(instances, credentials=None, live_zabbix_url="", duty_live_zabbix_url="", zabbix_urls=None) -> dict:
    credentials = load_saved_credentials() if credentials is None else credentials
    result = {}
    for target in zabbix_profile_credential_targets(instances, live_zabbix_url, duty_live_zabbix_url, zabbix_urls):
        key = target["id"]
        saved = credentials.get(key, {}) if isinstance(credentials, dict) else {}
        result[key] = {
            "login": str(saved.get("login", "") or ""),
            "password": str(saved.get("password", "") or ""),
        }
    return result


def save_zabbix_profile_credentials(instances, values_by_key: dict, credentials=None, live_zabbix_url="", duty_live_zabbix_url="", zabbix_urls=None) -> dict:
    credentials = load_saved_credentials() if credentials is None else dict(credentials)
    values_by_key = values_by_key or {}
    for target in zabbix_profile_credential_targets(instances, live_zabbix_url, duty_live_zabbix_url, zabbix_urls):
        key = target["id"]
        if key not in values_by_key:
            continue
        values = values_by_key.get(key) or {}
        credentials[key] = {
            "login": str(values.get("login", "") or ""),
            "password": str(values.get("password", "") or ""),
        }
    save_credentials(credentials)
    return credentials


def clear_zabbix_profile_credentials(instances, credentials=None) -> dict:
    credentials = load_saved_credentials() if credentials is None else dict(credentials)
    credentials.pop(ZABBIX_COMMON_CREDENTIALS_KEY, None)
    for instance in instances or []:
        key = zabbix_credential_key_for_instance(instance)
        if key:
            credentials.pop(key, None)
    save_credentials(credentials)
    return credentials


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


def build_otrs_login_injection_js(login: str, password: str, auto_submit: bool = False) -> str:
    login = str(login or "")
    password = str(password or "")
    if not login or not password:
        return ""

    def js_string(value):
        return str(value).replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")

    return f"""
    (function() {{
        const user = document.querySelector('#User');
        const password = document.querySelector('#Password');
        const button = document.querySelector('#LoginButton');

        if (!user || !password) {{
            return 'no-login-form';
        }}

        user.focus();
        user.value = '{js_string(login)}';
        user.dispatchEvent(new Event('input', {{ bubbles: true }}));
        user.dispatchEvent(new Event('change', {{ bubbles: true }}));

        password.focus();
        password.value = '{js_string(password)}';
        password.dispatchEvent(new Event('input', {{ bubbles: true }}));
        password.dispatchEvent(new Event('change', {{ bubbles: true }}));

        if ({str(bool(auto_submit)).lower()} && button) {{
            setTimeout(() => button.click(), 500);
            return 'filled-and-submitted';
        }}

        return 'filled';
    }})();
    """


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


def default_encrypted_profile_export_filename():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"oko_profile_{timestamp}.okoenc"


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


def export_profile_credentials_encrypted_file(destination_path, password: str, credentials=None):
    from app.profile_crypto import encrypt_profile_payload

    path = Path(destination_path)
    payload = make_profile_credentials_export(credentials)
    encrypted_payload = encrypt_profile_payload(payload, password)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(encrypted_payload, file, ensure_ascii=False, indent=2)

    try:
        os.chmod(path, 0o600)
    except Exception:
        pass

    return path


def import_profile_credentials_encrypted_file(source_path, password: str):
    from app.profile_crypto import decrypt_profile_payload

    path = Path(source_path)
    with path.open("r", encoding="utf-8") as file:
        encrypted_payload = json.load(file)

    payload = decrypt_profile_payload(encrypted_payload, password)

    if payload.get("type") != PROFILE_EXPORT_TYPE:
        raise ValueError("Unsupported profile export type")

    raw_credentials = payload.get("credentials")
    if not isinstance(raw_credentials, dict):
        raise ValueError("Invalid profile credentials payload")

    imported_credentials = {}
    for key, data in raw_credentials.items():
        if not isinstance(data, dict):
            continue

        imported_credentials[str(key)] = {
            "login": _decode(data.get("login", "")),
            "password": _decode(data.get("password", "")),
        }

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
