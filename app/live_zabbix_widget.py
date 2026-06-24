"""Qt widget for the Live Zabbix Monitor."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import json

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
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
from app.live_zabbix import DOM_PARSER_SCRIPT_PLACEHOLDER, JS_HEALTH_CHECK_SCRIPT, JS_SMOKE_TEST_SCRIPT, SnapshotDiff, diff_snapshots, ensure_live_monitor_defaults
from app.logger import get_logger
from app.trigger_model import append_history_event, enrich_problem
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
        self.processed_keys = set()
        self.last_diff = SnapshotDiff()
        self.view = None
        self.page = None
        self.current_zabbix_id = ""
        self.profile_warning = ""
        self.profile_selection_reason = ""
        self.last_load_ok = None
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
        self.poll_status_label = QLabel("Остановлен")
        self.updated_label = QLabel("Последнее обновление: —")
        self.counts_label = QLabel("Новые: 0 | Активные: 0 | Решённые: 0 | Обработанные: 0")
        self.start_button.clicked.connect(self.start_monitor)
        self.stop_button.clicked.connect(self.stop_monitor)
        self.check_dom_button.clicked.connect(self.check_dom_now)
        self.save_button.clicked.connect(self.save_monitor_settings)
        self.open_url_button.clicked.connect(self.open_configured_url)
        self.show_webview_button.clicked.connect(self.show_webview)
        for widget in [self.start_button, self.stop_button, self.check_dom_button, self.save_button, self.open_url_button, self.show_webview_button, self.poll_status_label, self.updated_label]:
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
            "Статус Око",
        ]
        self.table = QTableWidget(0, len(self.table_columns))
        self.table.setHorizontalHeaderLabels(self.table_columns)
        self.table.setObjectName("LiveZabbixProblemsTable")
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
        defaults = [105, 82, 42, 145, 460, 76, 86, 72, 130, 80]
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
        save_config(self.config)
        self._recreate_web_view_if_needed()
        self._update_diagnostics({"safe_debug": {}, "items": []}, status_text="Настройки сохранены")

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
        try:
            self.view.loadFinished.disconnect(self._on_loaded)
        except RuntimeError:
            pass
        self.view.loadFinished.connect(self._on_loaded)
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
        self.last_separator_rows = payload.get("separators") or []
        self._parse_attempts.append(payload)
        if not force and not raw_items and len(self._parse_attempts) < 3:
            self._update_diagnostics(payload, status_text="Страница загружена, ждём таблицу Zabbix Problems…")
            return
        if not force and raw_items:
            self._parse_attempts = []
        items = []
        for raw in raw_items:
            item = enrich_problem(self.config, raw or {}, processed_keys=self.processed_keys)
            if raw.get("graph_urls") and not item.graph_urls:
                item.graph_urls = [url for url in raw.get("graph_urls", []) if url]
            items.append(item)
        diff = diff_snapshots(self.previous_snapshot.values(), items, self.processed_keys)
        self.last_diff = diff
        self.current_snapshot = {item.key: item for item in items}
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
    def _is_acknowledge_page_url_or_title(url_value, title_value):
        combined = f"{url_value or ''} {title_value or ''}".casefold()
        return (
            "popup_action" in combined
            or "acknowledge" in combined
            or "action=popup.acknowledge" in combined
            or "обновление проблемы" in combined
        )

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
            "problem_count": int((payload or {}).get("problem_count") or safe_debug.get("problem_count") or len((payload or {}).get("items") or [])),
            "zero_reason": (payload or {}).get("zero_reason") or safe_debug.get("zero_reason") or "",
        })
        safe_debug.update(self._qwebengine_url_diagnostics())
        safe_debug.update(self.last_js_result_meta or {})
        if safe_debug["problem_count"] == 0 and not safe_debug["zero_reason"]:
            safe_debug["zero_reason"] = ZERO_PROBLEMS_MESSAGE
        if safe_debug.get("js_result_error") == "JS returned empty string":
            safe_debug["zero_reason"] = JS_EMPTY_STRING_ERROR_MESSAGE
        if safe_debug.get("load_finished_ok") is True and not safe_debug.get("document_location_href") and safe_debug.get("js_result_is_none"):
            safe_debug["zero_reason"] = WEBENGINE_JS_ERROR_MESSAGE
        if self._is_acknowledge_page_url_or_title(health.get("href", ""), health.get("title", "")):
            safe_debug["zero_reason"] = ACKNOWLEDGE_PAGE_MESSAGE
        return safe_debug

    def _update_diagnostics(self, payload, status_text=None):
        report = self._diagnostic_payload(payload)
        self.diagnostics_text.setPlainText(json.dumps(report, ensure_ascii=False, indent=2))
        if status_text:
            self.poll_status_label.setText(status_text)

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
                item.status,
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value or ""))
                if column == 1:
                    color = self._severity_color(item.severity_level, item.severity_class, item.severity)
                    if color:
                        cell.setBackground(QColor(color))
                if column == 6 and (item.ack_url or item.problem_url):
                    cell.setForeground(QColor("#64b5f6"))
                    font = cell.font()
                    font.setUnderline(True)
                    cell.setFont(font)
                    cell.setToolTip("Открыть подтверждение Zabbix")
                    cell.setData(Qt.UserRole, item.ack_url or item.problem_url)
                if column == 3 and item.host_url:
                    cell.setForeground(QColor("#64b5f6"))
                    font = cell.font()
                    font.setUnderline(True)
                    cell.setFont(font)
                    cell.setToolTip("Открыть узел")
                    cell.setData(Qt.UserRole, item.host_url)
                if column == 4 and (item.graph_urls or item.problem_url):
                    cell.setForeground(QColor("#64b5f6"))
                    font = cell.font()
                    font.setUnderline(True)
                    cell.setFont(font)
                    cell.setToolTip("Открыть график/проблему")
                    cell.setData(Qt.UserRole, {"graph_urls": list(item.graph_urls), "problem_url": item.problem_url})
                self.table.setItem(row, column, cell)
            table_row += 1
        self.counts_label.setText(f"Новые: {len(diff.new)} | Активные: {len(diff.active)} | Решённые: {len(diff.resolved)} | Обработанные: {len(diff.processed)}")
        self.updated_label.setText("Последнее обновление: " + datetime.now().strftime("%H:%M:%S"))
        if all_items:
            self.poll_status_label.setText(f"ОК: проблем {len(all_items)}")
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
            self.view = None
