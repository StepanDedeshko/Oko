"""Local Oko application users and roles.

This module stores only password hashes for logging into Oko itself.
External system credentials are kept separately in app.credentials/profile logic.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import uuid


USERS_DIR = Path.home() / ".config" / "zabbix_duty_panel"
USERS_FILE = USERS_DIR / "users.local.json"

ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_USER = "user"
ADMIN_ROLES = {ROLE_OWNER, ROLE_ADMIN}
ALLOWED_ROLES = {ROLE_OWNER, ROLE_ADMIN, ROLE_USER}

PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 240_000
MIN_PASSWORD_LENGTH = 4


def users_file_path(path: str | Path | None = None) -> Path:
    return Path(path) if path is not None else USERS_FILE


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_login(login: str) -> str:
    return str(login or "").strip()


def login_key(login: str) -> str:
    return normalize_login(login).casefold()


def _empty_store() -> dict:
    return {"version": 1, "users": []}


def load_users(path: str | Path | None = None) -> dict:
    store_path = users_file_path(path)
    if not store_path.exists():
        return _empty_store()

    try:
        with store_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except Exception:
        return _empty_store()

    if not isinstance(data, dict):
        return _empty_store()

    users = data.get("users", [])
    if not isinstance(users, list):
        users = []

    normalized = _empty_store()
    normalized["version"] = int(data.get("version", 1) or 1)
    normalized["users"] = [user for user in users if isinstance(user, dict)]
    return normalized


def save_users(data: dict, path: str | Path | None = None):
    store_path = users_file_path(path)
    store_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": int((data or {}).get("version", 1) or 1),
        "users": list((data or {}).get("users", []) or []),
    }

    with store_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    try:
        os.chmod(store_path, 0o600)
    except Exception:
        pass


def has_users(path: str | Path | None = None) -> bool:
    return bool(load_users(path).get("users"))


def _new_salt() -> str:
    return secrets.token_hex(16)


def _hash_password(password: str, salt_hex: str, iterations: int = PASSWORD_HASH_ITERATIONS) -> str:
    password_bytes = str(password or "").encode("utf-8")
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password_bytes, salt, int(iterations))
    return digest.hex()


def _verify_password(password: str, user: dict) -> bool:
    salt = str(user.get("password_salt", "") or "")
    expected = str(user.get("password_hash", "") or "")
    iterations = int(user.get("password_iterations", PASSWORD_HASH_ITERATIONS) or PASSWORD_HASH_ITERATIONS)

    if not salt or not expected:
        return False

    try:
        actual = _hash_password(password, salt, iterations)
    except Exception:
        return False

    return hmac.compare_digest(actual, expected)


def public_user(user: dict | None) -> dict:
    if not user:
        return {}

    hidden = {
        "password_hash",
        "password_salt",
        "password_iterations",
        "password_algorithm",
    }
    return {key: deepcopy(value) for key, value in user.items() if key not in hidden}


def active_admin_users(data: dict) -> list[dict]:
    return [
        user
        for user in (data or {}).get("users", []) or []
        if bool(user.get("active", True)) and str(user.get("role", ROLE_USER)) in ADMIN_ROLES
    ]


def _find_user(data: dict, login: str) -> dict | None:
    wanted = login_key(login)
    for user in (data or {}).get("users", []) or []:
        if str(user.get("login_key") or login_key(user.get("login", ""))) == wanted:
            return user
    return None


def _validate_login_password(login: str, password: str):
    if not normalize_login(login):
        raise ValueError("Логин не может быть пустым.")
    if len(str(password or "")) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов.")


def create_user(
    login: str,
    password: str,
    role: str = ROLE_USER,
    display_name: str = "",
    active: bool = True,
    path: str | Path | None = None,
) -> dict:
    data = load_users(path)
    normalized_login = normalize_login(login)
    _validate_login_password(normalized_login, password)

    if _find_user(data, normalized_login):
        raise ValueError("Пользователь с таким логином уже существует.")

    selected_role = str(role or ROLE_USER)
    if selected_role not in ALLOWED_ROLES:
        raise ValueError("Недопустимая роль пользователя.")

    if not data.get("users"):
        selected_role = ROLE_OWNER

    salt = _new_salt()
    now = _utc_now()
    user = {
        "id": str(uuid.uuid4()),
        "login": normalized_login,
        "login_key": login_key(normalized_login),
        "display_name": str(display_name or normalized_login).strip() or normalized_login,
        "role": selected_role,
        "active": bool(active),
        "password_algorithm": PASSWORD_HASH_ALGORITHM,
        "password_iterations": PASSWORD_HASH_ITERATIONS,
        "password_salt": salt,
        "password_hash": _hash_password(password, salt),
        "created_at": now,
        "updated_at": now,
    }

    data.setdefault("users", []).append(user)
    save_users(data, path)
    return public_user(user)


def authenticate_user(login: str, password: str, path: str | Path | None = None) -> dict | None:
    data = load_users(path)
    user = _find_user(data, login)
    if not user:
        return None
    if not bool(user.get("active", True)):
        return None
    if not _verify_password(password, user):
        return None
    return public_user(user)


def _ensure_not_last_admin_change(data: dict, target_login: str, new_role: str | None = None, new_active: bool | None = None):
    target_key = login_key(target_login)
    simulated = deepcopy(data)

    for user in simulated.get("users", []) or []:
        user_key = str(user.get("login_key") or login_key(user.get("login", "")))
        if user_key != target_key:
            continue
        if new_role is not None:
            user["role"] = new_role
        if new_active is not None:
            user["active"] = bool(new_active)
        break

    if not active_admin_users(simulated):
        raise ValueError("Нельзя удалить, отключить или понизить последнего администратора.")


def update_user(
    login: str,
    *,
    role: str | None = None,
    active: bool | None = None,
    display_name: str | None = None,
    path: str | Path | None = None,
) -> dict:
    data = load_users(path)
    user = _find_user(data, login)
    if not user:
        raise ValueError("Пользователь не найден.")

    if role is not None:
        role = str(role)
        if role not in ALLOWED_ROLES:
            raise ValueError("Недопустимая роль пользователя.")

    if role is not None or active is not None:
        _ensure_not_last_admin_change(data, login, new_role=role, new_active=active)

    if role is not None:
        user["role"] = role
    if active is not None:
        user["active"] = bool(active)
    if display_name is not None:
        user["display_name"] = str(display_name or "").strip() or user.get("login", "")

    user["updated_at"] = _utc_now()
    save_users(data, path)
    return public_user(user)


def set_user_password(login: str, password: str, path: str | Path | None = None) -> dict:
    data = load_users(path)
    user = _find_user(data, login)
    if not user:
        raise ValueError("Пользователь не найден.")
    _validate_login_password(user.get("login", login), password)

    salt = _new_salt()
    user["password_algorithm"] = PASSWORD_HASH_ALGORITHM
    user["password_iterations"] = PASSWORD_HASH_ITERATIONS
    user["password_salt"] = salt
    user["password_hash"] = _hash_password(password, salt)
    user["updated_at"] = _utc_now()

    save_users(data, path)
    return public_user(user)
