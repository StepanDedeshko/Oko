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
            snapshot_item = ZabbixProblemSnapshotItem(key=build_problem_key(item), **{k: v for k, v in dict(item or {}).items() if k in {"trigger_name", "host", "severity", "started_at", "status", "info", "duration", "acknowledged", "ack_text", "ack_url", "actions_text", "tags", "severity_class", "severity_level", "event_id", "problem_url", "graph_urls", "trigger_kind", "processed"}})
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




JS_SMOKE_TEST_SCRIPT = r"""
(function() {
  return JSON.stringify({smoke: "ok", href: String(window.location.href || "")});
})();
"""


JS_HEALTH_CHECK_SCRIPT = r"""
(function() {
  var result = {
    href: String(window.location.href || ""),
    title: String(document.title || ""),
    readyState: String(document.readyState || ""),
    bodyExists: !!document.body,
    bodyTextLength: document.body && document.body.innerText ? document.body.innerText.length : -1,
    htmlLength: document.documentElement && document.documentElement.outerHTML ? document.documentElement.outerHTML.length : -1
  };
  return JSON.stringify(result);
})();
"""

DOM_PARSER_SCRIPT_PLACEHOLDER = r"""
(function() {
  function text(el) { return (el && (el.innerText || el.textContent) || '').replace(/\s+/g, ' ').trim(); }
  function abs(href) { try { return new URL(href, document.location.href).href; } catch(e) { return href || ''; } }
  function safeUrl(value) {
    try {
      var u = new URL(value || document.location.href, document.location.href);
      var q = [];
      u.searchParams.forEach(function(v, k) { q.push(k + '=***'); });
      return u.pathname + (q.length ? '?' + q.join('&') : '');
    } catch(e) { return ''; }
  }
  function attrs(el) {
    var out = {};
    if (!el || !el.attributes) return out;
    Array.from(el.attributes).forEach(function(a) {
      if (a.name === 'id' || a.name === 'class' || a.name === 'role' || a.name.indexOf('data-') === 0) out[a.name] = String(a.value || '').slice(0, 160);
    });
    return out;
  }
  function selector(row) {
    var parent = row.parentElement;
    var table = row.closest('table');
    return (table ? 'table' + (table.id ? '#' + table.id : '') + (table.className ? '.' + String(table.className).trim().replace(/\s+/g, '.') : '') + ' > ' : '') + (parent ? parent.tagName.toLowerCase() + ' > ' : '') + row.tagName.toLowerCase();
  }
  function normalizeHeader(value) { return String(value || '').replace(/\s+/g, ' ').trim().toLowerCase(); }
  var headerAliases = {
    started_at: ['время', 'time'],
    severity: ['важность', 'severity'],
    info: ['инфо', 'info'],
    host: ['узел сети', 'host', 'hosts'],
    trigger_name: ['проблема', 'problem'],
    duration: ['длительность', 'duration'],
    acknowledged: ['подтверждено', 'acknowledged'],
    actions_text: ['действия', 'actions'],
    tags: ['теги', 'tags']
  };
  function buildHeaderMap(table) {
    var map = {};
    var headerRows = Array.from(table.querySelectorAll('thead tr'));
    if (!headerRows.length) headerRows = Array.from(table.querySelectorAll('tr')).slice(0, 2);
    headerRows.forEach(function(row) {
      Array.from(row.querySelectorAll('th')).forEach(function(th, index) {
        var header = normalizeHeader(text(th));
        Object.keys(headerAliases).forEach(function(field) {
          if (headerAliases[field].indexOf(header) !== -1) map[field] = index;
        });
      });
    });
    return map;
  }
  function severityLevel(value, className) {
    var joined = (String(value || '') + ' ' + String(className || '')).toLowerCase();
    if (/disaster|чрезвычай/.test(joined)) return 'disaster';
    if (/high|высок/.test(joined)) return 'high';
    if (/average|средн/.test(joined)) return 'average';
    if (/warning|предупр/.test(joined)) return 'warning';
    if (/info|information|информ/.test(joined)) return 'info';
    if (/na-bg|not classified|не классиф/.test(joined)) return 'not_classified';
    return '';
  }
  function eventIdFromRow(row) {
    var direct = row.getAttribute('data-eventid') || row.getAttribute('data-event-id') || row.getAttribute('data-problemid') || row.getAttribute('data-problem-id') || '';
    if (direct) return direct;
    var eventInput = row.querySelector('input[name="eventids[0]"], input[name^="eventids"], input[id^="eventids_"]');
    if (eventInput && eventInput.value) return eventInput.value;
    var href = (Array.from(row.querySelectorAll('a[href]')).map(function(a) { return a.href || ''; }).find(function(h) { return /eventid=\d+|eventids%5B0%5D=\d+|eventids\[0\]=\d+/i.test(h); }) || '');
    var match = href.match(/(?:eventid|eventids%5B0%5D|eventids\[0\])=(\d+)/i);
    return match ? match[1] : '';
  }
  function cellAt(cells, map, field, fallbackIndex) {
    var index = Object.prototype.hasOwnProperty.call(map, field) ? map[field] : fallbackIndex;
    return index >= 0 && index < cells.length ? cells[index] : null;
  }
  var tables = Array.from(document.querySelectorAll('table'));
  var rows = Array.from(document.querySelectorAll('tr'));
  var loginDetected = !!document.querySelector('input[type=password], input[name*=password i], form[action*=login i]') || /login|sign[ -]?in|вход/i.test(document.title || '');
  var items = [];
  var candidates = [];
  var headerMap = {};
  var problemTable = tables.find(function(table) {
    var map = buildHeaderMap(table);
    if (Object.prototype.hasOwnProperty.call(map, 'trigger_name') && Object.prototype.hasOwnProperty.call(map, 'host')) {
      headerMap = map;
      return true;
    }
    return false;
  }) || tables[0] || null;
  if (problemTable && !Object.keys(headerMap).length) headerMap = buildHeaderMap(problemTable);
  var dataRows = problemTable ? Array.from(problemTable.querySelectorAll('tbody tr')).filter(function(row) { return row.querySelectorAll('td').length; }) : rows;
  dataRows.forEach(function(row) {
    var rowText = text(row);
    var cellsRaw = Array.from(row.querySelectorAll('td,th'));
    var cells = cellsRaw.map(text);
    if (!rowText || cellsRaw.length < 2) return;
    var links = Array.from(row.querySelectorAll('a[href]'));
    var hasHeaderMap = Object.keys(headerMap).length > 0;
    var looksLikeProblem = hasHeaderMap || links.some(function(a) { return /event|problem|tr_events|trigger|zabbix\.php/i.test(a.href || ''); }) || row.hasAttribute('data-eventid') || row.hasAttribute('data-problemid') || /problem|event|trigger/i.test(row.className || '');
    if (!looksLikeProblem && cellsRaw.length < 4) return;
    candidates.push(row);
    var severityCell = cellAt(cellsRaw, headerMap, 'severity', 1);
    var ackCell = cellAt(cellsRaw, headerMap, 'acknowledged', 6);
    var actionsCell = cellAt(cellsRaw, headerMap, 'actions_text', 7);
    var problemCell = cellAt(cellsRaw, headerMap, 'trigger_name', cellsRaw.length - 1);
    var problemLink = (problemCell ? Array.from(problemCell.querySelectorAll('a[href]')) : links).find(function(a) { return /event|problem|tr_events|trigger|zabbix\.php/i.test(a.href || ''); }) || links.find(function(a) { return /event|problem|tr_events|trigger|zabbix\.php/i.test(a.href || ''); });
    var graphLink = links.find(function(a) { return /chart|graph|history|graphs/i.test(a.href || ''); });
    var ackLink = (ackCell ? Array.from(ackCell.querySelectorAll('a[href]')) : links).find(function(a) { return /acknowledge|eventid|problem/i.test(a.href || '') || /подтверд|ack/i.test(text(a)); });
    var eventId = eventIdFromRow(row);
    var severityText = text(severityCell) || cells[1] || '';
    var severityClass = severityCell ? String(severityCell.className || '') : '';
    var ackText = text(ackCell);
    var acknowledged = /да|yes|acknowledged|подтвержден/i.test(ackText) && !/нет|no|unack/i.test(ackText);
    items.push({
      id: eventId || row.id || '',
      event_id: eventId,
      started_at: text(cellAt(cellsRaw, headerMap, 'started_at', 0)) || cells[0] || '',
      severity: severityText,
      severity_class: severityClass,
      severity_level: severityLevel(severityText, severityClass),
      info: text(cellAt(cellsRaw, headerMap, 'info', 2)),
      host: text(cellAt(cellsRaw, headerMap, 'host', 3)) || cells[1] || '',
      trigger_name: text(problemCell) || rowText,
      duration: text(cellAt(cellsRaw, headerMap, 'duration', 5)),
      acknowledged: acknowledged,
      ack_text: ackText,
      ack_url: ackLink ? abs(ackLink.getAttribute('href')) : (problemLink ? abs(problemLink.getAttribute('href')) : ''),
      actions_text: text(actionsCell),
      tags: text(cellAt(cellsRaw, headerMap, 'tags', 8)),
      status: 'active',
      problem_url: problemLink ? abs(problemLink.getAttribute('href')) : '',
      graph_urls: graphLink ? [abs(graphLink.getAttribute('href'))] : []
    });
  });
  var sampleRows = candidates.slice(0, 5).map(function(row) {
    var cells = Array.from(row.querySelectorAll('td,th')).slice(0, 12);
    return {selector: selector(row), tag: row.tagName.toLowerCase(), attributes: attrs(row), cell_count: row.querySelectorAll('td,th').length, links_count: row.querySelectorAll('a[href]').length, cells: cells.map(function(cell, i) { return {cell_index: i, tag: cell.tagName.toLowerCase(), attributes: attrs(cell), text_length: text(cell).length, links_count: cell.querySelectorAll('a[href]').length}; })};
  });
  var reason = '';
  if (items.length === 0) {
    if (loginDetected) reason = 'Похоже, открыта страница логина.';
    else if (tables.length === 0 || rows.length === 0) reason = 'Таблица Zabbix Problems ещё не загружена или отсутствует.';
    else if (candidates.length === 0) reason = 'DOM Zabbix не распознан: строки таблиц не похожи на проблемы.';
    else reason = 'Кандидаты найдены, но не удалось извлечь проблемы из DOM.';
  }
  var safeDebug = {title: String(document.title || '').slice(0, 160), url_path: safeUrl(document.location.href), login_detected: loginDetected, table_count: tables.length, tr_count: rows.length, header_map: headerMap, candidate_count: candidates.length, problem_count: items.length, zero_reason: reason, sample_rows: sampleRows};
  return JSON.stringify({ok: true, url: document.location.href, title: document.title || '', login_detected: loginDetected, table_count: tables.length, tr_count: rows.length, header_map: headerMap, candidate_count: candidates.length, problem_count: items.length, items: items, safe_debug: safeDebug, zero_reason: reason});
})();
"""
