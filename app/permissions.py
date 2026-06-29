"""Section permissions, user config export and import compatibility helpers."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime

SECTION_PROFILE = "section.profile"
SECTION_DUTY_SETTINGS = "section.duty_settings"
SECTION_SERVICE_CHECKS_USER = "section.service_checks_user"
SECTION_NOTES = "section.notes"
SECTION_UPDATE = "section.update"
SECTION_THEME = "section.theme"
SECTION_CHANGELOG = "section.changelog"
SECTION_ADMIN = "section.admin"
SECTION_PRODUCTS_PAGES = "section.products_pages"
SECTION_DEVELOPER = "section.developer"
SECTION_TEMPLATES = "section.templates"
SECTION_SERVICE_CHECKS_TECHNICAL = "section.service_checks_technical"

ALL_SECTION_PERMISSIONS = [
    SECTION_PROFILE, SECTION_DUTY_SETTINGS, SECTION_SERVICE_CHECKS_USER, SECTION_NOTES,
    SECTION_UPDATE, SECTION_THEME, SECTION_CHANGELOG, SECTION_ADMIN, SECTION_PRODUCTS_PAGES,
    SECTION_DEVELOPER, SECTION_TEMPLATES, SECTION_SERVICE_CHECKS_TECHNICAL,
]
SAFE_AGENT_SECTION_PERMISSIONS = [
    SECTION_PROFILE, SECTION_DUTY_SETTINGS, SECTION_SERVICE_CHECKS_USER, SECTION_NOTES,
    SECTION_UPDATE, SECTION_THEME, SECTION_CHANGELOG,
]
SECTION_NAMES = {
    SECTION_PROFILE: "Профиль",
    SECTION_DUTY_SETTINGS: "Настройки дежурки",
    SECTION_SERVICE_CHECKS_USER: "Проверка сервисов",
    SECTION_NOTES: "Заметки",
    SECTION_UPDATE: "Обновление",
    SECTION_THEME: "Тема",
    SECTION_CHANGELOG: "Что нового",
    SECTION_ADMIN: "Администрирование",
    SECTION_PRODUCTS_PAGES: "Продукты и страницы",
    SECTION_DEVELOPER: "Режим разработчика",
    SECTION_TEMPLATES: "Шаблоны",
    SECTION_SERVICE_CHECKS_TECHNICAL: "Технические настройки проверок",
}
SECTION_BY_NAME = {v: k for k, v in SECTION_NAMES.items()}
ADMIN_ROLES = {"owner", "admin"}
AGENT_ROLES = {"agent", "user"}

LEGACY_DUTY_URL_KEYS = {
    "live_zabbix_url": [("live_zabbix_monitor", "problems_url"), ("live_zabbix_monitor", "url"), ("duty_mode", "live_zabbix_url")],
    "redmine_create_url": [("duty_mode", "redmine_create_url"), ("live_zabbix_monitor", "redmine_create_url")],
    "otrs_create_url": [("duty_mode", "otrs_create_url"), ("duty_mode", "otrs", "create_url")],
    "mm_otrs_create_url": [("duty_mode", "mm_otrs_create_url"), ("live_zabbix_monitor", "mm_otrs_create_url")],
}


def default_permissions_for_role(role: str) -> list[str]:
    if str(role or "").lower() in ADMIN_ROLES:
        return list(ALL_SECTION_PERMISSIONS)
    if str(role or "").lower() in {"custom"}:
        return []
    return list(SAFE_AGENT_SECTION_PERMISSIONS)


def normalize_user_permissions(user: dict | None) -> dict:
    user = deepcopy(user or {})
    role = str(user.get("role") or "agent").lower()
    if role == "user":
        role = "agent"
    user["role"] = role
    permissions = user.get("section_permissions")
    if permissions is None:
        permissions = user.get("permissions")
    if not permissions:
        permissions = default_permissions_for_role(role)
    if role in ADMIN_ROLES:
        permissions = ALL_SECTION_PERMISSIONS
    user["section_permissions"] = sorted({p for p in permissions if p in ALL_SECTION_PERMISSIONS})
    groups = user.get("service_group_ids")
    if groups is None:
        groups = user.get("service_groups", [])
    user["service_group_ids"] = sorted({str(g) for g in (groups or []) if str(g)})
    user.setdefault("active", True)
    return user


def has_permission(user: dict | None, permission: str) -> bool:
    user = normalize_user_permissions(user)
    return permission in set(user.get("section_permissions") or [])


def can_open_section(user: dict | None, section_name: str) -> bool:
    permission = SECTION_BY_NAME.get(section_name)
    return True if permission is None else has_permission(user, permission)


def visible_sections_for_user(user: dict | None, section_names: list[str]) -> list[str]:
    return [name for name in section_names if can_open_section(user, name)]


def _get_nested(config, path):
    cur = config
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return ""
        cur = cur.get(key)
    return str(cur or "")


def get_duty_link(config: dict, key: str) -> str:
    duty_links = (config or {}).get("duty_links", {}) if isinstance(config, dict) else {}
    if isinstance(duty_links, dict) and duty_links.get(key):
        return str(duty_links.get(key) or "")
    for path in LEGACY_DUTY_URL_KEYS.get(key, []):
        value = _get_nested(config or {}, path)
        if value:
            return value
    return ""


def ensure_duty_links(config: dict) -> dict:
    links = config.setdefault("duty_links", {})
    for key in LEGACY_DUTY_URL_KEYS:
        links.setdefault(key, get_duty_link(config, key))
    return links


def set_duty_link(config: dict, key: str, value: str):
    ensure_duty_links(config)[key] = str(value or "").strip()



def visible_service_groups_for_user(config: dict, user: dict | None) -> list[dict]:
    """Return service credential groups visible in the user-facing service UI.

    Admin/owner users with an empty service_group_ids list see every group.
    Agents with an empty list intentionally see no groups.
    """
    normalized = normalize_user_permissions(user)
    groups = deepcopy((((config or {}).get("service_checks") or {}).get("credential_groups") or []))
    allowed = set(normalized.get("service_group_ids") or [])
    if normalized.get("role") in ADMIN_ROLES and not allowed:
        return groups
    if not allowed:
        return []
    return [group for group in groups if str(group.get("id", "")) in allowed]


def service_check_items_for_group(config: dict, group_id: str) -> list[dict]:
    checks = (config or {}).get("service_checks", {}) or {}
    group_id = str(group_id or "")
    service_ids = set()
    for group in checks.get("credential_groups", []) or []:
        if str(group.get("id", "")) == group_id:
            service_ids = {str(item) for item in group.get("service_ids", []) or [] if str(item)}
            break
    result = []
    for item in checks.get("items", []) or []:
        if str(item.get("credential_group_id", "")) == group_id or str(item.get("id", "")) in service_ids:
            result.append(item)
    return result

def service_checks_for_user(config: dict, user: dict | None) -> dict:
    from app.config import sanitize_export_data
    checks = deepcopy((config or {}).get("service_checks", {}) or {})
    visible_groups = visible_service_groups_for_user(config or {}, user)
    allowed = {str(group.get("id", "")) for group in visible_groups if str(group.get("id", ""))}
    checks["credential_groups"] = [g for g in checks.get("credential_groups", []) if str(g.get("id", "")) in allowed]
    checks["items"] = [i for i in checks.get("items", []) if str(i.get("credential_group_id", "")) in allowed]
    return sanitize_export_data({"service_checks": checks}).get("service_checks", {})


def build_user_settings_export(config: dict, user: dict) -> dict:
    from app.config import sanitize_export_data
    user = normalize_user_permissions(user)
    payload = {
        "app": "Око",
        "format": "oko_user_settings_export",
        "format_version": 1,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": {k: deepcopy(user.get(k)) for k in ("login", "display_name", "role", "active", "section_permissions", "service_group_ids")},
        "settings": {
            "settings": deepcopy((config or {}).get("settings", {})),
            "time_ranges": deepcopy((config or {}).get("time_ranges", [])),
            "products": deepcopy((config or {}).get("products", [])),
            "duty_mode": deepcopy((config or {}).get("duty_mode", {})),
            "duty_links": deepcopy(ensure_duty_links(config or {})),
            "service_checks": service_checks_for_user(config or {}, user),
            "templates": deepcopy((config or {}).get("templates", {})),
            "live_zabbix_monitor": deepcopy((config or {}).get("live_zabbix_monitor", {})),
        },
    }
    return sanitize_export_data(payload)


def import_user_settings_payload(current_config: dict, payload: dict, keep_passwords: bool = True) -> dict:
    if payload.get("format") != "oko_user_settings_export":
        raise ValueError("unsupported user settings export format")
    result = deepcopy(current_config or {})
    for key, value in (payload.get("settings") or {}).items():
        result[key] = deepcopy(value)
    user = normalize_user_permissions(payload.get("user") or {})
    result["_current_user"] = user
    ensure_duty_links(result)
    return result
