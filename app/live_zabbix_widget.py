"""Qt widget for the Live Zabbix Monitor."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import json

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import save_config
from app.live_zabbix import DOM_PARSER_SCRIPT_PLACEHOLDER, JS_HEALTH_CHECK_SCRIPT, JS_SMOKE_TEST_SCRIPT, SnapshotDiff, diff_snapshots, ensure_live_monitor_defaults, split_items_by_duty_filter
from app.logger import get_logger
from app.templates import get_redmine_task_template
from app.trigger_model import SPECIAL_TRIGGER_KIND, append_history_event, enrich_problem, format_graph_links
from app.webengine_lifecycle import register_web_view, safe_delete_web_view

DOM_PARSER_SCRIPT = DOM_PARSER_SCRIPT_PLACEHOLDER
WEBENGINE_JS_ERROR_MESSAGE = "Ошибка диагностики WebEngine: JS не вернул document.location.href. Проверьте выполнение runJavaScript, page.url/view.url и выбранный WebEngine profile."
JS_EMPTY_STRING_ERROR_MESSAGE = "Ошибка JS диагностики: runJavaScript вернул пустую строку. DOM-парсер не запускался корректно."
ZERO_PROBLEMS_MESSAGE = "Страница загружена, но проблемы не найдены. Возможные причины: страница логина, таблица ещё не загрузилась, DOM Zabbix не распознан."
ACKNOWLEDGE_PAGE_MESSAGE = "Открыта форма подтверждения Zabbix. Мониторинг страницы Problems не выполняется в этом WebView."


class ZabbixAcknowledgeDialog(QDialog):
    """Separate WebView for Zabbix acknowledge/update popup pages."""

    def __init__(self, profile, url, parent=None, closed_callback=None):
        super().__init__(parent)
        self.closed_callback = closed_callback
        self.setWindowTitle("Подтверждение Zabbix")
        self.resize(1100, 760)
        layout = QVBoxLayout(self)
        self.view = register_web_view(QWebEngineView(self))
        if profile is not None:
            self.page = QWebEnginePage(profile, self.view)
            self.view.setPage(self.page)
        layout.addWidget(self.view)
        self.view.load(QUrl(url))

    def closeEvent(self, event):
        view = self.view
        self.view = None
        if view is not None:
            safe_delete_web_view(view, logger=get_logger(), context="ZabbixAcknowledgeDialog")
        if self.closed_callback:
            self.closed_callback()
        super().closeEvent(event)


class LiveZabbixMonitorWidget(QWidget):
    """Minimal UI that polls a single Zabbix Problems page with the existing WebEngine session."""

    def __init__(self, config, profiles, credentials=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.profiles = profiles or {}
        self.credentials = credentials or {}
        self.settings = ensure_live_monitor_defaults(config)
        self.logger = get_logger()
        self.previous_snapshot = {}
        self.current_snapshot = {}
        self.all_snapshot = {}
        self.hidden_snapshot = {}
        self.last_filter_counts = {"raw": 0, "visible": 0, "hidden": 0}
        self.processed_keys = set()
        self.last_diff = SnapshotDiff()
        self.view = None
        self.page = None
        self.current_zabbix_id = ""
        self.profile_warning = ""
        self.profile_selection_reason = ""
        self.last_load_ok = None
        self._load_finished_connected = False
        self.last_js_health = None
        self.last_js_smoke = None
        self.last_js_result_meta = {}
        self._restoring_column_widths = False
        self.ack_dialogs = []
        self.last_separator_rows = []
        self._parse_attempts = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_now)
        self._build_ui()
        self._create_web_view()
        self._update_diagnostics({"safe_debug": {}, "items": []}, status_text="Остановлен")

    def _build_ui(self):
        root = QVBoxLayout(self)

        settings_form = QFormLayout()
        self.url_input = QLineEdit(self.problems_url())
        self.url_input.setPlaceholderText("https://zabbix.example/zabbix.php?action=problem.view")
        self.interval_input = QSpinBox()
        self.interval_input.setRange(5, 15)
        self.interval_input.setValue(int(self.settings.get("poll_interval_seconds", 10)))
        self.zabbix_profile_combo = QComboBox()
        self._populate_profile_combo()
        settings_form.addRow("URL Zabbix Problems:", self.url_input)
        settings_form.addRow("Интервал опроса:", self.interval_input)
        settings_form.addRow("WebEngine profile:", self.zabbix_profile_combo)
        root.addLayout(settings_form)

        controls = QHBoxLayout()
        self.start_button = QPushButton("Старт")
        self.stop_button = QPushButton("Стоп")
        self.check_dom_button = QPushButton("Проверить DOM")
        self.save_button = QPushButton("Сохранить")
        self.open_url_button = QPushButton("Открыть URL в браузере")
        self.show_webview_button = QPushButton("Показать WebView")
        self.open_redmine_button = QPushButton("Открыть Redmine")
        self.poll_status_label = QLabel("Остановлен")
        self.updated_label = QLabel("Последнее обновление: —")
        self.duty_filter_checkbox = QCheckBox("Только интересующие")
        self.duty_filter_checkbox.setChecked(bool(self.settings.get("duty_filter_enabled", True)))
        self.duty_filter_checkbox.toggled.connect(self._on_duty_filter_toggled)
        self.counts_label = QLabel("Новые: 0 | Активные: 0 | Решённые: 0 | Обработанные: 0 | Всего: 0 | Показано: 0 | Скрыто фильтром: 0")
        self.start_button.clicked.connect(self.start_monitor)
        self.stop_button.clicked.connect(self.stop_monitor)
        self.check_dom_button.clicked.connect(self.check_dom_now)
        self.save_button.clicked.connect(self.save_monitor_settings)
        self.open_url_button.clicked.connect(self.open_configured_url)
        self.show_webview_button.clicked.connect(self.show_webview)
        self.open_redmine_button.clicked.connect(self.open_redmine_for_selected_row)
        for widget in [self.start_button, self.stop_button, self.check_dom_button, self.save_button, self.open_url_button, self.show_webview_button, self.open_redmine_button, self.duty_filter_checkbox, self.poll_status_label, self.updated_label]:
            controls.addWidget(widget)
        controls.addStretch()
        controls.addWidget(self.counts_label)
        root.addLayout(controls)

        self.diagnostics_text = QPlainTextEdit()
        self.diagnostics_text.setReadOnly(True)
        self.diagnostics_text.setMaximumHeight(220)
        self.diagnostics_text.setPlaceholderText("Диагностика DOM")
        root.addWidget(QLabel("Диагностика DOM"))
        root.addWidget(self.diagnostics_text)

        self.table_columns = [
            "Время",
            "Важность",
            "Инфо",
            "Узел сети",
            "Проблема",
            "Длительность",
            "Подтверждено",
            "Действия",
            "Теги",
        ]
        self.table = QTableWidget(0, len(self.table_columns))
        self.table.setHorizontalHeaderLabels(self.table_columns)
        self.table.setObjectName("LiveZabbixProblemsTable")
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setStyleSheet(
            """
            QTableWidget#LiveZabbixProblemsTable {
                font-size: 10px;
                gridline-color: rgba(128, 128, 128, 90);
            }
            QTableWidget#LiveZabbixProblemsTable::item {
                padding: 1px 3px;
            }
            QHeaderView::section {
                font-size: 10px;
                padding: 2px 4px;
            }
            """
        )
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.verticalHeader().setMinimumSectionSize(18)
        self.table.cellClicked.connect(self._on_table_cell_clicked)
        self._configure_table_columns()
        root.addWidget(self.table, stretch=1)

    def _configure_table_columns(self):
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        defaults = [105, 82, 42, 145, 460, 76, 86, 120, 130]
        widths = self.settings.get("table_column_widths") or defaults
        self._restoring_column_widths = True
        for index, width in enumerate(defaults):
            value = widths[index] if index < len(widths) else width
            self.table.setColumnWidth(index, max(60, int(value)))
        self._restoring_column_widths = False
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.sectionResized.connect(self._save_table_column_widths)

    def _save_table_column_widths(self, *_args):
        if self._restoring_column_widths:
            return
        self.settings["table_column_widths"] = [self.table.columnWidth(index) for index in range(self.table.columnCount())]
        save_config(self.config)

    def _profile_for_url(self, url):
        configured = str(self.settings.get("zabbix_id") or "").strip()
        if configured:
            reason = "Выбран явно в live_zabbix_monitor.zabbix_id."
            return configured, self.profiles.get(configured), "" if configured in self.profiles else f"Профиль {configured!r} не найден.", reason
        host = (urlparse(url or "").hostname or "").casefold()
        if host:
            for instance in self.config.get("zabbix_instances", []):
                if not instance.get("enabled", True):
                    continue
                candidates = [instance.get("login_url", ""), instance.get("url", ""), instance.get("base_url", "")]
                if any((urlparse(value).hostname or "").casefold() == host for value in candidates if value):
                    zabbix_id = instance.get("id", "")
                    reason = "Определён по домену URL Zabbix Problems."
                    return zabbix_id, self.profiles.get(zabbix_id), "" if zabbix_id in self.profiles else f"Профиль {zabbix_id!r} найден по URL, но WebEngine profile отсутствует.", reason
        fallback = self._first_zabbix_id()
        warning = "Не удалось определить Zabbix profile по URL; используется первый доступный профиль." if fallback else "Не удалось определить Zabbix profile: нет доступных профилей."
        reason = "Fallback: live_zabbix_monitor.zabbix_id пустой и домен URL не совпал с zabbix_instances."
        return fallback, self.profiles.get(fallback), warning, reason

    def _create_web_view(self):
        self.current_zabbix_id, profile, self.profile_warning, self.profile_selection_reason = self._profile_for_url(self.problems_url())
        self.view = register_web_view(QWebEngineView())
        if profile is not None:
            self.page = QWebEnginePage(profile, self.view)
            self.view.setPage(self.page)
        self.view.hide()

    def _recreate_web_view_if_needed(self):
        zabbix_id, profile, warning, reason = self._profile_for_url(self.problems_url())
        if self.view is not None and zabbix_id == self.current_zabbix_id:
            self.profile_warning = warning
            self.profile_selection_reason = reason
            return
        if self.view is not None:
            safe_delete_web_view(self.view, logger=self.logger, context="LiveZabbixMonitorWidget profile switch", load_handler=self._on_loaded)
            self._load_finished_connected = False
        self.current_zabbix_id = zabbix_id
        self.profile_warning = warning
        self.profile_selection_reason = reason
        self.view = register_web_view(QWebEngineView())
        if profile is not None:
            self.page = QWebEnginePage(profile, self.view)
            self.view.setPage(self.page)
        self.view.hide()

    def _populate_profile_combo(self):
        self.zabbix_profile_combo.clear()
        self.zabbix_profile_combo.addItem("Авто по URL", "")
        selected = str(self.settings.get("zabbix_id") or "")
        for instance in self.config.get("zabbix_instances", []):
            if not instance.get("enabled", True):
                continue
            zabbix_id = str(instance.get("id") or "")
            if not zabbix_id:
                continue
            label = str(instance.get("name") or zabbix_id)
            self.zabbix_profile_combo.addItem(f"{label} ({zabbix_id})", zabbix_id)
        for index in range(self.zabbix_profile_combo.count()):
            if self.zabbix_profile_combo.itemData(index) == selected:
                self.zabbix_profile_combo.setCurrentIndex(index)
                break

    def _first_zabbix_id(self):
        for instance in self.config.get("zabbix_instances", []):
            if instance.get("enabled", True):
                return instance.get("id", "")
        return ""

    def problems_url(self):
        if self.settings.get("problems_url"):
            return self.settings.get("problems_url")
        for product in self.config.get("products", []) or []:
            for dashboard in product.get("dashboards", []) or []:
                if dashboard.get("type") == "problems_page" and dashboard.get("url"):
                    return dashboard.get("url")
        return ""

    def save_monitor_settings(self):
        self.settings["problems_url"] = self.url_input.text().strip()
        self.settings["poll_interval_seconds"] = int(self.interval_input.value())
        self.settings["zabbix_id"] = str(self.zabbix_profile_combo.currentData() or "")
        self.settings["duty_filter_enabled"] = bool(self.duty_filter_checkbox.isChecked())
        save_config(self.config)
        self._recreate_web_view_if_needed()
        self._update_diagnostics({"safe_debug": {}, "items": []}, status_text="Настройки сохранены")

    def _on_duty_filter_toggled(self, checked):
        self.settings["duty_filter_enabled"] = bool(checked)
        save_config(self.config)
        if self.all_snapshot:
            visible, hidden = split_items_by_duty_filter(self.config, self.all_snapshot.values(), filter_enabled=bool(checked))
            self.hidden_snapshot = {item.key: item for item in hidden}
            self.current_snapshot = {item.key: item for item in visible}
            self.last_filter_counts = {"raw": len(self.all_snapshot), "visible": len(visible), "hidden": len(hidden)}
            diff = diff_snapshots(self.previous_snapshot.values(), visible, self.processed_keys)
            self.last_diff = diff
            self.previous_snapshot = dict(self.current_snapshot)
            self._render(diff, {"items": [item.to_dict() for item in visible], "safe_debug": {}})

    def _filter_separators_for_visible_items(self, separators, visible_items):
        separators = [row for row in (separators or []) if str(row.get("text") or "").strip()]
        if not separators or not visible_items:
            return []
        visible_indexes = sorted(index for index in (getattr(item, "row_index", -1) for item in visible_items) if index >= 0)
        if not visible_indexes:
            return separators
        result = []
        for index, separator in enumerate(separators):
            try:
                start = int(separator.get("row_index", -1))
            except (TypeError, ValueError):
                start = -1
            try:
                end = int(separators[index + 1].get("row_index", 10**9)) if index + 1 < len(separators) else 10**9
            except (TypeError, ValueError):
                end = 10**9
            if any(start < item_index < end for item_index in visible_indexes):
                result.append(separator)
        return result

    def open_configured_url(self):
        url = self.url_input.text().strip()
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def show_webview(self):
        if self.view is None:
            return
        self.view.resize(1280, 800)
        self.view.show()
        self.view.raise_()
        self.view.activateWindow()

    def start_monitor(self):
        self.save_monitor_settings()
        url = self.problems_url()
        if not url:
            self.poll_status_label.setText("Ошибка: URL Zabbix Problems не задан")
            return
        self.poll_status_label.setText("Запуск")
        if not self._load_finished_connected:
            self.view.loadFinished.connect(self._on_loaded)
            self._load_finished_connected = True
        self.view.load(QUrl(url))
        self.timer.start(int(self.settings.get("poll_interval_seconds", 10)) * 1000)

    def stop_monitor(self):
        self.timer.stop()
        self.poll_status_label.setText("Остановлен")

    def poll_now(self):
        if self.view is not None:
            self.poll_status_label.setText("Опрос страницы…")
            self.view.reload()

    def check_dom_now(self):
        if self.view is None:
            return
        self.poll_status_label.setText("Проверка DOM…")
        self._run_dom_parser(force=True)

    def _on_loaded(self, ok):
        self.last_load_ok = bool(ok)
        if not ok:
            self.poll_status_label.setText("Ошибка загрузки Zabbix Problems")
            self._update_diagnostics({"safe_debug": {}, "items": [], "ok": False}, status_text="Ошибка загрузки Zabbix Problems")
            return
        self.poll_status_label.setText("Страница загружена, ждём DOM…")
        self._parse_attempts = []
        for delay_ms in (500, 1500, 3000):
            QTimer.singleShot(delay_ms, lambda force=False: self._run_dom_parser(force=force))

    def _run_dom_parser(self, force=False):
        if self.view is not None and self.view.page() is not None:
            self.view.page().runJavaScript(JS_SMOKE_TEST_SCRIPT, lambda smoke: self._on_js_smoke_checked(smoke, force=force))

    def _js_result_meta(self, result):
        preview = repr(result)
        if len(preview) > 500:
            preview = preview[:500] + "…"
        return {
            "js_result_type": type(result).__name__,
            "js_result_is_none": result is None,
            "js_result_preview": preview,
        }

    def _decode_js_json_result(self, result):
        meta = self._js_result_meta(result)
        if result is None:
            meta["js_result_error"] = "JS diagnostic returned None / invalid result"
            return None, meta
        if isinstance(result, str):
            if result == "":
                meta["js_result_error"] = "JS returned empty string"
                return None, meta
            try:
                return json.loads(result), meta
            except json.JSONDecodeError as exc:
                meta["js_result_error"] = f"JSON parse error: {exc}"
                return None, meta
        if isinstance(result, dict):
            return result, meta
        meta["js_result_error"] = "JS diagnostic returned invalid result type"
        return None, meta

    def _js_error_status(self, meta):
        if meta.get("js_result_error") == "JS returned empty string":
            return JS_EMPTY_STRING_ERROR_MESSAGE
        return WEBENGINE_JS_ERROR_MESSAGE

    def _js_error_payload(self, meta, health_check=None, smoke_check=None):
        return {
            "ok": False,
            "items": [],
            "safe_debug": {
                "zero_reason": meta.get("js_result_error") or "JS diagnostic returned None / invalid result",
                "health_check": health_check or {},
                "smoke_check": smoke_check or {},
            },
        }

    def _on_js_smoke_checked(self, smoke_result, force=False):
        smoke, meta = self._decode_js_json_result(smoke_result)
        self.last_js_smoke = smoke
        self.last_js_result_meta = meta
        if not isinstance(smoke, dict) or smoke.get("smoke") != "ok":
            payload = self._js_error_payload(meta, smoke_check=smoke if isinstance(smoke, dict) else {})
            self._parse_attempts.append(payload)
            self._update_diagnostics(payload, status_text=self._js_error_status(meta))
            return
        self.view.page().runJavaScript(JS_HEALTH_CHECK_SCRIPT, lambda health: self._on_js_health_checked(health, force=force))

    def _on_js_health_checked(self, health_result, force=False):
        health, meta = self._decode_js_json_result(health_result)
        self.last_js_health = health
        self.last_js_result_meta = meta
        if not isinstance(health, dict) or not str(health.get("href") or ""):
            payload = self._js_error_payload(meta, health_check=health if isinstance(health, dict) else {})
            self._parse_attempts.append(payload)
            self._update_diagnostics(payload, status_text=self._js_error_status(meta))
            return
        self.view.page().runJavaScript(DOM_PARSER_SCRIPT, lambda result: self._on_dom_parsed(result, force=force))

    def _history_path(self) -> Path:
        path = Path(str(self.settings.get("history_path") or "data/live_zabbix_history.jsonl"))
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        return path

    def _on_dom_parsed(self, payload, force=False):
        payload, meta = self._decode_js_json_result(payload)
        self.last_js_result_meta = meta
        if isinstance(payload, list):
            payload = {"ok": True, "items": payload, "safe_debug": {"problem_count": len(payload)}}
        if not isinstance(payload, dict):
            payload = self._js_error_payload(meta)
            self._parse_attempts.append(payload)
            self._update_diagnostics(payload, status_text=self._js_error_status(meta))
            return
        raw_items = payload.get("items") or []
        raw_separators = payload.get("separators") or []
        self._parse_attempts.append(payload)
        if not force and not raw_items and len(self._parse_attempts) < 3:
            self._update_diagnostics(payload, status_text="Страница загружена, ждём таблицу Zabbix Problems…")
            return
        if not force and raw_items:
            self._parse_attempts = []
        all_items = []
        for raw in raw_items:
            item = enrich_problem(self.config, raw or {}, processed_keys=self.processed_keys)
            if raw.get("graph_urls") and not item.graph_urls:
                item.graph_urls = [url for url in raw.get("graph_urls", []) if url]
            all_items.append(item)
        filter_enabled = bool(self.settings.get("duty_filter_enabled", True))
        visible_items, hidden_items = split_items_by_duty_filter(self.config, all_items, filter_enabled=filter_enabled)
        self.last_filter_counts = {"raw": len(all_items), "visible": len(visible_items), "hidden": len(hidden_items)}
        self.last_separator_rows = self._filter_separators_for_visible_items(raw_separators, visible_items)
        payload["raw_problem_count"] = len(all_items)
        payload["visible_problem_count"] = len(visible_items)
        payload["hidden_by_filter_count"] = len(hidden_items)
        payload["duty_filter_enabled"] = filter_enabled
        payload.setdefault("safe_debug", {})
        payload["safe_debug"].update({
            "raw_problem_count": len(all_items),
            "visible_problem_count": len(visible_items),
            "hidden_by_filter_count": len(hidden_items),
            "duty_filter_enabled": filter_enabled,
        })
        diff = diff_snapshots(self.previous_snapshot.values(), visible_items, self.processed_keys)
        self.last_diff = diff
        self.all_snapshot = {item.key: item for item in all_items}
        self.hidden_snapshot = {item.key: item for item in hidden_items}
        self.current_snapshot = {item.key: item for item in visible_items}
        self._write_history(diff)
        self.previous_snapshot = dict(self.current_snapshot)
        self._render(diff, payload)

    def _write_history(self, diff):
        for event_name, items in (("new", diff.new), ("active", diff.active), ("resolved", diff.resolved), ("processed", diff.processed)):
            for item in items:
                append_history_event(self._history_path(), event_name, item)

    @staticmethod
    def _safe_url_for_report(value):
        parsed = urlparse(value or "")
        query = "&".join(f"{key}=***" for key in [part.split("=", 1)[0] for part in parsed.query.split("&") if part])
        return (parsed.path or "") + (f"?{query}" if query else "")

    @staticmethod
    def _masked_host(value):
        host = urlparse(value or "").hostname or ""
        if not host:
            return ""
        parts = host.split(".")
        if len(parts) <= 2:
            return "***." + parts[-1]
        return "***." + ".".join(parts[-2:])

    def _qwebengine_url_diagnostics(self):
        requested = self.problems_url()
        qurl = QUrl(requested)
        view_url = self.view.url().toString() if self.view is not None else ""
        page_url = self.view.page().url().toString() if self.view is not None and self.view.page() is not None else ""
        return {
            "requested_url_full_masked": self._safe_url_for_report(requested),
            "qurl_is_valid": qurl.isValid(),
            "qurl_scheme": qurl.scheme(),
            "qurl_host_masked": self._masked_host(requested),
            "view_url_after_load": self._safe_url_for_report(view_url),
            "page_url_after_load": self._safe_url_for_report(page_url),
            "load_finished_ok": self.last_load_ok,
        }

    @staticmethod
    def _acknowledge_detected_reason(url_value, title_value):
        title = str(title_value or "")
        url = str(url_value or "")
        if "проблемы" in title.casefold():
            return ""
        parsed = urlparse(url)
        query = dict(part.split("=", 1) if "=" in part else (part, "") for part in parsed.query.split("&") if part)
        if query.get("action") == "popup.acknowledge.create":
            return "action=popup.acknowledge.create"
        popup_action = query.get("popup_action", "")
        if popup_action in {"acknowledge.edit", "acknowledge.create"}:
            return "popup_action=acknowledge"
        if "обновление проблемы" in title.casefold():
            return "title contains Обновление проблемы"
        return ""

    def _diagnostic_payload(self, payload):
        safe_debug = dict((payload or {}).get("safe_debug") or {})
        health = self.last_js_health if isinstance(self.last_js_health, dict) else {}
        smoke = self.last_js_smoke if isinstance(self.last_js_smoke, dict) else {}
        safe_debug.update({
            "used_url": self._safe_url_for_report(self.problems_url()),
            "document_location_href": safe_debug.get("url_path") or "",
            "document_title": safe_debug.get("title") or (payload or {}).get("title", ""),
            "zabbix_id": self.current_zabbix_id,
            "available_zabbix_ids": [str(instance.get("id") or "") for instance in self.config.get("zabbix_instances", []) if instance.get("enabled", True) and instance.get("id")],
            "selected_zabbix_id": self.current_zabbix_id,
            "profile_selection_reason": self.profile_selection_reason,
            "webengine_profile_used": bool(self.current_zabbix_id and self.current_zabbix_id in self.profiles),
            "profile_warning": self.profile_warning,
            "loadFinished": "ok" if self.last_load_ok else ("error" if self.last_load_ok is False else "not_loaded"),
            "js_health_check": {
                "href": self._safe_url_for_report(health.get("href", "")),
                "title": str(health.get("title", ""))[:160],
                "readyState": health.get("readyState", ""),
                "bodyExists": health.get("bodyExists", False),
                "bodyTextLength": health.get("bodyTextLength", -1),
                "htmlLength": health.get("htmlLength", -1),
            },
            "js_smoke_test": {
                "smoke": smoke.get("smoke", ""),
                "href": self._safe_url_for_report(smoke.get("href", "")),
            },
            "login_detected": bool((payload or {}).get("login_detected") or safe_debug.get("login_detected")),
            "table_count": int((payload or {}).get("table_count") or safe_debug.get("table_count") or 0),
            "tr_count": int((payload or {}).get("tr_count") or safe_debug.get("tr_count") or 0),
            "candidate_count": int((payload or {}).get("candidate_count") or safe_debug.get("candidate_count") or 0),
            "problem_table_found": bool((payload or {}).get("problem_table_found") or safe_debug.get("problem_table_found", False)),
            "direct_problem_rows_count": int((payload or {}).get("direct_problem_rows_count") or safe_debug.get("direct_problem_rows_count") or 0),
            "nested_rows_skipped": int((payload or {}).get("nested_rows_skipped") or safe_debug.get("nested_rows_skipped") or 0),
            "invalid_problem_rows_skipped": int((payload or {}).get("invalid_problem_rows_skipped") or safe_debug.get("invalid_problem_rows_skipped") or 0),
            "history_rows_skipped": int((payload or {}).get("history_rows_skipped") or safe_debug.get("history_rows_skipped") or 0),
            "sample_skipped_rows": (payload or {}).get("sample_skipped_rows") or safe_debug.get("sample_skipped_rows") or [],
            "problem_count": int((payload or {}).get("problem_count") or safe_debug.get("problem_count") or len((payload or {}).get("items") or [])),
            "raw_problem_count": int((payload or {}).get("raw_problem_count") or safe_debug.get("raw_problem_count") or self.last_filter_counts.get("raw", 0)),
            "visible_problem_count": int((payload or {}).get("visible_problem_count") or safe_debug.get("visible_problem_count") or self.last_filter_counts.get("visible", 0)),
            "hidden_by_filter_count": int((payload or {}).get("hidden_by_filter_count") or safe_debug.get("hidden_by_filter_count") or self.last_filter_counts.get("hidden", 0)),
            "duty_filter_enabled": bool((payload or {}).get("duty_filter_enabled", safe_debug.get("duty_filter_enabled", self.settings.get("duty_filter_enabled", True)))),
            "zero_reason": (payload or {}).get("zero_reason") or safe_debug.get("zero_reason") or "",
            "acknowledge_detected_reason": (payload or {}).get("acknowledge_detected_reason") or safe_debug.get("acknowledge_detected_reason") or "",
        })
        safe_debug.update(self._qwebengine_url_diagnostics())
        safe_debug.update(self.last_js_result_meta or {})
        if safe_debug["problem_count"] == 0 and not safe_debug["zero_reason"]:
            safe_debug["zero_reason"] = ZERO_PROBLEMS_MESSAGE
        if safe_debug.get("js_result_error") == "JS returned empty string":
            safe_debug["zero_reason"] = JS_EMPTY_STRING_ERROR_MESSAGE
        if safe_debug.get("load_finished_ok") is True and not safe_debug.get("document_location_href") and safe_debug.get("js_result_is_none"):
            safe_debug["zero_reason"] = WEBENGINE_JS_ERROR_MESSAGE
        acknowledge_reason = safe_debug.get("acknowledge_detected_reason") or self._acknowledge_detected_reason(health.get("href", ""), health.get("title", ""))
        safe_debug["acknowledge_detected_reason"] = acknowledge_reason
        if acknowledge_reason:
            safe_debug["zero_reason"] = ACKNOWLEDGE_PAGE_MESSAGE
        return safe_debug

    def _update_diagnostics(self, payload, status_text=None):
        report = self._diagnostic_payload(payload)
        self.diagnostics_text.setPlainText(json.dumps(report, ensure_ascii=False, indent=2))
        if status_text:
            self.poll_status_label.setText(status_text)

    def _clickable_cell_foreground(self) -> QColor:
        theme_name = str((self.config.get("settings", {}) if isinstance(self.config, dict) else {}).get("theme") or "").casefold()
        light_themes = {"white_1", "light_standard"}
        if theme_name in light_themes or theme_name.startswith("white") or "light" in theme_name or "свет" in theme_name:
            return QColor("#000000")
        return QColor("#ffffff")

    def _render(self, diff, payload=None):
        all_items = diff.new + diff.active + diff.resolved + diff.processed
        separator_rows = [row for row in self.last_separator_rows if str(row.get("text") or "").strip()]
        self.table.setRowCount(len(all_items) + len(separator_rows))
        table_row = 0
        for separator in separator_rows:
            label = QTableWidgetItem(str(separator.get("text") or ""))
            label.setTextAlignment(Qt.AlignCenter)
            label.setBackground(QColor("#263238"))
            self.table.setItem(table_row, 0, label)
            self.table.setSpan(table_row, 0, 1, self.table.columnCount())
            table_row += 1
        for item in all_items:
            row = table_row
            values = [
                item.started_at,
                item.severity,
                item.info,
                item.host,
                item.trigger_name,
                item.duration,
                item.ack_text or ("Да" if item.acknowledged else "Нет"),
                item.actions_text,
                item.tags,
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value or ""))
                cell.setData(Qt.UserRole + 1, item.key)
                if column == 1:
                    color = self._severity_color(item.severity_level, item.severity_class, item.severity)
                    if color:
                        cell.setBackground(QColor(color))
                    cell.setForeground(QColor("#000000"))
                if column == 6 and (item.ack_url or item.problem_url):
                    cell.setForeground(self._clickable_cell_foreground())
                    font = cell.font()
                    font.setUnderline(True)
                    cell.setFont(font)
                    cell.setToolTip("Открыть подтверждение Zabbix")
                    cell.setData(Qt.UserRole, item.ack_url or item.problem_url)
                if column == 3 and item.host_url:
                    cell.setForeground(self._clickable_cell_foreground())
                    font = cell.font()
                    font.setUnderline(True)
                    cell.setFont(font)
                    cell.setToolTip("Открыть узел")
                    cell.setData(Qt.UserRole, item.host_url)
                if column == 4 and (item.graph_urls or item.problem_url):
                    cell.setForeground(self._clickable_cell_foreground())
                    font = cell.font()
                    font.setUnderline(True)
                    cell.setFont(font)
                    cell.setToolTip("Открыть график/проблему")
                    cell.setData(Qt.UserRole, {"graph_urls": list(item.graph_urls), "problem_url": item.problem_url})
                if column == 7 and item.actions_tooltip:
                    cell.setToolTip(item.actions_tooltip)
                self.table.setItem(row, column, cell)
            table_row += 1
        self.counts_label.setText(f"Новые: {len(diff.new)} | Активные: {len(diff.active)} | Решённые: {len(diff.resolved)} | Обработанные: {len(diff.processed)} | Всего: {self.last_filter_counts.get('raw', len(all_items))} | Показано: {self.last_filter_counts.get('visible', len(all_items))} | Скрыто фильтром: {self.last_filter_counts.get('hidden', 0)}")
        self.updated_label.setText("Последнее обновление: " + datetime.now().strftime("%H:%M:%S"))
        if all_items:
            self.poll_status_label.setText(f"ОК: проблем {len(all_items)}")
        elif self.last_filter_counts.get("raw", 0) and self.last_filter_counts.get("hidden", 0):
            self.poll_status_label.setText(f"ОК: показано 0, скрыто фильтром {self.last_filter_counts.get('hidden', 0)}")
        elif (payload or {}).get("safe_debug", {}).get("zero_reason") == "JS diagnostic returned None / invalid result":
            self.poll_status_label.setText(WEBENGINE_JS_ERROR_MESSAGE)
        else:
            self.poll_status_label.setText(ZERO_PROBLEMS_MESSAGE)
        self._update_diagnostics(payload or {"safe_debug": {}, "items": []})

    @staticmethod
    def _severity_color(level, severity_class="", severity_text=""):
        key = " ".join([str(level or ""), str(severity_class or ""), str(severity_text or "")]).casefold()
        if "disaster" in key or "чрезвычай" in key:
            return "#e45959"
        if "high" in key or "высок" in key:
            return "#ff8a65"
        if "average" in key or "средн" in key:
            return "#ffb74d"
        if "warning" in key or "предупр" in key:
            return "#ffd54f"
        if "info" in key or "информ" in key:
            return "#64b5f6"
        if "na-bg" in key or "not_classified" in key or "не классиф" in key:
            return "#b0bec5"
        return ""

    class _SafeTemplateValues(dict):
        def __missing__(self, key):
            return "{" + str(key) + "}"

    def _unique_live_items(self, items):
        result = []
        seen = set()
        for item in items or []:
            key = getattr(item, "key", "") or str(id(item))
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def _selected_live_problem_items(self):
        rows = sorted({cell.row() for cell in self.table.selectedItems() if cell is not None})
        if not rows:
            row = self.table.currentRow()
            if row >= 0:
                rows = [row]

        result = []
        for row in rows:
            key = ""
            for column in range(self.table.columnCount()):
                cell = self.table.item(row, column)
                if cell is None:
                    continue
                key = cell.data(Qt.UserRole + 1)
                if key:
                    break
            if key and key in self.current_snapshot:
                result.append(self.current_snapshot[key])
            elif key and key in self.all_snapshot:
                result.append(self.all_snapshot[key])
        return self._unique_live_items(result)

    def _same_host_visible_items(self, host):
        host_key = str(host or "").strip().casefold()
        if not host_key:
            return []
        return self._unique_live_items(
            item
            for item in self.current_snapshot.values()
            if str(item.host or "").strip().casefold() == host_key
        )

    def _choose_redmine_items_for_selection(self):
        items = self._selected_live_problem_items()
        if not items:
            return []

        if len(items) == 1:
            same_host_items = self._same_host_visible_items(items[0].host)
            if len(same_host_items) > 1:
                host = str(items[0].host or "узел сети")
                answer = QMessageBox.question(
                    self,
                    "Redmine",
                    f"По узлу «{host}» найдено проблем: {len(same_host_items)}.\n\n"
                    "Создать одну задачу по всем проблемам этого узла?\n\n"
                    "Да — все проблемы узла.\n"
                    "Нет — только выбранная строка.",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.Yes,
                )
                if answer == QMessageBox.Cancel:
                    return []
                if answer == QMessageBox.Yes:
                    return same_host_items

        return items

    @staticmethod
    def _unique_text_values(values):
        result = []
        seen = set()
        for value in values or []:
            text = str(value or "").strip()
            key = text.casefold()
            if not text or key in seen:
                continue
            seen.add(key)
            result.append(text)
        return result

    def _redmine_subject(self, items):
        items = self._unique_live_items(items)
        hosts = self._unique_text_values(getattr(item, "host", "") for item in items)
        triggers = self._unique_text_values(getattr(item, "trigger_name", "") for item in items)

        if len(items) == 1:
            host = hosts[0] if hosts else "узле сети"
            trigger = triggers[0] if triggers else "Zabbix"
            return f"На {host} наблюдается триггер {trigger}"

        if len(hosts) == 1:
            return f"На {hosts[0]} наблюдаются триггеры"

        return "На нескольких узлах наблюдаются триггеры"

    def _redmine_graph_link_for_item(self, item):
        graph_urls = list(getattr(item, "graph_urls", []) or [])
        if graph_urls:
            return str(graph_urls[0] or "")
        return str(getattr(item, "problem_url", "") or "")

    def _redmine_description(self, items):
        items = self._unique_live_items(items)
        hosts = self._unique_text_values(getattr(item, "host", "") for item in items)
        host_text = hosts[0] if len(hosts) == 1 else "несколько узлов"

        lines = [
            f"Узел: {host_text}",
            "IP: не определён",
            "",
            "Триггеры:",
        ]

        for index, item in enumerate(items, start=1):
            trigger_name = str(getattr(item, "trigger_name", "") or "Проблема Zabbix").strip()
            lines.append(f"{index}. {trigger_name}")

            graph_link = self._redmine_graph_link_for_item(item)
            if graph_link:
                lines.append(f"Ссылка на график: {graph_link}")
            else:
                lines.append("Ссылка на график: не найдена")

            lines.append("")

        return "\n".join(lines).strip()

    def _combined_graph_urls(self, items):
        urls = []
        seen = set()
        for item in items or []:
            for url in getattr(item, "graph_urls", []) or []:
                text = str(url or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                urls.append(text)
        return urls

    @staticmethod
    def _merge_redmine_url_params(base_url, dynamic_params, default_params=None):
        parsed = urlparse(str(base_url or ""))
        existing_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        dynamic_keys = set(dynamic_params)
        default_params = default_params or {}

        result_pairs = []
        existing_keys = set()
        for key, value in existing_pairs:
            existing_keys.add(key)
            if key not in dynamic_keys:
                result_pairs.append((key, value))

        for key, value in default_params.items():
            if value not in (None, "") and key not in existing_keys and key not in dynamic_keys:
                result_pairs.append((key, str(value)))

        for key, value in dynamic_params.items():
            if value not in (None, ""):
                result_pairs.append((key, str(value)))

        query = urlencode(result_pairs, doseq=True)
        return urlunparse(parsed._replace(query=query))

    def _build_redmine_open_url(self, items):
        items = self._unique_live_items(items)
        if not items:
            return "", "Проблемы для Redmine не выбраны."

        is_special = any(str(getattr(item, "trigger_kind", "") or "").casefold() == SPECIAL_TRIGGER_KIND for item in items)
        template = get_redmine_task_template(self.config, special=is_special)

        create_url = str(template.get("create_url") or "").strip()
        if not create_url:
            return "", "URL создания задачи Redmine не задан в настройках шаблона."

        subject = self._redmine_subject(items)
        description = self._redmine_description(items)

        default_params = {
            "issue[tracker_id]": str(template.get("tracker_id") or "32"),
            "issue[assigned_to_id]": str(template.get("assigned_to_id") or "1121"),
            "issue[custom_field_values][94]": str(template.get("custom_field_94") or "Применим"),
        }

        if template.get("priority_id"):
            default_params["issue[priority_id]"] = str(template.get("priority_id"))

        dynamic_params = {
            "issue[subject]": subject,
            "issue[description]": description,
        }

        redmine_url = self._merge_redmine_url_params(create_url, dynamic_params, default_params)
        if len(redmine_url) > 6500:
            return redmine_url, f"Redmine-ссылка всё ещё длинная: {len(redmine_url)} символов. Лучше выбрать меньше строк."

        return redmine_url, ""

    def open_redmine_for_selected_row(self):
        items = self._choose_redmine_items_for_selection()
        if not items:
            QMessageBox.information(self, "Redmine", "Выберите одну или несколько строк проблемы в Live Zabbix Monitor.")
            return

        redmine_url, warning = self._build_redmine_open_url(items)
        if not redmine_url:
            QMessageBox.warning(self, "Redmine", warning or "Не удалось собрать ссылку Redmine.")
            return

        if warning:
            QMessageBox.warning(self, "Redmine", warning)

        is_special = any(str(getattr(item, "trigger_kind", "") or "").casefold() == SPECIAL_TRIGGER_KIND for item in items)
        graph_urls = self._combined_graph_urls(items)
        if is_special and graph_urls:
            if QMessageBox.question(
                self,
                "Redmine",
                "Среди выбранных проблем есть специальный триггер. Открыть связанные графики для ручной проверки?",
                QMessageBox.Open | QMessageBox.Cancel,
            ) == QMessageBox.Open:
                self.open_graphs(graph_urls)

        opened = QDesktopServices.openUrl(QUrl(redmine_url))
        if not opened:
            QMessageBox.warning(self, "Redmine", "Не удалось открыть Redmine-ссылку в браузере.")

    def open_acknowledgement(self, url):
        if not url:
            return
        profile = self.view.page().profile() if self.view is not None and self.view.page() is not None else None
        dialog = ZabbixAcknowledgeDialog(profile, url, parent=self, closed_callback=self.poll_now)
        self.ack_dialogs.append(dialog)
        dialog.finished.connect(lambda _=0, d=dialog: self._ack_dialog_finished(d))
        dialog.show()

    def _ack_dialog_finished(self, dialog):
        if dialog in self.ack_dialogs:
            self.ack_dialogs.remove(dialog)

    def _on_table_cell_clicked(self, row, column):
        item = self.table.item(row, column)
        payload = item.data(Qt.UserRole) if item is not None else ""
        if column == 3:
            if payload:
                if QMessageBox.question(self, "Zabbix", "Открыть узел сети в Zabbix?", QMessageBox.Open | QMessageBox.Cancel) == QMessageBox.Open:
                    QDesktopServices.openUrl(QUrl(str(payload)))
            else:
                QMessageBox.information(self, "Zabbix", "Ссылка на узел не найдена.")
            return
        if column == 4:
            graph_urls = payload.get("graph_urls", []) if isinstance(payload, dict) else []
            problem_url = payload.get("problem_url", "") if isinstance(payload, dict) else ""
            if graph_urls:
                if QMessageBox.question(self, "Zabbix", "Открыть график проблемы?", QMessageBox.Open | QMessageBox.Cancel) == QMessageBox.Open:
                    self.open_graphs(graph_urls)
            elif problem_url:
                if QMessageBox.question(self, "Zabbix", "Открыть проблему в Zabbix?", QMessageBox.Open | QMessageBox.Cancel) == QMessageBox.Open:
                    QDesktopServices.openUrl(QUrl(str(problem_url)))
            else:
                QMessageBox.information(self, "Zabbix", "Ссылка на график/проблему не найдена.")
            return
        if column == 6 and payload:
            self.open_acknowledgement(payload)

    def open_graphs(self, urls):
        for url in urls or []:
            QDesktopServices.openUrl(QUrl(str(url)))

    def mark_processed(self, key):
        if not key:
            return
        self.processed_keys.add(key)
        item = self.current_snapshot.get(key)
        if item:
            item.processed = True
            item.status = "processed"
            append_history_event(self._history_path(), "processed", item)
            self._render(diff_snapshots([], self.current_snapshot.values(), self.processed_keys), {"items": list(self.current_snapshot.values()), "safe_debug": {"problem_count": len(self.current_snapshot)}})

    def pause_refresh(self):
        self.stop_monitor()

    def resume_refresh(self):
        pass

    def cleanup(self):
        self.stop_monitor()
        if self.view is not None:
            safe_delete_web_view(self.view, logger=self.logger, context="LiveZabbixMonitorWidget", load_handler=self._on_loaded)
            self._load_finished_connected = False
            self.view = None
