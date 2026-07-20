"""User-facing Zabbix reports section."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin
import json

from PySide6.QtCore import QDate, QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
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
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import save_config
from app.logger import get_logger
from app.permissions import get_duty_link
from app.reports import (
    REPORT_HEADERS,
    aggregate_outages,
    build_report_rows,
    format_duration,
    load_outages_from_csv,
    load_passage_items_json,
    normalize_host,
    normalize_passage_items,
    passage_average_key,
    passage_item_map,
    save_passage_items_json,
    write_report_csv,
)
from app.webengine_lifecycle import register_web_view, run_javascript_if_alive, safe_delete_web_view


PASSAGE_ITEMS_STORAGE_KEY = "zbx_passage_items"
REPORT_CONCURRENCY = 3

AUTH_INSPECT_SCRIPT = r"""
(function() {
  var text = String(document.body ? document.body.innerText : '');
  var gate = document.querySelector('button#login, button[name="login"]');
  var login = document.querySelector('input#name, input[name="name"], input[placeholder="Логин"]');
  var password = document.querySelector('input#password, input[name="password"], input[placeholder="Пароль"]');
  if (login && password) return JSON.stringify({state:'login_form'});
  if (gate && /Вы не выполнили вход|Для просмотра этой страницы вы должны войти в систему|Возможно сессия просрочена или был изменен пароль/i.test(text)) {
    return JSON.stringify({state:'gate', login_url:String(gate.getAttribute('data-login-url') || '')});
  }
  return JSON.stringify({state:'ready'});
})();
"""

PASSAGE_ITEMS_COLLECTOR_SCRIPT = r"""
(function() {
  function clean(value) { return String(value || '').replace(/\r/g, '').trim(); }
  function itemIdFromRow(row) {
    var direct = row.getAttribute('data-itemid') || row.getAttribute('data-item-id') || '';
    if (/^\d+$/.test(direct)) return direct;
    var nodes = Array.from(row.querySelectorAll('[data-itemid], [data-item-id], input[value], a[href]'));
    for (var i = 0; i < nodes.length; i += 1) {
      var node = nodes[i];
      var attr = node.getAttribute('data-itemid') || node.getAttribute('data-item-id') || '';
      if (/^\d+$/.test(attr)) return attr;
      var href = node.getAttribute('href') || '';
      var match = href.match(/(?:itemids?(?:%5B\d*%5D|\[\d*\])?|itemid)=(\d+)/i);
      if (match) return match[1];
      var value = String(node.value || '');
      if (/^\d+$/.test(value) && /item/i.test(String(node.name || node.id || ''))) return value;
    }
    return '';
  }
  function normalize(items) {
    var out = [], seen = {};
    (items || []).forEach(function(item) {
      if (!item || typeof item !== 'object') return;
      var itemid = clean(item.itemid || item.item_id || item.id);
      if (!/^\d+$/.test(itemid)) return;
      var rowText = clean(item.rowText || item.row_text || item.host);
      var host = clean(item.host);
      if (!host) host = (rowText.split(/\n/).map(clean).filter(Boolean)[0] || '');
      if (!host) return;
      var key = host.toLowerCase() + '::' + itemid;
      if (seen[key]) return;
      seen[key] = true;
      out.push({host:host, itemid:itemid, type:clean(item.type), rowText:rowText || host});
    });
    return out;
  }

  var cached = [];
  try { cached = JSON.parse(localStorage.getItem('__STORAGE_KEY__') || '[]'); } catch (e) { cached = []; }
  var found = [];
  Array.from(document.querySelectorAll('tr')).forEach(function(row) {
    var rowText = clean(row.innerText || row.textContent);
    var lowered = rowText.toLowerCase();
    var type = '';
    if (lowered.indexOf('srabotok') !== -1) type = 'srabotok';
    else if (lowered.indexOf('сработок') !== -1) type = 'сработок';
    if (!type) return;
    var itemid = itemIdFromRow(row);
    if (!itemid) return;
    var cells = Array.from(row.children || []).filter(function(node){ return node.tagName === 'TD' || node.tagName === 'TH'; });
    var host = cells.length ? clean(cells[0].innerText || cells[0].textContent) : '';
    if (!host) host = (rowText.split(/\n/).map(clean).filter(Boolean)[0] || '');
    found.push({host:host, itemid:itemid, type:type, rowText:rowText});
  });
  var items = normalize(cached.concat(found));
  try { localStorage.setItem('__STORAGE_KEY__', JSON.stringify(items)); } catch (e) {}
  return JSON.stringify({ok:true, cached_count:normalize(cached).length, found_count:normalize(found).length, items:items});
})();
""".replace("__STORAGE_KEY__", PASSAGE_ITEMS_STORAGE_KEY)

REPORT_RUNNER_TEMPLATE = r"""
(function() {
  var tasks = __TASKS__;
  var concurrency = __CONCURRENCY__;
  var ranges = [
    ['00:00:00', '05:59:59'],
    ['06:00:00', '11:59:59'],
    ['12:00:00', '17:59:59'],
    ['18:00:00', '23:59:59']
  ];
  var state = {
    running:true,
    done:false,
    cancelled:false,
    auth_required:false,
    error:'',
    completed_tasks:0,
    completed_requests:0,
    total_tasks:tasks.length,
    total_requests:tasks.length * ranges.length,
    results:[]
  };
  window.__okoReportState = state;

  function makeUrl(task, range) {
    var url = new URL('history.php', location.href);
    url.searchParams.set('action', 'showvalues');
    url.searchParams.append('itemids[]', String(task.itemid));
    url.searchParams.set('from', task.date + ' ' + range[0]);
    url.searchParams.set('to', task.date + ' ' + range[1]);
    return url.toString();
  }

  function extractValues(html) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    var bodyText = String(doc.body ? doc.body.textContent : '');
    if (/Вы не выполнили вход|Для просмотра этой страницы вы должны войти в систему|Возможно сессия просрочена или был изменен пароль/i.test(bodyText)) {
      var error = new Error('AUTH_REQUIRED');
      error.authRequired = true;
      throw error;
    }
    var tables = Array.from(doc.querySelectorAll('table'));
    for (var t = 0; t < tables.length; t += 1) {
      var rows = Array.from(tables[t].querySelectorAll('tbody tr'));
      if (!rows.length) continue;
      var values = [];
      rows.forEach(function(row) {
        var cells = row.querySelectorAll('td');
        if (cells.length < 2) return;
        var raw = String(cells[1].textContent || '').trim().replace(/\s/g, '').replace(',', '.');
        if (!/^-?\d+(?:\.\d+)?$/.test(raw)) return;
        var value = Number(raw);
        if (Number.isFinite(value)) values.push(value);
      });
      if (values.length) return values;
    }
    return [];
  }

  async function processTask(task) {
    var allValues = [];
    try {
      for (var r = 0; r < ranges.length; r += 1) {
        if (state.cancelled) throw new Error('CANCELLED');
        var response = await fetch(makeUrl(task, ranges[r]), {
          method:'GET', credentials:'same-origin', cache:'no-store'
        });
        if (!response.ok) throw new Error('HTTP ' + response.status);
        var html = await response.text();
        allValues.push.apply(allValues, extractValues(html));
        state.completed_requests += 1;
      }
      var avg = null;
      if (allValues.length) {
        var sum = allValues.reduce(function(total, value){ return total + value; }, 0);
        avg = sum / allValues.length;
      }
      return {
        date:task.date,
        host:task.host,
        itemid:task.itemid,
        avg:avg,
        count:allValues.length,
        status:allValues.length ? 'OK' : 'Нет данных'
      };
    } catch (error) {
      if (error && error.authRequired) {
        state.auth_required = true;
        throw error;
      }
      return {
        date:task.date,
        host:task.host,
        itemid:task.itemid,
        avg:null,
        count:0,
        status:state.cancelled ? 'Отменено' : ('Ошибка: ' + String(error && error.message || error || 'unknown'))
      };
    }
  }

  var nextIndex = 0;
  async function worker() {
    while (!state.cancelled) {
      var index = nextIndex++;
      if (index >= tasks.length) return;
      var result = await processTask(tasks[index]);
      state.results.push(result);
      state.completed_tasks += 1;
    }
  }

  Promise.all(Array.from({length:Math.min(concurrency, Math.max(1, tasks.length))}, function(){ return worker(); }))
    .then(function() {
      state.running = false;
      state.done = true;
    })
    .catch(function(error) {
      state.running = false;
      state.done = true;
      state.error = state.auth_required ? 'Сессия Zabbix истекла' : String(error && error.message || error || 'unknown');
    });

  return JSON.stringify({started:true, total_tasks:tasks.length, total_requests:state.total_requests});
})();
"""

REPORT_POLL_SCRIPT = r"""
(function() {
  var s = window.__okoReportState || {};
  return JSON.stringify({
    running:!!s.running,
    done:!!s.done,
    cancelled:!!s.cancelled,
    auth_required:!!s.auth_required,
    error:String(s.error || ''),
    completed_tasks:Number(s.completed_tasks || 0),
    completed_requests:Number(s.completed_requests || 0),
    total_tasks:Number(s.total_tasks || 0),
    total_requests:Number(s.total_requests || 0),
    results:s.done ? (s.results || []) : []
  });
})();
"""


class ReportsWidget(QWidget):
    """Section ``Отчеты`` with the report ``Отчет по сработкам``."""

    def __init__(self, config, profiles=None, credentials=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.profiles = profiles or {}
        self.credentials = credentials or {}
        self.logger = get_logger()
        self.settings = self.config.setdefault("reports", {}).setdefault("trigger_report", {})

        self.csv_path = ""
        self.passage_items = []
        self.aggregates = []
        self.selected_aggregates = []
        self.passage_averages = {}
        self.report_rows = []
        self.output_path = ""
        self._pending_report_tasks = []
        self._web_mode = ""
        self._report_auth_retries = 0

        self.view = None
        self.page = None
        self.current_zabbix_id = ""
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(600)
        self.poll_timer.timeout.connect(self._poll_report_state)

        self._build_ui()
        self._load_cached_passage_items()
        self._refresh_csv_summary()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("Отчеты")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        report_box = QGroupBox("Отчет по сработкам")
        report_layout = QVBoxLayout(report_box)
        report_layout.setSpacing(10)

        hint = QLabel(
            "CSV задает интервалы недоступности. Око оставляет только 8 заданных аварийных триггеров, "
            "суммирует простой по дате и узлу и получает среднее количество проходов из Zabbix history.php. "
            "Потерянные проходы считаются по формуле: время в минутах × среднее значение / 5."
        )
        hint.setWordWrap(True)
        report_layout.addWidget(hint)

        form = QFormLayout()
        csv_row = QHBoxLayout()
        self.csv_input = QLineEdit()
        self.csv_input.setReadOnly(True)
        self.csv_input.setPlaceholderText("CSV: Время / Время восстановления / Узел сети / Проблема")
        csv_button = QPushButton("Выбрать CSV")
        csv_button.clicked.connect(self.choose_csv)
        csv_row.addWidget(self.csv_input, stretch=1)
        csv_row.addWidget(csv_button)
        form.addRow("Исходный CSV:", csv_row)

        yesterday = date.today() - timedelta(days=1)
        self.date_from = QDateEdit(QDate(yesterday.year, yesterday.month, yesterday.day))
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("dd.MM.yyyy")
        self.date_to = QDateEdit(QDate(yesterday.year, yesterday.month, yesterday.day))
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("dd.MM.yyyy")
        self.date_from.dateChanged.connect(self._refresh_csv_summary)
        self.date_to.dateChanged.connect(self._refresh_csv_summary)
        form.addRow("Дата начала:", self.date_from)
        form.addRow("Дата окончания:", self.date_to)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Тест — первые 5 узлов", "5")
        self.mode_combo.addItem("Все узлы из CSV", "all")
        self.mode_combo.currentIndexChanged.connect(self._refresh_csv_summary)
        form.addRow("Какие узлы обрабатывать:", self.mode_combo)
        report_layout.addLayout(form)

        zabbix_box = QGroupBox("Zabbix / itemid проходов")
        zabbix_form = QFormLayout(zabbix_box)
        self.profile_combo = QComboBox()
        self._populate_profile_combo()
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        zabbix_form.addRow("Zabbix profile:", self.profile_combo)

        self.items_url_input = QLineEdit(self._default_items_source_url())
        self.items_url_input.setPlaceholderText("URL страницы Zabbix, где находятся элементы srabotok / сработок")
        zabbix_form.addRow("Страница элементов:", self.items_url_input)

        item_buttons = QHBoxLayout()
        sync_button = QPushButton("Синхронизировать itemid")
        sync_button.clicked.connect(self.sync_passage_items)
        import_button = QPushButton("Импорт JSON itemid")
        import_button.clicked.connect(self.import_passage_items)
        item_buttons.addWidget(sync_button)
        item_buttons.addWidget(import_button)
        item_buttons.addStretch(1)
        zabbix_form.addRow("", item_buttons)
        self.items_label = QLabel("Itemid: 0")
        zabbix_form.addRow("Состояние:", self.items_label)
        report_layout.addWidget(zabbix_box)

        self.summary_label = QLabel("Выберите CSV.")
        self.summary_label.setWordWrap(True)
        report_layout.addWidget(self.summary_label)

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
        report_layout.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label = QLabel("Готов к работе")
        report_layout.addWidget(self.progress)
        report_layout.addWidget(self.status_label)
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

    def _populate_profile_combo(self):
        self.profile_combo.clear()
        selected = str(self.settings.get("zabbix_id") or "")
        names = {}
        for instance in self.config.get("zabbix_instances", []) or []:
            zabbix_id = str(instance.get("id") or "")
            if zabbix_id:
                names[zabbix_id] = str(instance.get("name") or zabbix_id)
        for zabbix_id in self.profiles:
            self.profile_combo.addItem(names.get(zabbix_id, zabbix_id), zabbix_id)
        if not self.profiles:
            self.profile_combo.addItem("Автоматический WebEngine profile", "")
        index = self.profile_combo.findData(selected)
        if index >= 0:
            self.profile_combo.setCurrentIndex(index)

    def _profile_changed(self, *_args):
        self.settings["zabbix_id"] = str(self.profile_combo.currentData() or "")
        save_config(self.config)
        self._destroy_web_view()

    def _default_items_source_url(self) -> str:
        if self.settings.get("items_url"):
            return str(self.settings.get("items_url") or "")
        live = self.config.get("live_zabbix_monitor", {}) or {}
        return str(live.get("problems_url") or live.get("url") or get_duty_link(self.config, "live_zabbix_url") or "")

    def _items_path(self) -> Path:
        configured = str(self.settings.get("passage_items_path") or "data/report_passage_items.json")
        path = Path(configured)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        return path

    def _load_cached_passage_items(self):
        path = self._items_path()
        if path.exists():
            try:
                self.passage_items = load_passage_items_json(path)
            except Exception:
                self.logger.exception("Failed to load report passage itemids")
                self.passage_items = []
        self._update_items_label()

    def _update_items_label(self):
        self.items_label.setText(f"Itemid: {len(self.passage_items)}")

    @staticmethod
    def _qdate_to_date(value: QDate) -> date:
        return date(value.year(), value.month(), value.day())

    def _current_dates(self):
        return self._qdate_to_date(self.date_from.date()), self._qdate_to_date(self.date_to.date())

    def choose_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать CSV Zabbix", "", "CSV (*.csv);;Все файлы (*)")
        if not path:
            return
        self.csv_path = path
        self.csv_input.setText(path)
        try:
            events = load_outages_from_csv(path)
        except Exception as exc:
            QMessageBox.warning(self, "Отчет по сработкам", str(exc))
            return
        if events:
            first = min(item.started_at.date() for item in events)
            last = max(item.started_at.date() for item in events)
            self.date_from.setDate(QDate(first.year, first.month, first.day))
            self.date_to.setDate(QDate(last.year, last.month, last.day))
        self._refresh_csv_summary()

    def _select_aggregates(self, aggregates):
        aggregates = list(aggregates or [])
        if self.mode_combo.currentData() == "all":
            return aggregates
        allowed = []
        seen = set()
        for item in aggregates:
            key = normalize_host(item.host)
            if key not in seen:
                seen.add(key)
                allowed.append(key)
            if len(allowed) >= 5:
                break
        allowed = set(allowed)
        return [item for item in aggregates if normalize_host(item.host) in allowed]

    def _refresh_csv_summary(self, *_args):
        if not self.csv_path:
            self.summary_label.setText("Выберите CSV.")
            return
        date_from, date_to = self._current_dates()
        if date_from > date_to:
            self.summary_label.setText("Дата начала не может быть позже даты окончания.")
            return
        try:
            events = load_outages_from_csv(self.csv_path, date_from=date_from, date_to=date_to)
            self.aggregates = aggregate_outages(events)
            selected = self._select_aggregates(self.aggregates)
            item_map = passage_item_map(self.passage_items)
            unique_hosts = {normalize_host(item.host) for item in selected}
            missing = [item.host for item in selected if normalize_host(item.host) not in item_map]
            self.summary_label.setText(
                f"Найдено событий: {len(events)} | Строк после суммирования: {len(selected)} | "
                f"Узлов: {len(unique_hosts)} | Без itemid: {len({normalize_host(v) for v in missing})}"
            )
        except Exception as exc:
            self.summary_label.setText(f"Ошибка CSV: {exc}")

    def import_passage_items(self):
        path, _ = QFileDialog.getOpenFileName(self, "Импорт itemid", "", "JSON (*.json);;Все файлы (*)")
        if not path:
            return
        try:
            self.passage_items = load_passage_items_json(path)
            save_passage_items_json(self.passage_items, self._items_path())
            self._update_items_label()
            self._refresh_csv_summary()
            QMessageBox.information(self, "Отчет по сработкам", f"Загружено itemid: {len(self.passage_items)}")
        except Exception as exc:
            QMessageBox.warning(self, "Отчет по сработкам", str(exc))

    def sync_passage_items(self):
        url = self.items_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Отчет по сработкам", "Укажите URL страницы Zabbix с элементами srabotok / сработок.")
            return
        self.settings["items_url"] = url
        self.settings["zabbix_id"] = str(self.profile_combo.currentData() or "")
        save_config(self.config)
        self.status_label.setText("Открываю страницу Zabbix и собираю itemid…")
        self._load_source_page("collector")

    def _ensure_web_view(self):
        zabbix_id = str(self.profile_combo.currentData() or "")
        if self.view is not None and zabbix_id == self.current_zabbix_id:
            return
        self._destroy_web_view()
        self.current_zabbix_id = zabbix_id
        self.view = register_web_view(QWebEngineView())
        profile = self.profiles.get(zabbix_id)
        if profile is not None:
            self.page = QWebEnginePage(profile, self.view)
            self.view.setPage(self.page)
        else:
            self.page = self.view.page()
        self.view.hide()
        self.view.loadFinished.connect(self._on_source_loaded)

    def _destroy_web_view(self):
        if self.view is None:
            return
        try:
            safe_delete_web_view(self.view, logger=self.logger, context="ReportsWidget")
        finally:
            self.view = None
            self.page = None
            self.current_zabbix_id = ""

    def _load_source_page(self, mode: str):
        url = self.items_url_input.text().strip() or self._default_items_source_url()
        if not url:
            QMessageBox.warning(self, "Отчет по сработкам", "Не задан URL Zabbix для отчета.")
            self._set_running(False)
            return
        self._ensure_web_view()
        self._web_mode = mode
        self._auth_attempts = 0
        self.view.load(QUrl(url))

    def _on_source_loaded(self, ok):
        if not ok:
            self.status_label.setText("Ошибка загрузки страницы Zabbix")
            self._set_running(False)
            return
        page = self.view.page() if self.view is not None else None
        if page is None:
            return
        run_javascript_if_alive(page, AUTH_INSPECT_SCRIPT, self._on_auth_inspected)

    def _on_auth_inspected(self, result):
        try:
            payload = json.loads(result or "{}")
        except (TypeError, ValueError):
            payload = {}
        state = payload.get("state") or "ready"
        if state == "ready":
            self._auth_attempts = 0
            self._after_ready_page()
            return
        if self._auth_attempts >= 6:
            self.status_label.setText("Не удалось автоматически войти в Zabbix")
            self._set_running(False)
            return
        self._auth_attempts += 1
        if state == "gate":
            login_url = str(payload.get("login_url") or "")
            if login_url:
                current = self.view.url().toString() if self.view is not None else self.items_url_input.text().strip()
                self.view.load(QUrl(urljoin(current, login_url)))
            else:
                page = self.view.page() if self.view is not None else None
                if page is not None:
                    run_javascript_if_alive(page, "(function(){var b=document.querySelector('button#login,button[name=login]'); if(b){b.click();return true;}return false;})();")
            return
        if state == "login_form":
            creds = self._saved_zabbix_credentials()
            if not creds.get("login") or not creds.get("password"):
                self.status_label.setText("Zabbix: нет сохраненных логина/пароля")
                self._set_running(False)
                return
            script = self._autofill_script(creds["login"], creds["password"])
            page = self.view.page() if self.view is not None else None
            if page is not None:
                run_javascript_if_alive(page, script)
                QTimer.singleShot(1200, lambda: run_javascript_if_alive(page, AUTH_INSPECT_SCRIPT, self._on_auth_inspected))

    def _saved_zabbix_credentials(self):
        candidates = []
        zabbix_id = str(self.profile_combo.currentData() or "")
        if zabbix_id:
            candidates.append(self.credentials.get(zabbix_id))
        candidates.extend((self.credentials.get("zabbix"), self.credentials.get("Zabbix"), self.credentials))
        for value in candidates:
            if not isinstance(value, dict):
                continue
            login = value.get("login") or value.get("username") or value.get("user") or ""
            password = value.get("password") or value.get("pass") or value.get("secret") or ""
            if login and password:
                return {"login": str(login), "password": str(password)}
        return {"login": "", "password": ""}

    @staticmethod
    def _autofill_script(login, password):
        return r"""
(function() {
  var loginValue = __LOGIN__;
  var passwordValue = __PASSWORD__;
  var login = document.querySelector('input#name, input[name="name"], input[placeholder="Логин"]');
  var password = document.querySelector('input#password, input[name="password"], input[placeholder="Пароль"]');
  var submit = document.querySelector('input[name="enter"], input[type="submit"], button[type="submit"]');
  function setValue(input, value) {
    if (!input) return;
    input.focus(); input.value = value;
    input.dispatchEvent(new Event('input', {bubbles:true}));
    input.dispatchEvent(new Event('change', {bubbles:true}));
  }
  if (!login || !password) return false;
  setValue(login, loginValue); setValue(password, passwordValue);
  if (submit) submit.click();
  return true;
})();
""".replace("__LOGIN__", json.dumps(login)).replace("__PASSWORD__", json.dumps(password))

    def _after_ready_page(self):
        page = self.view.page() if self.view is not None else None
        if page is None:
            return
        if self._web_mode == "collector":
            run_javascript_if_alive(page, PASSAGE_ITEMS_COLLECTOR_SCRIPT, self._on_items_collected)
        elif self._web_mode == "report":
            self._start_report_runner()

    def _on_items_collected(self, result):
        try:
            payload = json.loads(result or "{}")
        except (TypeError, ValueError):
            payload = {}
        items = normalize_passage_items(payload.get("items") or [])
        if not items:
            self.status_label.setText("Itemid не найдены на странице и в localStorage")
            QMessageBox.warning(
                self,
                "Отчет по сработкам",
                "Itemid не найдены. Проверьте URL страницы элементов или импортируйте JSON со списком itemid.",
            )
            return
        self.passage_items = items
        save_passage_items_json(items, self._items_path())
        self.settings["passage_items_path"] = str(self.settings.get("passage_items_path") or "data/report_passage_items.json")
        save_config(self.config)
        self._update_items_label()
        self._refresh_csv_summary()
        self.status_label.setText(
            f"Itemid синхронизированы: {len(items)} (на странице найдено {payload.get('found_count', 0)})"
        )

    def start_report(self):
        if not self.csv_path:
            QMessageBox.warning(self, "Отчет по сработкам", "Сначала выберите CSV.")
            return
        if not self.passage_items:
            QMessageBox.warning(self, "Отчет по сработкам", "Сначала синхронизируйте itemid или импортируйте JSON itemid.")
            return
        date_from, date_to = self._current_dates()
        if date_from > date_to:
            QMessageBox.warning(self, "Отчет по сработкам", "Дата начала не может быть позже даты окончания.")
            return
        try:
            events = load_outages_from_csv(self.csv_path, date_from=date_from, date_to=date_to)
            self.aggregates = aggregate_outages(events)
            self.selected_aggregates = self._select_aggregates(self.aggregates)
        except Exception as exc:
            QMessageBox.warning(self, "Отчет по сработкам", str(exc))
            return
        if not self.selected_aggregates:
            QMessageBox.information(self, "Отчет по сработкам", "За выбранный период подходящих аварийных триггеров не найдено.")
            return

        default_name = f"Отчет_по_сработкам_{date_from.isoformat()}_{date_to.isoformat()}.csv"
        output, _ = QFileDialog.getSaveFileName(self, "Сохранить отчет", default_name, "CSV (*.csv)")
        if not output:
            return
        if not output.lower().endswith(".csv"):
            output += ".csv"
        self.output_path = output

        item_map = passage_item_map(self.passage_items)
        tasks = []
        for item in self.selected_aggregates:
            passage_item = item_map.get(normalize_host(item.host))
            if not passage_item:
                continue
            tasks.append(
                {
                    "date": item.report_date.isoformat(),
                    "host": item.host,
                    "itemid": passage_item["itemid"],
                }
            )
        self._pending_report_tasks = tasks
        self.passage_averages = {}
        self._report_auth_retries = 0
        self.progress.setValue(0)
        self._set_running(True)

        if not tasks:
            self.status_label.setText("Для узлов из CSV не найдено itemid. Формирую отчет без данных о проходах.")
            self._finalize_report()
            return

        self.settings["items_url"] = self.items_url_input.text().strip()
        self.settings["zabbix_id"] = str(self.profile_combo.currentData() or "")
        save_config(self.config)
        self.status_label.setText(f"Подготовка Zabbix: задач {len(tasks)}, максимум запросов {len(tasks) * 4}")
        self._load_source_page("report")

    def _start_report_runner(self):
        page = self.view.page() if self.view is not None else None
        if page is None:
            self._set_running(False)
            return
        script = REPORT_RUNNER_TEMPLATE.replace(
            "__TASKS__", json.dumps(self._pending_report_tasks, ensure_ascii=False)
        ).replace("__CONCURRENCY__", str(REPORT_CONCURRENCY))
        run_javascript_if_alive(page, script, self._on_report_runner_started)

    def _on_report_runner_started(self, result):
        try:
            payload = json.loads(result or "{}")
        except (TypeError, ValueError):
            payload = {}
        if not payload.get("started"):
            self.status_label.setText("Не удалось запустить сбор history.php")
            self._set_running(False)
            return
        self.status_label.setText(
            f"Сбор проходов: 0/{payload.get('total_tasks', 0)} задач, 0/{payload.get('total_requests', 0)} запросов"
        )
        self.poll_timer.start()

    def _poll_report_state(self):
        page = self.view.page() if self.view is not None else None
        if page is None:
            self.poll_timer.stop()
            return
        run_javascript_if_alive(page, REPORT_POLL_SCRIPT, self._on_report_state)

    def _on_report_state(self, result):
        try:
            payload = json.loads(result or "{}")
        except (TypeError, ValueError):
            return
        total_requests = max(1, int(payload.get("total_requests") or 0))
        completed_requests = int(payload.get("completed_requests") or 0)
        self.progress.setValue(min(100, int(completed_requests * 100 / total_requests)))
        self.status_label.setText(
            f"Сбор проходов: {payload.get('completed_tasks', 0)}/{payload.get('total_tasks', 0)} задач, "
            f"{completed_requests}/{payload.get('total_requests', 0)} запросов"
        )
        if not payload.get("done"):
            return
        self.poll_timer.stop()
        if payload.get("auth_required"):
            if self._report_auth_retries >= 2:
                self.status_label.setText("Сессия Zabbix истекла; автоматический повтор не удался")
                self._set_running(False)
                return
            self._report_auth_retries += 1
            self.status_label.setText("Сессия Zabbix истекла. Выполняю повторный вход…")
            self._load_source_page("report")
            return

        for item in payload.get("results") or []:
            avg = item.get("avg")
            if avg is None:
                continue
            try:
                report_date = date.fromisoformat(str(item.get("date") or ""))
                self.passage_averages[passage_average_key(report_date, str(item.get("host") or ""))] = float(avg)
            except (TypeError, ValueError):
                continue
        self._finalize_report()

    def _finalize_report(self):
        try:
            self.report_rows = build_report_rows(self.selected_aggregates, self.passage_averages)
            write_report_csv(self.report_rows, self.output_path)
            self._render_report()
            missing = sum(1 for row in self.report_rows if row.passage_average is None)
            self.progress.setValue(100)
            self.status_label.setText(
                f"Отчет готов: {len(self.report_rows)} строк. Без данных о проходах: {missing}. Файл: {self.output_path}"
            )
            QMessageBox.information(self, "Отчет по сработкам", f"Отчет сформирован:\n{self.output_path}")
        except Exception as exc:
            self.logger.exception("Failed to finalize trigger report")
            QMessageBox.warning(self, "Отчет по сработкам", str(exc))
        finally:
            self._set_running(False)

    def _render_report(self):
        self.table.setRowCount(len(self.report_rows))
        for row_index, row in enumerate(self.report_rows):
            values = (
                row.report_date.strftime("%d.%m.%Y"),
                row.host,
                format_duration(row.downtime_seconds),
                "" if row.passage_average is None else f"{row.passage_average:.4f}".replace(".", ","),
                "" if row.lost_passages is None else f"{row.lost_passages:.2f}".replace(".", ","),
            )
            for column, value in enumerate(values):
                self.table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def cancel_report(self):
        if not self.start_button.isEnabled():
            page = self.view.page() if self.view is not None else None
            if page is not None:
                run_javascript_if_alive(page, "(function(){if(window.__okoReportState){window.__okoReportState.cancelled=true;}return true;})();")
            self.poll_timer.stop()
            self.status_label.setText("Обработка остановлена пользователем")
            self._set_running(False)

    def _set_running(self, running: bool):
        self.start_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.date_from.setEnabled(not running)
        self.date_to.setEnabled(not running)
        self.mode_combo.setEnabled(not running)

    def cleanup(self):
        self.poll_timer.stop()
        page = self.view.page() if self.view is not None else None
        if page is not None:
            run_javascript_if_alive(page, "(function(){if(window.__okoReportState){window.__okoReportState.cancelled=true;}return true;})();")
        self._destroy_web_view()
