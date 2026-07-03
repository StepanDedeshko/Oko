"""Live Zabbix Problems monitor foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import json

from app.trigger_model import ZabbixProblemSnapshotItem, build_problem_key
from app.duty_zabbix import (
    annotate_zabbix_problems_with_trigger_catalog,
    load_zabbix_trigger_catalog,
    problem_matches_keywords,
    zabbix_problem_visible_by_trigger_filters,
)

LIVE_MONITOR_CONFIG_KEY = "live_zabbix_monitor"


LIVE_PERIOD_ALL = "all"
LIVE_PERIOD_TODAY = "today"
LIVE_PERIOD_7_DAYS = "7_days"
DEFAULT_REDMINE_LOGIN_URL = "https://redmine.stdpr.ru/login?back_url=https%3A%2F%2Fredmine.stdpr.ru%2Fprojects"


def zabbix_auth_required_from_html(html: str) -> dict:
    """Detect Zabbix expired-session pages without exposing page text or secrets."""
    text = str(html or "")
    lowered = text.casefold()
    required_markers = (
        "вы не выполнили вход",
        "для просмотра этой страницы вы должны войти в систему",
        "возможно сессия просрочена или был изменен пароль",
    )
    has_message = any(marker in lowered for marker in required_markers) and "msg-bad" in lowered
    login_url = ""
    marker = "data-login-url="
    marker_index = lowered.find(marker)
    if marker_index >= 0:
        value_start = marker_index + len(marker)
        quote = text[value_start:value_start + 1]
        if quote in {"'", '"'}:
            value_end = text.find(quote, value_start + 1)
            if value_end >= 0:
                login_url = text[value_start + 1:value_end]
    has_button = 'id="login"' in lowered or "id='login'" in lowered or 'name="login"' in lowered or "name='login'" in lowered
    return {"auth_required": bool(has_message and has_button), "login_url": login_url}


def is_unprocessed_problem(item) -> bool:
    ack_text = str(getattr(item, "ack_text", "") or (item.get("ack_text", "") if isinstance(item, dict) else "")).strip().casefold()
    if ack_text in {"нет", "no"}:
        return True
    if ack_text in {"да", "yes"}:
        return False
    acknowledged = getattr(item, "acknowledged", None) if not isinstance(item, dict) else item.get("acknowledged")
    return acknowledged is False


def _item_started_at(item):
    raw = getattr(item, "started_at", "") if not isinstance(item, dict) else item.get("started_at", "")
    raw = str(raw or "").strip()
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%y %H:%M:%S", "%d.%m.%y %H:%M"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        now = datetime.now()
        return now.replace(hour=parsed.hour, minute=parsed.minute, second=parsed.second, microsecond=0)
    return datetime.min


def apply_live_zabbix_table_filters(items, *, period=LIVE_PERIOD_ALL, unprocessed_only=False, now=None):
    """Apply combined Live Zabbix table filters and return newest problems first."""
    now = now or datetime.now()
    period = period or LIVE_PERIOD_ALL
    result = []
    for item in list(items or []):
        started = _item_started_at(item)
        if period == LIVE_PERIOD_TODAY and started < now.replace(hour=0, minute=0, second=0, microsecond=0):
            continue
        if period == LIVE_PERIOD_7_DAYS and started < now - timedelta(days=7):
            continue
        if unprocessed_only and not is_unprocessed_problem(item):
            continue
        result.append(item)
    return sorted(result, key=_item_started_at, reverse=True)


def default_live_monitor_config() -> dict:
    return {
        "enabled": False,
        "zabbix_id": "",
        "problems_url": "",
        "poll_interval_seconds": 60,
        "history_path": "data/live_zabbix_history.jsonl",
        "duty_filter_enabled": True,
        "redmine_login_url": DEFAULT_REDMINE_LOGIN_URL,
        "redmine_username": "",
        "redmine_password": "",
        "redmine_save_credentials": False,
        "auto_ack_after_task_enabled": False,
        "auto_ack_after_redmine_enabled": False,
        "auto_ack_after_mm_otrs_enabled": False,
    }


def redmine_credentials_should_be_saved(settings: dict) -> bool:
    return bool(
        settings.get("redmine_save_credentials", False)
        or settings.get("redmine_username")
        or settings.get("redmine_login")
        or settings.get("redmine_password")
    )


def apply_redmine_credentials_save(
    settings: dict,
    *,
    save_credentials: bool,
    username: str,
    password: str,
) -> dict:
    settings["redmine_save_credentials"] = bool(save_credentials)
    if settings["redmine_save_credentials"]:
        redmine_login = username.strip()
        settings["redmine_username"] = redmine_login
        settings["redmine_login"] = redmine_login
        settings["redmine_password"] = password
    else:
        settings["redmine_username"] = ""
        settings["redmine_login"] = ""
        settings["redmine_password"] = ""
    return settings


def ensure_live_monitor_defaults(config: dict) -> dict:
    settings = config.setdefault(LIVE_MONITOR_CONFIG_KEY, {})
    defaults = default_live_monitor_config()
    for key, value in defaults.items():
        settings.setdefault(key, value)
    if redmine_credentials_should_be_saved(settings):
        settings["redmine_save_credentials"] = True
    try:
        settings["poll_interval_seconds"] = max(60, min(3600, int(settings.get("poll_interval_seconds", 60))))
    except (TypeError, ValueError):
        settings["poll_interval_seconds"] = 60
    return settings


def problem_to_duty_filter_row(problem: ZabbixProblemSnapshotItem | dict) -> dict:
    """Convert a live-monitor problem into the row shape used by duty mode filters."""
    payload = problem.to_dict() if isinstance(problem, ZabbixProblemSnapshotItem) else dict(problem or {})
    return {
        "time": str(payload.get("started_at") or payload.get("time") or ""),
        "severity": str(payload.get("severity") or ""),
        "host": str(payload.get("host") or ""),
        "problem": str(payload.get("trigger_name") or payload.get("problem") or ""),
        "tags": str(payload.get("tags") or ""),
        "raw_text": " ".join(str(payload.get(key) or "") for key in ("started_at", "severity", "host", "trigger_name", "tags", "info", "actions_text")),
    }


def split_items_by_duty_filter(config: dict, items, filter_enabled=True):
    """Split live problems with the same keyword/catalog rules that duty mode uses."""
    items = list(items or [])
    if not filter_enabled:
        return items, []
    settings = (config or {}).get("duty_mode", {}) if isinstance(config, dict) else {}
    keywords = settings.get("zabbix_problem_keywords", [])
    excludes = settings.get("zabbix_problem_exclude_keywords", [])
    rows = []
    row_to_item = []
    for item in items:
        row = problem_to_duty_filter_row(item)
        if not problem_matches_keywords(row, keywords=keywords, exclude_keywords=excludes):
            continue
        rows.append(row)
        row_to_item.append((row, item))
    catalog = load_zabbix_trigger_catalog(config=config)
    annotate_zabbix_problems_with_trigger_catalog(rows, catalog)
    visible = []
    keyword_matched_item_ids = {id(item) for _row, item in row_to_item}
    hidden = [item for item in items if id(item) not in keyword_matched_item_ids]
    for row, item in row_to_item:
        if zabbix_problem_visible_by_trigger_filters(row):
            visible.append(item)
        else:
            hidden.append(item)
    return visible, hidden


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
            snapshot_item = ZabbixProblemSnapshotItem(key=build_problem_key(item), **{k: v for k, v in dict(item or {}).items() if k in {"trigger_name", "host", "host_url", "severity", "started_at", "status", "info", "duration", "acknowledged", "ack_text", "ack_url", "actions_text", "actions_tooltip", "tags", "severity_class", "severity_level", "event_id", "problem_url", "graph_urls", "trigger_kind", "processed", "row_index"}})
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
    var headerRows = directHeaderRows(table);
    headerRows.forEach(function(row) {
      directCells(row).filter(function(cell) { return cell.tagName === 'TH'; }).forEach(function(th, index) {
        var header = normalizeHeader(text(th));
        Object.keys(headerAliases).forEach(function(field) {
          if (headerAliases[field].indexOf(header) !== -1) map[field] = index;
        });
      });
    });
    map.__header_count = Object.keys(map).filter(function(key) { return key.indexOf('__') !== 0; }).length ? (headerRows[0] ? directCells(headerRows[0]).length : 0) : 0;
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
  function directCells(row) { return Array.from(row.children).filter(function(child) { return ['TD', 'TH'].indexOf(child.tagName) !== -1; }); }
  function isSeparatorRow(row, cellsRaw) {
    var value = text(row).toLowerCase();
    if (/^(сегодня|вчера)$/.test(value)) return true;
    if (cellsRaw.length === 1 && (cellsRaw[0].hasAttribute('colspan') || /сегодня|вчера/.test(value))) return true;
    if (/separator|group|timeline|date/.test(row.className || '') && cellsRaw.length <= 2) return true;
    return false;
  }
  function cellAt(cells, map, field, fallbackIndex) {
    var headerCount = map.__header_count || cells.length;
    var offset = cells.length > headerCount ? cells.length - headerCount : 0;
    var index = Object.prototype.hasOwnProperty.call(map, field) ? map[field] + offset : fallbackIndex;
    return index >= 0 && index < cells.length ? cells[index] : null;
  }
  function acknowledgeDetectedReason() {
    var title = String(document.title || '');
    var href = String(document.location.href || '');
    if (/проблемы/i.test(title)) return '';
    var actionInput = document.querySelector('#acknowledge_form input[name="action"], input[name="action"][value="popup.acknowledge.create"]');
    if (actionInput && actionInput.value === 'popup.acknowledge.create') return 'action=popup.acknowledge.create';
    if (document.querySelector('#acknowledge_form')) return '#acknowledge_form found';
    if (/[?&]action=popup\.acknowledge\.create(?:&|$)/i.test(href)) return 'action=popup.acknowledge.create';
    if (/[?&]popup_action=acknowledge\.(?:edit|create)(?:&|$)/i.test(href)) return 'popup_action=acknowledge';
    if (/обновление проблемы/i.test(title)) return 'title contains Обновление проблемы';
    if (document.querySelector('.overlay-dialogue #acknowledge_form, .modal #acknowledge_form, .modal-popup #acknowledge_form')) return 'visible acknowledge form in popup';
    return '';
  }
  var acknowledgeReason = acknowledgeDetectedReason();
  if (acknowledgeReason) {
    var ackDebug = {title: String(document.title || '').slice(0, 160), url_path: safeUrl(document.location.href), login_detected: false, table_count: 0, tr_count: 0, header_map: {}, candidate_count: 0, problem_count: 0, acknowledge_detected_reason: acknowledgeReason, zero_reason: 'Открыта форма подтверждения Zabbix. Мониторинг страницы Problems не выполняется в этом WebView.', sample_rows: []};
    return JSON.stringify({ok: true, url: document.location.href, title: document.title || '', login_detected: false, table_count: 0, tr_count: 0, header_map: {}, candidate_count: 0, problem_count: 0, acknowledge_detected_reason: acknowledgeReason, items: [], separators: [], safe_debug: ackDebug, zero_reason: ackDebug.zero_reason});
  }
  function directChildRows(table) {
    var bodies = Array.from(table.children).filter(function(child) { return child.tagName === 'TBODY'; });
    var source = bodies.length ? bodies : [table];
    var result = [];
    source.forEach(function(parent) {
      Array.from(parent.children).forEach(function(child) {
        if (child.tagName === 'TR' && child.closest('table') === table) result.push(child);
      });
    });
    return result;
  }
  function directHeaderRows(table) {
    var heads = Array.from(table.children).filter(function(child) { return child.tagName === 'THEAD'; });
    var result = [];
    heads.forEach(function(parent) {
      Array.from(parent.children).forEach(function(child) { if (child.tagName === 'TR' && child.closest('table') === table) result.push(child); });
    });
    if (!result.length) result = directChildRows(table).slice(0, 2);
    return result;
  }
  var tables = Array.from(document.querySelectorAll('table')).filter(function(table) { return !table.closest('.overlay-dialogue, .modal, .modal-popup, #acknowledge_form, .table-forms, td'); });
  var rows = Array.from(document.getElementsByTagName('tr'));
  var loginDetected = !!document.querySelector('input[type=password], input[name*=password i], form[action*=login i]') || /login|sign[ -]?in|вход/i.test(document.title || '');
  var loginButton = document.querySelector('button#login[name=login], button#login, button[name=login]');
  var zabbixAuthRequired = !!(loginButton && loginButton.getAttribute('data-login-url') && document.querySelector('output.msg-bad.msg-global') && /Вы не выполнили вход|Для просмотра этой страницы вы должны войти в систему|Возможно сессия просрочена или был изменен пароль/i.test(text(document.body)));
  if (zabbixAuthRequired) {
    var authDebug = {title: String(document.title || '').slice(0, 160), url_path: safeUrl(document.location.href), login_detected: true, auth_required: true, data_login_url: loginButton.getAttribute('data-login-url') || '', table_count: tables.length, tr_count: rows.length, header_map: {}, candidate_count: 0, problem_count: 0, zero_reason: 'auth_required', sample_rows: []};
    return JSON.stringify({ok: false, auth_required: true, data_login_url: loginButton.getAttribute('data-login-url') || '', login_detected: true, items: [], separators: [], safe_debug: authDebug, zero_reason: 'auth_required'});
  }
  var items = [];
  var separators = [];
  var candidates = [];
  var nestedRowsSkipped = 0;
  var invalidProblemRowsSkipped = 0;
  var historyRowsSkipped = 0;
  var sampleSkippedRows = [];
  function rememberSkipped(row, reason, cellsRaw) {
    if (reason === 'nested') nestedRowsSkipped += 1;
    else if (reason === 'history') historyRowsSkipped += 1;
    else invalidProblemRowsSkipped += 1;
    if (sampleSkippedRows.length < 5) sampleSkippedRows.push({reason: reason, classes: String(row.className || '').slice(0, 160), cell_count: cellsRaw ? cellsRaw.length : directCells(row).length, text_length: text(row).length});
  }
  function isHistoryRow(cellsRaw) {
    if (cellsRaw.length < 3 || cellsRaw.length > 4) return false;
    var joined = cellsRaw.map(text).join(' ');
    return /\d{2}\.\d{2}\.\d{4}/.test(joined) && /https?:\/\/[^ ]*redmine/i.test(joined);
  }
  function compactText(value, limit) {
    value = String(value || '').replace(/\s+/g, ' ').trim();
    limit = limit || 160;
    return value.length > limit ? value.slice(0, limit - 1) + '…' : value;
  }
  function actionMessageInfo(actionsCell) {
    if (!actionsCell) return {short_text: '', full_text: ''};
    var nestedRows = Array.from(actionsCell.querySelectorAll('table tr')).filter(function(row) { return row.closest('td') === actionsCell || actionsCell.contains(row); });
    var messages = [];
    nestedRows.forEach(function(row) {
      var cells = directCells(row).map(text).filter(Boolean);
      if (cells.length >= 3) messages.push(cells[0] + ' — ' + cells[1] + ': ' + cells.slice(2).join(' '));
      else if (cells.length) messages.push(cells.join(' — '));
    });
    var full = messages.length ? messages[messages.length - 1] : text(actionsCell);
    return {short_text: compactText(full, 140), full_text: full};
  }
  function hasValidSeverity(value, className) { return !!severityLevel(value, className); }
  var headerMap = {};
  var requiredProblemHeaders = ['started_at', 'severity', 'host', 'trigger_name'];
  var problemTable = tables.find(function(table) {
    var map = buildHeaderMap(table);
    var mappedFields = Object.keys(map).filter(function(key) { return key.indexOf('__') !== 0; });
    if (requiredProblemHeaders.every(function(field) { return mappedFields.indexOf(field) !== -1; })) {
      headerMap = map;
      return true;
    }
    return false;
  }) || null;
  if (problemTable && !Object.keys(headerMap).filter(function(key) { return key.indexOf('__') !== 0; }).length) headerMap = buildHeaderMap(problemTable);
  var dataRows = problemTable ? directChildRows(problemTable).filter(function(row) { return row.closest('table') === problemTable && directCells(row).some(function(cell) { return cell.tagName === 'TD'; }); }) : [];
  dataRows.forEach(function(row, rowIndex) {
    if (problemTable && row.closest('table') !== problemTable) { rememberSkipped(row, 'nested'); return; }
    var rowText = text(row);
    var cellsRaw = directCells(row);
    var cells = cellsRaw.map(text);
    if (isSeparatorRow(row, cellsRaw)) { separators.push({row_type: 'separator', text: rowText, row_index: rowIndex}); return; }
    if (!rowText || cellsRaw.length < 2 || cellsRaw.some(function(cell) { return cell.hasAttribute('colspan'); })) { rememberSkipped(row, 'invalid', cellsRaw); return; }
    if (isHistoryRow(cellsRaw)) { rememberSkipped(row, 'history', cellsRaw); return; }
    var links = Array.from(row.querySelectorAll('a[href]'));
    var hasHeaderMap = Object.keys(headerMap).filter(function(key) { return key.indexOf('__') !== 0; }).length > 0;
    var looksLikeProblem = hasHeaderMap || links.some(function(a) { return /event|problem|tr_events|trigger|zabbix\.php/i.test(a.href || ''); }) || row.hasAttribute('data-eventid') || row.hasAttribute('data-problemid') || /problem|event|trigger/i.test(row.className || '');
    if (!looksLikeProblem && cellsRaw.length < 4) { rememberSkipped(row, 'invalid', cellsRaw); return; }
    var severityCell = cellAt(cellsRaw, headerMap, 'severity', 1);
    var ackCell = cellAt(cellsRaw, headerMap, 'acknowledged', 6);
    var actionsCell = cellAt(cellsRaw, headerMap, 'actions_text', 7);
    var problemCell = cellAt(cellsRaw, headerMap, 'trigger_name', cellsRaw.length - 1);
    var hostCell = cellAt(cellsRaw, headerMap, 'host', 3);
    var hostLink = (hostCell ? Array.from(hostCell.querySelectorAll('a[href]')) : []).find(function(a) { return /host|hostid|hosts|zabbix\.php/i.test(a.href || ''); });
    var problemLink = (problemCell ? Array.from(problemCell.querySelectorAll('a[href]')) : links).find(function(a) { return /event|problem|tr_events|trigger|zabbix\.php/i.test(a.href || ''); }) || links.find(function(a) { return /event|problem|tr_events|trigger|zabbix\.php/i.test(a.href || ''); });
    var graphLink = links.find(function(a) { return /chart|graph|history|graphs/i.test(a.href || ''); });
    var ackLink = (ackCell ? Array.from(ackCell.querySelectorAll('a[href]')) : links).find(function(a) { return /acknowledge|eventid|problem/i.test(a.href || '') || /подтверд|ack/i.test(text(a)); });
    var eventId = eventIdFromRow(row);
    var actionsInfo = actionMessageInfo(actionsCell);
    var severityText = text(severityCell) || cells[1] || '';
    var severityClass = severityCell ? String(severityCell.className || '') : '';
    var ackText = text(ackCell);
    var acknowledged = /да|yes|acknowledged|подтвержден/i.test(ackText) && !/нет|no|unack/i.test(ackText);
    if (!hasValidSeverity(severityText, severityClass) || !text(problemCell) || (!text(hostCell) && !problemLink && !eventId)) { rememberSkipped(row, 'invalid', cellsRaw); return; }
    candidates.push(row);
    items.push({
      id: eventId || row.id || '',
      event_id: eventId,
      started_at: text(cellAt(cellsRaw, headerMap, 'started_at', 0)) || cells[0] || '',
      severity: severityText,
      severity_class: severityClass,
      severity_level: severityLevel(severityText, severityClass),
      info: text(cellAt(cellsRaw, headerMap, 'info', 2)),
      host: text(hostCell) || cells[1] || '',
      host_url: hostLink ? abs(hostLink.getAttribute('href')) : '',
      trigger_name: text(problemCell) || rowText,
      duration: text(cellAt(cellsRaw, headerMap, 'duration', 5)),
      acknowledged: acknowledged,
      ack_text: ackText,
      ack_url: ackLink ? abs(ackLink.getAttribute('href')) : (problemLink ? abs(problemLink.getAttribute('href')) : ''),
      actions_text: actionsInfo.short_text,
      actions_tooltip: actionsInfo.full_text,
      tags: text(cellAt(cellsRaw, headerMap, 'tags', 8)),
      status: 'active',
      problem_url: problemLink ? abs(problemLink.getAttribute('href')) : '',
      graph_urls: graphLink ? [abs(graphLink.getAttribute('href'))] : [],
      row_index: rowIndex
    });
  });
  var sampleRows = candidates.slice(0, 5).map(function(row) {
    var cells = Array.from(row.querySelectorAll('td,th')).slice(0, 12);
    return {selector: selector(row), tag: row.tagName.toLowerCase(), attributes: attrs(row), cell_count: row.querySelectorAll('td,th').length, links_count: row.querySelectorAll('a[href]').length, cells: cells.map(function(cell, i) { return {cell_index: i, tag: cell.tagName.toLowerCase(), attributes: attrs(cell), text_length: text(cell).length, links_count: cell.querySelectorAll('a[href]').length}; })};
  });
  var reason = '';
  if (items.length === 0) {
    if (loginDetected) reason = 'Похоже, открыта страница логина.';
    else if (/проблемы/i.test(document.title || '') && (tables.length === 0 || rows.length === 0)) reason = 'Problems page loaded, but Problems table not found';
    else if (tables.length === 0 || rows.length === 0) reason = 'Таблица Zabbix Problems ещё не загружена или отсутствует.';
    else if (candidates.length === 0) reason = 'DOM Zabbix не распознан: строки таблиц не похожи на проблемы.';
    else reason = 'Кандидаты найдены, но не удалось извлечь проблемы из DOM.';
  }
  var safeDebug = {title: String(document.title || '').slice(0, 160), url_path: safeUrl(document.location.href), login_detected: loginDetected, table_count: tables.length, tr_count: rows.length, problem_table_found: !!problemTable, direct_problem_rows_count: dataRows.length, nested_rows_skipped: nestedRowsSkipped, invalid_problem_rows_skipped: invalidProblemRowsSkipped, history_rows_skipped: historyRowsSkipped, sample_skipped_rows: sampleSkippedRows, header_map: headerMap, acknowledge_detected_reason: '', separator_count: separators.length, candidate_count: candidates.length, problem_count: items.length, zero_reason: reason, sample_rows: sampleRows};
  return JSON.stringify({ok: true, url: document.location.href, title: document.title || '', login_detected: loginDetected, table_count: tables.length, tr_count: rows.length, problem_table_found: !!problemTable, direct_problem_rows_count: dataRows.length, nested_rows_skipped: nestedRowsSkipped, invalid_problem_rows_skipped: invalidProblemRowsSkipped, history_rows_skipped: historyRowsSkipped, sample_skipped_rows: sampleSkippedRows, header_map: headerMap, acknowledge_detected_reason: '', candidate_count: candidates.length, problem_count: items.length, separators: separators, items: items, safe_debug: safeDebug, zero_reason: reason});
})();
"""
