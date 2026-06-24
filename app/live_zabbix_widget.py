"""Qt widget for the Live Zabbix Monitor."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.live_zabbix import DOM_PARSER_SCRIPT_PLACEHOLDER, SnapshotDiff, diff_snapshots, ensure_live_monitor_defaults
from app.logger import get_logger
from app.trigger_model import append_history_event, enrich_problem
from app.webengine_lifecycle import register_web_view, safe_delete_web_view

DOM_PARSER_SCRIPT = DOM_PARSER_SCRIPT_PLACEHOLDER


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
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_now)
        self._build_ui()
        self._create_web_view()

    def _build_ui(self):
        root = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.start_button = QPushButton("Старт")
        self.stop_button = QPushButton("Стоп")
        self.poll_status_label = QLabel("Остановлен")
        self.updated_label = QLabel("Последнее обновление: —")
        self.counts_label = QLabel("Новые: 0 | Активные: 0 | Решённые: 0 | Обработанные: 0")
        self.start_button.clicked.connect(self.start_monitor)
        self.stop_button.clicked.connect(self.stop_monitor)
        controls.addWidget(self.start_button); controls.addWidget(self.stop_button); controls.addWidget(self.poll_status_label); controls.addWidget(self.updated_label); controls.addStretch(); controls.addWidget(self.counts_label)
        root.addLayout(controls)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Время", "Host", "Severity", "Триггер", "Статус", "Zabbix", "Графики", "Redmine"])
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, stretch=1)

    def _create_web_view(self):
        zabbix_id = self.settings.get("zabbix_id") or self._first_zabbix_id()
        profile = self.profiles.get(zabbix_id)
        self.view = register_web_view(QWebEngineView())
        if profile is not None:
            self.page = QWebEnginePage(profile, self.view)
            self.view.setPage(self.page)
        self.view.hide()

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

    def start_monitor(self):
        url = self.problems_url()
        if not url:
            self.poll_status_label.setText("Ошибка: URL Zabbix Problems не задан")
            return
        self.poll_status_label.setText("Запуск")
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

    def _on_loaded(self, ok):
        if not ok:
            self.poll_status_label.setText("Ошибка загрузки Zabbix Problems")
            return
        self.view.page().runJavaScript(DOM_PARSER_SCRIPT, self._on_dom_parsed)

    def _history_path(self) -> Path:
        path = Path(str(self.settings.get("history_path") or "data/live_zabbix_history.jsonl"))
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        return path

    def _on_dom_parsed(self, raw_items):
        items = []
        for raw in raw_items or []:
            item = enrich_problem(self.config, raw or {}, processed_keys=self.processed_keys)
            if raw.get("graph_urls") and not item.graph_urls:
                item.graph_urls = [url for url in raw.get("graph_urls", []) if url]
            items.append(item)
        diff = diff_snapshots(self.previous_snapshot.values(), items, self.processed_keys)
        self.last_diff = diff
        self.current_snapshot = {item.key: item for item in items}
        self._write_history(diff)
        self.previous_snapshot = dict(self.current_snapshot)
        self._render(diff)

    def _write_history(self, diff):
        for event_name, items in (("new", diff.new), ("active", diff.active), ("resolved", diff.resolved), ("processed", diff.processed)):
            for item in items:
                append_history_event(self._history_path(), event_name, item)

    def _render(self, diff):
        all_items = diff.new + diff.active + diff.resolved + diff.processed
        self.table.setRowCount(len(all_items))
        for row, item in enumerate(all_items):
            for column, value in enumerate([item.started_at, item.host, item.severity, item.trigger_name, item.status]):
                self.table.setItem(row, column, QTableWidgetItem(value))
            open_button = QPushButton("Открыть")
            open_button.setEnabled(bool(item.problem_url))
            open_button.clicked.connect(lambda _=False, url=item.problem_url: QDesktopServices.openUrl(QUrl(url)))
            self.table.setCellWidget(row, 5, open_button)
            graphs_button = QPushButton("Открыть графики")
            graphs_button.setEnabled(bool(item.graph_urls))
            graphs_button.clicked.connect(lambda _=False, urls=list(item.graph_urls): self.open_graphs(urls))
            self.table.setCellWidget(row, 6, graphs_button)
            redmine_button = QPushButton("Создать Redmine")
            redmine_button.clicked.connect(lambda _=False, key=item.key: self.mark_processed(key))
            self.table.setCellWidget(row, 7, redmine_button)
        self.counts_label.setText(f"Новые: {len(diff.new)} | Активные: {len(diff.active)} | Решённые: {len(diff.resolved)} | Обработанные: {len(diff.processed)}")
        self.updated_label.setText("Последнее обновление: " + datetime.now().strftime("%H:%M:%S"))
        self.poll_status_label.setText(f"ОК: проблем {len(all_items)}")

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
            self._render(diff_snapshots([], self.current_snapshot.values(), self.processed_keys))

    def pause_refresh(self):
        self.stop_monitor()

    def resume_refresh(self):
        pass

    def cleanup(self):
        self.stop_monitor()
        if self.view is not None:
            safe_delete_web_view(self.view, logger=self.logger, context="LiveZabbixMonitorWidget", load_handler=self._on_loaded)
            self.view = None
