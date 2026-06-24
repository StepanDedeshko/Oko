"""Shared Zabbix trigger model for Redmine and Live Zabbix Monitor."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Iterable

from app.time_range import apply_time_range_to_url

TRIGGER_CATALOG_CONFIG_KEY = "zabbix_trigger_definitions"
SPECIAL_REDMINE_COMPAT_CONFIG_KEY = "special_redmine_triggers"
SPECIAL_TRIGGER_KIND = "special"
STANDARD_TRIGGER_KIND = "standard"

DEFAULT_SPECIAL_TRIGGER_DEFINITIONS = [
    {
        "id": f"special_trigger_{index}",
        "enabled": False,
        "kind": SPECIAL_TRIGGER_KIND,
        "display_name": f"Специальный триггер {index}",
        "match": {"trigger_ids": [], "trigger_names": [], "hosts": []},
        "graph_urls": [],
        "graph_ids": [],
    }
    for index in range(1, 6)
]


@dataclass
class TriggerDefinition:
    id: str
    enabled: bool = True
    kind: str = STANDARD_TRIGGER_KIND
    display_name: str = ""
    match: dict = field(default_factory=dict)
    graph_urls: list[str] = field(default_factory=list)
    graph_ids: list[str] = field(default_factory=list)


@dataclass
class ZabbixProblemSnapshotItem:
    key: str
    trigger_name: str = ""
    host: str = ""
    severity: str = ""
    started_at: str = ""
    status: str = "active"
    info: str = ""
    duration: str = ""
    acknowledged: bool = False
    ack_text: str = ""
    ack_url: str = ""
    actions_text: str = ""
    tags: str = ""
    severity_class: str = ""
    severity_level: str = ""
    event_id: str = ""
    problem_url: str = ""
    graph_urls: list[str] = field(default_factory=list)
    trigger_kind: str = STANDARD_TRIGGER_KIND
    processed: bool = False

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "trigger_name": self.trigger_name,
            "host": self.host,
            "severity": self.severity,
            "started_at": self.started_at,
            "status": self.status,
            "info": self.info,
            "duration": self.duration,
            "acknowledged": self.acknowledged,
            "ack_text": self.ack_text,
            "ack_url": self.ack_url,
            "actions_text": self.actions_text,
            "tags": self.tags,
            "severity_class": self.severity_class,
            "severity_level": self.severity_level,
            "event_id": self.event_id,
            "problem_url": self.problem_url,
            "graph_urls": list(self.graph_urls),
            "trigger_kind": self.trigger_kind,
            "processed": bool(self.processed),
        }


def normalize_trigger_text(value) -> str:
    return " ".join(str(value or "").casefold().split())


def build_problem_key(problem: dict | ZabbixProblemSnapshotItem) -> str:
    if isinstance(problem, ZabbixProblemSnapshotItem):
        problem = problem.to_dict()
    for field_name in ("event_id", "problem_id", "id", "key"):
        value = str((problem or {}).get(field_name) or "").strip()
        if value:
            return value
    host = normalize_trigger_text((problem or {}).get("host"))
    name = normalize_trigger_text((problem or {}).get("trigger_name") or (problem or {}).get("name") or (problem or {}).get("display_name"))
    started_at = normalize_trigger_text((problem or {}).get("started_at") or (problem or {}).get("time"))
    severity = normalize_trigger_text((problem or {}).get("severity"))
    return "|".join(part for part in [host, name, started_at, severity] if part)


def default_trigger_catalog_config() -> dict:
    return {"version": 1, "items": deepcopy(DEFAULT_SPECIAL_TRIGGER_DEFINITIONS)}


def _legacy_redmine_items(config: dict) -> list[dict]:
    legacy = (config or {}).get(SPECIAL_REDMINE_COMPAT_CONFIG_KEY, {})
    items = legacy.get("items", []) if isinstance(legacy, dict) else []
    converted = []
    for index, item in enumerate(items or [], start=1):
        converted.append({
            "id": item.get("id") or f"special_trigger_{index}",
            "enabled": bool(item.get("enabled", False)),
            "kind": SPECIAL_TRIGGER_KIND,
            "display_name": item.get("display_name", f"Специальный триггер {index}"),
            "match": deepcopy(item.get("match") or {"trigger_ids": [], "trigger_names": [], "hosts": []}),
            "graph_urls": deepcopy(item.get("graph_urls") or []),
            "graph_ids": deepcopy(item.get("graph_ids") or []),
        })
    return converted


def ensure_trigger_catalog_defaults(config: dict) -> dict:
    settings = config.setdefault(TRIGGER_CATALOG_CONFIG_KEY, {})
    settings.setdefault("version", 1)
    items = settings.setdefault("items", [])
    if not items:
        legacy = _legacy_redmine_items(config)
        items.extend(legacy or deepcopy(DEFAULT_SPECIAL_TRIGGER_DEFINITIONS))
    for index, item in enumerate(items, start=1):
        item.setdefault("id", f"trigger_definition_{index}")
        item.setdefault("enabled", False)
        item.setdefault("kind", SPECIAL_TRIGGER_KIND if index <= 5 else STANDARD_TRIGGER_KIND)
        item.setdefault("display_name", "")
        item.setdefault("match", {})
        item["match"].setdefault("trigger_ids", [])
        item["match"].setdefault("trigger_names", [])
        item["match"].setdefault("hosts", [])
        item.setdefault("graph_urls", [])
        item.setdefault("graph_ids", [])
    # keep the previous Redmine config section available for older config exports/UI
    legacy = config.setdefault(SPECIAL_REDMINE_COMPAT_CONFIG_KEY, {"version": 1, "items": []})
    legacy.setdefault("version", 1)
    legacy.setdefault("items", [])
    return settings


def iter_trigger_definitions(config: dict) -> Iterable[dict]:
    return ensure_trigger_catalog_defaults(config).get("items", []) or []


def find_trigger_definition(config: dict, problem: dict | ZabbixProblemSnapshotItem) -> dict | None:
    if isinstance(problem, ZabbixProblemSnapshotItem):
        problem = problem.to_dict()
    trigger_id = normalize_trigger_text((problem or {}).get("trigger_id") or (problem or {}).get("id") or (problem or {}).get("key"))
    trigger_name = normalize_trigger_text((problem or {}).get("trigger_name") or (problem or {}).get("display_name") or (problem or {}).get("name"))
    host = normalize_trigger_text((problem or {}).get("host"))
    for item in iter_trigger_definitions(config):
        if not item.get("enabled", False):
            continue
        match = item.get("match") or {}
        ids = {normalize_trigger_text(value) for value in match.get("trigger_ids", []) if normalize_trigger_text(value)}
        names = {normalize_trigger_text(value) for value in match.get("trigger_names", []) if normalize_trigger_text(value)}
        hosts = {normalize_trigger_text(value) for value in match.get("hosts", []) if normalize_trigger_text(value)}
        id_ok = bool(trigger_id and trigger_id in ids)
        name_ok = bool(trigger_name and trigger_name in names)
        host_ok = not hosts or bool(host and host in hosts)
        if (id_ok or name_ok) and host_ok:
            return item
    return None


def trigger_kind_for_problem(config: dict, problem: dict | ZabbixProblemSnapshotItem) -> str:
    definition = find_trigger_definition(config, problem)
    return definition.get("kind", SPECIAL_TRIGGER_KIND) if definition else STANDARD_TRIGGER_KIND


def _all_config_graphs(config):
    for product in (config or {}).get("products", []) or []:
        product_name = product.get("name", "")
        for dashboard in product.get("dashboards", []) or []:
            dashboard_name = dashboard.get("name", "")
            if dashboard.get("type") != "graphs_grid":
                continue
            for index, graph in enumerate(dashboard.get("graphs", []) or []):
                graph_id = graph.get("id") or f"{product_name}::{dashboard_name}::{index}::{graph.get('title', '')}"
                yield str(graph_id), graph


def graph_url_from_config(graph, time_range="1h") -> str:
    url = (graph or {}).get("open_url") or (graph or {}).get("zabbix_url") or (graph or {}).get("external_url") or (graph or {}).get("url") or ""
    if url and (graph or {}).get("use_time_range", True):
        return apply_time_range_to_url(url, time_range)
    return str(url or "")


def graph_urls_for_problem(config: dict, problem: dict | ZabbixProblemSnapshotItem, time_range="1h") -> list[str]:
    definition = find_trigger_definition(config, problem)
    if not definition or definition.get("kind") != SPECIAL_TRIGGER_KIND:
        return []
    urls = [str(url or "").strip() for url in definition.get("graph_urls", []) if str(url or "").strip()]
    graph_ids = {str(value or "").strip() for value in definition.get("graph_ids", []) if str(value or "").strip()}
    if graph_ids:
        for graph_id, graph in _all_config_graphs(config):
            if graph_id in graph_ids:
                url = graph_url_from_config(graph, time_range=time_range)
                if url:
                    urls.append(url)
    result = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def format_graph_links(urls, empty_text="Не указаны") -> str:
    links = [str(url or "").strip() for url in urls or [] if str(url or "").strip()]
    if not links:
        return empty_text
    return "\n".join(f"{index}. {url}" for index, url in enumerate(links, start=1))


def enrich_problem(config: dict, problem: dict, time_range="1h", processed_keys: set[str] | None = None) -> ZabbixProblemSnapshotItem:
    key = build_problem_key(problem)
    graph_urls = graph_urls_for_problem(config, {**problem, "key": key}, time_range=time_range)
    kind = trigger_kind_for_problem(config, {**problem, "key": key})
    return ZabbixProblemSnapshotItem(
        key=key,
        trigger_name=str(problem.get("trigger_name") or problem.get("name") or problem.get("display_name") or ""),
        host=str(problem.get("host") or ""),
        severity=str(problem.get("severity") or ""),
        started_at=str(problem.get("started_at") or problem.get("time") or ""),
        status=str(problem.get("status") or "active"),
        info=str(problem.get("info") or ""),
        duration=str(problem.get("duration") or ""),
        acknowledged=bool(problem.get("acknowledged", False)),
        ack_text=str(problem.get("ack_text") or ""),
        ack_url=str(problem.get("ack_url") or ""),
        actions_text=str(problem.get("actions_text") or problem.get("actions") or ""),
        tags=str(problem.get("tags") or ""),
        severity_class=str(problem.get("severity_class") or ""),
        severity_level=str(problem.get("severity_level") or ""),
        event_id=str(problem.get("event_id") or problem.get("eventids_0") or problem.get("id") or ""),
        problem_url=str(problem.get("problem_url") or problem.get("url") or ""),
        graph_urls=graph_urls,
        trigger_kind=kind,
        processed=key in (processed_keys or set()),
    )


def append_history_event(path: str | Path, event_type: str, problem: ZabbixProblemSnapshotItem | dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = problem.to_dict() if isinstance(problem, ZabbixProblemSnapshotItem) else dict(problem or {})
    record = {"ts": datetime.now(timezone.utc).isoformat(), "event": event_type, "problem": payload}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
