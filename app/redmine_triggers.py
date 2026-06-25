"""Compatibility wrappers around the shared Zabbix trigger model."""

from copy import deepcopy

from app.trigger_model import (
    SPECIAL_REDMINE_COMPAT_CONFIG_KEY as SPECIAL_REDMINE_TRIGGERS_CONFIG_KEY,
    SPECIAL_TRIGGER_KIND as SPECIAL_REDMINE_TEMPLATE_KIND,
    STANDARD_TRIGGER_KIND as STANDARD_REDMINE_TEMPLATE_KIND,
    DEFAULT_SPECIAL_TRIGGER_DEFINITIONS,
    ensure_trigger_catalog_defaults,
    find_trigger_definition,
    trigger_kind_for_problem,
    graph_url_from_config,
    graph_urls_for_problem,
    format_graph_links,
)

DEFAULT_SPECIAL_REDMINE_TRIGGERS = [
    {"id": item["id"], "enabled": item["enabled"], "match": deepcopy(item["match"]), "graph_urls": [], "graph_ids": []}
    for item in DEFAULT_SPECIAL_TRIGGER_DEFINITIONS
]


def default_special_redmine_triggers_config():
    return {"version": 1, "items": deepcopy(DEFAULT_SPECIAL_REDMINE_TRIGGERS)}


def ensure_special_redmine_triggers_defaults(config):
    shared = ensure_trigger_catalog_defaults(config)
    legacy = config.setdefault(SPECIAL_REDMINE_TRIGGERS_CONFIG_KEY, {})
    legacy.setdefault("version", 1)
    legacy_items = legacy.setdefault("items", [])
    if not legacy_items:
        legacy_items.extend(deepcopy(DEFAULT_SPECIAL_REDMINE_TRIGGERS))
    for index, item in enumerate(legacy_items, start=1):
        item.setdefault("id", f"special_redmine_trigger_{index}")
        item.setdefault("enabled", False)
        item.setdefault("match", {})
        item["match"].setdefault("trigger_ids", [])
        item["match"].setdefault("trigger_names", [])
        item["match"].setdefault("hosts", [])
        item.setdefault("graph_urls", [])
        item.setdefault("graph_ids", [])
    # If a caller still edits special_redmine_triggers directly, mirror enabled
    # entries into the shared catalog so Live Monitor and Redmine classify the same way.
    shared_items = shared.setdefault("items", [])
    existing_ids = {item.get("id") for item in shared_items}
    for item in legacy_items:
        if item.get("id") not in existing_ids:
            shared_items.append({
                "id": item.get("id"),
                "enabled": item.get("enabled", False),
                "kind": SPECIAL_REDMINE_TEMPLATE_KIND,
                "display_name": item.get("display_name", ""),
                "match": deepcopy(item.get("match") or {}),
                "graph_urls": deepcopy(item.get("graph_urls") or []),
                "graph_ids": deepcopy(item.get("graph_ids") or []),
            })
    return legacy


def find_special_redmine_trigger(config, trigger):
    ensure_special_redmine_triggers_defaults(config)
    definition = find_trigger_definition(config, trigger)
    if definition and definition.get("kind") == SPECIAL_REDMINE_TEMPLATE_KIND:
        return definition
    return None


def redmine_template_kind_for_trigger(config, trigger):
    return trigger_kind_for_problem(config, trigger)


def special_redmine_graph_urls(config, trigger, time_range="1h"):
    ensure_special_redmine_triggers_defaults(config)
    return graph_urls_for_problem(config, trigger, time_range=time_range)
