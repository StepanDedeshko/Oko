"""Fully automatic Zabbix trigger report UI.

The operator selects an exact date/time period. Oko downloads Problems directly
from Zabbix, finds passage item IDs automatically, reads history for the same
period and writes one final report.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
import csv
import io
import json

from PySide6.QtCore import QDate, QTime, QUrl
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.config import save_config
from app.permissions import get_duty_link
from app.reports import (
    REPORT_HEADERS,
    OutageAggregate,
    normalize_host,
    normalize_passage_items,
    parse_datetime_value,
    passage_item_map,
    problem_matches_report_trigger,
    save_passage_items_json,
)
from app.reports_widget import ReportsWidget as _LegacyReportsWidget
from app.webengine_lifecycle import run_javascript_if_alive


REPORT_CONCURRENCY = 3

PROBLEM_EXPORT_TEMPLATE = r"""
(async function() {
  try {
    var url = new URL(__BASE_URL__ || location.href, location.href);
    url.searchParams.set('action', 'problem.view.csv');
    url.searchParams.set('show', '2');
    url.searchParams.set('filter_set', '1');
    url.searchParams.set('filter_custom_time', '1');
    url.searchParams.set('from', __FROM__);
    url.searchParams.set('to', __TO__);
    url.searchParams.delete('page');
    var response = await fetch(url.toString(), {credentials:'same-origin', cache:'no-store'});
    var text = await response.text();
    if (/Вы не выполнили вход|Для просмотра этой страницы вы должны войти в систему|Возможно сессия просрочена или был изменен пароль/i.test(text)) {
      return JSON.stringify({ok:false, auth_required:true, error:'Сессия Zabbix истекла'});
    }
    if (!response.ok) return JSON.stringify({ok:false, error:'HTTP ' + response.status});
    if (/^\s*<!doctype html|^\s*<html/i.test(text)) {
      return JSON.stringify({ok:false, error:'Zabbix вернул HTML вместо problem.view.csv'});
    }
    return JSON.stringify({ok:true, csv:text});
  } catch (error) {
    return JSON.stringify({ok:false, error:String(error && error.message || error || 'unknown')});
  }
})();
"""

ITEM_DISCOVERY_TEMPLATE = r"""
(async function() {
  var username = __LOGIN__, password = __PASSWORD__, requestId = 1;
  async function rpc(method, params, auth) {
    var body = {jsonrpc:'2.0', method:method, params:params || {}, id:requestId++};
    if (auth) body.auth = auth;
    var response = await fetch(new URL('api_jsonrpc.php', location.href).toString(), {
      method:'POST', credentials:'same-origin', cache:'no-store',
      headers:{'Content-Type':'application/json-rpc'}, body:JSON.stringify(body)
    });
    if (!response.ok) throw new Error('API HTTP ' + response.status);
    var payload = await response.json();
    if (payload.error) throw new Error(String(payload.error.data || payload.error.message || 'Zabbix API error'));
    return payload.result;
  }
  async function login() {
    try { return await rpc('user.login', {username:username, password:password}, null); }
    catch (first) { return await rpc('user.login', {user:username, password:password}, null); }
  }
  async function findItems(auth, term) {
    return await rpc('item.get', {
      output:['itemid','name','key_','value_type'], selectHosts:['hostid','host','name'],
      search:{name:term}, sortfield:'itemid'
    }, auth);
  }
  try {
    if (!username || !password) return JSON.stringify({ok:false, error:'Нет сохраненных учетных данных Zabbix'});
    var auth = await login();
    var batches = await Promise.all([findItems(auth, 'srabotok'), findItems(auth, 'сработок')]);
    var out = [], seen = {};
    batches.forEach(function(items) {
      (items || []).forEach(function(item) {
        var host = (item.hosts || [])[0] || {};
        [String(host.name || '').trim(), String(host.host || '').trim()].filter(Boolean).forEach(function(alias) {
          var key = alias.toLowerCase() + '::' + String(item.itemid || '');
          if (seen[key]) return;
          seen[key] = true;
          out.push({host:alias, itemid:String(item.itemid || ''), type:String(item.name || item.key_ || ''), rowText:alias});
        });
      });
    });
    return JSON.stringify({ok:true, items:out});
  } catch (error) {
    return JSON.stringify({ok:false, error:String(error && error.message || error || 'unknown')});
  }
})();
"""

REPORT_RUNNER_TEMPLATE = r"""
(function() {
  var tasks = __TASKS__, concurrency = __CONCURRENCY__;
  var totalRequests = tasks.reduce(function(n, task){ return n + (task.ranges || []).length; }, 0);
  var state = {
    running:true, done:false, cancelled:false, auth_required:false, error:'',
    completed_tasks:0, completed_requests:0, total_tasks:tasks.length,
    total_requests:totalRequests, results:[]
  };
  window.__okoReportState = state;
  function makeUrl(task, range) {
    var url = new URL('history.php', location.href);
    url.searchParams.set('action', 'showvalues');
    url.searchParams.append('itemids[]', String(task.itemid));
    url.searchParams.set('from', range.from);
    url.searchParams.set('to', range.to);
    return url.toString();
  }
  function valuesFromHtml(html) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    var body = String(doc.body ? doc.body.textContent : '');
    if (/Вы не выполнили вход|Для просмотра этой страницы вы должны войти в систему|Возможно сессия просрочена или был изменен пароль/i.test(body)) {
      var error = new Error('AUTH_REQUIRED'); error.authRequired = true; throw error;
    }
    var tables = Array.from(doc.querySelectorAll('table'));
    for (var t = 0; t < tables.length; t += 1) {
      var values = [];
      Array.from(tables[t].querySelectorAll('tbody tr')).forEach(function(row) {
        var cells = row.querySelectorAll('td');
        if (cells.length < 2) return;
        var raw = String(cells[1].textContent || '').trim().replace(/\s/g, '').replace(',', '.');
        if (/^-?\d+(?:\.\d+)?$/.test(raw)) values.push(Number(raw));
      });
      if (values.length) return values.filter(Number.isFinite);
    }
    return [];
  }
  async function processTask(task) {
    var allValues = [];
    try {
      var ranges = task.ranges || [];
      for (var r = 0; r < ranges.length; r += 1) {
        if (state.cancelled) throw new Error('CANCELLED');
        var response = await fetch(makeUrl(task, ranges[r]), {credentials:'same-origin', cache:'no-store'});
        if (!response.ok) throw new Error('HTTP ' + response.status);
        allValues.push.apply(allValues, valuesFromHtml(await response.text()));
        state.completed_requests += 1;
      }
      var avg = allValues.length ? allValues.reduce(function(a,b){return a+b;},0) / allValues.length : null;
      return {date:task.date, host:task.host, itemid:task.itemid, avg:avg, count:allValues.length};
    } catch (error) {
      if (error && error.authRequired) { state.auth_required = true; throw error; }
      return {date:task.date, host:task.host, itemid:task.itemid, avg:null, count:0};
    }
  }
  var nextIndex = 0;
  async function worker() {
    while (!state.cancelled) {
      var index = nextIndex++;
      if (index >= tasks.length) return;
      state.results.push(await processTask(tasks[index]));
      state.completed_tasks += 1;
    }
  }
  Promise.all(Array.from({length:Math.min(concurrency, Math.max(1, tasks.length))}, function(){return worker();}))
    .then(function(){state.running=false;state.done=true;})
    .catch(function(error){state.running=false;state.done=true;state.error=state.auth_required?'Сессия Zabbix истекла':String(error && error.message || error || 'unknown');});
  return JSON.stringify({started:true, total_tasks:tasks.length, total_requests:totalRequests});
})();
"""


class ReportsWidget(_LegacyReportsWidget):
    """Automatic report: no user-supplied CSV or itemid JSON is required."""

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        title = QLabel("Отчеты")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        report_box = QGroupBox("Отчет по сработкам")
        layout = QVBoxLayout(report_box)
        layout.setSpacing(10)
        hint = QLabel(
            "Выберите точный период. Око само скачает историю Problems из Zabbix, отберет 8 аварийных "
            "триггеров, найдет itemid проходов и соберет history.php за тот же период. "
            "Потерянные проходы = время недоступности в минутах × среднее значение / 5."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.setMaximumWidth(280)
        self._populate_profile_combo()
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        form.addRow("Zabbix:", self.profile_combo)

        yesterday = date.today() - timedelta(days=1)
        self.date_from = QDateEdit(QDate(yesterday.year, yesterday.month, yesterday.day))
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("dd.MM.yyyy")
        self.date_from.setFixedWidth(120)
        self.time_from = QTimeEdit(QTime(0, 0, 0))
        self.time_from.setDisplayFormat("HH:mm:ss")
        self.time_from.setFixedWidth(90)
        self.date_to = QDateEdit(QDate(yesterday.year, yesterday.month, yesterday.day))
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("dd.MM.yyyy")
        self.date_to.setFixedWidth(120)
        self.time_to = QTimeEdit(QTime(23, 59, 59))
        self.time_to.setDisplayFormat("HH:mm:ss")
        self.time_to.setFixedWidth(90)

        period_widget = QWidget()
        period_layout = QHBoxLayout(period_widget)
        period_layout.setContentsMargins(0, 0, 0, 0)
        period_layout.setSpacing(6)
        for widget in (QLabel("с"), self.date_from, self.time_from, QLabel("по"), self.date_to, self.time_to):
            period_layout.addWidget(widget)
        period_layout.addStretch(1)
        form.addRow("Период:", period_widget)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Тест — первые 5 узлов", "5")
        self.mode_combo.addItem("Все найденные узлы", "all")
        self.mode_combo.setMaximumWidth(240)
        form.addRow("Обработка:", self.mode_combo)
        layout.addLayout(form)

        self.summary_label = QLabel("Источник данных — Zabbix. Исходный CSV и ручной импорт itemid не нужны.")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        actions = QHBoxLayout()
        self.start_button = QPushButton("Сформировать отчет")
        self.start_button.setObjectName("PrimaryAction")
        self.start_button.clicked.connect(self.start_report)
        self.cancel_button = QPushButton("Остановить")
        self.cancel_button.clicked.connect(self.cancel_report)
        self.cancel_button.setEnabled(False)
        actions.addWidget(self.start_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label = QLabel("Готов к работе")
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)
        root.addWidget(report_box)

        self.table = QTableWidget(0, len(REPORT_HEADERS))
        self.table.setHorizontalHeaderLabels(list(REPORT_HEADERS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, stretch=1)

    def _update_items_label(self):
        pass

    def _refresh_csv_summary(self, *_args):
        pass

    def _default_problems_url(self) -> str:
        live = self.config.get("live_zabbix_monitor", {}) or {}
        return str(live.get("problems_url") or live.get("url") or get_duty_link(self.config, "live_zabbix_url") or "").strip()

    @staticmethod
    def _datetime_from_controls(qdate: QDate, qtime: QTime) -> datetime:
        return datetime(qdate.year(), qdate.month(), qdate.day(), qtime.hour(), qtime.minute(), qtime.second())

    def _current_period(self):
        return (
            self._datetime_from_controls(self.date_from.date(), self.time_from.time()),
            self._datetime_from_controls(self.date_to.date(), self.time_to.time()),
        )

    @staticmethod
    def _resolve_header(fieldnames, aliases):
        lookup = {" ".join(str(name or "").replace("\ufeff", "").split()).casefold(): name for name in (fieldnames or [])}
        for alias in aliases:
            found = lookup.get(" ".join(alias.split()).casefold())
            if found is not None:
                return found
        return None

    def _parse_problem_export(self, text: str):
        sample = text[:8192]
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
        except csv.Error:
            delimiter = ";"
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        start_col = self._resolve_header(reader.fieldnames, ("Время", "Time"))
        recovery_col = self._resolve_header(reader.fieldnames, ("Время восстановления", "Recovery time", "Recovery"))
        host_col = self._resolve_header(reader.fieldnames, ("Узел сети", "Host", "Hosts"))
        problem_col = self._resolve_header(reader.fieldnames, ("Проблема", "Problem"))
        if not start_col or not host_col or not problem_col:
            raise ValueError("В выгрузке Problems Zabbix не найдены обязательные столбцы Время / Узел сети / Проблема")
        rows = []
        for row in reader:
            problem = str(row.get(problem_col) or "").strip()
            if not problem_matches_report_trigger(problem):
                continue
            rows.append({
                "started_at": row.get(start_col),
                "recovered_at": row.get(recovery_col) if recovery_col else "",
                "host": row.get(host_col),
                "problem": problem,
            })
        return rows

    def _aggregate_export_events(self, raw_events):
        buckets = {}
        accepted = 0
        for raw in raw_events:
            host = " ".join(str(raw.get("host") or "").split())
            started = parse_datetime_value(raw.get("started_at"))
            recovered = parse_datetime_value(raw.get("recovered_at")) or self._period_end
            if not host or started is None or recovered < started:
                continue
            start = max(started, self._period_start)
            end = min(recovered, self._period_end)
            if end <= start:
                continue
            accepted += 1
            cursor = start
            while cursor < end:
                next_midnight = datetime.combine(cursor.date() + timedelta(days=1), time.min)
                segment_end = min(end, next_midnight)
                key = (cursor.date(), normalize_host(host))
                bucket = buckets.setdefault(key, {
                    "report_date": cursor.date(), "host": host,
                    "downtime_seconds": 0.0, "event_count": 0,
                })
                bucket["downtime_seconds"] += (segment_end - cursor).total_seconds()
                bucket["event_count"] += 1
                cursor = segment_end
        self._source_event_count = accepted
        result = [OutageAggregate(**payload) for payload in buckets.values()]
        return sorted(result, key=lambda item: (item.report_date, normalize_host(item.host)))

    @staticmethod
    def _ranges_for_day(report_date, period_start, period_end):
        result = []
        for hour in (0, 6, 12, 18):
            block_start = datetime.combine(report_date, time(hour, 0, 0))
            block_end = datetime.combine(report_date, time(23, 59, 59) if hour == 18 else time(hour + 5, 59, 59))
            start, end = max(block_start, period_start), min(block_end, period_end)
            if start <= end:
                result.append({"from": start.strftime("%Y-%m-%d %H:%M:%S"), "to": end.strftime("%Y-%m-%d %H:%M:%S")})
        return result

    def start_report(self):
        self._period_start, self._period_end = self._current_period()
        if self._period_start > self._period_end:
            QMessageBox.warning(self, "Отчет по сработкам", "Начало периода не может быть позже окончания.")
            return
        if not self._default_problems_url():
            QMessageBox.warning(self, "Отчет по сработкам", "Не задан URL страницы Problems Zabbix.")
            return
        default_name = f"Отчет_по_сработкам_{self._period_start.strftime('%Y-%m-%d_%H%M%S')}_{self._period_end.strftime('%Y-%m-%d_%H%M%S')}.csv"
        output, _ = QFileDialog.getSaveFileName(self, "Сохранить отчет", default_name, "CSV (*.csv)")
        if not output:
            return
        self.output_path = output if output.lower().endswith(".csv") else output + ".csv"
        self.selected_aggregates = []
        self.passage_averages = {}
        self.report_rows = []
        self._pending_report_tasks = []
        self._report_auth_retries = 0
        self.progress.setValue(0)
        self.table.setRowCount(0)
        self.settings["zabbix_id"] = str(self.profile_combo.currentData() or "")
        save_config(self.config)
        self._set_running(True)
        self.summary_label.setText(
            f"Период: {self._period_start.strftime('%d.%m.%Y %H:%M:%S')} — {self._period_end.strftime('%d.%m.%Y %H:%M:%S')}"
        )
        self.status_label.setText("Скачиваю историю проблем Zabbix за выбранный период…")
        self._load_source_page("outages")

    def _load_source_page(self, mode: str):
        url = self._default_problems_url()
        if not url:
            self._set_running(False)
            return
        self._ensure_web_view()
        self._web_mode = mode
        self._auth_attempts = 0
        self.view.load(QUrl(url))

    def _after_ready_page(self):
        page = self.view.page() if self.view is not None else None
        if page is None:
            return
        if self._web_mode == "outages":
            script = PROBLEM_EXPORT_TEMPLATE
            script = script.replace("__BASE_URL__", json.dumps(self._default_problems_url(), ensure_ascii=False))
            script = script.replace("__FROM__", json.dumps(self._period_start.strftime("%Y-%m-%d %H:%M:%S")))
            script = script.replace("__TO__", json.dumps(self._period_end.strftime("%Y-%m-%d %H:%M:%S")))
            run_javascript_if_alive(page, script, self._on_outages_downloaded)
        elif self._web_mode == "report":
            self._start_report_runner()

    def _on_outages_downloaded(self, result):
        try:
            payload = json.loads(result or "{}")
        except (TypeError, ValueError):
            payload = {}
        if payload.get("auth_required"):
            self._load_source_page("outages")
            return
        if not payload.get("ok"):
            QMessageBox.warning(self, "Отчет по сработкам", str(payload.get("error") or "Не удалось скачать Problems"))
            self._set_running(False)
            return
        try:
            raw_events = self._parse_problem_export(str(payload.get("csv") or ""))
        except Exception as exc:
            QMessageBox.warning(self, "Отчет по сработкам", str(exc))
            self._set_running(False)
            return
        aggregates = self._aggregate_export_events(raw_events)
        self.selected_aggregates = self._select_aggregates(aggregates)
        if not self.selected_aggregates:
            QMessageBox.information(self, "Отчет по сработкам", "За выбранный период подходящих аварийных триггеров не найдено.")
            self._set_running(False)
            return
        hosts = {normalize_host(item.host) for item in self.selected_aggregates}
        missing = [host for host in hosts if host not in passage_item_map(self.passage_items)]
        self.summary_label.setText(
            f"Аварийных событий: {self._source_event_count} | строк отчета: {len(self.selected_aggregates)} | узлов: {len(hosts)}"
        )
        if missing:
            self._discover_passage_items()
        else:
            self._start_history_stage()

    def _discover_passage_items(self):
        creds = self._saved_zabbix_credentials()
        page = self.view.page() if self.view is not None else None
        if page is None or not creds.get("login") or not creds.get("password"):
            self._start_history_stage()
            return
        self.status_label.setText("Автоматически ищу itemid 'srabotok' и 'сработок'…")
        script = ITEM_DISCOVERY_TEMPLATE.replace("__LOGIN__", json.dumps(creds["login"])).replace("__PASSWORD__", json.dumps(creds["password"]))
        run_javascript_if_alive(page, script, self._on_items_discovered)

    def _on_items_discovered(self, result):
        try:
            payload = json.loads(result or "{}")
        except (TypeError, ValueError):
            payload = {}
        if payload.get("ok"):
            discovered = normalize_passage_items(payload.get("items") or [])
            self.passage_items = normalize_passage_items(list(self.passage_items) + discovered)
            try:
                save_passage_items_json(self.passage_items, self._items_path())
            except Exception:
                self.logger.exception("Failed to cache passage itemids")
            self.status_label.setText(f"Itemid найдены автоматически: {len(discovered)} записей")
        else:
            self.status_label.setText(f"Автопоиск itemid не удался: {payload.get('error', 'неизвестная ошибка')}")
        self._start_history_stage()

    def _start_history_stage(self):
        item_map = passage_item_map(self.passage_items)
        tasks = []
        for aggregate in self.selected_aggregates:
            item = item_map.get(normalize_host(aggregate.host))
            if not item:
                continue
            ranges = self._ranges_for_day(aggregate.report_date, self._period_start, self._period_end)
            if ranges:
                tasks.append({"date": aggregate.report_date.isoformat(), "host": aggregate.host, "itemid": item["itemid"], "ranges": ranges})
        self._pending_report_tasks = tasks
        if not tasks:
            self._finalize_report()
            return
        total_requests = sum(len(task["ranges"]) for task in tasks)
        self.status_label.setText(f"Собираю проходы: задач {len(tasks)}, запросов {total_requests}")
        self._web_mode = "report"
        self._start_report_runner()

    def _start_report_runner(self):
        page = self.view.page() if self.view is not None else None
        if page is None:
            self._set_running(False)
            return
        script = REPORT_RUNNER_TEMPLATE.replace("__TASKS__", json.dumps(self._pending_report_tasks, ensure_ascii=False))
        script = script.replace("__CONCURRENCY__", str(REPORT_CONCURRENCY))
        run_javascript_if_alive(page, script, self._on_report_runner_started)

    def _set_running(self, running: bool):
        self.start_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.date_from.setEnabled(not running)
        self.time_from.setEnabled(not running)
        self.date_to.setEnabled(not running)
        self.time_to.setEnabled(not running)
        self.mode_combo.setEnabled(not running)
        self.profile_combo.setEnabled(not running)
