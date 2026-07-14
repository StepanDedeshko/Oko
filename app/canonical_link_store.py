from __future__ import annotations

from typing import Any

import app.canonical_links as _runtime

CANONICAL_LINKS_SCHEMA_VERSION = 1
CANONICAL_LINKS_SCHEMA_KEY = "_duty_links_schema_version"

LINK_KEYS = _runtime.LINK_KEYS


def _clean(value: Any) -> str:
    return str(value or "").strip()


def ensure_canonical_links(config: dict) -> dict:
    """Return canonical shared URLs without adding metadata inside duty_links.

    Older release-candidate builds briefly stored ``_schema_version`` inside
    ``duty_links``. It is accepted and migrated to a private top-level marker so
    the public duty_links mapping continues to contain URL keys only.
    """
    links = config.setdefault("duty_links", {})
    if not isinstance(links, dict):
        links = {}
        config["duty_links"] = links

    legacy_schema_version = links.pop("_schema_version", None)
    try:
        schema_version = int(
            config.get(CANONICAL_LINKS_SCHEMA_KEY, legacy_schema_version or 0) or 0
        )
    except (TypeError, ValueError):
        schema_version = 0

    first_canonical_migration = schema_version < CANONICAL_LINKS_SCHEMA_VERSION
    for key in LINK_KEYS:
        has_key = key in links
        current = _clean(links.get(key))
        if not has_key or (first_canonical_migration and not current):
            recovered = _runtime._legacy_value(config, key)
            if recovered:
                links[key] = recovered
            else:
                links.setdefault(key, "")
        else:
            links[key] = current

    config[CANONICAL_LINKS_SCHEMA_KEY] = CANONICAL_LINKS_SCHEMA_VERSION
    _runtime._sync_legacy_mirrors(config, links)
    return links


def get_canonical_link(config: dict, key: str) -> str:
    if key not in LINK_KEYS:
        return ""
    return _clean(ensure_canonical_links(config).get(key))


def set_canonical_link(config: dict, key: str, value: str) -> None:
    if key not in LINK_KEYS:
        return
    links = ensure_canonical_links(config)
    links[key] = _clean(value)
    _runtime._sync_legacy_mirrors(config, links)


def migrate_canonical_links(config: dict) -> bool:
    before = _runtime._json_snapshot(config)
    ensure_canonical_links(config)
    return before != _runtime._json_snapshot(config)


def install_canonical_link_settings(config: dict) -> bool:
    """Use the compatibility UI layer with the canonical metadata-free store."""
    _runtime.CANONICAL_LINKS_SCHEMA_VERSION = CANONICAL_LINKS_SCHEMA_VERSION
    _runtime.ensure_canonical_links = ensure_canonical_links
    _runtime.get_canonical_link = get_canonical_link
    _runtime.set_canonical_link = set_canonical_link
    _runtime.migrate_canonical_links = migrate_canonical_links
    return _runtime.install_canonical_link_settings(config)
