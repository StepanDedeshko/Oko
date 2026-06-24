"""Live Zabbix Problems monitor foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json

from app.trigger_model import ZabbixProblemSnapshotItem, build_problem_key

LIVE_MONITOR_CONFIG_KEY = "live_zabbix_monitor"


def default_live_monitor_config() -> dict:
    return {"enabled": False, "zabbix_id": "", "problems_url": "", "poll_interval_seconds": 10, "history_path": "data/live_zabbix_history.jsonl"}


def ensure_live_monitor_defaults(config: dict) -> dict:
    settings = config.setdefault(LIVE_MONITOR_CONFIG_KEY, {})
    defaults = default_live_monitor_config()
    for key, value in defaults.items():
        settings.setdefault(key, value)
    try:
        settings["poll_interval_seconds"] = max(5, min(15, int(settings.get("poll_interval_seconds", 10))))
    except (TypeError, ValueError):
        settings["poll_interval_seconds"] = 10
    return settings


@dataclass
class SnapshotDiff:
    new: list[ZabbixProblemSnapshotItem] = field(default_factory=list)
    active: list[ZabbixProblemSnapshotItem] = field(default_factory=list)
    resolved: list[ZabbixProblemSnapshotItem] = field(default_factory=list)
    processed: list[ZabbixProblemSnapshotItem] = field(default_factory=list)


def normalize_snapshot(items) -> dict[str, ZabbixProblemSnapshotItem]:
    result = {}
    for item in items or []:
        if isinstance(item, ZabbixProblemSnapshotItem):
            snapshot_item = item
        else:
            snapshot_item = ZabbixProblemSnapshotItem(key=build_problem_key(item), **{k: v for k, v in dict(item or {}).items() if k in {"trigger_name", "host", "severity", "started_at", "status", "problem_url", "graph_urls", "trigger_kind", "processed"}})
        if snapshot_item.key:
            result[snapshot_item.key] = snapshot_item
    return result


def diff_snapshots(previous, current, processed_keys: set[str] | None = None) -> SnapshotDiff:
    processed_keys = processed_keys or set()
    prev = normalize_snapshot(previous)
    cur = normalize_snapshot(current)
    diff = SnapshotDiff()
    for key, item in cur.items():
        item.processed = item.processed or key in processed_keys
        if item.processed:
            item.status = "processed"
            diff.processed.append(item)
        elif key in prev:
            item.status = "active"
            diff.active.append(item)
        else:
            item.status = "new"
            diff.new.append(item)
    for key, item in prev.items():
        if key not in cur:
            item.status = "resolved"
            diff.resolved.append(item)
    return diff



DOM_PARSER_SCRIPT_PLACEHOLDER = r"""
(function() {
  function text(el) { return (el && (el.innerText || el.textContent) || '').replace(/\s+/g, ' ').trim(); }
  function abs(href) { try { return new URL(href, document.location.href).href; } catch(e) { return href || ''; } }
  var rows = Array.from(document.querySelectorAll('tr'));
  var items = [];
  rows.forEach(function(row) {
    var rowText = text(row);
    if (!rowText || rowText.length < 3) return;
    var cells = Array.from(row.querySelectorAll('td,th')).map(text).filter(Boolean);
    if (cells.length < 2) return;
    var problemLink = Array.from(row.querySelectorAll('a[href]')).find(function(a) { return /event|problem|tr_events|trigger|zabbix\.php/i.test(a.href || ''); });
    var graphLink = Array.from(row.querySelectorAll('a[href]')).find(function(a) { return /chart|graph|history|graphs/i.test(a.href || ''); });
    var key = row.getAttribute('data-eventid') || row.getAttribute('data-event-id') || row.getAttribute('data-problemid') || row.getAttribute('data-problem-id') || row.id || '';
    var guessTime = cells[0] || '';
    var guessSeverity = cells.find(function(c) { return /disaster|high|average|warning|information|not classified|чрезвычай|высок|средн|предупр|информ|не классиф/i.test(c); }) || '';
    var guessHost = cells.length > 2 ? cells[1] : '';
    var guessName = cells[cells.length - 1] || rowText;
    items.push({id: key, event_id: key, started_at: guessTime, severity: guessSeverity, host: guessHost, trigger_name: guessName, status: 'active', problem_url: problemLink ? abs(problemLink.getAttribute('href')) : '', graph_urls: graphLink ? [abs(graphLink.getAttribute('href'))] : []});
  });
  return items;
})();
"""
