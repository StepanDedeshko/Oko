"""Qt widget for the Live Zabbix Monitor."""

from __future__ import annotations

from datetime import datetime, timedelta
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
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import save_config
from app.live_zabbix import DEFAULT_REDMINE_LOGIN_URL, DOM_PARSER_SCRIPT_PLACEHOLDER, JS_HEALTH_CHECK_SCRIPT, JS_SMOKE_TEST_SCRIPT, LIVE_PERIOD_7_DAYS, LIVE_PERIOD_ALL, LIVE_PERIOD_TODAY, SnapshotDiff, apply_live_zabbix_table_filters, diff_snapshots, ensure_live_monitor_defaults, split_items_by_duty_filter
from app.logger import get_logger
from app.templates import get_redmine_task_template
from app.trigger_model import SPECIAL_TRIGGER_KIND, append_history_event, enrich_problem, format_graph_links
from app.webengine_lifecycle import register_web_view, safe_delete_web_view

DOM_PARSER_SCRIPT = DOM_PARSER_SCRIPT_PLACEHOLDER
WEBENGINE_JS_ERROR_MESSAGE = "Ошибка диагностики WebEngine: JS не вернул document.location.href. Проверьте выполнение runJavaScript, page.url/view.url и выбранный WebEngine profile."
JS_EMPTY_STRING_ERROR_MESSAGE = "Ошибка JS диагностики: runJavaScript вернул пустую строку. DOM-парсер не запускался корректно."
ZERO_PROBLEMS_MESSAGE = "Страница загружена, но проблемы не найдены. Возможные причины: страница логина, таблица ещё не загрузилась, DOM Zabbix не распознан."
ACKNOWLEDGE_PAGE_MESSAGE = "Открыта форма подтверждения Zabbix. Мониторинг страницы Problems не выполняется в этом WebView."
REDMINE_WATCHER_USER_IDS = (
    "10", "18", "24", "770", "882", "915", "916", "971", "976", "977",
    "994", "1010", "1110", "1112", "1192", "1221", "1225", "1226",
    "1235", "1264", "122", "973", "984", "1012", "1121", "1157",
    "1162", "1165", "1190", "1198", "1204", "1216", "1253", "1261",
    "1269",
)


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


class RedmineAuthorizationDialog(QDialog):
    """Persistent-profile Redmine login window that reopens the original create URL."""

    REDMINE_STATUS_TEXT = "Войдите в Redmine во встроенном окне Око. После успешного входа создание задачи будет открыто повторно."
    REDMINE_LOGIN_SELECTORS = {
        "username": 'input#username, input[name="username"]',
        "password": 'input#password, input[name="password"]',
        "submit": 'input#login-submit, input[name="login"], input[type="submit"]',
    }

    def __init__(self, profile, login_url, original_create_url, settings, parent=None, success_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Авторизация Redmine")
        self.resize(1100, 760)
        self.original_create_url = original_create_url
        self.settings = settings or {}
        self.success_callback = success_callback
        self.view = register_web_view(QWebEngineView(self))
        if profile is not None:
            self.page = QWebEnginePage(profile, self.view)
            self.view.setPage(self.page)

        layout = QVBoxLayout(self)
        self.status_label = QLabel(self.REDMINE_STATUS_TEXT)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addWidget(self.view)
        self.view.loadFinished.connect(self._on_login_loaded)
        self.view.load(QUrl(login_url or DEFAULT_REDMINE_LOGIN_URL))

    @staticmethod
    def autofill_script(username, password):
        return """
(function() {
  var username = %s;
  var password = %s;
  var usernameInput = document.querySelector('input#username, input[name="username"]');
  var passwordInput = document.querySelector('input#password, input[name="password"]');
  var submitInput = document.querySelector('input#login-submit, input[name="login"], input[type="submit"]');
  function setValue(input, value) {
    if (!input) return;
    input.focus();
    input.value = value;
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
  }
  if (usernameInput && passwordInput && username && password) {
    setValue(usernameInput, username);
    setValue(passwordInput, password);
    if (submitInput) submitInput.click();
    return true;
  }
  return false;
})();
""" % (json.dumps(username or ""), json.dumps(password or ""))

    @staticmethod
    def login_success_script():
        return r"""
(function() {
  var path = String(window.location.pathname || '').toLowerCase();
  var hasLoginForm = !!document.querySelector('form[action*="/login"] input#username, form[action*="/login"] input[name="username"], input#login-submit');
  return JSON.stringify({success: path.indexOf('/login') === -1 && !hasLoginForm});
})();
"""

    def _on_login_loaded(self, ok):
        page = self.view.page() if self.view is not None else None
        if page is None:
            return
        page.runJavaScript(self.login_success_script(), self._on_login_success_check)
        username = str(self.settings.get("redmine_username") or "")
        password = str(self.settings.get("redmine_password") or "")
        if username and password:
            page.runJavaScript(self.autofill_script(username, password))

    def _on_login_success_check(self, result):
        try:
            payload = json.loads(result or "{}")
        except (TypeError, ValueError):
            payload = {}
        if payload.get("success"):
            if self.success_callback:
                self.success_callback(self.original_create_url)
            self.accept()

    def closeEvent(self, event):
        view = self.view
        self.view = None
        if view is not None:
            safe_delete_web_view(view, logger=get_logger(), context="RedmineAuthorizationDialog")
        super().closeEvent(event)


class RedmineCreateDialog(QDialog):
    """In-app Redmine issue creation guard using the shared persistent profile."""

    BROKEN_MARKERS = ("default error page for nginx", "/usr/share/nginx/html/50x.html", "Red Hat Enterprise Linux")
    LOGIN_MARKERS = ('form[action*="/login"]', 'input#username', 'input[name="username"]', 'input#password', 'input[name="password"]')
    ISSUE_FORM_MARKERS = ('input[name="issue[subject]"]', 'textarea[name="issue[description]"]')

    def __init__(self, profile, redmine_url, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Создание задачи Redmine")
        self.resize(1200, 820)
        self.redmine_url = redmine_url
        self.settings = settings or {}
        self.auth_dialog = None
        self.view = register_web_view(QWebEngineView(self))
        if profile is not None:
            self.page = QWebEnginePage(profile, self.view)
            self.view.setPage(self.page)
        layout = QVBoxLayout(self)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addWidget(self.view)
        self.view.loadFinished.connect(self._on_create_loaded)
        self.view.load(QUrl(redmine_url))

    @staticmethod
    def issue_form_guard_script():
        return r"""
(function() {
  var html = String(document.documentElement ? document.documentElement.innerHTML : '');
  var lowered = html.toLowerCase();
  var path = String(window.location.pathname || '').toLowerCase();
  var hasSubject = !!document.querySelector('input[name="issue[subject]"]');
  var hasDescription = !!document.querySelector('textarea[name="issue[description]"]');
  var hasIssuePath = path.indexOf('/issues/new') !== -1;
  var hasLogin = !!document.querySelector('form[action*="/login"] input#username, form[action*="/login"] input[name="username"], input#login-submit');
  var hasBroken = lowered.indexOf('default error page for nginx') !== -1
    || lowered.indexOf('/usr/share/nginx/html/50x.html') !== -1
    || html.indexOf('Red Hat Enterprise Linux') !== -1;
  return JSON.stringify({valid_issue_form: hasSubject && hasDescription && hasIssuePath, login_required: hasLogin, broken: hasBroken});
})();
"""

    def _on_create_loaded(self, ok):
        page = self.view.page() if self.view is not None else None
        if page is None:
            return
        page.runJavaScript(self.issue_form_guard_script(), self._on_create_guard_result)

    def _on_create_guard_result(self, result):
        try:
            payload = json.loads(result or "{}")
        except (TypeError, ValueError):
            payload = {}
        if payload.get("valid_issue_form"):
            self.status_label.setText("")
            return
        if payload.get("login_required") or payload.get("broken"):
            self._open_redmine_auth_dialog()
            return
        self.status_label.setText("Redmine не открыл форму создания задачи. Проверьте авторизацию Redmine и настройки шаблона.")

    def _open_redmine_auth_dialog(self):
        profile = self.view.page().profile() if self.view is not None and self.view.page() is not None else None
        login_url = str(self.settings.get("redmine_login_url") or DEFAULT_REDMINE_LOGIN_URL)
        self.auth_dialog = RedmineAuthorizationDialog(profile, login_url, self.redmine_url, self.settings, self, self._reopen_original_create_url)
        self.auth_dialog.show()

    def _reopen_original_create_url(self, original_create_url):
        self.view.load(QUrl(original_create_url))

    def closeEvent(self, event):
        view = self.view
        self.view = None
        if view is not None:
            safe_delete_web_view(view, logger=get_logger(), context="RedmineCreateDialog")
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
        self.mm_otrs_dialogs = []
        self.redmine_dialogs = []
        self.redmine_graph_lookup_view = None
        self._redmine_graph_lookup_queue = []
        self._redmine_graph_lookup_items = []
        self._redmine_graph_lookup_callback = None
        self._redmine_graph_lookup_load_slot = None
        self._redmine_ip_lookup_queue = []
        self._redmine_ip_lookup_items = []
        self._redmine_ip_lookup_callback = None
        self._redmine_ip_lookup_total = 0
        self.last_separator_rows = []
        self._parse_attempts = []
        self._monitor_started = False
        self._zabbix_auth_retrying = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_now)
        self._build_ui()
        self._create_web_view()
        self._update_diagnostics({"safe_debug": {}, "items": []}, status_text="Остановлен")

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Служебные настройки Live Zabbix остаются в виджете для совместимости,
        # но обычному пользователю не показываются. Управление ими вынесено в
        # запароленный раздел “Режим разработчика”.
        self.url_input = QLineEdit(self.problems_url())
        self.url_input.setPlaceholderText("https://zabbix.example/zabbix.php?action=problem.view")
        self.url_input.setVisible(False)

        self.interval_input = QSpinBox()
        self.interval_input.setRange(60, 3600)
        poll_interval = int(self.settings.get("poll_interval_seconds", 60) or 60)
        poll_interval = max(60, poll_interval)
        self.interval_input.setValue(poll_interval)
        self.interval_input.setVisible(False)
        self.settings["poll_interval_seconds"] = poll_interval

        self.zabbix_profile_combo = QComboBox()
        self._populate_profile_combo()
        profile_index = self.zabbix_profile_combo.findData(self.settings.get("zabbix_profile_id", "zbx_product_1"))
        if profile_index < 0:
            profile_index = self.zabbix_profile_combo.findData("zbx_product_1")
        if profile_index >= 0:
            self.zabbix_profile_combo.setCurrentIndex(profile_index)
        self.zabbix_profile_combo.setVisible(False)

        self.show_developer_tools = bool(
            self.settings.get("show_developer_tools", False)
            or self.settings.get("show_live_zabbix_diagnostics", False)
        )

        controls = QHBoxLayout()
        self.check_dom_button = QPushButton("Проверить DOM")
        self.save_button = QPushButton("Сохранить")
        self.open_url_button = QPushButton("Открыть Zabbix")
        self.show_webview_button = QPushButton("Показать WebView")
        self.open_redmine_button = QPushButton("Открыть Redmine")
        self.poll_status_label = QLabel("Остановлен")
        self.updated_label = QLabel("Последнее обновление: —")
        self.period_filter_combo = QComboBox()
        self.period_filter_combo.addItem("Все", LIVE_PERIOD_ALL)
        self.period_filter_combo.addItem("Сегодня", LIVE_PERIOD_TODAY)
        self.period_filter_combo.addItem("7 дней", LIVE_PERIOD_7_DAYS)
        saved_period = str(self.settings.get("period_filter", LIVE_PERIOD_ALL) or LIVE_PERIOD_ALL)
        period_index = self.period_filter_combo.findData(saved_period)
        self.period_filter_combo.setCurrentIndex(period_index if period_index >= 0 else 0)
        self.period_filter_combo.currentIndexChanged.connect(self._on_table_filters_changed)
        self.unprocessed_filter_checkbox = QCheckBox("Не обработано")
        self.unprocessed_filter_checkbox.setChecked(bool(self.settings.get("unprocessed_filter_enabled", False)))
        self.unprocessed_filter_checkbox.toggled.connect(self._on_table_filters_changed)
        self.duty_filter_checkbox = QCheckBox("Только интересующие")
        self.duty_filter_checkbox.setChecked(bool(self.settings.get("duty_filter_enabled", True)))
        self.duty_filter_checkbox.toggled.connect(self._on_duty_filter_toggled)
        self.counts_label = QLabel("Новые: 0 | Активные: 0 | Решённые: 0 | Обработанные: 0 | Всего: 0 | Показано: 0 | Скрыто фильтром: 0")
        self.check_dom_button.clicked.connect(self.check_dom_now)
        self.save_button.clicked.connect(self.save_monitor_settings)
        self.open_url_button.clicked.connect(self.open_configured_url)
        self.show_webview_button.clicked.connect(self.show_webview)
        self.open_redmine_button.clicked.connect(self.open_redmine_for_selected_row)
        normal_controls = [
            self.open_url_button,
            self.open_redmine_button,
            self.duty_filter_checkbox,
            self.period_filter_combo,
            self.unprocessed_filter_checkbox,
            self.poll_status_label,
            self.updated_label,
        ]
        developer_controls = [
            self.save_button,
            self.check_dom_button,
            self.show_webview_button,
        ]

        for widget in normal_controls:
            controls.addWidget(widget)

        if self.show_developer_tools:
            for widget in developer_controls:
                controls.addWidget(widget)
        controls.addStretch()
        controls.addWidget(self.counts_label)
        root.addLayout(controls)

        self.diagnostics_text = QPlainTextEdit()
        self.diagnostics_text.setReadOnly(True)
        self.diagnostics_text.setMaximumHeight(220)
        self.diagnostics_text.setPlaceholderText("Диагностика DOM")
        self.diagnostics_label = QLabel("Диагностика DOM")
        root.addWidget(self.diagnostics_label)
        root.addWidget(self.diagnostics_text)
        self.diagnostics_label.setVisible(self.show_developer_tools)
        self.diagnostics_text.setVisible(self.show_developer_tools)

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
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(
            """
            QTableWidget#LiveZabbixProblemsTable {
                font-size: 11px;
                border: 1px solid rgba(120, 150, 170, 80);
                border-radius: 8px;
                gridline-color: rgba(120, 150, 170, 42);
                selection-background-color: palette(highlight);
                selection-color: palette(highlighted-text);
                outline: 0;
            }
            QHeaderView::section {
                font-size: 11px;
                font-weight: 600;
                padding: 6px 8px;
                border: 0;
                border-bottom: 1px solid rgba(120, 150, 170, 95);
            }
            """
        )
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.verticalHeader().setMinimumSectionSize(28)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)
        self._configure_table_columns()
        root.addWidget(self.table, stretch=1)

    def showEvent(self, event):
        super().showEvent(event)
        self.start_monitor()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def _configure_table_columns(self):
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        defaults = [105, 110, 42, 145, 460, 76, 86, 120, 130]
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
        self.settings["period_filter"] = str(self.period_filter_combo.currentData() or LIVE_PERIOD_ALL)
        self.settings["unprocessed_filter_enabled"] = bool(self.unprocessed_filter_checkbox.isChecked())
        save_config(self.config)
        self._recreate_web_view_if_needed()
        self._update_diagnostics({"safe_debug": {}, "items": []}, status_text="Настройки сохранены")

    def _on_duty_filter_toggled(self, checked):
        self.settings["duty_filter_enabled"] = bool(checked)
        save_config(self.config)
        self._refresh_filtered_snapshot()

    def _on_table_filters_changed(self, *_args):
        self.settings["period_filter"] = str(self.period_filter_combo.currentData() or LIVE_PERIOD_ALL)
        self.settings["unprocessed_filter_enabled"] = bool(self.unprocessed_filter_checkbox.isChecked())
        save_config(self.config)
        self._refresh_filtered_snapshot()

    def _apply_current_filters(self, items):
        duty_visible, duty_hidden = split_items_by_duty_filter(
            self.config,
            items,
            filter_enabled=bool(self.settings.get("duty_filter_enabled", True)),
        )
        visible = apply_live_zabbix_table_filters(
            duty_visible,
            period=str(self.settings.get("period_filter", LIVE_PERIOD_ALL) or LIVE_PERIOD_ALL),
            unprocessed_only=bool(self.settings.get("unprocessed_filter_enabled", False)),
        )
        visible_keys = {item.key for item in visible}
        hidden = list(duty_hidden) + [item for item in duty_visible if item.key not in visible_keys]
        return visible, hidden

    def _refresh_filtered_snapshot(self):
        if not self.all_snapshot:
            return
        visible, hidden = self._apply_current_filters(self.all_snapshot.values())
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
        if self._monitor_started and self.timer.isActive():
            return
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
        self.timer.start(int(self.settings.get("poll_interval_seconds", 60)) * 1000)
        self._monitor_started = True

    def stop_monitor(self):
        self.timer.stop()
        self._monitor_started = False
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
        if payload.get("auth_required") or (payload.get("safe_debug") or {}).get("auth_required"):
            self._silent_zabbix_autologin(payload)
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
        visible_items, hidden_items = self._apply_current_filters(all_items)
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

    def _zabbix_saved_credentials(self):
        credentials = self.credentials or {}
        candidates = []
        if self.current_zabbix_id:
            candidates.append(credentials.get(self.current_zabbix_id))
        candidates.extend([credentials.get("zabbix"), credentials.get("Zabbix"), credentials])
        for value in candidates:
            if not isinstance(value, dict):
                continue
            login = value.get("login") or value.get("username") or value.get("user") or ""
            password = value.get("password") or value.get("pass") or value.get("secret") or ""
            if login and password:
                return {"login": str(login), "password": str(password)}
        return {"login": "", "password": ""}

    def _silent_zabbix_autologin(self, payload):
        if self._zabbix_auth_retrying:
            return
        creds = self._zabbix_saved_credentials()
        if not creds.get("login") or not creds.get("password"):
            self.poll_status_label.setText("Zabbix: нет сохранённых доступов")
            self._update_diagnostics(payload or {"safe_debug": {"auth_status": "missing_credentials"}, "items": []}, status_text="missing_credentials")
            return
        login_url = str(payload.get("data_login_url") or (payload.get("safe_debug") or {}).get("data_login_url") or "")
        self._zabbix_auth_retrying = True
        if login_url and self.view is not None:
            self.poll_status_label.setText("Zabbix: тихое восстановление сессии…")
            self.view.load(self.view.url().resolved(QUrl(login_url)))
            QTimer.singleShot(1500, lambda: self._fill_zabbix_login_form(creds, 1))
        else:
            self._fill_zabbix_login_form(creds, 1)

    def _fill_zabbix_login_form(self, creds, attempt=1):
        page = self.view.page() if self.view is not None else None
        if page is None:
            self._zabbix_auth_retrying = False
            return
        login_json = json.dumps(creds.get("login", ""), ensure_ascii=False)
        password_json = json.dumps(creds.get("password", ""), ensure_ascii=False)
        js = f"""
(function() {{
  const loginValue = {login_json};
  const passwordValue = {password_json};
  function fire(el) {{ if (!el) return; ["input", "change", "blur"].forEach(function(t) {{ try {{ el.dispatchEvent(new Event(t, {{bubbles: true}})); }} catch(e) {{}} }}); }}
  function setValue(el, value) {{ if (!el) return false; el.value = value; fire(el); return true; }}
  const user = document.querySelector('input[name="name"], input[name="username"], input#name, input#username, input[type="text"]');
  const pass = document.querySelector('input[name="password"], input#password, input[type="password"]');
  const button = document.querySelector('button[type="submit"], input[type="submit"], button[name="enter"], input[name="enter"], button#enter, button#login');
  const userSet = setValue(user, loginValue);
  const passSet = setValue(pass, passwordValue);
  if (userSet && passSet) {{ if (button) button.click(); else if (pass && pass.form) pass.form.submit(); }}
  return JSON.stringify({{login_form_found: !!(user || pass), submitted: !!(userSet && passSet)}});
}})();
"""
        def after(result):
            if '"submitted":true' in str(result or ""):
                self.poll_status_label.setText("Zabbix: проверяю сессию…")
                QTimer.singleShot(2500, self._finish_zabbix_autologin)
            elif attempt < 6:
                QTimer.singleShot(1000, lambda: self._fill_zabbix_login_form(creds, attempt + 1))
            else:
                self._zabbix_auth_retrying = False
                self.poll_status_label.setText("Zabbix: нет сохранённых доступов")
        page.runJavaScript(js, after)

    def _finish_zabbix_autologin(self):
        self._zabbix_auth_retrying = False
        self.poll_status_label.setText("Zabbix: OK")
        if self.view is not None:
            self.view.load(QUrl(self.problems_url()))

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

    def _is_light_theme(self) -> bool:
        theme_name = str((self.config.get("settings", {}) if isinstance(self.config, dict) else {}).get("theme") or "").casefold()
        light_themes = {"white_1", "light_standard"}
        return theme_name in light_themes or theme_name.startswith("white") or "light" in theme_name or "свет" in theme_name

    def _clickable_cell_foreground(self) -> QColor:
        if self._is_light_theme():
            return QColor("#000000")
        return QColor("#ffffff")

    @staticmethod
    def _month_name_ru(month_number):
        months = (
            "Январь",
            "Февраль",
            "Март",
            "Апрель",
            "Май",
            "Июнь",
            "Июль",
            "Август",
            "Сентябрь",
            "Октябрь",
            "Ноябрь",
            "Декабрь",
        )
        try:
            index = int(month_number) - 1
        except (TypeError, ValueError):
            return ""
        if 0 <= index < len(months):
            return months[index]
        return ""

    @staticmethod
    def _parse_zabbix_started_at(value):
        value = str(value or "").strip()
        if not value:
            return None

        for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%y %H:%M:%S", "%d.%m.%y %H:%M"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass

        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                parsed = datetime.strptime(value, fmt)
            except ValueError:
                continue

            now = datetime.now()
            return now.replace(hour=parsed.hour, minute=parsed.minute, second=parsed.second, microsecond=0)

        return None

    def _timeline_separator_labels_for_item(self, item, state):
        started_at = str(getattr(item, "started_at", "") or "").strip()
        started_dt = self._parse_zabbix_started_at(started_at)
        if started_dt is None:
            return []

        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        item_date = started_dt.date()
        labels = []

        if item_date == today:
            if state.get("day") != item_date:
                labels.append("Сегодня")
                state["day"] = item_date
                state["month"] = None
                state["hour"] = None

            hour_key = (item_date, started_dt.hour)
            if state.get("hour") != hour_key:
                labels.append(f"{started_dt.hour:02d}:00")
                state["hour"] = hour_key

            return labels

        if item_date == yesterday:
            if state.get("day") != item_date:
                labels.append("Вчера")
                state["day"] = item_date
                state["month"] = None
                state["hour"] = None
            return labels

        month_key = (item_date.year, item_date.month)
        if state.get("month") != month_key:
            month_label = self._month_name_ru(item_date.month)
            if month_label:
                labels.append(month_label)
            state["month"] = month_key
            state["day"] = None
            state["hour"] = None

        if state.get("day") != item_date:
            labels.append(started_dt.strftime("%d.%m.%Y"))
            state["day"] = item_date
            state["hour"] = None

        return labels

    def _append_timeline_separator_row(self, row, text):
        label = QTableWidgetItem(str(text or ""))
        label.setTextAlignment(Qt.AlignCenter)
        label.setFlags(Qt.ItemFlag.ItemIsEnabled)

        font = label.font()
        font.setBold(True)
        font.setPointSize(max(font.pointSize(), 11))
        label.setFont(font)

        if self._is_light_theme():
            bg = QColor("#dfeef6")
            fg = QColor("#1f3440")
        else:
            bg = QColor("#163142")
            fg = QColor("#e1f0f6")

        label.setBackground(bg)
        label.setForeground(fg)

        self.table.insertRow(row)
        self.table.setItem(row, 0, label)
        self.table.setSpan(row, 0, 1, self.table.columnCount())
        self.table.setRowHeight(row, 30)

    def _render(self, diff, payload=None):
        all_items = diff.new + diff.active + diff.resolved + diff.processed
        self.table.setRowCount(0)

        table_row = 0
        separator_state = {}

        for item in all_items:
            for separator_label in self._timeline_separator_labels_for_item(item, separator_state):
                self._append_timeline_separator_row(table_row, separator_label)
                table_row += 1

            self.table.insertRow(table_row)
            values = [
                item.started_at,
                item.severity,
                item.info,
                item.host,
                item.trigger_name,
                item.duration,
                item.ack_text or ("Да" if item.acknowledged else "Нет"),
                item.actions_text or "—",
                item.tags,
            ]

            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value or ""))
                cell.setData(Qt.UserRole + 1, item.key)

                if column in {0, 1, 2, 5, 6}:
                    cell.setTextAlignment(Qt.AlignCenter)

                if column == 1:
                    color = self._severity_color(item.severity_level, item.severity_class, item.severity)
                    if color:
                        cell.setBackground(QColor(color))
                        cell.setForeground(QColor("#000000"))

                if column == 6 and (item.ack_url or item.problem_url):
                    cell.setForeground(self._clickable_cell_foreground())
                    cell.setToolTip("Правый клик: открыть подтверждение Zabbix")
                    cell.setData(Qt.UserRole, item.ack_url or item.problem_url)

                if column == 6:
                    ack_text = str(value or "").strip().casefold()
                    if ack_text in {"да", "yes"}:
                        cell.setForeground(QColor("#2e7d32"))
                    elif ack_text in {"нет", "no"}:
                        cell.setForeground(QColor("#c62828"))

                if column == 3 and item.host_url:
                    cell.setForeground(self._clickable_cell_foreground())
                    cell.setToolTip("Правый клик: открыть узел в Zabbix")
                    cell.setData(Qt.UserRole, item.host_url)

                if column == 4 and (item.graph_urls or item.problem_url):
                    cell.setForeground(self._clickable_cell_foreground())
                    cell.setToolTip("Правый клик: открыть график/проблему")
                    cell.setData(Qt.UserRole, {"graph_urls": list(item.graph_urls), "problem_url": item.problem_url})

                if column == 7 and str(value or "").strip() == "—":
                    cell.setTextAlignment(Qt.AlignCenter)
                    cell.setForeground(QColor("#8b9aa5"))

                if column == 7 and item.actions_tooltip:
                    cell.setToolTip(item.actions_tooltip)

                self.table.setItem(table_row, column, cell)

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

        # Цвета важности должны оставаться независимыми от темы приложения:
        # это смысловая индикация Zabbix, а не декоративный стиль таблицы.
        if "disaster" in key or "чрезвычай" in key:
            return "#e45959"
        if "high" in key or "высок" in key:
            return "#e97659"
        if "average" in key or "средн" in key:
            return "#ffa059"
        if "warning" in key or "предупр" in key:
            return "#ffc859"
        if "info" in key or "информ" in key:
            return "#7499ff"
        if "na-bg" in key or "not_classified" in key or "не классиф" in key:
            return "#97aab3"
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

    def _choose_redmine_items_for_selection(self, title="Redmine"):
        items = self._selected_live_problem_items()
        if not items:
            return []

        if len(items) == 1:
            same_host_items = self._same_host_visible_items(items[0].host)
            if len(same_host_items) > 1:
                host = str(items[0].host or "узел сети")
                answer = QMessageBox.question(
                    self,
                    title,
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

    @staticmethod
    def _is_real_graph_url(url):
        value = str(url or "")
        if not value:
            return False
        lowered = value.casefold()
        return (
            "history.php" in lowered and "action=showgraph" in lowered
        ) or (
            "history.php" in lowered and "itemids" in lowered
        ) or (
            "chart.php" in lowered and ("graphid" in lowered or "itemids" in lowered)
        )

    def _redmine_graph_link_for_item(self, item):
        for url in list(getattr(item, "graph_urls", []) or []):
            if self._is_real_graph_url(url):
                return str(url or "")
        return ""

    def _redmine_trigger_description_lines(self, items):
        lines = []
        for index, item in enumerate(items or [], start=1):
            trigger_name = str(getattr(item, "trigger_name", "") or "Проблема Zabbix").strip()
            lines.append(f"{index}. {trigger_name}")

            graph_link = self._redmine_graph_link_for_item(item)
            if graph_link:
                lines.append(f"Ссылка на график: {graph_link}")
            else:
                lines.append("Ссылка на график: не найдена")

        return lines

    def _redmine_group_items_by_host(self, items):
        grouped = []
        index_by_host = {}

        for item in items or []:
            host = str(getattr(item, "host", "") or "узел не определён").strip() or "узел не определён"
            host_key = host.casefold()

            if host_key not in index_by_host:
                index_by_host[host_key] = len(grouped)
                grouped.append((host, []))

            grouped[index_by_host[host_key]][1].append(item)

        return grouped

    @staticmethod
    def _redmine_extract_ipv4_from_text(value):
        import re as _re

        text = str(value or "")
        if not text:
            return ""

        for match in _re.finditer(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)", text):
            ip = match.group(0)
            try:
                parts = [int(part) for part in ip.split(".")]
            except Exception:
                continue

            if len(parts) != 4:
                continue
            if not all(0 <= part <= 255 for part in parts):
                continue
            if ip in {"0.0.0.0", "255.255.255.255"}:
                continue

            return ip

        return ""

    def _redmine_item_ip_text(self, item):
        if isinstance(item, dict):
            existing = str(item.get("host_ip", "") or "").strip()
        else:
            existing = str(getattr(item, "host_ip", "") or "").strip()

        if existing:
            return existing

        candidate_values = []
        for attr in (
            "host",
            "host_url",
            "trigger_name",
            "tags",
            "info",
            "actions_text",
            "actions_tooltip",
            "problem_url",
            "raw_text",
            "status",
            "duration",
        ):
            if isinstance(item, dict):
                candidate_values.append(item.get(attr, ""))
            else:
                candidate_values.append(getattr(item, attr, ""))

        if isinstance(item, dict):
            candidate_values.extend(item.values())
        elif hasattr(item, "__dict__"):
            candidate_values.extend((getattr(item, "__dict__", {}) or {}).values())

        for value in candidate_values:
            ip = self._redmine_extract_ipv4_from_text(value)
            if ip:
                try:
                    if isinstance(item, dict):
                        item["host_ip"] = ip
                    else:
                        item.host_ip = ip
                except Exception:
                    pass
                return ip

        return ""


    def _redmine_ip_text_for_items(self, items):
        ips = self._unique_text_values(self._redmine_item_ip_text(item) for item in items or [])
        if not ips:
            hosts = self._unique_text_values(
                (item.get("host", "") if isinstance(item, dict) else getattr(item, "host", ""))
                for item in items or []
            )
            if hosts:
                return "не найден (" + ", ".join(hosts) + ")"
            return "не найден"

        if len(ips) == 1:
            return ips[0]

        return ", ".join(ips)


    def _redmine_description(self, items):
        items = self._unique_live_items(items)
        grouped_hosts = self._redmine_group_items_by_host(items)

        if len(grouped_hosts) <= 1:
            host_text = grouped_hosts[0][0] if grouped_hosts else "узел не определён"
            ip_text = self._redmine_ip_text_for_items(items)

            lines = [
                f"Узел: {host_text}",
                f"IP: {ip_text}",
                "",
                "Триггеры:",
            ]

            lines.extend(self._redmine_trigger_description_lines(items))
            lines.append("")
            lines.append("Просьба проверить.")
            return "\n".join(lines).strip()

        lines = []
        for host_index, (host, host_items) in enumerate(grouped_hosts, start=1):
            ip_text = self._redmine_ip_text_for_items(host_items)

            lines.append(f"{host_index}. Узел: {host}")
            lines.append(f"IP: {ip_text}")
            lines.append("Триггеры:")
            lines.extend(self._redmine_trigger_description_lines(host_items))
            lines.append("")

        lines.append("Просьба проверить.")
        return "\n".join(lines).strip()

    def _combined_graph_urls(self, items):
        urls = []
        seen = set()
        for item in items or []:
            for url in getattr(item, "graph_urls", []) or []:
                text = str(url or "").strip()
                if not text or text in seen or not self._is_real_graph_url(text):
                    continue
                seen.add(text)
                urls.append(text)
        return urls

    @staticmethod
    def _append_redmine_param_pairs(result_pairs, key, value):
        if value is None or value == "":
            return

        if isinstance(value, (list, tuple, set)):
            for item in value:
                if item is None or item == "":
                    continue
                result_pairs.append((key, str(item)))
            return

        result_pairs.append((key, str(value)))

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
            if key not in existing_keys and key not in dynamic_keys:
                LiveZabbixMonitorWidget._append_redmine_param_pairs(result_pairs, key, value)

        for key, value in dynamic_params.items():
            LiveZabbixMonitorWidget._append_redmine_param_pairs(result_pairs, key, value)

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
            "issue[custom_field_values][94]": str(template.get("custom_field_94") or "Не применим"),
            "issue[watcher_user_ids][]": REDMINE_WATCHER_USER_IDS,
        }

        if template.get("priority_id"):
            default_params["issue[priority_id]"] = str(template.get("priority_id"))

        dynamic_params = {
            "issue[subject]": subject,
            "issue[description]": description,
        }

        redmine_url = self._merge_redmine_url_params(create_url, dynamic_params, default_params)
        if len(redmine_url) > 6500:
            return redmine_url, f"Redmine-ссылка длинная: {len(redmine_url)} символов. Лучше выбрать меньше строк."

        return redmine_url, ""

    @staticmethod
    def _graph_link_lookup_script():
        return r"""
(function() {
  function abs(href) {
    try { return new URL(href, document.location.href).href; }
    catch(e) { return href || ''; }
  }

  function isGraphUrl(value) {
    value = String(value || '').toLowerCase();
    return (
      value.indexOf('history.php') !== -1 && value.indexOf('action=showgraph') !== -1
    ) || (
      value.indexOf('history.php') !== -1 && value.indexOf('itemids') !== -1
    ) || (
      value.indexOf('chart.php') !== -1 && (value.indexOf('graphid') !== -1 || value.indexOf('itemids') !== -1)
    );
  }

  var exact = document.querySelector('body > div > ul > li:nth-child(5) > a[href]');
  if (exact && isGraphUrl(exact.getAttribute('href') || exact.href || '')) {
    return JSON.stringify({ok: true, graph_url: abs(exact.getAttribute('href') || exact.href || ''), source: 'exact'});
  }

  var links = Array.from(document.querySelectorAll('a[href]'));
  var graph = links.find(function(a) {
    return isGraphUrl(a.getAttribute('href') || a.href || '');
  });

  return JSON.stringify({
    ok: true,
    graph_url: graph ? abs(graph.getAttribute('href') || graph.href || '') : '',
    source: graph ? 'fallback' : '',
    title: String(document.title || '').slice(0, 160)
  });
})();
"""

    def _ensure_redmine_graph_lookup_view(self):
        if self.redmine_graph_lookup_view is not None:
            return
        self.redmine_graph_lookup_view = register_web_view(QWebEngineView())
        profile = self.view.page().profile() if self.view is not None and self.view.page() is not None else None
        if profile is not None:
            page = QWebEnginePage(profile, self.redmine_graph_lookup_view)
            self.redmine_graph_lookup_view.setPage(page)
        self.redmine_graph_lookup_view.hide()

    def _cleanup_redmine_graph_lookup_view(self):
        if self.redmine_graph_lookup_view is not None:
            safe_delete_web_view(self.redmine_graph_lookup_view, logger=self.logger, context="LiveZabbixMonitorWidget Redmine graph lookup")
            self.redmine_graph_lookup_view = None

    def _items_need_graph_lookup(self, items):
        result = []
        for item in items or []:
            if self._redmine_graph_link_for_item(item):
                continue
            if str(getattr(item, "problem_url", "") or "").strip():
                result.append(item)
        return result

    def _enrich_redmine_graph_links(self, items, callback):
        items = self._unique_live_items(items)
        queue = self._items_need_graph_lookup(items)
        if not queue:
            callback(items)
            return

        self._redmine_graph_lookup_items = items
        self._redmine_graph_lookup_queue = list(queue)
        self._redmine_graph_lookup_callback = callback
        self.poll_status_label.setText(f"Ищу ссылки на графики: 0/{len(queue)}")
        self._ensure_redmine_graph_lookup_view()
        self._load_next_redmine_graph_lookup()

    def _load_next_redmine_graph_lookup(self):
        if not self._redmine_graph_lookup_queue:
            callback = self._redmine_graph_lookup_callback
            items = self._redmine_graph_lookup_items
            self._redmine_graph_lookup_callback = None
            self.poll_status_label.setText("Ссылки на графики обработаны")
            if callback:
                callback(items)
            return

        item = self._redmine_graph_lookup_queue.pop(0)
        url = str(getattr(item, "problem_url", "") or "").strip()
        if not url:
            self._load_next_redmine_graph_lookup()
            return

        total = len(self._redmine_graph_lookup_items)
        left = len(self._redmine_graph_lookup_queue)
        self.poll_status_label.setText(f"Ищу ссылку на график: {total - left}/{total}")

        if self._redmine_graph_lookup_load_slot is not None:
            try:
                self.redmine_graph_lookup_view.loadFinished.disconnect(self._redmine_graph_lookup_load_slot)
            except (TypeError, RuntimeError):
                pass
            self._redmine_graph_lookup_load_slot = None

        self._redmine_graph_lookup_load_slot = lambda ok, current_item=item: self._on_redmine_graph_lookup_loaded(ok, current_item)
        self.redmine_graph_lookup_view.loadFinished.connect(self._redmine_graph_lookup_load_slot)
        self.redmine_graph_lookup_view.load(QUrl(url))

    def _on_redmine_graph_lookup_loaded(self, ok, item):
        if not ok:
            self.logger.warning("Redmine graph lookup page failed: problem_url=%s", getattr(item, "problem_url", ""))
            self._load_next_redmine_graph_lookup()
            return

        page = self.redmine_graph_lookup_view.page() if self.redmine_graph_lookup_view is not None else None
        if page is None:
            self._load_next_redmine_graph_lookup()
            return

        page.runJavaScript(
            self._graph_link_lookup_script(),
            lambda result, current_item=item: self._on_redmine_graph_lookup_js_result(result, current_item),
        )

    def _on_redmine_graph_lookup_js_result(self, result, item):
        payload, meta = self._decode_js_json_result(result)
        graph_url = ""
        if isinstance(payload, dict):
            graph_url = str(payload.get("graph_url") or "").strip()

        if graph_url and self._is_real_graph_url(graph_url):
            urls = [url for url in list(getattr(item, "graph_urls", []) or []) if self._is_real_graph_url(url)]
            if graph_url not in urls:
                urls.insert(0, graph_url)
            item.graph_urls = urls
            self.logger.info("Redmine graph link found: trigger=%s graph_url=%s", getattr(item, "trigger_name", ""), graph_url)
        else:
            self.logger.info("Redmine graph link not found: trigger=%s meta=%s", getattr(item, "trigger_name", ""), meta)

        self._load_next_redmine_graph_lookup()

    def _item_has_redmine_ip(self, item):
        return bool(str(getattr(item, "host_ip", "") or "").strip())

    def _items_need_ip_lookup(self, items):
        result = []
        seen_hosts = set()
        for item in items or []:
            if self._item_has_redmine_ip(item):
                continue

            host = str(getattr(item, "host", "") or "").strip()
            if not host:
                continue

            host_key = host.casefold()
            if host_key in seen_hosts:
                continue

            seen_hosts.add(host_key)
            result.append(item)
        return result

    def _apply_redmine_host_ip(self, source_item, ip):
        ip_text = str(ip or "").strip()
        if not ip_text:
            return

        host_key = str(getattr(source_item, "host", "") or "").strip().casefold()
        if not host_key:
            return

        for item in self._redmine_ip_lookup_items or []:
            if str(getattr(item, "host", "") or "").strip().casefold() == host_key:
                item.host_ip = ip_text

    def _enrich_redmine_host_ips(self, items, callback):
        items = self._unique_live_items(items)
        queue = self._items_need_ip_lookup(items)
        if not queue:
            callback(items)
            return

        self._redmine_ip_lookup_items = items
        self._redmine_ip_lookup_queue = list(queue)
        self._redmine_ip_lookup_callback = callback
        self._redmine_ip_lookup_total = len(queue)
        self.poll_status_label.setText(f"Ищу IP узлов: 0/{len(queue)}")
        self._load_next_redmine_ip_lookup()

    def _load_next_redmine_ip_lookup(self):
        if not self._redmine_ip_lookup_queue:
            callback = self._redmine_ip_lookup_callback
            items = self._redmine_ip_lookup_items
            self._redmine_ip_lookup_callback = None
            self._redmine_ip_lookup_total = 0
            self.poll_status_label.setText("IP узлов обработаны")
            if callback:
                callback(items)
            return

        item = self._redmine_ip_lookup_queue.pop(0)
        total = self._redmine_ip_lookup_total or len(self._redmine_ip_lookup_queue) + 1
        done = total - len(self._redmine_ip_lookup_queue)
        self.poll_status_label.setText(f"Ищу IP узла: {done}/{total}")

        page = self.view.page() if self.view is not None and self.view.page() is not None else None
        if page is None:
            self.logger.warning("Redmine IP lookup skipped: Live Zabbix WebView page is not available")
            self._load_next_redmine_ip_lookup()
            return

        page.runJavaScript(
            self._host_ip_open_host_menu_script(item),
            lambda result, current_item=item: self._on_redmine_ip_host_menu_result(result, current_item),
        )

    def _on_redmine_ip_host_menu_result(self, result, item):
        payload, meta = self._decode_js_json_result(result)
        if not isinstance(payload, dict) or not payload.get("ok"):
            self.logger.info(
                "Redmine IP lookup host menu not opened: host=%s trigger=%s meta=%s",
                getattr(item, "host", ""),
                getattr(item, "trigger_name", ""),
                meta,
            )
            self._load_next_redmine_ip_lookup()
            return

        QTimer.singleShot(450, lambda current_item=item: self._click_redmine_traceroute_menu(current_item, 0))

    def _click_redmine_traceroute_menu(self, item, attempt=0):
        page = self.view.page() if self.view is not None and self.view.page() is not None else None
        if page is None:
            self._load_next_redmine_ip_lookup()
            return

        page.runJavaScript(
            self._host_ip_click_traceroute_script(),
            lambda result, current_item=item, current_attempt=attempt: self._on_redmine_traceroute_menu_result(result, current_item, current_attempt),
        )

    def _on_redmine_traceroute_menu_result(self, result, item, attempt):
        payload, meta = self._decode_js_json_result(result)
        if not isinstance(payload, dict) or not payload.get("ok"):
            if attempt < 2:
                QTimer.singleShot(500, lambda current_item=item, next_attempt=attempt + 1: self._click_redmine_traceroute_menu(current_item, next_attempt))
                return

            self.logger.info(
                "Redmine IP lookup Traceroute menu item not found: host=%s trigger=%s meta=%s",
                getattr(item, "host", ""),
                getattr(item, "trigger_name", ""),
                meta,
            )
            self._load_next_redmine_ip_lookup()
            return

        QTimer.singleShot(900, lambda current_item=item: self._extract_redmine_traceroute_ip(current_item, 0))

    def _extract_redmine_traceroute_ip(self, item, attempt=0):
        page = self.view.page() if self.view is not None and self.view.page() is not None else None
        if page is None:
            self._load_next_redmine_ip_lookup()
            return

        page.runJavaScript(
            self._host_ip_extract_traceroute_script(),
            lambda result, current_item=item, current_attempt=attempt: self._on_redmine_traceroute_ip_result(result, current_item, current_attempt),
        )

    def _on_redmine_traceroute_ip_result(self, result, item, attempt):
        payload, meta = self._decode_js_json_result(result)
        ip = ""
        if isinstance(payload, dict):
            ip = str(payload.get("ip") or "").strip()

        if ip:
            self.logger.info(
                "Redmine IP lookup found: host=%s trigger=%s ip=%s",
                getattr(item, "host", ""),
                getattr(item, "trigger_name", ""),
                ip,
            )
            self._apply_redmine_host_ip(item, ip)
            self._load_next_redmine_ip_lookup()
            return

        if attempt < 2:
            QTimer.singleShot(700, lambda current_item=item, next_attempt=attempt + 1: self._extract_redmine_traceroute_ip(current_item, next_attempt))
            return

        self.logger.info(
            "Redmine IP lookup IP not found: host=%s trigger=%s meta=%s",
            getattr(item, "host", ""),
            getattr(item, "trigger_name", ""),
            meta,
        )
        self._load_next_redmine_ip_lookup()

    def _host_ip_open_host_menu_script(self, item):
        payload = json.dumps(
            {
                "host": str(getattr(item, "host", "") or ""),
                "host_url": str(getattr(item, "host_url", "") or ""),
                "trigger_name": str(getattr(item, "trigger_name", "") or ""),
                "row_index": getattr(item, "row_index", None),
            },
            ensure_ascii=False,
        )
        return r"""
(function() {
  var target = __TARGET__;

  function norm(value) {
    return String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();
  }

  function rawText(element) {
    return String(element ? (element.innerText || element.textContent || '') : '');
  }

  function text(element) {
    return norm(rawText(element));
  }

  function abs(href) {
    try { return new URL(href, document.location.href).href; }
    catch(e) { return href || ''; }
  }

  function visible(element) {
    if (!element) return false;
    var rect = element.getBoundingClientRect();
    return !!(rect.width || rect.height || element.getClientRects().length);
  }

  function clickElement(element) {
    try { element.scrollIntoView({block: 'center', inline: 'center'}); } catch(e) {}
    ['mouseover', 'mousedown', 'mouseup', 'click'].forEach(function(type) {
      try {
        element.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
      } catch(e) {}
    });
  }

  var host = norm(target.host);
  var hostUrl = String(target.host_url || '');
  var trigger = norm(target.trigger_name);
  var hasTargetRowIndex = target.row_index !== null && target.row_index !== undefined && target.row_index !== '';
  var targetRowIndex = hasTargetRowIndex ? Number(target.row_index) : NaN;
  var rows = Array.from(document.querySelectorAll('tr'));

  function rowScore(row, index) {
    var rowText = text(row);
    var links = Array.from(row.querySelectorAll('a'));

    var hostLinkExact = links.some(function(a) {
      return host && text(a) === host;
    });
    var hostUrlExact = links.some(function(a) {
      return hostUrl && abs(a.getAttribute('href') || a.href || '') === hostUrl;
    });
    var hostInRow = !!(host && rowText.indexOf(host) !== -1);
    var triggerInRow = !!(trigger && rowText.indexOf(trigger) !== -1);
    var rowIndexMatch = hasTargetRowIndex && !isNaN(targetRowIndex) && index === targetRowIndex;

    // Главное: если известен host, не даём одной только позиции строки выбрать первый попавшийся узел.
    if (host && !hostLinkExact && !hostUrlExact && !hostInRow) {
      return 0;
    }

    var score = 0;
    if (hostUrlExact) score += 20;
    if (hostLinkExact) score += 16;
    if (hostInRow) score += 10;
    if (triggerInRow) score += 3;
    if (rowIndexMatch && (hostLinkExact || hostUrlExact || hostInRow || triggerInRow)) score += 2;

    return score;
  }

  var best = null;
  var bestScore = 0;
  rows.forEach(function(row, index) {
    var score = rowScore(row, index);
    if (score > bestScore) {
      best = row;
      bestScore = score;
    }
  });

  if (!best || bestScore <= 0) {
    return JSON.stringify({
      ok: false,
      reason: 'problem_row_not_found',
      host: target.host || '',
      trigger: target.trigger_name || '',
      row_index: target.row_index
    });
  }

  var links = Array.from(best.querySelectorAll('a')).filter(visible);
  var hostLinks = links.filter(function(a) {
    var linkText = text(a);
    var href = abs(a.getAttribute('href') || a.href || '');
    return (
      (host && linkText === host) ||
      (host && linkText.indexOf(host) !== -1) ||
      (hostUrl && href === hostUrl)
    );
  });

  var hostLink = hostLinks[0] || links.find(function(a) {
    var href = String(a.getAttribute('href') || a.href || '');
    return /host|hostid|hosts|zabbix\.php/i.test(href || '') && (!host || text(a).indexOf(host) !== -1);
  });

  if (!hostLink) {
    return JSON.stringify({
      ok: false,
      reason: 'host_link_not_found',
      host: target.host || '',
      best_score: bestScore,
      row_text: rawText(best).slice(0, 300)
    });
  }

  var rect = hostLink.getBoundingClientRect();
  try {
    window.__oko_redmine_ip_lookup_target = {
      host: target.host || '',
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
      href: abs(hostLink.getAttribute('href') || hostLink.href || ''),
      time: Date.now()
    };
  } catch(e) {}

  try {
    document.dispatchEvent(new KeyboardEvent('keydown', {bubbles: true, cancelable: true, key: 'Escape', code: 'Escape', which: 27, keyCode: 27}));
    document.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true, cancelable: true, key: 'Escape', code: 'Escape', which: 27, keyCode: 27}));
  } catch(e) {}

  clickElement(hostLink);

  return JSON.stringify({
    ok: true,
    source: 'problems_page_host_link',
    host: target.host || '',
    link_text: rawText(hostLink).slice(0, 120),
    href: abs(hostLink.getAttribute('href') || hostLink.href || ''),
    target_x: rect.left + rect.width / 2,
    target_y: rect.top + rect.height / 2
  });
})();
""".replace("__TARGET__", payload)

    @staticmethod
    def _host_ip_click_traceroute_script():
        return r"""
(function() {
  function text(element) {
    return String(element ? (element.innerText || element.textContent || element.getAttribute('aria-label') || '') : '').replace(/\s+/g, ' ').trim();
  }

  function visible(element) {
    if (!element) return false;
    var rect = element.getBoundingClientRect();
    var style = window.getComputedStyle ? window.getComputedStyle(element) : null;
    return !!(rect.width || rect.height || element.getClientRects().length) &&
      (!style || (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0'));
  }

  function clickElement(element) {
    try { element.scrollIntoView({block: 'center', inline: 'center'}); } catch(e) {}
    ['mouseover', 'mousemove', 'mousedown', 'mouseup', 'click'].forEach(function(type) {
      try {
        element.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
      } catch(e) {}
    });
  }

  function center(element) {
    var r = element.getBoundingClientRect();
    return {x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height};
  }

  function distanceToTarget(element, target) {
    if (!target || typeof target.x !== 'number' || typeof target.y !== 'number') {
      return 999999999;
    }
    var c = center(element);
    var dx = c.x - target.x;
    var dy = c.y - target.y;
    return Math.sqrt(dx * dx + dy * dy);
  }

  var target = window.__oko_redmine_ip_lookup_target || {};

  var candidates = Array.from(document.querySelectorAll(
    'a.menu-popup-item, [role="menuitem"], .menu-popup-item, .menu-popup-item-text, a, button'
  )).filter(function(element) {
    if (!visible(element)) return false;
    var label = String(element.getAttribute('aria-label') || '');
    var value = text(element) + ' ' + label;
    return /traceroute/i.test(value);
  });

  if (!candidates.length) {
    return JSON.stringify({
      ok: false,
      reason: 'traceroute_not_found',
      target: target || {}
    });
  }

  candidates.sort(function(a, b) {
    return distanceToTarget(a, target) - distanceToTarget(b, target);
  });

  var traceroute = candidates[0];
  var tracerouteText = text(traceroute);
  var c = center(traceroute);
  var dist = distanceToTarget(traceroute, target);

  clickElement(traceroute);

  try {
    window.__oko_redmine_ip_traceroute_clicked = {
      host: target.host || '',
      time: Date.now(),
      x: c.x,
      y: c.y,
      distance: dist,
      text: tracerouteText
    };
  } catch(e) {}

  return JSON.stringify({
    ok: true,
    source: 'nearest_traceroute_menu_item',
    traceroute_text: tracerouteText,
    distance: dist,
    target: target || {},
    candidates_count: candidates.length
  });
})();
"""

    @staticmethod
    def _host_ip_extract_traceroute_script():
        return r"""
(function() {
  function text(element) {
    return String(element ? (element.value || element.innerText || element.textContent || '') : '');
  }

  function clickElement(element) {
    if (!element) return;
    try {
      element.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
    } catch(e) {
      try { element.click(); } catch(e2) {}
    }
  }

  var textarea =
    document.querySelector('body > div > div.overlay-dialogue.modal.modal-popup.modal-popup-medium > div.overlay-dialogue-body > form > ul > li > div.table-forms-td-right > textarea') ||
    document.querySelector('.overlay-dialogue textarea') ||
    document.querySelector('.modal-popup textarea') ||
    document.querySelector('textarea');

  var value = text(textarea);
  var ip = '';

  var afterTraceroute = value.match(/traceroute\s+to\s+([^\s,(]+)/i);
  if (afterTraceroute) {
    ip = afterTraceroute[1];
  }

  var ipv4 = value.match(/((?:\d{1,3}\.){3}\d{1,3})/);
  if (ipv4) {
    ip = ipv4[1];
  }

  var closeButton =
    document.querySelector('.overlay-dialogue .btn-overlay-close') ||
    document.querySelector('.overlay-dialogue button[title*="Закрыть"]') ||
    document.querySelector('.overlay-dialogue button[aria-label*="Закрыть"]') ||
    document.querySelector('.overlay-dialogue .icon-close') ||
    document.querySelector('.overlay-dialogue [data-action="close"]');

  if (ip && closeButton) {
    clickElement(closeButton);
  }

  return JSON.stringify({
    ok: !!ip,
    ip: ip,
    has_textarea: !!textarea,
    textarea_text: value.slice(0, 300)
  });
})();
"""

    def open_redmine_for_selected_row(self):
        items = self._choose_redmine_items_for_selection()
        if not items:
            QMessageBox.information(self, "Redmine", "Выберите одну или несколько строк проблемы в Live Zabbix Monitor.")
            return

        self._enrich_redmine_graph_links(items, self._open_redmine_after_graph_lookup)

    def _open_redmine_after_graph_lookup(self, items):
        self._enrich_redmine_host_ips(items, self._open_redmine_after_ip_lookup)

    def _open_redmine_after_ip_lookup(self, items):
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

        profile = self.view.page().profile() if self.view is not None and self.view.page() is not None else None
        dialog = RedmineCreateDialog(profile, redmine_url, ensure_live_monitor_defaults(self.config), self)
        self.redmine_dialogs.append(dialog)
        dialog.finished.connect(lambda _result, d=dialog: self.redmine_dialogs.remove(d) if d in self.redmine_dialogs else None)
        dialog.show()

    def open_mm_otrs_for_selected_row(self):
        items = self._choose_redmine_items_for_selection("ОТРС ММ")
        if not items:
            QMessageBox.information(self, "ОТРС ММ", "Выберите одну или несколько строк проблемы в Live Zabbix Monitor.")
            return

        self._enrich_redmine_host_ips(items, self._open_mm_otrs_after_ip_lookup)

    @staticmethod
    def _mm_otrs_common_prefix(hosts):
        prefixes = []
        for host in hosts or []:
            text = str(host or "").strip()
            if "-" not in text:
                return ""
            prefix = text.split("-", 1)[0].strip()
            if not prefix:
                return ""
            prefixes.append(prefix)

        if not prefixes:
            return ""

        first = prefixes[0]
        if all(prefix.casefold() == first.casefold() for prefix in prefixes):
            return first
        return ""

    def _mm_otrs_trigger_lines(self, triggers):
        triggers = self._unique_text_values(triggers)
        if not triggers:
            triggers = ["Проблема Zabbix"]

        if len(triggers) == 1:
            return ["Триггер:", triggers[0]]

        lines = ["Триггеры:"]
        for index, trigger in enumerate(triggers, start=1):
            lines.append(f"{index}. {trigger}")
        return lines

    def _build_mm_otrs_subject_and_body(self, items):
        """Build MM OTRS subject/body. For multi-host tasks, resolve IP per host."""
        items = self._unique_live_items(items)
        grouped_hosts = self._redmine_group_items_by_host(items)
        hosts = [host for host, _host_items in grouped_hosts]

        def item_trigger(item):
            return str(getattr(item, "trigger_name", "") or "Проблема Zabbix").strip()

        triggers = []
        seen_triggers = set()
        for item in items or []:
            trigger = item_trigger(item)
            if not trigger:
                continue
            key = trigger.casefold()
            if key in seen_triggers:
                continue
            seen_triggers.add(key)
            triggers.append(trigger)

        final_line = "Просьба проверить и восстановить работоспособность."

        if not grouped_hosts:
            subject = "На нескольких узлах наблюдаются триггеры"
            body_lines = ["На нескольких узлах наблюдаются триггеры", ""]
            if triggers:
                body_lines.append("Триггеры:")
                body_lines.extend(self._mm_otrs_trigger_lines(triggers))
                body_lines.append("")
            body_lines.append(final_line)
            return subject, "\n".join(body_lines)

        if len(grouped_hosts) == 1:
            host, host_items = grouped_hosts[0]
            ip_text = self._redmine_ip_text_for_items(host_items)

            if len(triggers) == 1:
                trigger = triggers[0]
                subject = f"На узле {host} наблюдается триггер {trigger}"
                body_lines = [
                    f"На узле {host} — IP: {ip_text} наблюдается триггер {trigger}",
                    "",
                    final_line,
                ]
                return subject, "\n".join(body_lines)

            subject = f"На узле {host} наблюдаются триггеры"
            body_lines = [
                f"На узле {host} — IP: {ip_text} наблюдаются триггеры:",
            ]
            body_lines.extend(self._mm_otrs_trigger_lines(triggers))
            body_lines.extend(["", final_line])
            return subject, "\n".join(body_lines)

        prefix = self._mm_otrs_common_prefix(hosts)
        if prefix:
            subject = f"На {prefix} наблюдаются триггеры на узлах"
            body_lines = [
                f"На серверах ст. {prefix} наблюдаются триггеры",
                "",
                "Узлы сети:",
            ]
        else:
            subject = "На нескольких узлах наблюдаются триггеры"
            body_lines = [
                "На нескольких узлах наблюдаются триггеры",
                "",
                "Узлы сети:",
            ]

        for index, (host, host_items) in enumerate(grouped_hosts, start=1):
            ip_text = self._redmine_ip_text_for_items(host_items)
            body_lines.append(f"{index}. {host} — IP: {ip_text}")

        body_lines.append("")

        if len(triggers) == 1:
            body_lines.append("Триггер:")
            body_lines.append(triggers[0])
        elif triggers:
            body_lines.append("Триггеры:")
            body_lines.extend(self._mm_otrs_trigger_lines(triggers))

        body_lines.extend(["", final_line])
        return subject, "\n".join(body_lines)


    def _open_mm_otrs_after_ip_lookup(self, items):
        url = str(self.settings.get("mm_otrs_create_url", "") or "").strip()
        if not url:
            QMessageBox.warning(
                self,
                "ОТРС ММ",
                "Не указан URL создания задачи ОТРС ММ.\n\nОткройте Настройки → Режим разработчика и заполните поле URL создания задачи ОТРС ММ.",
            )
            return

        subject, body = self._build_mm_otrs_subject_and_body(items)

        dialog = QDialog(self)
        dialog.setWindowTitle("Создать задачу на ММ")
        dialog.resize(1200, 820)

        root = QVBoxLayout(dialog)
        status_label = QLabel("Открываю форму создания задачи ОТРС ММ...")
        root.addWidget(status_label)

        view = register_web_view(QWebEngineView(dialog))
        profile = self.view.page().profile() if self.view is not None and self.view.page() is not None else None
        if profile is not None:
            page = QWebEnginePage(profile, view)
            view.setPage(page)

        root.addWidget(view, stretch=1)

        mm_otrs_state = {"started": False}

        def fill_form(ok):
            if not ok:
                status_label.setText("Страница открылась с ошибкой. Проверьте доступ/авторизацию.")
                return

            if mm_otrs_state["started"]:
                return

            mm_otrs_state["started"] = True
            status_label.setText("Страница загружена. Проверяю авторизацию ОТРС ММ...")
            QTimer.singleShot(1000, lambda: self._login_mm_otrs_if_needed(view, status_label, subject, body, 1))

        view.loadFinished.connect(fill_form)

        def cleanup(_result=0, current_dialog=dialog, current_view=view):
            try:
                self.mm_otrs_dialogs.remove(current_dialog)
            except ValueError:
                pass
            safe_delete_web_view(current_view, logger=self.logger, context="LiveZabbixMonitorWidget MM OTRS")

        dialog.finished.connect(cleanup)
        self.mm_otrs_dialogs.append(dialog)
        dialog.show()
        view.load(QUrl(url))

    def _mm_otrs_saved_credentials(self):
        """Return only OTRS credentials from the current profile credentials."""
        credentials = self.credentials or {}

        explicit_keys = (
            "otrs",
            "OTRS",
            "itsm",
            "ITSM",
            "mm_otrs",
            "MM_OTRS",
            "otrs_mm",
            "OTRS_MM",
            "мм",
            "ММ",
        )

        def extract_pair(value):
            if not isinstance(value, dict):
                return {"login": "", "password": ""}

            login = (
                value.get("login")
                or value.get("username")
                or value.get("user")
                or value.get("email")
                or value.get("otrs_login")
                or value.get("itsm_login")
                or ""
            )
            password = (
                value.get("password")
                or value.get("pass")
                or value.get("secret")
                or value.get("otrs_password")
                or value.get("itsm_password")
                or ""
            )

            return {
                "login": str(login or ""),
                "password": str(password or ""),
            }

        for key in explicit_keys:
            pair = extract_pair(credentials.get(key))
            if pair["login"] and pair["password"]:
                return pair

        services = credentials.get("services")
        if isinstance(services, dict):
            for key in explicit_keys:
                pair = extract_pair(services.get(key))
                if pair["login"] and pair["password"]:
                    return pair

        profiles = credentials.get("profiles")
        if isinstance(profiles, dict):
            for key in explicit_keys:
                pair = extract_pair(profiles.get(key))
                if pair["login"] and pair["password"]:
                    return pair

        return {"login": "", "password": ""}

    def _login_mm_otrs_if_needed(self, view, status_label, subject, body, attempt=1):
        creds = self._mm_otrs_saved_credentials()
        login_json = json.dumps(creds.get("login", ""), ensure_ascii=False)
        password_json = json.dumps(creds.get("password", ""), ensure_ascii=False)

        js = f"""
(function() {{
  const loginValue = {login_json};
  const passwordValue = {password_json};

  function fire(element) {{
    if (!element) return;
    ["input", "change", "blur"].forEach(function(type) {{
      try {{ element.dispatchEvent(new Event(type, {{bubbles: true}})); }} catch (e) {{}}
    }});
  }}

  function setValue(element, value) {{
    if (!element) return false;
    try {{
      element.focus();
      element.value = value;
      fire(element);
      return true;
    }} catch (e) {{
      return false;
    }}
  }}

  function clickElement(element) {{
    if (!element) return false;
    try {{ element.scrollIntoView({{block: "center", inline: "center"}}); }} catch (e) {{}}
    try {{
      ["mouseover", "mousedown", "mouseup", "click"].forEach(function(type) {{
        element.dispatchEvent(new MouseEvent(type, {{bubbles: true, cancelable: true, view: window}}));
      }});
      return true;
    }} catch (e) {{
      try {{ element.click(); return true; }} catch (e2) {{}}
    }}
    return false;
  }}

  const subjectInput =
    document.querySelector("#Subject") ||
    document.querySelector('input[name="Subject"]');

  if (subjectInput) {{
    return JSON.stringify({{
      needs_login: false,
      subject_found: true,
      login_clicked: false
    }});
  }}

  const loginButton = document.querySelector("#LoginButton");
  const passwordInput =
    document.querySelector("#Password") ||
    document.querySelector('input[name="Password"]') ||
    document.querySelector('input[type="password"]');

  const loginInput =
    document.querySelector("#User") ||
    document.querySelector("#Login") ||
    document.querySelector('input[name="User"]') ||
    document.querySelector('input[name="Login"]') ||
    document.querySelector('input[name="UserLogin"]') ||
    document.querySelector('input[type="text"]') ||
    document.querySelector('input[type="email"]');

  const needsLogin = !!(loginButton || passwordInput);

  if (!needsLogin) {{
    return JSON.stringify({{
      needs_login: false,
      subject_found: false,
      login_clicked: false
    }});
  }}

  if (!loginValue || !passwordValue) {{
    return JSON.stringify({{
      needs_login: true,
      missing_credentials: true,
      login_found: !!loginInput,
      password_found: !!passwordInput,
      login_button_found: !!loginButton
    }});
  }}

  const loginSet = setValue(loginInput, loginValue);
  const passwordSet = setValue(passwordInput, passwordValue);
  const clicked = clickElement(loginButton);

  return JSON.stringify({{
    needs_login: true,
    missing_credentials: false,
    login_found: !!loginInput,
    password_found: !!passwordInput,
    login_button_found: !!loginButton,
    login_set: loginSet,
    password_set: passwordSet,
    login_clicked: clicked
  }});
}})();
"""

        page = view.page() if view is not None else None
        if page is None:
            status_label.setText("Не удалось получить страницу ОТРС ММ.")
            return

        def after_login_check(result):
            text = str(result or "")

            if '"subject_found":true' in text:
                status_label.setText("Авторизация уже есть. Заполняю тему и описание...")
                self._fill_mm_otrs_direct_fields(view, status_label, subject, body, 1)
                return

            if '"missing_credentials":true' in text:
                status_label.setText("ОТРС просит логин/пароль, но сохранённые доступы профиля не найдены.")
                return

            if '"login_clicked":true' in text:
                status_label.setText("Логин и пароль подставлены, нажимаю Войти и жду форму задачи...")
                QTimer.singleShot(2500, lambda: self._login_mm_otrs_if_needed(view, status_label, subject, body, attempt + 1))
                return

            if attempt < 8:
                status_label.setText(f"Жду форму задачи или логина ОТРС ММ... {attempt}/8")
                QTimer.singleShot(1000, lambda: self._login_mm_otrs_if_needed(view, status_label, subject, body, attempt + 1))
                return

            status_label.setText("Не удалось определить форму задачи или форму логина ОТРС ММ.")

        page.runJavaScript(js, after_login_check)


    def _mm_otrs_required_field_steps(self):
        return [
            {
                "name": "Тип",
                "input_selector": "#TypeID_Search",
                "value": "Задача",
                "option_selector": "#TypeID_Select a.jstree-anchor",
                "option_text": "Задача",
            },
            {
                "name": "Клиент",
                "input_selector": "#FromCustomer",
                "value": "stp",
                "option_selector": "#ui-id-92",
            },
            {
                "name": "Очередь/направление",
                "input_selector": "#Dest_Search",
                "value": "",
                "option_selector": "#j6_2",
            },
            {
                "name": "Сервис",
                "input_selector": "#ServiceID_Search",
                "value": "",
                "option_selector": "#j9_14",
            },
            {
                "name": "SLA",
                "input_selector": "#SLAID_Search",
                "value": "",
                "option_selector": "body > div.InputField_ListContainer.ExpandToBottom",
                "click_first_child": True,
            },
        ]

    def _fill_mm_otrs_required_fields(self, view, status_label, subject, body, step_index=0, attempt=1):
        steps = self._mm_otrs_required_field_steps()
        if step_index >= len(steps):
            status_label.setText("Обязательные поля заполнены. Заполняю тему и описание...")
            QTimer.singleShot(700, lambda: self._fill_mm_otrs_form(view, status_label, subject, body, 1))
            return

        step = steps[step_index]
        step_json = json.dumps(step, ensure_ascii=False)

        js = f"""
(function() {{
  const step = {step_json};

  function fire(element) {{
    if (!element) return;
    ["input", "change", "keyup", "blur"].forEach(function(type) {{
      try {{ element.dispatchEvent(new Event(type, {{bubbles: true}})); }} catch (e) {{}}
    }});
  }}

  function clickElement(element) {{
    if (!element) return false;
    try {{ element.scrollIntoView({{block: "center", inline: "center"}}); }} catch (e) {{}}
    try {{
      ["mouseover", "mousedown", "mouseup", "click"].forEach(function(type) {{
        element.dispatchEvent(new MouseEvent(type, {{bubbles: true, cancelable: true, view: window}}));
      }});
      return true;
    }} catch (e) {{
      try {{ element.click(); return true; }} catch (e2) {{}}
    }}
    return false;
  }}

  function visible(element) {{
    if (!element) return false;
    const rect = element.getBoundingClientRect();
    const style = window.getComputedStyle ? window.getComputedStyle(element) : null;
    return !!(rect.width || rect.height || element.getClientRects().length) &&
      (!style || (style.visibility !== "hidden" && style.display !== "none"));
  }}

  const input = document.querySelector(step.input_selector);
  if (!input || !visible(input)) {{
    return JSON.stringify({{
      ok: false,
      reason: "input_not_ready",
      name: step.name,
      input_selector: step.input_selector,
      option_selector: step.option_selector
    }});
  }}

  try {{
    input.focus();
    clickElement(input);
    if (step.value) {{
      input.value = step.value;
      fire(input);
    }}
  }} catch (e) {{}}

  if (step.value && String(input.value || "").trim().casefold && String(input.value || "").trim().toLowerCase() === String(step.value || "").trim().toLowerCase()) {{
    return JSON.stringify({{
      ok: true,
      reason: "already_selected",
      name: step.name,
      input_found: true,
      input_value: String(input.value || "")
    }});
  }}

  let option = null;

  try {{
    const allOptions = Array.from(document.querySelectorAll(step.option_selector));
    if (step.option_text) {{
      option = allOptions.find(function(element) {{
        return visible(element) && String(element.innerText || element.textContent || "").trim() === String(step.option_text || "").trim();
      }});
    }}
    if (!option) {{
      option = allOptions.find(function(element) {{ return visible(element); }}) || null;
    }}
  }} catch (e) {{}}

  if (option && step.click_first_child) {{
    const child =
      Array.from(option.querySelectorAll("a, li, div, span"))
        .find(function(element) {{ return visible(element) && String(element.innerText || element.textContent || "").trim(); }});
    if (child) option = child;
  }}

  if (!option || !visible(option)) {{
    return JSON.stringify({{
      ok: false,
      reason: "option_not_ready",
      name: step.name,
      input_found: true,
      input_value: String(input.value || ""),
      option_selector: step.option_selector,
      option_text: step.option_text || ""
    }});
  }}

  const clicked = clickElement(option);

  return JSON.stringify({{
    ok: clicked,
    reason: clicked ? "" : "click_failed",
    name: step.name,
    input_found: true,
    input_value: String(input.value || ""),
    option_found: !!option,
    option_text: String(option.innerText || option.textContent || "").trim()
  }});
}})();
"""

        page = view.page() if view is not None else None
        if page is None:
            status_label.setText("Не удалось получить страницу ОТРС ММ.")
            return

        def after_step(result):
            text = str(result or "")
            parsed = {}
            if isinstance(result, dict):
                parsed = result
            elif isinstance(result, str):
                try:
                    parsed = json.loads(result)
                except Exception:
                    parsed = {}
            ok = bool(parsed.get("ok"))

            if ok:
                status_label.setText(f"ОТРС ММ: заполнено поле «{step.get('name', '')}».")
                QTimer.singleShot(
                    900,
                    lambda: self._fill_mm_otrs_required_fields(view, status_label, subject, body, step_index + 1, 1),
                )
                return

            if attempt < 10:
                status_label.setText(
                    f"ОТРС ММ: жду поле «{step.get('name', '')}»... попытка {attempt}/10"
                )
                QTimer.singleShot(
                    700,
                    lambda: self._fill_mm_otrs_required_fields(view, status_label, subject, body, step_index, attempt + 1),
                )
                return

            status_label.setText(
                f"ОТРС ММ: не удалось заполнить поле «{step.get('name', '')}». "
                f"Результат: {text[:300]}"
            )

        page.runJavaScript(js, after_step)


    def _fill_mm_otrs_direct_fields(self, view, status_label, subject, body, attempt=1, step_index=0):
        """Fill OTRS fields in dependency order: Type -> Customer -> Dest -> Service -> SLA."""
        steps = [
            {
                "name": "Тип",
                "field": "#TypeID",
                "value": "8",
                "search": "#TypeID_Search",
                "search_text": "Задача",
            },
            {
                "name": "Очередь",
                "field": "#Dest",
                "value": "23||2-я линия::ГУП ММ",
                "search": "#Dest_Search",
                "search_text": "ГУП ММ",
            },
            {
                "name": "Сервис",
                "field": "#ServiceID",
                "value": "247",
                "search": "#ServiceID_Search",
                "search_text": "Обслуживание оборудования",
            },
            {
                "name": "SLA",
                "field": "#SLAID",
                "value": "5",
                "search": "#SLAID_Search",
                "search_text": "SLA_none",
            },
        ]

        if step_index >= len(steps):
            status_label.setText("Поля ОТРС ММ заполнены. Заполняю тему и описание...")
            QTimer.singleShot(700, lambda: self._fill_mm_otrs_form(view, status_label, subject, body, 1))
            return

        step = steps[step_index]
        step_json = json.dumps(step, ensure_ascii=False)

        js = f"""
(function() {{
  const step = {step_json};

  function fire(element) {{
    if (!element) return;
    try {{ element.dispatchEvent(new Event("input", {{bubbles: true, cancelable: true}})); }} catch (e) {{}}
    try {{ element.dispatchEvent(new Event("change", {{bubbles: true, cancelable: true}})); }} catch (e) {{}}
    try {{ element.dispatchEvent(new Event("blur", {{bubbles: true, cancelable: true}})); }} catch (e) {{}}
  }}

  function setValue(selector, value) {{
    const element = document.querySelector(selector);
    if (!element) {{
      return {{ok: false, reason: "field_not_found", selector: selector, value: ""}};
    }}

    try {{
      element.value = value;
      fire(element);
      return {{
        ok: String(element.value || "") === String(value || ""),
        reason: String(element.value || "") === String(value || "") ? "" : "value_not_applied",
        selector: selector,
        value: String(element.value || "")
      }};
    }} catch (e) {{
      return {{ok: false, reason: String(e && e.message ? e.message : e), selector: selector, value: ""}};
    }}
  }}

  function setSearchText(selector, text) {{
    const element = document.querySelector(selector);
    if (!element) return false;
    try {{
      element.value = text;
      fire(element);
      return true;
    }} catch (e) {{
      return false;
    }}
  }}

  const fieldResult = setValue(step.field, step.value);
  const searchResult = setSearchText(step.search, step.search_text);

  return JSON.stringify({{
    ok: !!fieldResult.ok,
    name: step.name,
    field_result: fieldResult,
    search_result: searchResult,
    current: {{
      TypeID: document.querySelector("#TypeID") ? document.querySelector("#TypeID").value : "",
      Dest: document.querySelector("#Dest") ? document.querySelector("#Dest").value : "",
      ServiceID: document.querySelector("#ServiceID") ? document.querySelector("#ServiceID").value : "",
      SLAID: document.querySelector("#SLAID") ? document.querySelector("#SLAID").value : "",
      SLAID_Search: document.querySelector("#SLAID_Search") ? document.querySelector("#SLAID_Search").value : ""
    }}
  }});
}})();
"""

        page = view.page() if view is not None else None
        if page is None:
            status_label.setText("Не удалось получить страницу ОТРС ММ.")
            return

        def after_step(result):
            text = str(result or "")
            parsed = {}
            if isinstance(result, dict):
                parsed = result
            elif isinstance(result, str):
                try:
                    parsed = json.loads(result)
                except Exception:
                    parsed = {}

            if parsed.get("ok"):
                status_label.setText(f"ОТРС ММ: заполнено поле «{step.get('name', '')}».")

                if step_index == 0:
                    QTimer.singleShot(900, lambda: self._fill_mm_otrs_customer(view, status_label, subject, body, 1))
                    return

                QTimer.singleShot(
                    1000,
                    lambda: self._fill_mm_otrs_direct_fields(
                        view, status_label, subject, body, 1, step_index + 1
                    ),
                )
                return

            if attempt < 8:
                status_label.setText(f"ОТРС ММ: жду поле «{step.get('name', '')}»... попытка {attempt}/8")
                QTimer.singleShot(
                    800,
                    lambda: self._fill_mm_otrs_direct_fields(
                        view, status_label, subject, body, attempt + 1, step_index
                    ),
                )
                return

            status_label.setText(
                f"Не удалось заполнить поле «{step.get('name', '')}». "
                f"Продолжаю дальше. Результат: {text[:350]}"
            )
            QTimer.singleShot(
                800,
                lambda: self._fill_mm_otrs_direct_fields(
                    view, status_label, subject, body, 1, step_index + 1
                ),
            )

        page.runJavaScript(js, after_step)


    def _fill_mm_otrs_customer(self, view, status_label, subject, body, attempt=1):
        """Select OTRS customer from autocomplete and hide extra empty/raw customer rows."""
        js = r"""
(function() {
  function fire(element, type) {
    if (!element) return;
    try {
      element.dispatchEvent(new Event(type, {bubbles: true, cancelable: true}));
    } catch (e) {}
  }

  function key(element, type, keyValue, codeValue) {
    if (!element) return;
    const keyCode = keyValue === "Enter" ? 13 : (keyValue === "ArrowDown" ? 40 : 0);
    try {
      element.dispatchEvent(new KeyboardEvent(type, {
        bubbles: true,
        cancelable: true,
        key: keyValue || "",
        code: codeValue || keyValue || "",
        which: keyCode,
        keyCode: keyCode
      }));
    } catch (e) {}
  }

  function clickElement(element) {
    if (!element) return false;
    try {
      ["mouseover", "mousemove", "mousedown", "mouseup", "click"].forEach(function(type) {
        element.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
      });
      return true;
    } catch (e) {
      try { element.click(); return true; } catch (e2) {}
    }
    return false;
  }

  function visible(element) {
    if (!element) return false;
    const rect = element.getBoundingClientRect();
    const style = window.getComputedStyle ? window.getComputedStyle(element) : null;
    return !!(rect.width || rect.height || element.getClientRects().length) &&
      (!style || (style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0"));
  }

  function customerTextFields() {
    return Array.from(document.querySelectorAll(
      "input.CustomerTicketText, #CustomerTicketText, #CustomerTicketText_1, .MainCustomer"
    ));
  }

  function selectedCustomerText() {
    return customerTextFields().map(function(element) {
      return String(element.value || element.innerText || element.textContent || "").trim();
    }).filter(Boolean).join(" | ");
  }

  function isRealCustomerText(text) {
    return /stp@stdpr\.ru|Служба Поддержки/i.test(String(text || ""));
  }

  function isRawOrEmptyCustomerText(text) {
    const value = String(text || "").trim();
    return value === "" || /^stp$/i.test(value);
  }

  function findCustomerRow(field) {
    let current = field;
    for (let i = 0; current && i < 8; i += 1) {
      const textInputs = current.querySelectorAll ? current.querySelectorAll("input.CustomerTicketText").length : 0;
      const radios = current.querySelectorAll ? current.querySelectorAll("input.CustomerTicketRadio").length : 0;

      if (textInputs === 1 && radios <= 1) {
        return current;
      }

      current = current.parentElement;
    }

    return field.parentElement;
  }

  function hideExtraCustomerRow(field) {
    if (!field) return false;

    try {
      field.value = "";
      fire(field, "input");
      fire(field, "change");
      fire(field, "blur");
    } catch (e) {}

    const suffix = field.id && field.id.startsWith("CustomerTicketText")
      ? field.id.replace("CustomerTicketText", "")
      : "";

    const radio = document.querySelector("#CustomerSelected" + suffix);
    if (radio) {
      try {
        radio.checked = false;
        fire(radio, "change");
      } catch (e) {}
    }

    const row = findCustomerRow(field);
    if (row) {
      row.setAttribute("data-oko-hidden-extra-customer", "1");
      row.style.display = "none";
    }

    return true;
  }

  function normalizeCustomerRows() {
    let realField = null;

    customerTextFields().forEach(function(field) {
      const text = String(field.value || field.innerText || field.textContent || "").trim();
      if (isRealCustomerText(text)) {
        realField = field;
      }
    });

    if (!realField) {
      return {
        ok: false,
        reason: "real_customer_row_not_found",
        selected: selectedCustomerText()
      };
    }

    const suffix = realField.id && realField.id.startsWith("CustomerTicketText")
      ? realField.id.replace("CustomerTicketText", "")
      : "_1";

    const realRadio =
      document.querySelector("#CustomerSelected" + suffix) ||
      document.querySelector("#CustomerSelected_1");

    if (realRadio) {
      try {
        realRadio.checked = true;
        fire(realRadio, "click");
        fire(realRadio, "change");
      } catch (e) {}
    }

    let hidden_count = 0;

    customerTextFields().forEach(function(field) {
      if (field === realField) return;

      const text = String(field.value || field.innerText || field.textContent || "").trim();
      if (isRawOrEmptyCustomerText(text)) {
        if (hideExtraCustomerRow(field)) {
          hidden_count += 1;
        }
      }
    });

    const input = document.querySelector("#FromCustomer");
    if (input) {
      try {
        input.value = "";
        fire(input, "input");
        fire(input, "change");
        fire(input, "blur");
      } catch (e) {}
    }

    const counter = document.querySelector("#CustomerTicketCounterFromCustomer");
    if (counter) {
      try {
        counter.value = "1";
        fire(counter, "change");
      } catch (e) {}
    }

    return {
      ok: true,
      reason: "normalized",
      selected: selectedCustomerText(),
      real_field_id: realField.id || "",
      real_radio_id: realRadio ? realRadio.id : "",
      hidden_count: hidden_count,
      from_customer_value: input ? String(input.value || "") : "",
      counter: counter ? String(counter.value || "") : ""
    };
  }

  function clickableParent(element) {
    let current = element;
    for (let i = 0; current && i < 5; i += 1) {
      const tag = String(current.tagName || "").toLowerCase();
      const text = String(current.innerText || current.textContent || "").trim();
      if (["li", "a", "div", "span"].includes(tag) &&
          /Служба Поддержки|stp@stdpr\.ru|stp\.stdpr\.ru/i.test(text)) {
        return current;
      }
      current = current.parentElement;
    }
    return element;
  }

  const already = normalizeCustomerRows();
  if (already.ok) {
    return JSON.stringify({
      ok: true,
      reason: "already_selected_normalized",
      normalize: already
    });
  }

  const input = document.querySelector("#FromCustomer");
  if (!input) {
    return JSON.stringify({
      ok: false,
      reason: "FromCustomer_not_found",
      selected: selectedCustomerText()
    });
  }

  input.focus();
  input.value = "stp";

  try {
    input.setSelectionRange(0, input.value.length);
  } catch (e) {}

  ["focus", "input", "keydown", "keyup", "change"].forEach(function(type) {
    fire(input, type);
  });

  try {
    if (window.jQuery) {
      const jq = window.jQuery(input);
      jq.trigger("focus");
      jq.trigger("input");
      jq.trigger("keydown");
      jq.trigger("keyup");
      jq.trigger("change");
      if (jq.autocomplete) {
        jq.autocomplete("search", "stp");
      }
    }
  } catch (e) {}

  let clicked = false;
  let clickedText = "";
  let method = "keyboard";

  key(input, "keydown", "ArrowDown", "ArrowDown");
  key(input, "keyup", "ArrowDown", "ArrowDown");
  key(input, "keydown", "Enter", "Enter");
  key(input, "keyup", "Enter", "Enter");

  let normalizedAfterKeyboard = normalizeCustomerRows();

  if (!normalizedAfterKeyboard.ok) {
    const rect = input.getBoundingClientRect();
    const points = [
      [rect.left + 20, rect.bottom + 14],
      [rect.left + 160, rect.bottom + 14],
      [rect.left + 20, rect.bottom + 28],
      [rect.left + 160, rect.bottom + 28]
    ];

    for (const point of points) {
      const element = document.elementFromPoint(point[0], point[1]);
      const parent = clickableParent(element);
      const text = String(parent && (parent.innerText || parent.textContent) || "").trim();

      if (parent && visible(parent) && /Служба Поддержки|stp@stdpr\.ru|stp\.stdpr\.ru/i.test(text)) {
        clicked = clickElement(parent);
        clickedText = text;
        method = "elementFromPoint";
        break;
      }
    }
  }

  try {
    window.setTimeout(function() {
      normalizeCustomerRows();
    }, 350);
  } catch (e) {}

  const finalNormalize = normalizeCustomerRows();

  return JSON.stringify({
    ok: finalNormalize.ok,
    reason: finalNormalize.ok ? "selected_normalized" : "selection_started",
    method: method,
    clicked: clicked,
    clicked_text: clickedText,
    normalize: finalNormalize,
    selected: selectedCustomerText(),
    from_customer_value: input.value || ""
  });
})();
"""

        page = view.page() if view is not None else None
        if page is None:
            status_label.setText("Не удалось получить страницу ОТРС ММ.")
            return

        def after_customer(result):
            text = str(result or "")
            parsed = {}
            if isinstance(result, dict):
                parsed = result
            elif isinstance(result, str):
                try:
                    parsed = json.loads(result)
                except Exception:
                    parsed = {}

            if parsed.get("ok"):
                status_label.setText("Клиент ОТРС ММ выбран, лишняя строка скрыта. Заполняю очередь/сервис/SLA...")
                QTimer.singleShot(
                    1200,
                    lambda: self._fill_mm_otrs_direct_fields(view, status_label, subject, body, 1, 1),
                )
                return

            if attempt < 12:
                status_label.setText(f"Ищу и выбираю клиента stp из выпадающего списка... попытка {attempt}/12")
                QTimer.singleShot(
                    900,
                    lambda: self._fill_mm_otrs_customer(view, status_label, subject, body, attempt + 1),
                )
                return

            status_label.setText(
                "Не удалось выбрать клиента из выпадающего списка. "
                f"Результат: {text[:500]}. Продолжаю поля дальше."
            )
            QTimer.singleShot(
                900,
                lambda: self._fill_mm_otrs_direct_fields(view, status_label, subject, body, 1, 1),
            )

        page.runJavaScript(js, after_customer)


    def _fill_mm_otrs_form(self, view, status_label, subject, body, attempt=1):
        subject_json = json.dumps(subject, ensure_ascii=False)
        body_json = json.dumps(body, ensure_ascii=False)

        js = f"""
(function() {{
  const subject = {subject_json};
  const bodyText = {body_json};

  function htmlEscape(value) {{
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }}

  function fire(element) {{
    if (!element) return;
    ["input", "change", "blur"].forEach(function(type) {{
      try {{ element.dispatchEvent(new Event(type, {{bubbles: true}})); }} catch (e) {{}}
    }});
  }}

  const subjectInput =
    document.querySelector("#Subject") ||
    document.querySelector('input[name="Subject"]') ||
    document.querySelector('input.W75pc[name="Subject"]');

  if (subjectInput) {{
    subjectInput.focus();
    subjectInput.value = subject;
    fire(subjectInput);
  }}

  const bodyHtml = htmlEscape(bodyText).replace(/\\n/g, "<br>");
  let bodyFilled = false;
  let ckeditorUsed = false;
  let iframeFound = false;

  try {{
    if (window.CKEDITOR && window.CKEDITOR.instances) {{
      const names = Object.keys(window.CKEDITOR.instances);
      for (const name of names) {{
        window.CKEDITOR.instances[name].setData(bodyHtml);
        try {{ window.CKEDITOR.instances[name].updateElement(); }} catch (e) {{}}
        bodyFilled = true;
        ckeditorUsed = true;
        break;
      }}
    }}
  }} catch (e) {{}}

  const iframe =
    document.querySelector("#cke_1_contents > iframe") ||
    document.querySelector(".cke_wysiwyg_frame") ||
    document.querySelector("iframe");

  try {{
    if (iframe) {{
      iframeFound = true;
    }}
    if (iframe && iframe.contentDocument && iframe.contentDocument.body) {{
      iframe.contentDocument.body.innerHTML = bodyHtml;
      fire(iframe.contentDocument.body);
      bodyFilled = true;
    }}
  }} catch (e) {{}}

  return JSON.stringify({{
    subject_found: !!subjectInput,
    body_filled: bodyFilled,
    ckeditor_used: ckeditorUsed,
    iframe_found: iframeFound
  }});
}})();
"""

        page = view.page() if view is not None else None
        if page is None:
            status_label.setText("Не удалось получить страницу ОТРС ММ.")
            return

        def after_fill(result):
            text = str(result or "")
            subject_ok = '"subject_found":true' in text or "'subject_found': True" in text
            body_ok = '"body_filled":true' in text or "'body_filled': True" in text

            if subject_ok and body_ok:
                status_label.setText("Тема и описание заполнены. Проверьте остальные поля и создайте задачу вручную.")
                return

            if attempt < 6:
                status_label.setText(f"Форма ещё готовится, повтор заполнения {attempt + 1}/6...")
                QTimer.singleShot(800, lambda: self._fill_mm_otrs_form(view, status_label, subject, body, attempt + 1))
                return

            status_label.setText(
                "Не удалось полностью заполнить форму. Проверьте селекторы темы/описания. "
                f"Результат: {text[:300]}"
            )

        page.runJavaScript(js, after_fill)


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

    def _select_table_row_for_context_menu(self, row):
        if row < 0:
            return

        selected_rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        if not selected_rows:
            selected_rows = {index.row() for index in self.table.selectedIndexes()}

        # Правый клик по уже выделенной строке не должен сбрасывать
        # множественное выделение. Это важно для создания Redmine
        # по нескольким выбранным проблемам.
        if row in selected_rows:
            self.table.setFocus()
            return

        self.table.clearSelection()
        self.table.selectRow(row)
        self.table.setFocus()

    def _show_table_context_menu(self, position):
        item = self.table.itemAt(position)
        if item is None:
            return

        row = item.row()
        column = item.column()
        key = item.data(Qt.UserRole + 1)
        if not key:
            return

        self._select_table_row_for_context_menu(row)

        payload = item.data(Qt.UserRole)
        menu = QMenu(self)

        if column == 3:
            if payload:
                action = menu.addAction("Открыть узел сети в Zabbix")
                action.triggered.connect(lambda _checked=False, url=str(payload): QDesktopServices.openUrl(QUrl(url)))
            else:
                action = menu.addAction("Ссылка на узел не найдена")
                action.setEnabled(False)

        elif column == 4:
            graph_urls = payload.get("graph_urls", []) if isinstance(payload, dict) else []
            problem_url = payload.get("problem_url", "") if isinstance(payload, dict) else ""

            if graph_urls:
                action = menu.addAction("Открыть график проблемы")
                action.triggered.connect(lambda _checked=False, urls=list(graph_urls): self.open_graphs(urls))

            if problem_url:
                action = menu.addAction("Открыть проблему в Zabbix")
                action.triggered.connect(lambda _checked=False, url=str(problem_url): QDesktopServices.openUrl(QUrl(url)))

            if not graph_urls and not problem_url:
                action = menu.addAction("Ссылка на график/проблему не найдена")
                action.setEnabled(False)

        elif column == 6:
            if payload:
                action = menu.addAction("Открыть подтверждение Zabbix")
                action.triggered.connect(lambda _checked=False, url=str(payload): self.open_acknowledgement(url))
            else:
                action = menu.addAction("Ссылка на подтверждение не найдена")
                action.setEnabled(False)

        if menu.actions():
            menu.addSeparator()

        redmine_action = menu.addAction("Создать Redmine по выбранным строкам")
        redmine_action.triggered.connect(self.open_redmine_for_selected_row)
        mm_otrs_action = menu.addAction("Создать задачу на ММ")
        mm_otrs_action.triggered.connect(self.open_mm_otrs_for_selected_row)

        menu.exec(self.table.viewport().mapToGlobal(position))

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
        self._cleanup_redmine_graph_lookup_view()
        if self.view is not None:
            safe_delete_web_view(self.view, logger=self.logger, context="LiveZabbixMonitorWidget", load_handler=self._on_loaded)
            self._load_finished_connected = False
            self.view = None
