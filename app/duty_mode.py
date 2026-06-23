from datetime import datetime, timedelta, timezone
import json
import re

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, QUrl, QUrlQuery, Qt, Signal
from PySide6.QtGui import QDesktopServices, QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QGraphicsOpacityEffect,
    QTextEdit,
    QTextBrowser,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    MULTIMEDIA_AVAILABLE = True
except Exception:
    MULTIMEDIA_AVAILABLE = False
    QAudioOutput = None
    QMediaPlayer = None

from app.autologin import make_zabbix_login_js
from app.config import ensure_duty_mode_defaults, ensure_duty_triggers_defaults, save_config
from app.credentials import load_otrs_credentials, load_service_credentials
from app.duty_settings import DutyModeSettingsWidget
from app.duty_triggers import diagnose_metric_html, evaluate_stagnation_trigger
from app.logger import get_logger
from app.time_range import add_graph_cache_buster, apply_time_range_to_url
from app.webengine_lifecycle import register_web_view, safe_delete_web_view
from app.service_checks import (
    AUTH_HTML_FORM,
    AUTH_EXTERNAL_BROWSER_GROUP,
    AUTH_VISIBLE_HTML_FORM,
    ensure_service_checks_defaults,
    evaluate_service_check_page,
    build_auth_form_js,
    build_auth_form_presence_js,
    build_autofill_error_message,
    build_click_selector_js,
    build_click_action_js,
    build_load_false_diagnostics_js,
    build_result_selector_check_js,
    build_wait_selector_action_js,
    build_wait_selector_js,
    build_wait_text_action_js,
    load_false_continuation_action,
    load_false_diagnostics_log_parts,
    make_service_result,
    parse_autofill_callback_result,
    safe_autofill_result_repr,
    safe_autofill_script_preview,
    service_action_failure_message,
    service_result_display_label,
    service_status_label,
    summarize_service_results,
    build_service_check_note_text,
    visible_service_start_diagnostics,
    visible_html_form_should_start_autofill_wait,
)
from app.templates import (
    format_dt,
    format_numbered_lines,
    get_otrs_graph_check_template,
    render_template,
)


from app.note_links import plain_text_to_safe_html_with_links
from app.duty_zabbix import (
    adopt_latest_zabbix_problem_csv,
    apply_handled_zabbix_problems,
    cleanup_zabbix_problem_csv_files,
    ensure_zabbix_problem_export_dir,
    find_problems_page_url,
    filter_problems_by_period,
    format_zabbix_problems_note_block,
    load_compared_zabbix_problem_exports,
    load_handled_zabbix_problems,
    mark_zabbix_problems_handled,
    normalize_problem_row,
    problem_matches_keywords,
    rotate_zabbix_problem_csv_files,
    zabbix_problems_collect_js,
    zabbix_problems_next_page_js,
    zabbix_problem_row_status_color,
    zabbix_status_html,
)

def open_external_url(url):
    QDesktopServices.openUrl(QUrl(str(url or "")))


MSK = timezone(timedelta(hours=3))


def normalize_service_autofill_result(logger, service_id, result):
    parsed, parse_error = parse_autofill_callback_result(result)
    if parse_error is None:
        if isinstance(result, str):
            logger.info(
                "Service check autofill JSON parsed: service_id=%s ok=%s clicked=%s",
                service_id,
                bool(parsed.get("ok")),
                bool(parsed.get("clicked")),
            )
        return parsed, None

    reason = str(parse_error.get("error") or "invalid_result")
    if reason == "empty_string_result":
        logger.warning("Service check autofill empty string result: service_id=%s", service_id)
    elif reason == "invalid_json":
        logger.warning(
            "Service check autofill JSON parse failed: service_id=%s reason=%s",
            service_id,
            parse_error.get("details", ""),
        )
    elif reason == "invalid_json_type":
        logger.warning(
            "Service check autofill JSON type invalid: service_id=%s json_type=%s",
            service_id,
            parse_error.get("json_type", ""),
        )
    logger.warning(
        "Service check autofill raw result invalid: service_id=%s result_type=%s result_repr=%s",
        service_id,
        type(result).__name__,
        safe_autofill_result_repr(result),
    )
    return None, parse_error


DUTY_TRIGGER_STATUS_MESSAGES = {
    "OK": "Сработки поступают все в пределах нормы",
    "ALERT": "Обнаружено отсутствие сработок",
    "NO_DATA": "Нет данных для проверки сработок",
    "PARSE_ERROR": "Не удалось прочитать данные проверки сработок",
    "SOURCE_NOT_FOUND": "Источник данных для проверки не найден",
    "TARGET_NOT_FOUND": "Целевой график для проверки не найден",
    "ERROR": "Ошибка проверки сработок",
}

DUTY_TRIGGER_CHECK_COOLDOWN_SECONDS = 3
DUTY_TRIGGER_HIDDEN_WEBVIEW_TIMEOUT_MS = 30000
DUTY_TRIGGER_HTML_READ_DELAY_MS = 8000


def resolve_graph_surface_colors():
    app = QApplication.instance()
    theme_name = app.property("oko_theme_name") if app else None

    if theme_name in {"light_standard", "white_1"}:
        return {
            "page_bg": "#ffffff",
            "card_bg": "#ffffff",
            "border": "#b9d7e7" if theme_name == "white_1" else "#d1d5db",
        }

    if theme_name == "dark_1":
        return {
            "page_bg": "#0b0b0b",
            "card_bg": "#101722",
            "border": "#354458",
        }

    return {
        "page_bg": "#0b0b0b",
        "card_bg": "#06152d",
        "border": "#0d3d78",
    }


def normalize_lookup_text(value):
    return " ".join(str(value or "").split()).casefold()


def find_dashboard_by_product_section(config, product_name, section_name):
    """Find a dashboard config by product and section names."""
    target_product = normalize_lookup_text(product_name)
    target_section = normalize_lookup_text(section_name)
    if not target_product or not target_section:
        return None

    for product in config.get("products", []):
        if normalize_lookup_text(product.get("name", "")) != target_product:
            continue
        for dashboard in product.get("dashboards", []):
            if normalize_lookup_text(dashboard.get("name", "")) == target_section:
                return dashboard
    return None


def _mode_pages_source_url(dashboard, trigger_mode):
    modes = dashboard.get("modes", []) or []
    mode_index_by_name = {
        "mode_1": 0,
        "mode_2": 1,
    }
    preferred_index = mode_index_by_name.get(str(trigger_mode or "").strip())

    if preferred_index is not None and preferred_index < len(modes):
        return str(modes[preferred_index].get("url", "") or "").strip()

    for mode in modes:
        url = str(mode.get("url", "") or "").strip()
        if url:
            return url
    return ""


def build_dashboard_source_url(dashboard, time_range, trigger_mode=""):
    if not dashboard:
        return ""

    if dashboard.get("type") == "mode_pages":
        url = _mode_pages_source_url(dashboard, trigger_mode)
    else:
        url = ""
        for key in ("url", "open_url", "zabbix_url", "external_url"):
            url = str(dashboard.get(key, "") or "").strip()
            if url:
                break

    if url and dashboard.get("use_time_range", True):
        return apply_time_range_to_url(url, time_range)
    return url


def add_duty_trigger_cache_buster(url, timestamp_ms=None):
    """Add a manual duty trigger cache-buster without discarding existing query params."""
    qurl = QUrl(str(url or "").strip())
    if not qurl.isValid() or not qurl.toString():
        return str(url or "").strip()

    if timestamp_ms is None:
        timestamp_ms = int(datetime.now().timestamp() * 1000)

    query = QUrlQuery(qurl)
    query.removeQueryItem("_oko_trigger_check_ts")
    query.addQueryItem("_oko_trigger_check_ts", str(timestamp_ms))
    qurl.setQuery(query)
    return qurl.toString()


class DutyNotificationDialog(QDialog):
    def __init__(self, text, parent=None):
        super().__init__(parent)

        self.result_action = None
        self._closing_animation = None

        self.setObjectName("DutyNotificationDialog")
        self.setWindowTitle("Дежурное уведомление")
        self.setWindowModality(Qt.ApplicationModal)
        self.resize(560, 210)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self.opacity_effect)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 16)
        root.setSpacing(12)

        title = QLabel("Дежурное уведомление")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        message = QLabel(text)
        message.setWordWrap(True)
        message.setStyleSheet("font-size: 16px; padding: 10px; background: transparent;")
        root.addWidget(message)

        row = QHBoxLayout()
        row.setSpacing(10)

        check_button = QPushButton("Проверить")
        check_button.setObjectName("PrimaryAction")
        check_button.clicked.connect(self.choose_check)

        skip_button = QPushButton("Пропустить")
        skip_button.clicked.connect(self.choose_skip)

        row.addWidget(check_button)
        row.addWidget(skip_button)
        row.addStretch()

        root.addLayout(row)

        QTimer.singleShot(0, self._fade_in)

    def _fade_in(self):
        self._animate_opacity(0.0, 1.0, 180)

    def _animate_opacity(self, start, end, duration, finished=None):
        animation = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        animation.setDuration(duration)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(QEasingCurve.InOutCubic)
        if finished:
            animation.finished.connect(finished)
        self._closing_animation = animation
        animation.start(QPropertyAnimation.DeleteWhenStopped)

    def _finish(self, action):
        self.result_action = action
        self._animate_opacity(1.0, 0.0, 140, self.accept)

    def choose_check(self):
        self._finish("check")

    def choose_skip(self):
        self._finish("skip")





class ZabbixProblemsSelectionDialog(QDialog):
    def __init__(self, problems, export_dir=None, parent=None):
        super().__init__(parent)
        self.all_problems = list(problems or [])
        self.export_dir = export_dir
        self.selected_problems = []
        self.period_days = 1
        self.setWindowTitle("Замеченные проблемы Zabbix")
        self.resize(1180, 620)

        root = QVBoxLayout(self)
        title = QLabel("Замеченные проблемы Zabbix")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        period_row = QHBoxLayout()
        period_row.addWidget(QLabel("Период:"))
        self.period_buttons = {}
        for days, label in ((1, "1 день"), (3, "3 дня"), (7, "7 дней"), (14, "14 дней"), (30, "30 дней")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setChecked(days == self.period_days)
            button.clicked.connect(lambda _checked=False, value=days: self.set_period(value))
            self.period_buttons[days] = button
            period_row.addWidget(button)
        self.show_resolved_checkbox = QCheckBox("Показать решённые")
        self.show_resolved_checkbox.toggled.connect(self.render_table)
        self.hide_handled_checkbox = QCheckBox("Скрыть уже обработанные")
        self.hide_handled_checkbox.toggled.connect(self.render_table)
        period_row.addWidget(self.show_resolved_checkbox)
        period_row.addWidget(self.hide_handled_checkbox)
        period_row.addStretch(1)
        root.addLayout(period_row)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Статус", "Время", "Важность", "Узел сети", "Проблема", "Теги", "Обработка"])
        self.table.setWordWrap(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        root.addWidget(self.table, stretch=1)

        row = QHBoxLayout()
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        add = QPushButton("Добавить в задачу")
        add.setObjectName("PrimaryAction")
        add.clicked.connect(self.accept_selected)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(add)
        root.addLayout(row)
        self._visible_problems = []
        self.render_table()

    def set_period(self, days):
        self.period_days = int(days)
        for value, button in self.period_buttons.items():
            button.setChecked(value == self.period_days)
        self.render_table()

    def _filtered_problems(self):
        visible = filter_problems_by_period(self.all_problems, self.period_days)
        if not self.show_resolved_checkbox.isChecked():
            visible = [problem for problem in visible if str(problem.get("status", "ПРОБЛЕМА")) != "РЕШЕНО"]
        if self.hide_handled_checkbox.isChecked():
            visible = [problem for problem in visible if not problem.get("handled")]
        return visible

    def render_table(self):
        self._visible_problems = self._filtered_problems()
        self.table.setRowCount(0)
        for problem in self._visible_problems:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                problem.get("status", "ПРОБЛЕМА"),
                problem.get("time", ""),
                problem.get("severity", ""),
                problem.get("host", ""),
                problem.get("problem", ""),
                problem.get("tags", ""),
                "Уже обработана" if problem.get("handled") else "",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                if col == 0:
                    item.setCheckState(Qt.Unchecked)
                    color = zabbix_problem_row_status_color(problem.get("status", ""))
                    if color:
                        item.setForeground(QColor(color))
                elif col == 6 and problem.get("handled"):
                    item.setForeground(QColor("#f6d365"))
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()

    def accept_selected(self):
        selected = []
        for row, problem in enumerate(self._visible_problems):
            item = self.table.item(row, 0)
            if item is not None and item.checkState() == Qt.Checked:
                selected.append(problem)
        self.selected_problems = selected
        if self.export_dir and selected:
            mark_zabbix_problems_handled(self.export_dir, selected)
        self.accept()


class ZabbixProblemsDialog(QDialog):
    confirmed = Signal()
    problemsSelected = Signal(object)
    problemsDetected = Signal(object)

    def __init__(self, url, profile=None, credentials=None, config=None, parent=None):
        super().__init__(parent)
        self.url = str(url or "").strip()
        self.profile = profile
        self.credentials = credentials or {}
        self.config = config or {}
        self.detected_problems = []
        self.selected_problems = []
        self._problem_collect_rows = []
        self._problem_collect_seen = set()
        self._problem_collect_page = 0
        self.problem_export_dir = ensure_zabbix_problem_export_dir()
        self.csv_current_path = self.problem_export_dir / "current.csv"
        self.csv_previous_path = self.problem_export_dir / "previous.csv"
        self._csv_download_requested = False
        self._csv_download_finished = False
        self.logger = get_logger()
        self.view = None
        self.page = None
        self.setWindowTitle("Проверка проблем Zabbix")
        self.resize(1180, 820)

        root = QVBoxLayout(self)
        title = QLabel("Проблемы Zabbix")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        self.status_label = QLabel("Открываю страницу проблем Zabbix...")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.view = register_web_view(QWebEngineView(self))
        self.page = QWebEnginePage(self.profile, self.view) if self.profile is not None else QWebEnginePage(self.view)
        self.view.setPage(self.page)
        self._connect_csv_download_handler()
        self.view.loadFinished.connect(self.on_loaded)
        root.addWidget(self.view, stretch=1)

        row = QHBoxLayout()
        self.problems_button = QPushButton("Проблемы не найдены")
        self.problems_button.setEnabled(False)
        self.problems_button.clicked.connect(self.open_problems_selection)
        row.addWidget(self.problems_button)
        confirm = QPushButton("Проверено, перейти к графикам")
        confirm.setObjectName("PrimaryAction")
        confirm.clicked.connect(self.confirm)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.close)
        row.addStretch(1)
        row.addWidget(confirm)
        row.addWidget(close)
        root.addLayout(row)

        if self.url:
            self.view.load(QUrl(self.url))

    def on_loaded(self, ok):
        if not ok:
            self.status_label.setText("Не удалось открыть страницу проблем Zabbix.")
            return
        self.status_label.setText("Страница проблем Zabbix открыта. Проверьте проблемы и нажмите кнопку перехода к графикам.")
        login = str(self.credentials.get("login", "") or "")
        password = str(self.credentials.get("password", "") or "")
        js = make_zabbix_login_js(login, password)
        if js and self.page is not None:
            self.page.runJavaScript(js)
        QTimer.singleShot(1800, self.start_csv_problem_export)

    def _connect_csv_download_handler(self):
        try:
            profile = self.page.profile() if self.page is not None else None
            if profile is not None and hasattr(profile, "downloadRequested"):
                profile.downloadRequested.connect(self._handle_csv_download)
        except Exception:
            self.logger.exception("Failed to connect Zabbix CSV download handler")

    def start_csv_problem_export(self):
        if self.page is None:
            self.collect_problems_from_page()
            return
        self._csv_download_requested = False
        self._csv_download_finished = False
        self.status_label.setText("Пытаюсь скачать CSV со списком проблем Zabbix...")
        self.page.runJavaScript(
            """
            (function() {
                const button = document.querySelector('#export_csv');
                if (!button) { return false; }
                button.click();
                return true;
            })();
            """,
            self._after_export_csv_click,
        )

    def _after_export_csv_click(self, clicked):
        if clicked:
            QTimer.singleShot(9000, self._csv_download_timeout_fallback)
            return
        self.problems_button.setText("Не найдена кнопка экспорта CSV на странице проблем Zabbix")
        self.status_label.setText("Не найдена кнопка экспорта CSV на странице проблем Zabbix. Использую DOM fallback.")
        self.collect_problems_from_page()

    def _handle_csv_download(self, download):
        try:
            self._csv_download_requested = True
            self.csv_current_path, self.csv_previous_path = rotate_zabbix_problem_csv_files(self.problem_export_dir)
            if hasattr(download, "setDownloadDirectory"):
                download.setDownloadDirectory(str(self.problem_export_dir))
            if hasattr(download, "setDownloadFileName"):
                download.setDownloadFileName("current.csv")
            if hasattr(download, "isFinishedChanged"):
                download.isFinishedChanged.connect(lambda: self._finish_csv_download_if_ready())
            elif hasattr(download, "finished"):
                download.finished.connect(self._process_downloaded_csv)
            if hasattr(download, "accept"):
                download.accept()
            QTimer.singleShot(12000, self._finish_csv_download_if_ready)
        except Exception:
            self.logger.exception("Не удалось скачать CSV со списком проблем Zabbix")
            self.status_label.setText("Не удалось скачать CSV со списком проблем Zabbix. Использую DOM fallback.")
            self.collect_problems_from_page()

    def _finish_csv_download_if_ready(self):
        if self._csv_download_finished:
            return
        adopt_latest_zabbix_problem_csv(self.problem_export_dir)
        if self.csv_current_path.exists() and self.csv_current_path.stat().st_size > 0:
            self._process_downloaded_csv()

    def _csv_download_timeout_fallback(self):
        if self._csv_download_finished:
            return
        adopt_latest_zabbix_problem_csv(self.problem_export_dir)
        if self.csv_current_path.exists() and self.csv_current_path.stat().st_size > 0:
            self._process_downloaded_csv()
            return
        if not self._csv_download_requested:
            self.problems_button.setText("Не удалось скачать CSV со списком проблем Zabbix")
        self.status_label.setText("Не удалось скачать CSV со списком проблем Zabbix. Использую DOM fallback.")
        self.collect_problems_from_page()

    def _process_downloaded_csv(self):
        if self._csv_download_finished:
            return
        self._csv_download_finished = True
        try:
            problems = load_compared_zabbix_problem_exports(self.problem_export_dir, logger=self.logger)
            settings = self.config.get("duty_mode", {}) if isinstance(self.config, dict) else {}
            keywords = settings.get("zabbix_problem_keywords", [])
            excludes = settings.get("zabbix_problem_exclude_keywords", [])
            problems = [
                problem for problem in problems
                if problem_matches_keywords(problem, keywords=keywords, exclude_keywords=excludes)
            ]
            cleanup_zabbix_problem_csv_files(self.problem_export_dir, logger=self.logger)
            self.status_label.setText("CSV со списком проблем Zabbix обработан.")
            self.update_problem_counter(problems)
        except Exception:
            self.logger.exception("Не удалось обработать CSV со списком проблем Zabbix")
            self.status_label.setText("Не удалось обработать CSV со списком проблем Zabbix. Использую DOM fallback.")
            self.collect_problems_from_page()

    def collect_problems_from_page(self):
        self._problem_collect_rows = []
        self._problem_collect_seen = set()
        self._problem_collect_page = 0
        self._collect_current_problem_page()

    def _collect_current_problem_page(self):
        if self.page is None:
            self.update_problem_counter([], read_failed=True)
            return
        self.page.runJavaScript(zabbix_problems_collect_js(), self.after_collect_problems)

    def after_collect_problems(self, result):
        settings = self.config.get("duty_mode", {}) if isinstance(self.config, dict) else {}
        keywords = settings.get("zabbix_problem_keywords", [])
        excludes = settings.get("zabbix_problem_exclude_keywords", [])
        read_failed = not isinstance(result, (list, dict))
        rows = result.get("rows", []) if isinstance(result, dict) else (result if isinstance(result, list) else [])
        has_next = bool(result.get("hasNext")) if isinstance(result, dict) else False
        for row in rows[:500]:
            problem = normalize_problem_row(row)
            if problem is None:
                continue
            if not problem_matches_keywords(problem, keywords=keywords, exclude_keywords=excludes):
                continue
            key = problem.get("raw_text") or "|".join(str(problem.get(k, "")) for k in ("time", "severity", "host", "problem", "tags"))
            if key in self._problem_collect_seen:
                continue
            self._problem_collect_seen.add(key)
            self._problem_collect_rows.append(problem)
            if len(self._problem_collect_rows) >= 500:
                break

        self._problem_collect_page += 1
        if (
            has_next
            and self._problem_collect_page < 10
            and len(self._problem_collect_rows) < 500
            and self.page is not None
        ):
            self.page.runJavaScript(zabbix_problems_next_page_js())
            QTimer.singleShot(900, self._collect_current_problem_page)
            return
        self.update_problem_counter(self._problem_collect_rows, read_failed=read_failed)

    def _problem_counts(self, problems):
        problems = list(problems or [])
        active = [problem for problem in problems if str(problem.get("status", "ПРОБЛЕМА")) != "РЕШЕНО"]
        resolved = [problem for problem in problems if str(problem.get("status", "")) == "РЕШЕНО"]
        handled = [problem for problem in active if problem.get("handled")]
        return len(active), len(handled), len(resolved)

    def update_problem_counter(self, problems, read_failed=False):
        self.detected_problems = list(problems or [])
        self.problemsDetected.emit(self.detected_problems)
        if read_failed:
            self.problems_button.setText("Проблемы не найдены или не удалось прочитать список проблем")
            self.problems_button.setEnabled(False)
            return
        active_count, handled_count, resolved_count = self._problem_counts(self.detected_problems)
        if active_count:
            parts = [f"Замечены проблемы: {active_count}"]
            if handled_count:
                parts.append(f"уже обработаны: {handled_count}")
            if resolved_count:
                parts.append(f"решено с прошлой проверки: {resolved_count}")
            self.problems_button.setText(", ".join(parts))
            self.problems_button.setEnabled(True)
        elif resolved_count:
            self.problems_button.setText(f"Проблемы не найдены, решено с прошлой проверки: {resolved_count}")
            self.problems_button.setEnabled(True)
        else:
            self.problems_button.setText("Проблемы не найдены")
            self.problems_button.setEnabled(False)

    def open_problems_selection(self):
        dialog = ZabbixProblemsSelectionDialog(self.detected_problems, export_dir=self.problem_export_dir, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.selected_problems = list(dialog.selected_problems or [])
            self.problemsSelected.emit(self.selected_problems)
            active_count, handled_count, resolved_count = self._problem_counts(self.detected_problems)
            parts = [f"Замечены проблемы: {active_count}"] if active_count else ["Проблемы не найдены"]
            if handled_count:
                parts.append(f"уже обработаны: {handled_count}")
            if resolved_count:
                parts.append(f"решено с прошлой проверки: {resolved_count}")
            parts.append(f"добавлено в заметку: {len(self.selected_problems)}")
            self.problems_button.setText(", ".join(parts))

    def confirm(self):
        self.confirmed.emit()
        self.accept()

    def cleanup(self):
        view = self.view
        self.view = None
        self.page = None
        if view is not None:
            safe_delete_web_view(view, logger=self.logger, context="ZabbixProblemsDialog", load_handler=self.on_loaded)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)


class GraphCheckOverlayDialog(QDialog):
    """Glass-like overlay for duty graph verification."""

    confirmed = Signal()

    def __init__(self, graphs, config, profiles, credentials=None, parent=None):
        super().__init__(parent)
        self.graphs = graphs
        self.config = config
        self.profiles = profiles
        self.credentials = credentials or {}
        self.cards = []
        self.logger = get_logger()

        self.setObjectName("GraphCheckOverlayDialog")
        self.setWindowTitle("Проверка графиков")
        self.setWindowModality(Qt.NonModal)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        # Minimum size is clamped in _resize_to_work_area() so the window manager can still resize on small work areas.

        app = QApplication.instance()
        self.theme_name = "mass_effect"
        if app is not None:
            self.theme_name = str(app.property("oko_theme_name") or self.theme_name)
        self.theme_name = self.config.get("settings", {}).get("theme", self.theme_name)
        self._resize_to_work_area()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        panel = QWidget()
        panel.setObjectName("GraphCheckOverlayPanel")
        outer.addWidget(panel)

        content_root = QVBoxLayout(panel)
        content_root.setContentsMargins(12, 12, 12, 12)
        content_root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Проверка графиков")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Основная область — выбранные графики; декоративные слои не накладываются на рабочую зону.")
        subtitle.setWordWrap(True)
        close_button = QPushButton("Закрыть")
        close_button.setObjectName("DestructiveAction")
        close_button.clicked.connect(self.close)
        header.addWidget(title)
        header.addWidget(subtitle, stretch=1)
        header.addWidget(close_button)
        content_root.addLayout(header)

        scroll = QScrollArea()
        scroll.setObjectName("OverlayGraphArea")
        scroll.viewport().setObjectName("OverlayGraphViewport")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("OverlayGraphContent")
        self.cards_layout = QVBoxLayout(body)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        scroll.setWidget(body)
        content_root.addWidget(scroll, stretch=1)

        self._build_cards()

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 4, 0, 0)
        refresh_button = QPushButton("Обновить")
        refresh_button.setObjectName("GraphManualRefreshButton")
        refresh_button.setMinimumHeight(38)
        refresh_button.setToolTip("Перезагрузить графики в текущем окне проверки")
        refresh_button.clicked.connect(self.refresh_graphs)

        confirm_button = QPushButton("Проверено, завершить проверку Zabbix")
        confirm_button.setObjectName("PrimaryAction")
        confirm_button.setMinimumHeight(38)
        confirm_button.setMinimumWidth(160)
        confirm_button.clicked.connect(self.confirm_check)

        bottom_close_button = QPushButton("Закрыть")
        bottom_close_button.setObjectName("DestructiveAction")
        bottom_close_button.setMinimumHeight(38)
        bottom_close_button.clicked.connect(self.close)

        actions.addWidget(refresh_button)
        actions.addStretch(1)
        actions.addWidget(confirm_button)
        actions.addWidget(bottom_close_button)
        content_root.addLayout(actions)

    def _resize_to_work_area(self):
        screen = None
        parent = self.parentWidget()
        if parent is not None:
            try:
                screen = parent.screen()
            except Exception:
                screen = None
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(1180, 820)
            return

        geometry = screen.availableGeometry()
        max_width = max(1, geometry.width() - 80)
        max_height = max(1, geometry.height() - 80)
        width = min(max_width, max(520, int(geometry.width() * 0.92)))
        height = min(max_height, max(420, int(geometry.height() * 0.92)))
        self.setMinimumSize(min(520, max_width), min(420, max_height))
        self.resize(width, height)
        self.move(
            geometry.x() + (geometry.width() - width) // 2,
            geometry.y() + (geometry.height() - height) // 2,
        )

    def _build_cards(self):
        for item in self.graphs:
            zabbix_id = item.get("zabbix_id")
            profile = self.profiles.get(zabbix_id)
            if profile is None:
                label = QLabel(f"Профиль Zabbix не найден для графика: {item.get('title', 'График')}")
                label.setWordWrap(True)
                self.cards_layout.addWidget(label)
                continue
            card = DutyGraphCard(
                graph_config=item["graph"],
                profile=profile,
                credentials=self.credentials.get(zabbix_id, {}),
                time_range=self.config.get("duty_mode", {}).get("check_time_range", "1h"),
                parent=self,
            )
            card.setObjectName("OverlayGraphCard")
            self.cards.append(card)
            self.cards_layout.addWidget(card)
        self.cards_layout.addStretch(1)

    def refresh_graphs(self):
        self.logger.info("Duty graph overlay manual refresh requested")
        self.logger.info("Duty graph overlay manual refresh started: cards=%s", len(self.cards))
        for card in list(self.cards):
            if hasattr(card, "refresh_graph"):
                card.refresh_graph()
        self.logger.info("Duty graph overlay manual refresh finished")

    def confirm_check(self):
        self.logger.info("Duty graph check confirmed")
        self.confirmed.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def cleanup(self):
        if getattr(self, "_cleanup_started", False):
            return
        self._cleanup_started = True
        self.logger.info("Graph check overlay cleanup started")
        count = len(self.cards)
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                if hasattr(widget, "cleanup"):
                    widget.cleanup()
                widget.setParent(None)
                widget.deleteLater()
        self.cards.clear()
        self.logger.info("Graph check overlay cleanup finished")

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)


class DutySettingsDialog(QDialog):
    def __init__(self, config, on_saved_callback=None, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Настройки режима дежурства")
        self.resize(900, 700)

        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.widget = DutyModeSettingsWidget(
            config=config,
            on_saved_callback=on_saved_callback
        )
        scroll.setWidget(self.widget)
        root.addWidget(scroll)


class AttachExistingTaskDialog(QDialog):
    """
    Привязка уже созданной задачи дежурства по ссылке.

    Пользователь вставляет ссылку на задачу.
    Приложение берёт TicketID из ссылки, открывает страницу,
    пробует прочитать номер вида "Заявка#100068754" и проверяет тему.
    """

    def __init__(self, config, parent=None, task_type="zabbix"):
        super().__init__(parent)

        self.config = config
        self.logger = get_logger()
        self.task_type = "service_checks" if task_type == "service_checks" else "zabbix"
        self.setWindowTitle(self._task_window_title())
        self.resize(1000, 720)

        root = QVBoxLayout(self)

        title = QLabel(self._task_title())
        title.setObjectName("PageTitle")
        root.addWidget(title)

        root.addWidget(QLabel(self._task_link_label()))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://itsm.stdpr.ru/itsm/index.pl?...TicketID=... или номер задачи")
        self.url_input.setMinimumWidth(680)
        root.addWidget(self.url_input)

        row = QHBoxLayout()
        attach_button = QPushButton("Привязать")
        attach_button.setObjectName("PrimaryAction")
        attach_button.clicked.connect(self.bind_task_from_input)
        row.addWidget(attach_button)
        row.addStretch(1)
        root.addLayout(row)

        self.status_label = QLabel("Ожидание ссылки.")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.pending_ticket_id = ""
        self.pending_ticket_url = ""
        self.detect_attempt = 0
        self.max_detect_attempts = 8
        self._cleaned_up = False
        self._pending_result = None
        self._pending_continue_queue = True

        self.view = register_web_view(QWebEngineView())
        self.view.setStyleSheet("background-color: #0b0b0b; border: 0;")

        self.page = QWebEnginePage(self.view)
        try:
            self.page.setBackgroundColor(QColor("#0b0b0b"))
        except Exception:
            pass

        self.view.setPage(self.page)
        self.view.loadFinished.connect(self.on_loaded)

        root.addWidget(self.view, stretch=1)


    def _task_title(self):
        return "Задача для проверки сервисов" if self.task_type == "service_checks" else "Задача для проверки Zabbix / графиков"

    def _task_window_title(self):
        return "Привязать задачу проверки сервисов" if self.task_type == "service_checks" else "Привязать задачу Zabbix / графиков"

    def _task_description(self):
        if self.task_type == "service_checks":
            return "Используется для отдельной проверки сервисов в режиме дежурства. Вставь ссылку на задачу проверки сервисов."
        return "Используется для дежурной проверки графиков/Zabbix и уведомлений по графикам. Вставь ссылку на задачу Zabbix / графиков."

    def _task_link_label(self):
        return "Ссылка на задачу проверки сервисов:" if self.task_type == "service_checks" else "Ссылка на задачу Zabbix / графиков:"

    def _expected_subject(self):
        settings = self.get_settings()
        if self.task_type == "service_checks":
            return settings.get("duty_service_checks_expected_task_title") or settings.get("expected_service_checks_ticket_subject", "Дежурная проверка сервисов")
        return settings.get("duty_zabbix_expected_task_title") or settings.get("expected_ticket_subject", "Дежурная проверка Zabbix / графиков")

    def _save_task_binding(self, number="", ticket_id="", ticket_url=""):
        settings = self.get_settings()
        if self.task_type == "service_checks":
            if number:
                settings["duty_service_checks_task_number"] = number
            if ticket_id:
                settings["duty_service_checks_task_id"] = ticket_id
            if ticket_url:
                settings["duty_service_checks_task_url"] = ticket_url
            self.logger.info("Duty service checks task attached: ticket_id=%s", ticket_id or "not_set")
        else:
            if number:
                settings["current_ticket_number"] = number
                settings["duty_zabbix_task_number"] = number
            if ticket_id:
                settings["current_ticket_id"] = ticket_id
                settings["duty_zabbix_task_id"] = ticket_id
            if ticket_url:
                settings["current_ticket_url"] = ticket_url
                settings["duty_zabbix_task_url"] = ticket_url
            self.logger.info("Duty Zabbix task attached: ticket_id=%s", ticket_id or "not_set")
        save_config(self.config)

    def get_settings(self):
        return ensure_duty_mode_defaults(self.config)

    def inject_otrs_login_if_needed(self):
        settings = self.config.setdefault("duty_mode", {})

        if not settings.get("otrs_login_enabled", False):
            return

        otrs_credentials = load_otrs_credentials(self.config)
        login = str(otrs_credentials.get("login", "") or "")
        password = str(otrs_credentials.get("password", "") or "")
        auto_submit = bool(settings.get("otrs_auto_submit_login", False))

        if not login or not password:
            return

        def js_string(value):
            return str(value).replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")

        js = f"""
        (function() {{
            const user = document.querySelector('#User');
            const password = document.querySelector('#Password');
            const button = document.querySelector('#LoginButton');

            if (!user || !password) {{
                return 'no-login-form';
            }}

            user.focus();
            user.value = '{js_string(login)}';
            user.dispatchEvent(new Event('input', {{ bubbles: true }}));
            user.dispatchEvent(new Event('change', {{ bubbles: true }}));

            password.focus();
            password.value = '{js_string(password)}';
            password.dispatchEvent(new Event('input', {{ bubbles: true }}));
            password.dispatchEvent(new Event('change', {{ bubbles: true }}));

            if ({str(auto_submit).lower()} && button) {{
                setTimeout(() => button.click(), 500);
                return 'filled-and-submitted';
            }}

            return 'filled';
        }})();
        """

        self.view.page().runJavaScript(js)

    def extract_ticket_id_from_url(self, url):
        match = re.search(r"[?;]TicketID=([^;&?#]+)", url or "")
        if match:
            return match.group(1).strip()
        return ""

    def open_task_url(self):
        self.bind_task_from_input()

    def attach_task(self):
        self.bind_task_from_input()

    def bind_task_from_input(self):
        value = self.url_input.text().strip()
        if not value:
            QMessageBox.warning(self, "Привязка задачи", "Введите ссылку или номер задачи.")
            return
        if value.isdigit():
            self.status_label.setText("Для проверки заголовка нужна ссылка на задачу. Вставьте полную ссылку ОТРС.")
            QMessageBox.warning(self, "Привязка задачи", "Для проверки заголовка задачи введите полную ссылку, а не только номер.")
            return
        ticket_id = self.extract_ticket_id_from_url(value)
        if not ticket_id:
            self.status_label.setText("Не удалось открыть задачу. Проверьте ссылку или доступ.")
            QMessageBox.warning(self, "Привязка задачи", "Не удалось открыть задачу. Проверьте ссылку или доступ.")
            return
        self.pending_ticket_id = ticket_id
        self.pending_ticket_url = value
        self.status_label.setText("Открываю задачу и проверяю заголовок...")
        self.view.load(QUrl(value))

    def on_loaded(self, ok):
        self.inject_otrs_login_if_needed()

        if not ok:
            self.status_label.setText("Не удалось загрузить страницу задачи.")
            return

        current_url = self.view.url().toString()
        ticket_id = self.extract_ticket_id_from_url(current_url)

        if ticket_id:
            self.pending_ticket_id = ticket_id
            self.pending_ticket_url = current_url
            self.url_input.setText(current_url)
            self.status_label.setText(f"Страница открыта. TicketID={ticket_id}. Проверяю заголовок...")
            self.start_delayed_detect()
        else:
            self.status_label.setText(
                "Страница открыта. Если это страница авторизации — войди. "
                "Если это задача, но TicketID не виден, проверь ссылку."
            )


    def start_delayed_detect(self):
        current_url = self.view.url().toString()
        ticket_id = self.pending_ticket_id or self.extract_ticket_id_from_url(current_url)

        if not ticket_id:
            self.status_label.setText(
                "Не удалось открыть задачу. Проверьте ссылку или доступ."
            )
            return

        self.pending_ticket_id = ticket_id
        self.pending_ticket_url = current_url or self.pending_ticket_url

        self.detect_attempt = 0
        if self.task_type == "service_checks":
            self.logger.info("Duty service checks task title check started")
        else:
            self.logger.info("Duty Zabbix task title check started")
        self.status_label.setText("Жду 3 секунды и читаю заголовок активной страницы...")
        QTimer.singleShot(3000, self.detect_task_number_from_page)


    def normalize_text(self, text):
        return re.sub(r"\s+", " ", str(text or "")).strip()

    def subject_matches(self, subject):
        expected = self._expected_subject()

        subject_norm = self.normalize_text(subject).lower()
        expected_norm = self.normalize_text(expected).lower()

        return expected_norm in subject_norm

    def detect_task_number_from_page(self):
        self.detect_attempt += 1

        js = r"""
        (function() {
            function clean(text) {
                return String(text || '').replace(/\s+/g, ' ').trim();
            }

            function readDocument(doc, prefix) {
                const selectors = [
                    '.Headline h1',
                    '.Headline.NoMargin h1',
                    'div.Headline h1',
                    'h1'
                ];

                const candidates = [];

                for (const selector of selectors) {
                    const elements = Array.from(doc.querySelectorAll(selector));
                    for (const el of elements) {
                        candidates.push({
                            selector: prefix + selector,
                            text: clean(el.innerText || el.textContent || ''),
                            html: clean(el.innerHTML || '')
                        });
                    }
                }

                const bodyText = clean(doc.body ? (doc.body.innerText || doc.body.textContent || '') : '');
                const bodyHtml = clean(doc.body ? (doc.body.innerHTML || '') : '');

                return { candidates, bodyText, bodyHtml };
            }

            let allCandidates = [];
            let bodyTexts = [];
            let bodyHtmls = [];

            const main = readDocument(document, '');
            allCandidates = allCandidates.concat(main.candidates);
            bodyTexts.push(main.bodyText);
            bodyHtmls.push(main.bodyHtml);

            const frames = Array.from(document.querySelectorAll('iframe, frame'));
            for (let i = 0; i < frames.length; i++) {
                try {
                    const doc = frames[i].contentDocument || frames[i].contentWindow.document;
                    if (doc) {
                        const frameData = readDocument(doc, 'frame[' + i + '] ');
                        allCandidates = allCandidates.concat(frameData.candidates);
                        bodyTexts.push(frameData.bodyText);
                        bodyHtmls.push(frameData.bodyHtml);
                    }
                } catch (e) {
                    bodyTexts.push('frame[' + i + '] inaccessible: ' + e.message);
                }
            }

            const combinedText = clean(bodyTexts.join(' '));
            const combinedHtml = clean(bodyHtmls.join(' '));

            let sourceText = '';
            let sourceSelector = '';

            for (const item of allCandidates) {
                if (item.text.includes('Заявка#') || item.html.includes('Заявка#')) {
                    sourceText = item.text || item.html;
                    sourceSelector = item.selector;
                    break;
                }
            }

            if (!sourceText && combinedText.includes('Заявка#')) {
                sourceText = combinedText;
                sourceSelector = 'combined body.innerText';
            }

            if (!sourceText && combinedHtml.includes('Заявка#')) {
                sourceText = combinedHtml.replace(/<[^>]+>/g, ' ');
                sourceText = clean(sourceText);
                sourceSelector = 'combined body.innerHTML';
            }

            const result = {
                sourceType: 'js',
                found: false,
                selector: sourceSelector,
                title: sourceText.slice(0, 500),
                source: (sourceText || combinedText || combinedHtml).slice(0, 1500),
                bodyText: combinedText.slice(0, 1000),
                bodyHtml: combinedHtml.slice(0, 1000),
                ticketNumber: '',
                subject: ''
            };

            if (!sourceText) {
                return result;
            }

            const patterns = [
                /Заявка#\s*(\d+)\s*[—-]\s*([^<\n\r]+)/i,
                /Заявка#\s*(\d+)/i,
                /Ticket#\s*(\d+)\s*[—-]\s*([^<\n\r]+)/i,
                /#\s*(\d{5,})\s*[—-]\s*([^<\n\r]+)/i
            ];

            for (const pattern of patterns) {
                const match = sourceText.match(pattern);
                if (match && match[1]) {
                    result.found = true;
                    result.ticketNumber = clean(match[1]);
                    result.subject = clean(match[2] || '');
                    break;
                }
            }

            if (result.ticketNumber && !result.subject) {
                const split = sourceText.split(/[—-]/);
                if (split.length > 1) {
                    result.subject = clean(split.slice(1).join('—'));
                }
            }

            return result;
        })();
        """
        self.view.page().runJavaScript(js, self.after_detect_task_number_js)

    def after_detect_task_number_js(self, result):
        number = ""
        if isinstance(result, dict):
            number = str(result.get("ticketNumber", "") or "").strip()

        if number:
            self.after_detect_task_number(result)
            return

        self.last_js_debug = result
        self.view.page().toPlainText(self.after_plain_text_read)

    def after_plain_text_read(self, text):
        self.last_plain_text = text or ""
        self.view.page().toHtml(self.after_html_read)

    def after_html_read(self, html):
        result = self.parse_title_from_texts(
            plain_text=getattr(self, "last_plain_text", ""),
            html=html or "",
            js_debug=getattr(self, "last_js_debug", None)
        )
        self.after_detect_task_number(result)

    def parse_title_from_texts(self, plain_text="", html="", js_debug=None):
        def clean(value):
            return re.sub(r"\s+", " ", str(value or "")).strip()

        plain = clean(plain_text)
        raw_html = str(html or "")
        html_text = clean(re.sub(r"<[^>]+>", " ", raw_html))

        source = ""
        source_type = ""

        for candidate, candidate_type in [
            (plain, "toPlainText"),
            (html_text, "toHtml stripped"),
            (raw_html, "toHtml raw"),
        ]:
            if "Заявка#" in candidate:
                source = candidate
                source_type = candidate_type
                break

        result = {
            "sourceType": source_type or "qt-empty",
            "selector": source_type,
            "title": source[:500],
            "source": source[:1500],
            "bodyText": plain[:1000],
            "bodyHtml": raw_html[:1000],
            "ticketNumber": "",
            "subject": "",
            "jsDebug": js_debug,
        }

        if not source:
            return result

        patterns = [
            r"Заявка#\s*(\d+)\s*[—-]\s*([^<\n\r]+)",
            r"Заявка#\s*(\d+)",
            r"Ticket#\s*(\d+)\s*[—-]\s*([^<\n\r]+)",
            r"#\s*(\d{5,})\s*[—-]\s*([^<\n\r]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, source, re.IGNORECASE)
            if match:
                result["ticketNumber"] = clean(match.group(1))
                if len(match.groups()) >= 2 and match.group(2):
                    result["subject"] = clean(match.group(2))
                break

        if result["ticketNumber"] and not result["subject"] and "—" in source:
            result["subject"] = clean(source.split("—", 1)[1])

        return result

    def after_detect_task_number(self, result):
        title = ""
        source = ""
        body_text = ""
        body_html = ""
        selector = ""
        number = ""
        subject = ""
        source_type = ""

        if isinstance(result, dict):
            title = str(result.get("title", "") or "").strip()
            source = str(result.get("source", "") or "").strip()
            body_text = str(result.get("bodyText", "") or "").strip()
            body_html = str(result.get("bodyHtml", "") or "").strip()
            selector = str(result.get("selector", "") or "").strip()
            source_type = str(result.get("sourceType", "") or "").strip()
            number = str(result.get("ticketNumber", "") or "").strip()
            subject = str(result.get("subject", "") or "").strip()

        ticket_id = self.pending_ticket_id or self.extract_ticket_id_from_url(self.view.url().toString())
        ticket_url = self.pending_ticket_url or self.view.url().toString()

        if not number and self.detect_attempt < self.max_detect_attempts:
            self.status_label.setText(
                f"Пока не вижу заголовок задачи. Попытка {self.detect_attempt}/{self.max_detect_attempts}. "
                "Жду ещё 2 секунды..."
            )
            QTimer.singleShot(2000, self.detect_task_number_from_page)
            return

        if not number:
            self.status_label.setText(
                "TicketID найден, но номер заявки из заголовка не прочитан.\n\n"
                f"TicketID={ticket_id}\n"
                f"URL={self.view.url().toString()}\n"
                f"Источник={source_type or 'не найден'}\n"
                f"Селектор={selector or 'не найден'}\n"
                f"Title/source: {title or source}\n\n"
                f"toPlainText/body.innerText: {body_text}\n\n"
                f"toHtml/body.innerHTML: {body_html}\n\n"
                "Задача НЕ привязана. Скорее всего страница в QWebEngine отдаёт пустой DOM или открыт экран авторизации."
            )
            return

        if not self.subject_matches(subject):
            expected = self._expected_subject()
            self.status_label.setText(
                "Заголовок задачи не соответствует ожидаемому типу проверки.\n\n"
                f"Найдена задача: Заявка#{number}\n"
                f"Тема: {subject}\n"
                f"Ожидалось: {expected}\n"
                f"Источник: {source_type}, селектор: {selector}\n\n"
                "Задача НЕ привязана."
            )
            QMessageBox.warning(
                self,
                "Проверь задачу",
                "Заголовок задачи не соответствует ожидаемому типу проверки.\n\n"
                f"Найдена: Заявка#{number}\n"
                f"Тема: {subject}\n\n"
                f"Ожидалось: {expected}\n\n"
                "Задача не привязана к дежурству."
            )
            return

        self._save_task_binding(number=number, ticket_id=ticket_id, ticket_url=ticket_url)
        if self.task_type == "service_checks":
            self.logger.info("Duty service checks task title check finished")
        else:
            self.logger.info("Duty Zabbix task title check finished")

        self.status_label.setText(
            f"Задача успешно привязана. {self._task_title()}: Заявка#{number}, TicketID={ticket_id}."
        )
        QMessageBox.information(self, "Привязка задачи", "Задача успешно привязана.")
        self.accept()


    def cleanup(self):
        if getattr(self, "_cleaned_up", False):
            return
        self._cleaned_up = True
        view = getattr(self, "view", None)
        self.view = None
        self.page = None
        safe_delete_web_view(view, logger=get_logger(), context="AttachExistingTaskDialog", load_handler=self.on_loaded)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)


class OtrsCreateTaskDialog(QDialog):
    """
    Простое окно создания базовой задачи ОТРС без автозаполнения.

    Пользователь вручную создаёт задачу в ОТРС, затем вводит номер задачи
    или пробует найти номер на странице.
    """

    def __init__(self, config, parent=None, task_type="zabbix"):
        super().__init__(parent)

        self.config = config
        self.logger = get_logger()
        self.task_type = "service_checks" if task_type == "service_checks" else "zabbix"

        self.setWindowTitle(self._task_create_title())
        self.resize(1280, 850)

        root = QVBoxLayout(self)

        title = QLabel(self._task_create_title())
        title.setObjectName("PageTitle")
        root.addWidget(title)

        hint = QLabel(self._task_create_hint())
        hint.setWordWrap(True)
        root.addWidget(hint)

        url_row = QHBoxLayout()

        self.url_input = QLineEdit()
        self.url_input.setText(self.get_otrs_settings().get(
            "create_url",
            "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentNewTicketForm;NewTicketFormID=6"
        ))

        open_button = QPushButton("Открыть страницу создания")
        open_button.clicked.connect(self.load_create_page)

        url_row.addWidget(QLabel("URL создания:"))
        url_row.addWidget(self.url_input, stretch=1)
        url_row.addWidget(open_button)

        root.addLayout(url_row)

        task_row = QHBoxLayout()

        self.ticket_number_input = QLineEdit()
        self.ticket_number_input.setText(self._current_task_number())
        self.ticket_number_input.setPlaceholderText("Например: 202605261234567")

        find_number_button = QPushButton("Попробовать найти номер на странице")
        find_number_button.clicked.connect(self.try_detect_ticket_number)

        save_number_button = QPushButton("Привязать номер задачи")
        save_number_button.clicked.connect(self.save_ticket_number)

        task_row.addWidget(QLabel("Номер задачи проверки сервисов:" if self.task_type == "service_checks" else "Номер задачи Zabbix / графиков:"))
        task_row.addWidget(self.ticket_number_input, stretch=1)
        task_row.addWidget(find_number_button)
        task_row.addWidget(save_number_button)

        root.addLayout(task_row)

        ticket_id_row = QHBoxLayout()

        self.ticket_id_input = QLineEdit()
        self.ticket_id_input.setText(self.get_settings().get("current_ticket_id", ""))
        self.ticket_id_input.setPlaceholderText("TicketID из ссылки задачи")

        remember_open_button = QPushButton("Запомнить открытую задачу")
        remember_open_button.clicked.connect(self.remember_current_ticket_url)

        ticket_id_row.addWidget(QLabel("TicketID:"))
        ticket_id_row.addWidget(self.ticket_id_input, stretch=1)
        ticket_id_row.addWidget(remember_open_button)

        root.addLayout(ticket_id_row)

        self.status_label = QLabel("Ожидание.")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.view = register_web_view(QWebEngineView())
        self.view.setStyleSheet("background-color: #0b0b0b; border: 0;")

        self.page = QWebEnginePage(self.view)
        try:
            self.page.setBackgroundColor(QColor("#0b0b0b"))
        except Exception:
            pass

        self.view.setPage(self.page)
        self.view.loadFinished.connect(self.on_loaded)
        self.view.urlChanged.connect(self.on_url_changed)

        root.addWidget(self.view, stretch=1)

        self.auto_captured_ticket_id = ""
        self.load_create_page()


    def _task_create_title(self):
        return "Создать задачу проверки сервисов" if self.task_type == "service_checks" else "Создать задачу Zabbix / графиков"

    def _task_create_hint(self):
        settings = self.get_settings()
        if self.task_type == "service_checks":
            expected = settings.get("duty_service_checks_expected_task_title") or "Дежурная проверка сервисов"
            return f"Создай задачу ОТРС с заголовком «{expected}». После создания укажи номер задачи проверки сервисов ниже."
        expected = settings.get("duty_zabbix_expected_task_title") or "Дежурная проверка Zabbix / графиков"
        return f"Создай задачу ОТРС с заголовком «{expected}». После создания укажи номер задачи Zabbix / графиков ниже."

    def _current_task_number(self):
        settings = self.get_settings()
        if self.task_type == "service_checks":
            return settings.get("duty_service_checks_task_number", "")
        return settings.get("duty_zabbix_task_number") or settings.get("current_ticket_number", "")

    def get_settings(self):
        return ensure_duty_mode_defaults(self.config)

    def get_otrs_settings(self):
        settings = self.config.setdefault("duty_mode", {})
        otrs = settings.setdefault("otrs", {})
        otrs.setdefault("create_url", "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentNewTicketForm;NewTicketFormID=6")
        otrs.setdefault("note_url_base", "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketNote;TicketID=")
        otrs.setdefault("note_url_template", "")
        return otrs


    def inject_otrs_login_if_needed(self):
        settings = self.config.setdefault("duty_mode", {})

        if not settings.get("otrs_login_enabled", False):
            return

        otrs_credentials = load_otrs_credentials(self.config)
        login = str(otrs_credentials.get("login", "") or "")
        password = str(otrs_credentials.get("password", "") or "")
        auto_submit = bool(settings.get("otrs_auto_submit_login", False))

        if not login or not password:
            return

        def js_string(value):
            return str(value).replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")

        js = f"""
        (function() {{
            const user = document.querySelector('#User');
            const password = document.querySelector('#Password');
            const button = document.querySelector('#LoginButton');

            if (!user || !password) {{
                return 'no-login-form';
            }}

            user.focus();
            user.value = '{js_string(login)}';
            user.dispatchEvent(new Event('input', {{ bubbles: true }}));
            user.dispatchEvent(new Event('change', {{ bubbles: true }}));

            password.focus();
            password.value = '{js_string(password)}';
            password.dispatchEvent(new Event('input', {{ bubbles: true }}));
            password.dispatchEvent(new Event('change', {{ bubbles: true }}));

            if ({str(auto_submit).lower()} && button) {{
                setTimeout(() => button.click(), 500);
                return 'filled-and-submitted';
            }}

            return 'filled';
        }})();
        """

        self.view.page().runJavaScript(js)

    def load_create_page(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "ОТРС", "URL создания задачи не указан.")
            return

        self.get_otrs_settings()["create_url"] = url
        save_config(self.config)

        if self.task_type == "service_checks":
            self.logger.info("Duty service checks task create requested")
        else:
            self.logger.info("Duty Zabbix task create requested")
        self.status_label.setText("Открываю страницу создания задачи ОТРС...")
        self.view.load(QUrl(url))

    def on_loaded(self, ok):
        if ok:
            self.inject_otrs_login_if_needed()
            self.status_label.setText("Страница загружена. Создай задачу и укажи её номер.")
        else:
            self.status_label.setText("Страница не загрузилась.")

    def on_url_changed(self, qurl):
        url = qurl.toString()
        ticket_id = self.extract_ticket_id_from_url(url)

        if ticket_id and ticket_id != self.auto_captured_ticket_id:
            self.auto_captured_ticket_id = ticket_id
            self.save_ticket_binding(ticket_id=ticket_id, ticket_url=url, show_message=False)

            self.ticket_id_input.setText(ticket_id)
            self.status_label.setText(
                f"TicketID найден автоматически: {ticket_id}. Задача дежурства привязана."
            )

            # После перехода в задачу пробуем достать номер из текста страницы,
            # но не мешаем работе, если номер не найдётся.
            QTimer.singleShot(1500, self.try_detect_ticket_number)

    def save_ticket_binding(self, ticket_id="", ticket_url="", ticket_number="", show_message=True):
        settings = self.get_settings()

        if self.task_type == "service_checks":
            if ticket_id:
                settings["duty_service_checks_task_id"] = ticket_id
            if ticket_url:
                settings["duty_service_checks_task_url"] = ticket_url
            if ticket_number:
                settings["duty_service_checks_task_number"] = ticket_number
            self.logger.info("Duty service checks task attached: ticket_id=%s", ticket_id or "not_set")
        else:
            if ticket_id:
                settings["current_ticket_id"] = ticket_id
                settings["duty_zabbix_task_id"] = ticket_id
            if ticket_url:
                settings["current_ticket_url"] = ticket_url
                settings["duty_zabbix_task_url"] = ticket_url
            if ticket_number:
                settings["current_ticket_number"] = ticket_number
                settings["duty_zabbix_task_number"] = ticket_number
            self.logger.info("Duty Zabbix task attached: ticket_id=%s", ticket_id or "not_set")

        save_config(self.config)

        if show_message:
            parts = []
            if ticket_number:
                parts.append(f"№{ticket_number}")
            if ticket_id:
                parts.append(f"TicketID={ticket_id}")

            QMessageBox.information(
                self,
                self._task_create_title(),
                self._task_create_title() + " привязана к задаче: " + ", ".join(parts)
            )

    def extract_ticket_id_from_url(self, url):
        match = re.search(r"[?;]TicketID=([^;&?#]+)", url or "")
        if match:
            return match.group(1).strip()
        return ""

    def remember_current_ticket_url(self):
        url = self.view.url().toString()
        ticket_id = self.extract_ticket_id_from_url(url)

        if not ticket_id:
            QMessageBox.warning(
                self,
                "TicketID",
                "В текущей ссылке не найден TicketID.\n\n"
                "После создания задачи ОТРС должен перенести тебя в созданную задачу, "
                "и в адресе должно появиться TicketID=..."
            )
            return

        self.ticket_id_input.setText(ticket_id)
        self.save_ticket_binding(ticket_id=ticket_id, ticket_url=url, show_message=True)

        if not self.ticket_number_input.text().strip():
            self.try_detect_ticket_number()

    def try_detect_ticket_number(self):
        js = r"""
        (function() {
            const text = (document.body.innerText || document.body.textContent || '').trim();

            // Частые варианты: "Заявка №...", "Ticket#...", "Ticket Number ..."
            const patterns = [
                /(?:Заявка|Задача|Ticket|TicketNumber|Ticket Number|Номер заявки|Номер задачи)[^\d]{0,30}(\d{5,})/i,
                /№\s*(\d{5,})/i,
                /\b(\d{10,})\b/
            ];

            for (const pattern of patterns) {
                const match = text.match(pattern);
                if (match && match[1]) {
                    return match[1];
                }
            }

            return "";
        })();
        """
        self.view.page().runJavaScript(js, self.after_detect_ticket_number)

    def after_detect_ticket_number(self, number):
        number = str(number or "").strip()

        if not number:
            QMessageBox.warning(
                self,
                "Номер задачи",
                "Не удалось автоматически найти номер задачи на странице. Введи номер вручную."
            )
            return

        self.ticket_number_input.setText(number)
        self.save_ticket_binding(ticket_number=number, show_message=False)
        self.status_label.setText(f"Найден номер задачи: {number}")

    def save_ticket_number(self):
        number = self.ticket_number_input.text().strip()

        if not number:
            QMessageBox.warning(self, "Номер задачи", "Укажи номер задачи.")
            return

        current_url = self.view.url().toString()
        ticket_id = self.ticket_id_input.text().strip() or self.extract_ticket_id_from_url(current_url)
        self.save_ticket_binding(
            ticket_id=ticket_id,
            ticket_url=current_url if ticket_id else "",
            ticket_number=number,
            show_message=False
        )

        QMessageBox.information(
            self,
            "Номер задачи",
            f"Дежурство привязано к задаче №{number}."
        )


    def cleanup(self):
        if getattr(self, "_cleaned_up", False):
            return
        self._cleaned_up = True
        view = getattr(self, "view", None)
        self.view = None
        self.page = None
        safe_delete_web_view(view, logger=get_logger(), context="OtrsCreateTaskDialog", load_handler=self.on_loaded)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)


class OtrsNoteDialog(QDialog):
    """
    Окно добавления заметки в задачу ОТРС.

    Умеет:
    - открыть заметку по сохранённому TicketID;
    - принять вручную ссылку на задачу или заметку;
    - вытащить TicketID из ссылки;
    - показать номер задачи из заголовка страницы;
    - вставить текст в CKEditor/contenteditable body.
    """

    def __init__(self, config, note_text, parent=None, on_saved_callback=None, saved_log_message=None, initial_note_url=None):
        super().__init__(parent)

        self.config = config
        self.note_text = note_text
        self.on_saved_callback = on_saved_callback
        self.saved_log_message = saved_log_message
        self.initial_note_url = str(initial_note_url or "").strip()
        self.note_saved = False
        self.logger = get_logger()

        self.setWindowTitle("Заметка в задачу ОТРС")
        self.resize(1280, 850)

        root = QVBoxLayout(self)

        title = QLabel("Заметка в задачу ОТРС")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        root.addWidget(self.info_label)

        ticket_row = QHBoxLayout()

        self.task_url_input = QLineEdit()
        self.task_url_input.setPlaceholderText("Можно вставить ссылку на задачу или ссылку на заметку с TicketID=...")

        use_task_url_button = QPushButton("Использовать эту ссылку")
        use_task_url_button.clicked.connect(self.use_manual_task_url)

        ticket_row.addWidget(QLabel("Ссылка/задача:"))
        ticket_row.addWidget(self.task_url_input, stretch=1)
        ticket_row.addWidget(use_task_url_button)

        root.addLayout(ticket_row)

        url_row = QHBoxLayout()

        self.url_input = QLineEdit()
        self.url_input.setText(self.initial_note_url or self.build_note_url())

        open_button = QPushButton("Открыть страницу заметки")
        open_button.clicked.connect(self.load_note_page)

        copy_button = QPushButton("Скопировать текст")
        copy_button.clicked.connect(lambda: self.copy_note(show_message=True))

        paste_button = QPushButton("Вставить текст в заметку")
        paste_button.clicked.connect(self.inject_note_text)

        detect_button = QPushButton("Прочитать номер задачи")
        detect_button.clicked.connect(self.detect_ticket_title)

        url_row.addWidget(QLabel("URL заметки:"))
        url_row.addWidget(self.url_input, stretch=1)
        url_row.addWidget(open_button)
        url_row.addWidget(copy_button)
        url_row.addWidget(paste_button)
        url_row.addWidget(detect_button)

        root.addLayout(url_row)

        self.note_editor = QTextEdit()
        self.note_editor.setPlainText(note_text)
        root.addWidget(self.note_editor, stretch=1)

        self.view = register_web_view(QWebEngineView())
        self.view.setStyleSheet("background-color: #0b0b0b; border: 0;")

        self.page = QWebEnginePage(self.view)
        try:
            self.page.setBackgroundColor(QColor("#0b0b0b"))
        except Exception:
            pass

        self.view.setPage(self.page)
        self.view.loadFinished.connect(self.on_loaded)
        self.view.urlChanged.connect(self.on_url_changed)

        root.addWidget(self.view, stretch=2)

        self.update_info_label()
        self.copy_note(show_message=False)

        if self.url_input.text().strip():
            self.load_note_page()


    def inject_otrs_login_if_needed(self):
        settings = self.config.setdefault("duty_mode", {})

        if not settings.get("otrs_login_enabled", False):
            return

        otrs_credentials = load_otrs_credentials(self.config)
        login = str(otrs_credentials.get("login", "") or "")
        password = str(otrs_credentials.get("password", "") or "")
        auto_submit = bool(settings.get("otrs_auto_submit_login", False))

        if not login or not password:
            return

        def js_string(value):
            return str(value).replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")

        js = f"""
        (function() {{
            const user = document.querySelector('#User');
            const password = document.querySelector('#Password');
            const button = document.querySelector('#LoginButton');

            if (!user || !password) {{
                return 'no-login-form';
            }}

            user.focus();
            user.value = '{js_string(login)}';
            user.dispatchEvent(new Event('input', {{ bubbles: true }}));
            user.dispatchEvent(new Event('change', {{ bubbles: true }}));

            password.focus();
            password.value = '{js_string(password)}';
            password.dispatchEvent(new Event('input', {{ bubbles: true }}));
            password.dispatchEvent(new Event('change', {{ bubbles: true }}));

            if ({str(auto_submit).lower()} && button) {{
                setTimeout(() => button.click(), 500);
                return 'filled-and-submitted';
            }}

            return 'filled';
        }})();
        """

        self.view.page().runJavaScript(js)


    def get_settings(self):
        return self.config.setdefault("duty_mode", {})

    def get_otrs_settings(self):
        settings = self.get_settings()
        return settings.setdefault("otrs", {})

    def get_task_number(self):
        return self.get_settings().get("current_ticket_number", "").strip()

    def get_ticket_id(self):
        return self.get_settings().get("current_ticket_id", "").strip()

    def extract_ticket_id_from_url(self, url):
        match = re.search(r"[?;]TicketID=([^;&?#]+)", url or "")
        if match:
            return match.group(1).strip()
        return ""

    def make_note_url_by_ticket_id(self, ticket_id):
        otrs = self.get_otrs_settings()
        base = otrs.get(
            "note_url_base",
            "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketNote;TicketID="
        ).strip()

        if not base:
            base = "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketNote;TicketID="

        return base + ticket_id

    def save_ticket_id_from_url(self, url):
        ticket_id = self.extract_ticket_id_from_url(url)

        if not ticket_id:
            return False

        settings = self.get_settings()
        settings["current_ticket_id"] = ticket_id
        settings["current_ticket_url"] = url

        note_url = self.make_note_url_by_ticket_id(ticket_id)
        self.url_input.setText(note_url)

        save_config(self.config)
        self.update_info_label()

        return True

    def use_manual_task_url(self):
        url = self.task_url_input.text().strip()

        if not url:
            QMessageBox.warning(self, "ОТРС", "Вставь ссылку на задачу или заметку.")
            return

        if not self.save_ticket_id_from_url(url):
            QMessageBox.warning(
                self,
                "ОТРС",
                "В ссылке не найден TicketID=...\n\n"
                "Вставь ссылку вида:\n"
                "https://.../index.pl?...TicketID=12345"
            )
            return

        QMessageBox.information(self, "ОТРС", "TicketID сохранён. Ссылка заметки собрана.")
        self.load_note_page()

    def build_note_url(self):
        ticket_number = self.get_task_number()
        ticket_id = self.get_ticket_id()
        otrs = self.get_otrs_settings()
        template = otrs.get("note_url_template", "").strip()

        if template:
            return (
                template
                .replace("{ticket_number}", ticket_number)
                .replace("{ticket_id}", ticket_id)
            )

        if ticket_id:
            return self.make_note_url_by_ticket_id(ticket_id)

        return ""

    def update_info_label(self):
        task_number = self.get_task_number()
        ticket_id = self.get_ticket_id()

        self.info_label.setText(
            f"Текущая задача дежурства: №{task_number or 'не указан'}, TicketID={ticket_id or 'не указан'}. "
            "Можно вставить ссылку на уже созданную задачу вручную."
        )

    def copy_note(self, show_message=False):
        text = self.note_editor.toPlainText().strip()

        if not text:
            return

        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

        if show_message:
            self.info_label.setText(self.info_label.text() + "\nТекст заметки скопирован в буфер обмена.")

    def load_note_page(self):
        url = self.url_input.text().strip()

        if not url:
            QMessageBox.warning(
                self,
                "ОТРС",
                "URL страницы заметки не указан.\n\n"
                "Вставь ссылку на задачу с TicketID или привяжи задачу при заступлении."
            )
            return

        self.view.load(QUrl(url))

    def on_url_changed(self, qurl):
        url = qurl.toString()
        if "TicketID=" in url:
            self.save_ticket_id_from_url(url)

    def on_loaded(self, ok):
        if ok:
            self.inject_otrs_login_if_needed()
            self.detect_ticket_title()
            # Даём CKEditor время прогрузиться, потом пробуем мягко вставить текст.
            QTimer.singleShot(1500, self.inject_note_text_silent)
            # Ставим наблюдатель за кнопкой "Отправить".
            QTimer.singleShot(2200, self.install_send_button_observer)

    def detect_ticket_title(self):
        js = r"""
        (function() {
            const h1 = document.querySelector('h1');
            const text = h1 ? h1.innerText.trim() : '';

            const result = { title: text, ticketNumber: '' };

            const match = text.match(/Заявка#(\d+)/i);
            if (match && match[1]) {
                result.ticketNumber = match[1];
            }

            return result;
        })();
        """
        self.view.page().runJavaScript(js, self.after_detect_ticket_title)

    def after_detect_ticket_title(self, result):
        if not isinstance(result, dict):
            return

        title = str(result.get("title", "") or "").strip()
        number = str(result.get("ticketNumber", "") or "").strip()

        changed = False
        settings = self.get_settings()

        if number:
            settings["current_ticket_number"] = number
            settings["duty_zabbix_task_number"] = number
            changed = True

        if changed:
            save_config(self.config)

        if title:
            self.info_label.setText(
                self.info_label.text() + f"\nСтраница ОТРС: {title}"
            )

    def install_send_button_observer(self):
        """
        Слушает ручное нажатие кнопки "Отправить" на странице заметки.
        Кнопку не нажимаем автоматически.
        После ручного нажатия закрываем окно заметки.
        """
        js = r"""
        (function() {
            if (window.__dezhurkaSendObserverInstalled) {
                return 'already-installed';
            }

            window.__dezhurkaSendObserverInstalled = true;
            window.__dezhurkaSendClicked = false;

            function findSendButton() {
                const candidates = Array.from(document.querySelectorAll('button, a, input[type="submit"], input[type="button"]'));

                return candidates.find(el => {
                    const text = (el.innerText || el.value || el.textContent || '').trim().toLowerCase();
                    return text.includes('отправить');
                });
            }

            const button = findSendButton();

            if (!button) {
                return 'send-button-not-found';
            }

            button.addEventListener('click', function() {
                window.__dezhurkaSendClicked = true;
            }, true);

            return 'installed';
        })();
        """

        self.view.page().runJavaScript(js)
        self.send_watch_timer = QTimer(self)
        self.send_watch_timer.timeout.connect(self.check_send_clicked)
        self.send_watch_timer.start(700)

    def check_send_clicked(self):
        js = "Boolean(window.__dezhurkaSendClicked);"
        self.view.page().runJavaScript(js, self.after_check_send_clicked)

    def after_check_send_clicked(self, clicked):
        if clicked and not self.note_saved:
            try:
                self.send_watch_timer.stop()
            except Exception:
                pass

            self.note_saved = True

            # Даём ОТРС время отправить форму и закрываем окно.
            QTimer.singleShot(1800, self.finish_saved_note)

    def finish_saved_note(self):
        self.logger.info(self.saved_log_message or "OTRS note saved")
        if self.on_saved_callback is not None:
            self.on_saved_callback()
        self.accept()

    def html_escape(self, text):
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def note_text_to_html(self):
        text = self.note_editor.toPlainText().strip()
        lines = [self.html_escape(line) for line in text.splitlines()]
        if not lines:
            return ""
        return "<br>".join(lines)

    def inject_note_text_silent(self):
        self.inject_note_text(show_message=False)

    def inject_note_text(self, show_message=True):
        html = self.note_text_to_html()

        if not html:
            if show_message:
                QMessageBox.warning(self, "Заметка", "Текст заметки пустой.")
            return

        js_html = html.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "")

        js = f"""
        (function() {{
            function setEditorBody(body) {{
                body.focus();
                body.innerHTML = '{js_html}';
                body.dispatchEvent(new Event('input', {{ bubbles: true }}));
                body.dispatchEvent(new Event('change', {{ bubbles: true }}));
                body.dispatchEvent(new KeyboardEvent('keyup', {{ bubbles: true, key: ' ' }}));
                return true;
            }}

            // Вариант 1: CKEditor iframe.
            const frames = Array.from(document.querySelectorAll('iframe'));
            for (const frame of frames) {{
                try {{
                    const doc = frame.contentDocument || frame.contentWindow.document;
                    const body = doc && doc.querySelector('body[contenteditable="true"], body.cke_editable');
                    if (body) {{
                        return setEditorBody(body) ? 'OK: CKEditor iframe' : 'FAIL';
                    }}
                }} catch (e) {{}}
            }}

            // Вариант 2: contenteditable прямо на странице.
            const body = document.querySelector('body[contenteditable="true"], .cke_editable[contenteditable="true"], [contenteditable="true"]');
            if (body) {{
                return setEditorBody(body) ? 'OK: contenteditable' : 'FAIL';
            }}

            return 'ОШИБКА: поле CKEditor/contenteditable не найдено';
        }})();
        """

        self.view.page().runJavaScript(
            js,
            lambda result: self.after_inject_note_text(result, show_message)
        )

    def after_inject_note_text(self, result, show_message=True):
        result_text = str(result or "")

        if result_text.startswith("OK:"):
            self.info_label.setText(
                self.info_label.text()
                + "\nТекст заметки вставлен автоматически. Проверь и нажми «Отправить» в ОТРС."
            )
        else:
            self.info_label.setText(
                self.info_label.text()
                + "\nАвтовставка не сработала. Текст уже скопирован в буфер, вставь его вручную."
                + f"\n{result_text}"
            )


    def cleanup(self):
        if getattr(self, "_cleaned_up", False):
            return
        self._cleaned_up = True
        if getattr(self, "send_watch_timer", None) is not None:
            try:
                self.send_watch_timer.stop()
                self.send_watch_timer.deleteLater()
            except RuntimeError:
                pass
            self.send_watch_timer = None
        view = getattr(self, "view", None)
        self.view = None
        self.page = None
        safe_delete_web_view(view, logger=get_logger(), context="OtrsNoteDialog", load_handler=self.on_loaded)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)


class ProblemTemplateDialog(QDialog):
    def __init__(self, graphs, config=None, parent=None):
        super().__init__(parent)

        self.graphs = graphs
        self.config = config or {}
        self.setWindowTitle("Есть проблема")
        self.resize(780, 640)

        root = QVBoxLayout(self)

        title = QLabel("Выбери графики, где есть отклонения")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        self.list_widget = QListWidget()
        for graph in graphs:
            item = QListWidgetItem(graph.get("title", "График"))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.list_widget.addItem(item)

        root.addWidget(self.list_widget, stretch=1)

        hint = QLabel("После создания заметки можно вставить этот текст в задачу ОТРС.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.result_text = QTextEdit()
        self.result_text.setPlaceholderText("Здесь появится сформированный шаблон...")
        root.addWidget(self.result_text, stretch=1)

        row = QHBoxLayout()

        build_button = QPushButton("Сформировать")
        build_button.clicked.connect(self.build_template)

        copy_button = QPushButton("Скопировать")
        copy_button.clicked.connect(self.copy_template)

        note_button = QPushButton("Создать заметку")
        note_button.clicked.connect(self.create_note)

        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.close)

        row.addWidget(build_button)
        row.addWidget(copy_button)
        row.addWidget(note_button)
        row.addWidget(close_button)
        row.addStretch()

        root.addLayout(row)

    def selected_graph_titles(self):
        titles = []

        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item.checkState() == Qt.Checked:
                titles.append(item.text())

        return titles

    def build_template(self):
        titles = self.selected_graph_titles()

        if not titles:
            QMessageBox.warning(self, "Есть проблема", "Выбери хотя бы один график.")
            return

        duty_settings = self.config.get("duty_mode", {})
        task_number = (duty_settings.get("duty_zabbix_task_number") or duty_settings.get("current_ticket_number", "")).strip()

        if len(titles) == 1:
            text = (
                "При проверке выявлены отклонения от показателей штатной работы "
                f"системы на графике {titles[0]}."
            )
        else:
            lines = [
                "При проверке выявлены отклонения от показателей штатной работы системы на графиках:"
            ]

            for number, title in enumerate(titles, start=1):
                lines.append(f"{number}. {title}")

            text = "\n".join(lines)

        if task_number:
            text += f"\n\nЗадача дежурства: №{task_number}"

        self.result_text.setPlainText(text)

    def copy_template(self):
        text = self.result_text.toPlainText().strip()

        if not text:
            self.build_template()
            text = self.result_text.toPlainText().strip()

        if text:
            self.result_text.selectAll()
            self.result_text.copy()
            QMessageBox.information(self, "Скопировано", "Шаблон скопирован в буфер обмена.")

    def create_note(self):
        if not self.result_text.toPlainText().strip():
            self.build_template()

        text = self.result_text.toPlainText().strip()

        if not text:
            return

        dialog = OtrsNoteDialog(
            config=self.config,
            note_text=text,
            parent=self
        )
        dialog.exec()


class DutyGraphCard(QFrame):
    def __init__(self, graph_config, profile, credentials=None, time_range="1h", parent=None):
        super().__init__(parent)

        self.graph_config = graph_config
        self.profile = profile
        self.credentials = credentials or {}
        self.time_range = time_range
        self.logger = get_logger()
        self._cleaned_up = False
        self._pending_result = None
        self._pending_continue_queue = True

        self.setObjectName("GraphCard")
        self.initial_view_height = 430
        self.setMinimumWidth(0)
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        colors = resolve_graph_surface_colors()
        self.setStyleSheet(
            f"QFrame#GraphCard, QFrame#OverlayGraphCard {{ background: transparent; "
            f"border: 1px solid {colors['border']}; border-radius: 14px; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        title = QLabel(graph_config.get("title", "График"))
        title.setObjectName("GraphTitle")
        title.setWordWrap(True)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        open_button = QPushButton("Открыть в Zabbix")
        open_button.setObjectName("GraphOpenButton")
        open_button.clicked.connect(self.open_external)
        open_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.view = register_web_view(QWebEngineView())
        self.view.setObjectName("GraphWebView")
        self.view.setAttribute(Qt.WA_TranslucentBackground, False)
        self.view.setMinimumWidth(0)
        self.view.setFixedHeight(self.initial_view_height)
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.view.setZoomFactor(0.85)
        self.view.setStyleSheet("background: transparent; border: 0;")

        self.graph_web_container = QFrame()
        self.graph_web_container.setObjectName("GraphWebContainer")
        self.graph_web_container.setAttribute(Qt.WA_TranslucentBackground, False)
        self.graph_web_container.setAutoFillBackground(False)
        self.graph_web_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.graph_web_container.setFixedHeight(self.initial_view_height)
        self.graph_web_container.setStyleSheet(
            "QFrame#GraphWebContainer { background: transparent; border: 0px; }"
        )
        web_layout = QVBoxLayout(self.graph_web_container)
        web_layout.setContentsMargins(0, 0, 0, 0)
        web_layout.setSpacing(0)

        self.page = QWebEnginePage(profile, self.view)
        self.view.setPage(self.page)
        self.view.loadFinished.connect(self.on_loaded)

        self.duty_trigger_status_label = QLabel("")
        self.duty_trigger_status_label.setObjectName("DutyTriggerStatus")
        self.duty_trigger_status_label.setWordWrap(True)
        self.duty_trigger_status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.duty_trigger_status_label.setVisible(False)
        self.duty_trigger_status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        root.addWidget(title)
        root.addWidget(open_button)
        web_layout.addWidget(self.view)
        root.addWidget(self.graph_web_container)
        root.addWidget(self.duty_trigger_status_label)

        self.load()

    def set_duty_trigger_status(self, status: str, message: str):
        status = str(status or "").strip().upper()
        message = str(message or "").strip()
        fallback_messages = {
            "OK": DUTY_TRIGGER_STATUS_MESSAGES["OK"],
            "ALERT": DUTY_TRIGGER_STATUS_MESSAGES["ALERT"],
            "NO_DATA": DUTY_TRIGGER_STATUS_MESSAGES["NO_DATA"],
            "PARSE_ERROR": DUTY_TRIGGER_STATUS_MESSAGES["PARSE_ERROR"],
            "SOURCE_NOT_FOUND": DUTY_TRIGGER_STATUS_MESSAGES["SOURCE_NOT_FOUND"],
            "TARGET_NOT_FOUND": DUTY_TRIGGER_STATUS_MESSAGES["TARGET_NOT_FOUND"],
        }
        icons = {
            "OK": "✓",
            "ALERT": "⚠",
            "NO_DATA": "ℹ",
            "PARSE_ERROR": "⚠",
            "SOURCE_NOT_FOUND": "⚠",
            "TARGET_NOT_FOUND": "⚠",
        }
        colors = {
            "OK": ("#166534", "#dcfce7", "#22c55e"),
            "ALERT": ("#7f1d1d", "#fee2e2", "#ef4444"),
            "NO_DATA": ("#1e3a8a", "#dbeafe", "#60a5fa"),
            "PARSE_ERROR": ("#78350f", "#fef3c7", "#f59e0b"),
            "SOURCE_NOT_FOUND": ("#78350f", "#fef3c7", "#f59e0b"),
            "TARGET_NOT_FOUND": ("#78350f", "#fef3c7", "#f59e0b"),
        }
        text = message or fallback_messages.get(status, "Статус проверки сработок недоступен")
        icon = icons.get(status, "ℹ")
        text_color, bg_color, border_color = colors.get(status, ("#374151", "#f3f4f6", "#9ca3af"))
        self.duty_trigger_status_label.setText(f"{icon} {text}")
        self.duty_trigger_status_label.setStyleSheet(
            "padding: 8px 10px;"
            "border-radius: 6px;"
            f"color: {text_color};"
            f"background-color: {bg_color};"
            f"border: 1px solid {border_color};"
        )
        self.duty_trigger_status_label.setVisible(True)

    def clear_duty_trigger_status(self):
        self.duty_trigger_status_label.clear()
        self.duty_trigger_status_label.setVisible(False)

    def build_url(self):
        url = self.graph_config.get("url", "")
        if self.graph_config.get("use_time_range", True):
            return apply_time_range_to_url(url, self.time_range)
        return url

    def build_open_url(self):
        return (
            self.graph_config.get("open_url")
            or self.graph_config.get("zabbix_url")
            or self.graph_config.get("external_url")
            or self.build_url()
        )

    def load(self):
        if self._cleaned_up or self.view is None:
            return
        self.view.load(QUrl(self.build_url()))

    def refresh_graph(self):
        if self._cleaned_up or self.view is None:
            return
        self.view.load(QUrl(add_graph_cache_buster(self.build_url())))

    def on_loaded(self, ok):
        if self._cleaned_up or self.view is None or not ok:
            return

        js = make_zabbix_login_js(
            self.credentials.get("login", ""),
            self.credentials.get("password", "")
        )
        if js and not self._cleaned_up and self.view is not None:
            self.view.page().runJavaScript(js)
        QTimer.singleShot(500, self.fit_content_height)
        QTimer.singleShot(1500, self.fit_content_height)
        QTimer.singleShot(2500, self.fit_content_height)

    def fit_content_height(self):
        if self._cleaned_up or self.view is None:
            return
        js = """
        (function() {
            const styleId = 'oko-duty-graph-fit';
            let style = document.getElementById(styleId);
            if (!style) {
                style = document.createElement('style');
                style.id = styleId;
                document.head.appendChild(style);
            }
            style.textContent = `
                html, body {
                    margin: 0 !important;
                    padding: 0 !important;
                    overflow: hidden !important;
                    min-height: 0 !important;
                    height: auto !important;
                }
                header, nav, footer, .sidebar, .header-title, .filter-container,
                #header, #footer, #sidebar, .server-name, .menu-main {
                    display: none !important;
                }
                img, svg, canvas {
                    max-width: 100% !important;
                    object-fit: contain !important;
                }
                table, tbody, tr, td, div {
                    max-width: 100% !important;
                    box-sizing: border-box !important;
                }
            `;
            function visibleRects(selector) {
                return Array.from(document.querySelectorAll(selector))
                    .map((node) => node.getBoundingClientRect())
                    .filter((rect) => rect.width > 20 && rect.height > 20);
            }
            let visibleUseful = visibleRects('img, svg, canvas');
            if (!visibleUseful.length) {
                visibleUseful = visibleRects('table');
            }
            if (!visibleUseful.length) {
                visibleUseful = visibleRects('[class*=graph], [id*=graph]');
            }
            const bottom = visibleUseful.length
                ? Math.max(...visibleUseful.map((rect) => rect.bottom))
                : Math.min(document.documentElement.scrollHeight || 0, document.body.scrollHeight || 0);
            const height = Math.max(260, Math.min(760, Math.ceil(bottom + 12)));
            document.documentElement.style.height = height + 'px';
            document.body.style.height = height + 'px';
            return height;
        })();
        """
        if not self._cleaned_up and self.view is not None:
            self.view.page().runJavaScript(js, self.apply_content_height)

    def apply_content_height(self, height):
        if self._cleaned_up or self.view is None:
            return
        try:
            height = int(float(height))
        except (TypeError, ValueError):
            return
        height = max(260, min(height, 760))
        self.view.setFixedHeight(height)
        self.graph_web_container.setFixedHeight(height)
        self.updateGeometry()

    def open_external(self):
        url = self.build_open_url()
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def cleanup(self):
        if self._cleaned_up:
            return
        self._cleaned_up = True
        title = self.graph_config.get("title", "График")
        self.logger.info("Graph WebView cleanup started: title=%s", title)
        view = self.view
        self.view = None
        self.page = None
        safe_delete_web_view(view, logger=self.logger, context=f"DutyGraphCard title={title}", load_handler=self.on_loaded)
        self.logger.info("Graph WebView cleanup finished: title=%s", title)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)



class ServiceCheckVisibleDialog(QDialog):
    completed = Signal(object, bool)
    cleanup_completed = Signal(str)

    def __init__(self, service, parent=None, group_services=None):
        super().__init__(parent)
        self.group_services = list(group_services or [service])
        self.group_index = 0
        self.group_results = []
        self.service = self.group_services[self.group_index]
        self.logger = get_logger()
        self.started_at = None
        self.finished = False
        self.emitted = False
        self.ssl_warning = ""
        self._cleaned_up = False
        self._pending_result = None
        self._pending_continue_queue = True
        self.state = "loading"
        self.auth_submitted = False
        self.logout_started = False

        self.setWindowTitle(f"Проверка сервиса: {service.get('name') or service.get('id') or 'Сервис'}")
        self.resize(1100, 760)

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Загрузка страницы проверки сервиса…")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.view = register_web_view(QWebEngineView())
        self.page = QWebEnginePage(self.view)
        self.view.setPage(self.page)
        layout.addWidget(self.view, stretch=1)

        manual_actions = QHBoxLayout()
        self.confirm_ok_button = QPushButton("Подтвердить ОК")
        self.confirm_ok_button.setObjectName("PrimaryAction")
        self.confirm_error_button = QPushButton("Ошибка")
        self.skip_button = QPushButton("Пропустить")
        self.close_continue_button = QPushButton("Закрыть и продолжить")
        self.confirm_ok_button.clicked.connect(self.confirm_ok)
        self.confirm_error_button.clicked.connect(self.confirm_error)
        self.skip_button.clicked.connect(self.skip_check)
        self.close_continue_button.clicked.connect(self.close_and_continue)
        manual_actions.addWidget(self.confirm_ok_button)
        manual_actions.addWidget(self.confirm_error_button)
        manual_actions.addWidget(self.skip_button)
        manual_actions.addWidget(self.close_continue_button)
        manual_actions.addStretch(1)
        layout.addLayout(manual_actions)

        self.timeout_timer = QTimer(self)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self.on_timeout)

        self.view.loadFinished.connect(self.on_loaded)
        try:
            self.page.certificateError.connect(self.on_certificate_error)
        except Exception:
            self.logger.warning("Service check certificateError signal is not available")

    def set_state(self, new_state):
        old_state = getattr(self, "state", "")
        if old_state == new_state:
            return
        self.state = new_state
        self.logger.info("Service check state changed: service_id=%s from=%s to=%s", self.service.get("id", ""), old_state, new_state)

    def callback_allowed(self, callback_name, expected_states):
        if self.finished or self.state in {"finished", "manual_required"} or self.state not in set(expected_states):
            self.logger.warning(
                "Service check callback ignored: service_id=%s callback=%s state=%s expected=%s",
                self.service.get("id", ""),
                callback_name,
                self.state,
                ",".join(expected_states),
            )
            return False
        return True

    def cancel_pending_timers(self, reason):
        service_id = self.service.get("id", "")
        self.autofill_wait_deadline = datetime.now()
        self.load_false_deadline = datetime.now()
        self.logger.info("Service check timers cancelled: service_id=%s reason=%s", service_id, reason)

    def is_shared_group(self):
        return len(getattr(self, "group_services", []) or []) > 1

    def group_name(self):
        return self.service.get("session_group", "")

    def is_group_login_owner(self):
        return (not self.is_shared_group()) or self.group_index == 0 or bool(self.service.get("session_group_login_owner", False))

    def is_group_logout_owner(self):
        return (not self.is_shared_group()) or self.group_index == len(self.group_services) - 1 or bool(self.service.get("session_group_logout_owner", False))

    def start(self):
        self.started_at = datetime.now()
        service_id = self.service.get("id", "")
        diagnostics = visible_service_start_diagnostics(self.service)
        self.logger.info(
            "Service check visible start: service_id=%s auth_type=%s has_url=%s has_login_selector=%s has_password_selector=%s has_submit_selector=%s",
            service_id,
            diagnostics["auth_type"],
            diagnostics["has_url"],
            diagnostics["has_login_selector"],
            diagnostics["has_password_selector"],
            diagnostics["has_submit_selector"],
        )
        self.logger.info("Service check visible dialog opened: service_id=%s", service_id)
        if self.is_shared_group():
            self.logger.info("Service check group started: group=%s services_count=%s", self.group_name(), len(self.group_services))
            self.logger.info("Service check group webview created: group=%s", self.group_name())
            self.logger.info("Service check group service started: group=%s service_id=%s index=%s/%s", self.group_name(), service_id, self.group_index + 1, len(self.group_services))
        self.timeout_timer.start(max(1, int(self.service.get("timeout_seconds", 15))) * 1000)
        self.logger.info("Service check visible load started: service_id=%s", service_id)
        self.view.load(QUrl(self.service.get("url", "")))

    def duration_ms(self):
        if not self.started_at:
            return 0
        return int((datetime.now() - self.started_at).total_seconds() * 1000)

    def on_certificate_error(self, error):
        service_id = self.service.get("id", "")
        service_name = self.service.get("name", "")
        service_url = self.service.get("url", "")
        self.logger.warning(
            "Service check SSL error: service_id=%s name=%s url=%s",
            service_id,
            service_name,
            service_url,
        )
        description = ""
        try:
            description = str(error.description() or "")
        except Exception:
            description = ""
        if self.service.get("allow_insecure_ssl", False):
            self.logger.warning("Service check SSL error accepted by config: service_id=%s", service_id)
            self.ssl_warning = "SSL-сертификат был принят как внутренний/самоподписанный."
            try:
                error.acceptCertificate()
            except Exception:
                self.logger.exception("Service check SSL accept failed: service_id=%s", service_id)
                self.finish("ssl_error", error="Ошибка SSL-сертификата: не удалось принять сертификат сервиса.")
            return

        self.logger.warning("Service check SSL error rejected: service_id=%s", service_id)
        try:
            error.rejectCertificate()
        except Exception:
            pass
        detail = "Ошибка SSL-сертификата: проверьте сертификат сервиса или включите “Разрешить внутренний/самоподписанный SSL-сертификат” в настройках сервиса."
        if description:
            detail += f" Подробности: {description}"
        self.finish("ssl_error", error=detail)

    def on_timeout(self):
        self.finish("timeout", error=f"страница не загрузилась за {self.service.get('timeout_seconds', 15)} секунд")

    def on_loaded(self, ok):
        service_id = self.service.get("id", "")
        self.logger.info("Service check visible load finished: service_id=%s ok=%s", service_id, ok)
        if not self.callback_allowed("load_finished", {"loading"}):
            return
        if self.finished:
            return
        if not ok:
            if not self.service.get("allow_http_error_load", False):
                self.logger.warning("Service check visible load failed: service_id=%s error=%s", service_id, "Страница не загрузилась")
                self.finish("load_error", error="Страница не загрузилась")
                return
            self.start_load_false_retry_wait()
            return
        self.start_visible_auth_flow()

    def start_visible_auth_flow(self):
        service_id = self.service.get("id", "")
        if self.is_shared_group() and not self.is_group_login_owner():
            self.logger.info("Service check group skip auth: group=%s service_id=%s reason=shared_session", self.group_name(), service_id)
            self.set_state("result_check")
            self.start_result_check_after_delay()
            return
        if self.is_shared_group():
            self.logger.info("Service check group login owner: group=%s service_id=%s", self.group_name(), service_id)
        missing_reasons = []
        if not self.service.get("login_selector"):
            missing_reasons.append("login_selector")
        if not self.service.get("password_selector"):
            missing_reasons.append("password_selector")
        if not self.service.get("submit_selector"):
            missing_reasons.append("submit_selector")
        if not visible_html_form_should_start_autofill_wait(self.service):
            reason = ", ".join(missing_reasons)
            self.logger.warning("Service check visible autofill wait not started: service_id=%s reason=%s", service_id, reason)
            self.finish("autofill_error", error=f"Не заполнены обязательные selector поля: {reason}", wait_for_manual=True)
            return
        self.start_autofill_wait()

    def start_load_false_retry_wait(self):
        self.set_state("auth_wait")
        self.load_false_attempt = 0
        self.load_false_deadline = datetime.now() + timedelta(seconds=self.autofill_wait_seconds())
        self.load_false_last_diagnostics = {}
        self.check_load_false_diagnostics()

    def check_load_false_diagnostics(self):
        if not self.callback_allowed("load_false_retry", {"auth_wait"}):
            return
        self.load_false_attempt += 1
        self.page.runJavaScript(build_load_false_diagnostics_js(self.service), self.after_load_false_diagnostics)

    def after_load_false_diagnostics(self, result):
        if not self.callback_allowed("load_false_diagnostics", {"auth_wait"}):
            return
        service_id = self.service.get("id", "")
        diagnostics, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
        if parse_error is not None:
            diagnostics = {}
        self.load_false_last_diagnostics = diagnostics
        parts = load_false_diagnostics_log_parts(diagnostics)
        self.logger.warning(
            "Service check visible load false diagnostics retry: service_id=%s attempt=%s body_found=%s readyState=%s title=%s location=%s login_found=%s password_found=%s submit_found=%s success_found=%s error_found=%s iframe_count=%s",
            service_id,
            self.load_false_attempt,
            parts["body_found"],
            parts["ready_state"],
            parts["title"],
            parts["location"],
            parts["login_found"],
            parts["password_found"],
            parts["submit_found"],
            parts["success_found"],
            parts["error_found"],
            parts["iframe_count"],
        )
        action = load_false_continuation_action(self.service, diagnostics)
        if action == "autofill":
            self.logger.warning("Service check visible load false selectors became available, continuing")
            self.start_visible_auth_flow()
            return
        if action == "result_selector":
            self.logger.warning("Service check visible load false result selector became available, continuing")
            self.set_state("result_check")
            self.read_page_text()
            return
        if action == "error_selector":
            self.logger.warning("Service check visible load false error selector matched")
            self.set_state("result_check")
            self.read_page_text()
            return
        if datetime.now() < self.load_false_deadline:
            QTimer.singleShot(500, self.check_load_false_diagnostics)
            return
        self.logger.warning("Service check visible load false selectors timeout: service_id=%s", service_id)
        final_parts = load_false_diagnostics_log_parts(self.load_false_last_diagnostics)
        self.logger.warning(
            "Service check visible load false final diagnostics: service_id=%s body_found=%s readyState=%s title=%s location=%s login_found=%s password_found=%s submit_found=%s success_found=%s error_found=%s iframe_count=%s",
            service_id,
            final_parts["body_found"],
            final_parts["ready_state"],
            final_parts["title"],
            final_parts["location"],
            final_parts["login_found"],
            final_parts["password_found"],
            final_parts["submit_found"],
            final_parts["success_found"],
            final_parts["error_found"],
            final_parts["iframe_count"],
        )
        self.logger.warning("Service check visible load failed: service_id=%s error=%s", service_id, "Страница не загрузилась")
        self.finish("load_error", error="Страница не загрузилась")

    def autofill_wait_seconds(self):
        try:
            return max(1, int(self.service.get("autofill_wait_seconds") or self.service.get("timeout_seconds", 15)))
        except Exception:
            return 15

    def start_autofill_wait(self):
        self.set_state("auth_wait")
        self.autofill_wait_attempt = 0
        self.autofill_wait_deadline = datetime.now() + timedelta(seconds=self.autofill_wait_seconds())
        service_id = self.service.get("id", "")
        self.logger.info("Service check autofill wait started: service_id=%s", service_id)
        self.status_label.setText("Ожидание появления формы авторизации…")
        self.check_autofill_form_presence()

    def check_autofill_form_presence(self):
        if not self.callback_allowed("autofill_wait", {"auth_wait"}):
            return
        self.autofill_wait_attempt += 1
        self.page.runJavaScript(build_auth_form_presence_js(self.service), self.after_autofill_wait_js)

    def after_autofill_wait_js(self, result):
        if not self.callback_allowed("autofill_wait_callback", {"auth_wait"}):
            return
        service_id = self.service.get("id", "")
        result, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
        if parse_error is not None:
            self.logger.warning("Service check autofill wait failed: service_id=%s reason=%s", service_id, parse_error.get("error", "invalid_result"))
            self.finish("autofill_error", error=build_autofill_error_message(self.service, parse_error), wait_for_manual=True)
            return
        diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else result
        login_found = bool(diagnostics.get("login_found"))
        password_found = bool(diagnostics.get("password_found"))
        submit_found = bool(diagnostics.get("submit_found"))
        self.logger.info(
            "Service check autofill wait attempt: service_id=%s attempt=%s login_found=%s password_found=%s submit_found=%s",
            service_id,
            self.autofill_wait_attempt,
            login_found,
            password_found,
            submit_found,
        )
        if login_found and password_found and submit_found:
            self.logger.info("Service check autofill form ready: service_id=%s", service_id)
            self.run_visible_autofill()
            return
        if datetime.now() >= self.autofill_wait_deadline:
            self.logger.warning("Service check autofill wait timeout: service_id=%s", service_id)
            wait_result = dict(result)
            wait_result["error"] = "missing_form_elements"
            wait_result["missing"] = [name for name, found in (("login", login_found), ("password", password_found), ("submit", submit_found)) if not found]
            self.finish("autofill_error", error=build_autofill_error_message(self.service, wait_result), wait_for_manual=True)
            return
        QTimer.singleShot(500, self.check_autofill_form_presence)

    def run_visible_autofill(self):
        if self.auth_submitted:
            self.logger.warning("Service check auth submit ignored: service_id=%s reason=already_submitted state=%s", self.service.get("id", ""), self.state)
            return
        self.set_state("authenticating")
        creds = load_service_credentials(self.service.get("id", ""))
        js = self.make_visible_login_js(creds)
        service_id = self.service.get("id", "")
        self.logger.info("Service check autofill script length: service_id=%s length=%s", service_id, len(js))
        head, tail = safe_autofill_script_preview(js, creds)
        self.logger.info("Service check autofill script preview: service_id=%s head=%s tail=%s", service_id, head, tail)
        self.page.runJavaScript(js, self.after_login_js)

    def make_visible_login_js(self, creds):
        return build_auth_form_js(self.service, creds, blur_fields=True)

    def after_login_js(self, result):
        if not self.callback_allowed("auth_submit_callback", {"authenticating"}):
            return
        service_id = self.service.get("id", "")
        self.logger.info("Service check autofill callback received: service_id=%s result_type=%s", service_id, type(result).__name__)
        result, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
        if parse_error is not None:
            reason = str(parse_error.get("error") or "invalid_result")
            error_message = build_autofill_error_message(self.service, parse_error)
            self.logger.warning("Service check autofill failed: service_id=%s reason=%s", service_id, reason)
            self.finish("autofill_error", error=error_message, wait_for_manual=True)
            return
        missing = set(result.get("missing") or [])
        self.logger.info(
            "Service check visible auth form found: service_id=%s login_found=%s password_found=%s submit_found=%s",
            service_id,
            "login" not in missing,
            "password" not in missing,
            "submit" not in missing,
        )
        if not result.get("ok"):
            reason = str(result.get("error") or "unknown")
            if reason == "unknown":
                self.logger.warning(
                    "Service check autofill raw result invalid: service_id=%s result_type=%s result_repr=%s",
                    service_id,
                    type(result).__name__,
                    safe_autofill_result_repr(result),
                )
            self.logger.warning("Service check autofill failed: service_id=%s reason=%s", service_id, reason)
            self.finish("autofill_error", error=build_autofill_error_message(self.service, result), wait_for_manual=True)
            return
        self.logger.info("Service check visible auth values dispatched: service_id=%s", service_id)
        if result.get("clicked"):
            self.auth_submitted = True
            self.logger.info("Service check visible auth submit clicked: service_id=%s", service_id)
        self.status_label.setText("Форма отправлена. Ожидание результата проверки…")
        self.set_state("result_check")
        self.start_result_check_after_delay()

    def result_wait_seconds(self):
        try:
            return max(30 if self.is_shared_group() else 1, int(self.service.get("result_wait_seconds") or self.service.get("timeout_seconds", 15)))
        except Exception:
            return 30 if self.is_shared_group() else 15

    def start_result_check_after_delay(self):
        if self.is_shared_group():
            try:
                self.timeout_timer.stop()
            except Exception:
                pass
            self.result_check_deadline = datetime.now() + timedelta(seconds=self.result_wait_seconds())
            self.logger.info("Service check group result check started: group=%s service_id=%s", self.group_name(), self.service.get("id", ""))
        QTimer.singleShot(max(0, int(self.service.get("post_login_delay_ms", 1500))), self.read_page_text)

    def read_page_text(self):
        if not self.callback_allowed("result_check", {"result_check"}):
            return
        self.page.runJavaScript(build_result_selector_check_js(self.service), self.after_result_selector_check)

    def after_result_selector_check(self, result):
        if not self.callback_allowed("result_selector_check", {"result_check"}):
            return
        service_id = self.service.get("id", "")
        result, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
        if parse_error is not None:
            self.logger.warning("Service check result selector parse failed: service_id=%s reason=%s", service_id, parse_error.get("error", "invalid_result"))
            result = {}
        self.result_selector_result = result
        success_found = bool(result.get("success_found"))
        error_found = bool(result.get("error_found"))
        self.logger.info("Service check result selector check: service_id=%s success_found=%s error_found=%s", service_id, success_found, error_found)
        if success_found:
            self.logger.info("Service check result success selector matched: service_id=%s selector=%s", service_id, result.get("matched_success_selector", ""))
        if error_found:
            self.logger.info("Service check result error selector matched: service_id=%s selector=%s", service_id, result.get("matched_error_selector", ""))
        if self.is_shared_group():
            if success_found:
                self.logger.info("Service check group result success: group=%s service_id=%s", self.group_name(), service_id)
            if not success_found and not error_found:
                if not self.service.get("success_selectors") and self.service.get("post_login_actions"):
                    self.logger.info("Service check group post_login started without result selector: group=%s service_id=%s reason=no_success_selectors", self.group_name(), service_id)
                    QTimer.singleShot(2000, lambda: self.start_post_login_actions("", "", "", ""))
                    return
                if datetime.now() < getattr(self, "result_check_deadline", datetime.now()):
                    QTimer.singleShot(500, self.read_page_text)
                    return
                self.logger.warning("Service check group result timeout: group=%s service_id=%s", self.group_name(), service_id)
                self.logger.warning(
                    "Service check group result timeout diagnostics: service_id=%s success_selectors_count=%s error_selectors_count=%s post_login_actions_count=%s current_title=%s sanitized_location=%s",
                    service_id,
                    len(self.service.get("success_selectors") or []),
                    len(self.service.get("error_selectors") or []),
                    len(self.service.get("post_login_actions") or []),
                    "",
                    "",
                )
                self.finish("timeout", error="Не найдены признаки результата в общей сессии.")
                return
        self.page.runJavaScript("document.body ? document.body.innerText : ''", self.analyze_text)

    def analyze_text(self, text):
        if not self.callback_allowed("analyze_text", {"result_check"}):
            return
        selector_result = getattr(self, "result_selector_result", {})
        status, matched_success, matched_error, error = evaluate_service_check_page(self.service, text, loaded=True, selector_result=selector_result)
        details = error if status == "ok" and str(error).startswith("Успешный признак найден по CSS selector:") else ""
        if status == "ok":
            self.start_post_login_actions(text, matched_success, matched_error, details)
            return
        self.finish(
            status,
            error="" if details else error,
            html_text=text,
            matched_success=matched_success,
            matched_error=matched_error,
            details=details,
        )

    def start_post_login_actions(self, html_text, matched_success, matched_error, login_details):
        actions = self.service.get("post_login_actions") or []
        if not actions:
            self._post_login_actions_completed = False
            self.start_logout_flow(html_text, matched_success, matched_error, login_details)
            return
        if self.is_shared_group():
            self.logger.info("Service check group post_login started: group=%s service_id=%s", self.group_name(), self.service.get("id", ""))
        self.set_state("post_login_actions")
        self.run_action_sequence(
            "post_login",
            actions,
            on_success=lambda: self.after_post_login_actions_success(html_text, matched_success, matched_error, login_details),
            on_failure=lambda action, reason: self.finish(
                "manual_required",
                error="Вход выполнен, но мини-тест не пройден.",
                html_text=html_text,
                matched_success=matched_success,
                matched_error=matched_error,
                details=service_action_failure_message("post_login", action, reason),
            ),
        )

    def after_post_login_actions_success(self, html_text, matched_success, matched_error, login_details):
        self._post_login_actions_completed = True
        if self.is_shared_group():
            self.logger.info("Service check group post_login success: group=%s service_id=%s", self.group_name(), self.service.get("id", ""))
        self.start_logout_flow(html_text, matched_success, matched_error, login_details)

    def run_action_sequence(self, sequence_name, actions, on_success, on_failure):
        self._action_sequence = {
            "name": sequence_name,
            "actions": list(actions or []),
            "index": 0,
            "on_success": on_success,
            "on_failure": on_failure,
            "deadline": None,
        }
        service_id = self.service.get("id", "")
        self.logger.info("Service check action sequence started: service_id=%s sequence=%s steps_count=%s", service_id, sequence_name, len(actions or []))
        self.run_current_action_step()

    def run_current_action_step(self):
        expected_state = "post_login_actions" if getattr(self, "_action_sequence", {}).get("name") == "post_login" else "logout_actions"
        if not self.callback_allowed("action_step", {expected_state}):
            return
        sequence = getattr(self, "_action_sequence", {})
        actions = sequence.get("actions") or []
        index = int(sequence.get("index", 0))
        service_id = self.service.get("id", "")
        sequence_name = sequence.get("name", "")
        if index >= len(actions):
            self.logger.info("Service check action sequence success: service_id=%s sequence=%s", service_id, sequence_name)
            sequence.get("on_success", lambda: None)()
            return
        action = actions[index]
        action_type = action.get("type")
        self.logger.info("Service check action step wait: service_id=%s sequence=%s step=%s/%s type=%s", service_id, sequence_name, index + 1, len(actions), action_type)
        sequence["deadline"] = datetime.now() + timedelta(seconds=max(1, int(action.get("timeout_seconds", 5))))
        self.execute_action_step(action)

    def execute_action_step(self, action):
        expected_state = "post_login_actions" if getattr(self, "_action_sequence", {}).get("name") == "post_login" else "logout_actions"
        if not self.callback_allowed("execute_action_step", {expected_state}):
            return
        action_type = action.get("type")
        if action_type == "delay":
            QTimer.singleShot(max(0, int(action.get("delay_ms", 0))), self.finish_action_step_success)
            return
        if action_type == "click":
            self.page.runJavaScript(build_click_action_js(action.get("selector", "")), lambda result: self.after_action_step_js(action, result))
            return
        if action_type == "wait_selector":
            self.page.runJavaScript(build_wait_selector_action_js(action.get("selector", "")), lambda result: self.after_action_step_js(action, result))
            return
        if action_type == "wait_text":
            self.page.runJavaScript(build_wait_text_action_js(action.get("text", "")), lambda result: self.after_action_step_js(action, result))
            return
        self.finish_action_step_failed(action, "unsupported_action_type")

    def after_action_step_js(self, action, result):
        expected_state = "post_login_actions" if getattr(self, "_action_sequence", {}).get("name") == "post_login" else "logout_actions"
        if not self.callback_allowed("action_step_callback", {expected_state}):
            return
        service_id = self.service.get("id", "")
        sequence = getattr(self, "_action_sequence", {})
        sequence_name = sequence.get("name", "")
        index = int(sequence.get("index", 0))
        total = len(sequence.get("actions") or [])
        parsed, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
        action_type = action.get("type")
        if parse_error is None and parsed.get("ok") and (parsed.get("found", True) or parsed.get("clicked", False)):
            if action_type == "click":
                self.logger.info("Service check action step click: service_id=%s sequence=%s step=%s/%s selector=%s", service_id, sequence_name, index + 1, total, action.get("selector", ""))
            self.finish_action_step_success()
            return
        reason = parse_error.get("error") if parse_error else (parsed.get("reason") or parsed.get("error") or "selector_not_found")
        if datetime.now() < sequence.get("deadline", datetime.now()):
            QTimer.singleShot(500, lambda: self.execute_action_step(action))
            return
        self.finish_action_step_failed(action, reason)

    def finish_action_step_success(self):
        expected_state = "post_login_actions" if getattr(self, "_action_sequence", {}).get("name") == "post_login" else "logout_actions"
        if not self.callback_allowed("action_step_success", {expected_state}):
            return
        sequence = getattr(self, "_action_sequence", {})
        service_id = self.service.get("id", "")
        sequence_name = sequence.get("name", "")
        index = int(sequence.get("index", 0))
        actions = sequence.get("actions") or []
        action = actions[index] if index < len(actions) else {}
        self.logger.info("Service check action step success: service_id=%s sequence=%s step=%s/%s", service_id, sequence_name, index + 1, len(actions))
        sequence["index"] = index + 1
        QTimer.singleShot(max(0, int(action.get("delay_ms", 0))), self.run_current_action_step)

    def finish_action_step_failed(self, action, reason):
        sequence = getattr(self, "_action_sequence", {})
        service_id = self.service.get("id", "")
        sequence_name = sequence.get("name", "")
        index = int(sequence.get("index", 0))
        total = len(sequence.get("actions") or [])
        self.logger.warning("Service check action step failed: service_id=%s sequence=%s step=%s/%s reason=%s", service_id, sequence_name, index + 1, total, reason)
        self.logger.warning("Service check action sequence failed: service_id=%s sequence=%s reason=%s", service_id, sequence_name, reason)
        sequence.get("on_failure", lambda _action, _reason: None)(action, reason)

    def navigate_next_group_service(self):
        if self.group_index + 1 >= len(self.group_services):
            return
        previous_id = self.service.get("id", "")
        self.group_index += 1
        self.service = self.group_services[self.group_index]
        self.state = "loading"
        self.logout_started = False
        self.auth_submitted = True
        self.cancel_pending_timers("group_navigation_next")
        next_id = self.service.get("id", "")
        self.logger.info("Service check group navigate next: group=%s from_service_id=%s to_service_id=%s", self.group_name(), previous_id, next_id)
        self.logger.info("Service check group service started: group=%s service_id=%s index=%s/%s", self.group_name(), next_id, self.group_index + 1, len(self.group_services))
        self.setWindowTitle(f"Проверка сервиса: {self.service.get('name') or next_id or 'Сервис'}")
        self.timeout_timer.start(max(1, int(self.service.get("timeout_seconds", 15))) * 1000)
        self.logger.info("Service check visible load started: service_id=%s", next_id)
        self.view.load(QUrl(self.service.get("url", "")))

    def start_logout_flow(self, html_text, matched_success, matched_error, login_details):
        service_id = self.service.get("id", "")
        if self.is_shared_group() and not self.is_group_logout_owner():
            self.group_results.append(make_service_result(
                self.service,
                status="ok",
                matched_success_text=matched_success,
                matched_error_text=matched_error,
                page_excerpt=html_text,
                duration_ms=self.duration_ms(),
                warning=self.ssl_warning,
                details="Вход выполнен, мини-тест пройден, общая сессия продолжается.",
            ))
            self.navigate_next_group_service()
            return
        if self.logout_started:
            self.logger.warning("Service check logout ignored: service_id=%s reason=already_started state=%s", service_id, self.state)
            self.finish("manual_required", error="Повторный запуск выхода предотвращён.", html_text=html_text, matched_success=matched_success, matched_error=matched_error, details="Повторный запуск выхода предотвращён.")
            return
        self.logout_started = True
        self.cancel_pending_timers("entering_logout")
        self.set_state("logout_actions")
        self._logout_html_text = html_text
        self._logout_matched_success = matched_success
        self._logout_matched_error = matched_error
        self._logout_login_details = login_details
        self.logger.info("Service check logout started: service_id=%s", service_id)
        if self.is_shared_group():
            self.logger.info("Service check group logout owner: group=%s service_id=%s", self.group_name(), service_id)
        logout_actions = self.service.get("logout_actions") or []
        if logout_actions:
            self.run_action_sequence(
                "logout",
                logout_actions,
                on_success=self.after_logout_actions_success,
                on_failure=lambda action, reason: self.finish(
                    "manual_required",
                    error="Вход выполнен, но сценарий выхода не завершён.",
                    html_text=self._logout_html_text,
                    matched_success=self._logout_matched_success,
                    matched_error=self._logout_matched_error,
                    details="Вход выполнен, мини-тест пройден, но автоматический выход не подтверждён. " + service_action_failure_message("logout", action, reason),
                ),
            )
            return
        if not self.service.get("logout_button_selector"):
            self.logger.warning("Service check logout failed: service_id=%s reason=%s", service_id, "missing_logout_button_selector")
            self.finish("manual_required", error="Вход выполнен, но selector кнопки выхода не указан.", html_text=html_text, matched_success=matched_success, matched_error=matched_error, details="Вход выполнен, но автоматический выход не подтверждён.")
            return
        menu_selector = self.service.get("logout_menu_selector", "")
        if menu_selector:
            self.logger.info("Service check logout menu click: service_id=%s selector=%s", service_id, menu_selector)
            self.page.runJavaScript(build_click_selector_js(menu_selector), self.after_logout_menu_click)
            return
        self.click_logout_button()

    def after_logout_actions_success(self):
        self.set_state("logout_success_wait")
        self.logout_deadline = datetime.now() + timedelta(seconds=max(1, int(self.service.get("logout_wait_seconds", 10))))
        QTimer.singleShot(500, self.check_logout_success)

    def after_logout_menu_click(self, result):
        if not self.callback_allowed("logout_menu_click", {"logout_actions"}):
            return
        service_id = self.service.get("id", "")
        result, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
        if parse_error is not None or not result.get("ok"):
            self.logger.warning("Service check logout failed: service_id=%s reason=%s", service_id, "logout_menu_not_found")
            self.finish("manual_required", error="Вход выполнен, но меню выхода не найдено.", html_text=self._logout_html_text, matched_success=self._logout_matched_success, matched_error=self._logout_matched_error, details="Вход выполнен, но автоматический выход не подтверждён.")
            return
        self.logger.info("Service check logout menu opened: service_id=%s", service_id)
        self.logout_menu_deadline = datetime.now() + timedelta(seconds=max(1, int(self.service.get("logout_menu_wait_seconds", 5))))
        self.wait_logout_button()

    def wait_logout_button(self):
        if not self.callback_allowed("wait_logout_button", {"logout_actions"}):
            return
        self.page.runJavaScript(build_wait_selector_js([self.service.get("logout_button_selector", "")]), self.after_wait_logout_button)

    def after_wait_logout_button(self, result):
        if not self.callback_allowed("wait_logout_button_callback", {"logout_actions"}):
            return
        service_id = self.service.get("id", "")
        result, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
        if parse_error is None and result.get("found"):
            self.click_logout_button()
            return
        if datetime.now() >= getattr(self, "logout_menu_deadline", datetime.now()):
            self.logger.warning("Service check logout timeout: service_id=%s", service_id)
            self.finish("manual_required", error="Вход выполнен, но кнопка выхода не появилась после открытия меню.", html_text=self._logout_html_text, matched_success=self._logout_matched_success, matched_error=self._logout_matched_error, details="Вход выполнен, но автоматический выход не подтверждён.")
            return
        QTimer.singleShot(500, self.wait_logout_button)

    def click_logout_button(self):
        service_id = self.service.get("id", "")
        selector = self.service.get("logout_button_selector", "")
        self.logger.info("Service check logout button click: service_id=%s selector=%s", service_id, selector)
        self.page.runJavaScript(build_click_selector_js(selector), self.after_logout_button_click)

    def after_logout_button_click(self, result):
        if not self.callback_allowed("logout_button_click", {"logout_actions"}):
            return
        service_id = self.service.get("id", "")
        result, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
        if parse_error is not None or not result.get("ok"):
            self.logger.warning("Service check logout failed: service_id=%s reason=%s", service_id, "logout_button_not_found")
            self.finish("manual_required", error="Вход выполнен, но кнопка выхода не найдена.", html_text=self._logout_html_text, matched_success=self._logout_matched_success, matched_error=self._logout_matched_error, details="Вход выполнен, но автоматический выход не подтверждён.")
            return
        self.set_state("logout_success_wait")
        self.logout_deadline = datetime.now() + timedelta(seconds=max(1, int(self.service.get("logout_wait_seconds", 10))))
        QTimer.singleShot(500, self.check_logout_success)

    def check_logout_success(self):
        if not self.callback_allowed("logout_success_wait", {"logout_success_wait"}):
            return
        self.page.runJavaScript(build_wait_selector_js(self.service.get("logout_success_selectors", [])), self.after_logout_success_selectors)

    def after_logout_success_selectors(self, result):
        if not self.callback_allowed("logout_success_selector", {"logout_success_wait"}):
            return
        service_id = self.service.get("id", "")
        result, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
        if parse_error is None and result.get("found"):
            self.logger.info("Service check logout success: service_id=%s", service_id)
            self.finish("ok", html_text=self._logout_html_text, matched_success=self._logout_matched_success, matched_error=self._logout_matched_error, details=self.logout_success_details())
            return
        self.page.runJavaScript("document.body ? document.body.innerText : ''", self.after_logout_success_text)

    def after_logout_success_text(self, text):
        if not self.callback_allowed("logout_success_text", {"logout_success_wait"}):
            return
        service_id = self.service.get("id", "")
        lowered = str(text or "").casefold()
        for marker in self.service.get("logout_success_texts", []):
            if str(marker).casefold() in lowered:
                self.logger.info("Service check logout success: service_id=%s", service_id)
                self.finish("ok", html_text=self._logout_html_text, matched_success=self._logout_matched_success, matched_error=self._logout_matched_error, details=self.logout_success_details())
                return
        if datetime.now() >= getattr(self, "logout_deadline", datetime.now()):
            self.logger.warning("Service check logout timeout: service_id=%s", service_id)
            self.finish("manual_required", error="Вход выполнен, но автоматический выход не подтверждён.", html_text=self._logout_html_text, matched_success=self._logout_matched_success, matched_error=self._logout_matched_error, details="Вход выполнен, но автоматический выход не подтверждён.")
            return
        QTimer.singleShot(500, self.check_logout_success)

    def logout_success_details(self):
        if getattr(self, "_post_login_actions_completed", False):
            return "Вход выполнен, мини-тест пройден, выход выполнен"
        return "Вход выполнен, сервис работает, выход выполнен"

    def finish(self, status, error="", html_text="", matched_success="", matched_error="", wait_for_manual=False, details=""):

        if self.finished:
            return
        try:
            self.timeout_timer.stop()
        except Exception:
            pass
        service_id = self.service.get("id", "")
        if wait_for_manual or status in {"unknown", "autofill_error"}:
            self.set_state("manual_required")
            self.status_label.setText(
                f"Результат: {service_status_label(status)}\n{error or 'Требуется ручное подтверждение результата.'}"
            )
            self.logger.info("Service check visible waiting for manual confirmation: service_id=%s", service_id)
            return

        self.finished = True
        self.set_state("finished")
        self.logger.info("Service check finished: service_id=%s status=%s", service_id, status)
        should_close = self.service.get("visible_window_close_on_success", True) if status == "ok" else self.service.get("visible_window_close_on_error", False)
        result = make_service_result(
            self.service,
            status=status,
            error=error or "",
            matched_success_text=matched_success,
            matched_error_text=matched_error,
            page_excerpt=html_text,
            duration_ms=self.duration_ms(),
            warning=self.ssl_warning,
            details=details,
        )
        if self.is_shared_group():
            self.group_results.append(result)
            result = list(self.group_results)
            self.logger.info("Service check group finished: group=%s status=%s", self.group_name(), status)
        self.status_label.setText(f"Результат: {service_status_label(status)}" + (f"\n{error}" if error else ""))
        if should_close:
            delay_seconds = max(0, int(self.service.get("visible_window_close_delay_seconds", 3)))
            self.logger.info("Service check visible window close scheduled: service_id=%s delay=%s", service_id, delay_seconds)
            QTimer.singleShot(delay_seconds * 1000, lambda: self.close_and_emit(result, True))
            return
        self.logger.info("Service check visible waiting for manual confirmation: service_id=%s", service_id)

    def finish_manual(self, status, details):
        if self.emitted:
            return
        self.finished = True
        self.set_state("finished")
        try:
            self.timeout_timer.stop()
        except Exception:
            pass
        service_id = self.service.get("id", "")
        self.logger.info("Service check visible manual result: service_id=%s status=%s", service_id, status)
        result = make_service_result(
            self.service,
            status=status,
            error="",
            duration_ms=self.duration_ms(),
            warning=self.ssl_warning,
            manual=True,
            details=details,
        )
        self.close_and_emit(result, True)

    def confirm_ok(self):
        self.finish_manual("ok", "Результат подтверждён вручную дежурным.")

    def confirm_error(self):
        self.finish_manual("error", "Ошибка подтверждена вручную дежурным.")

    def skip_check(self):
        self.finish_manual("skipped", "Проверка пропущена вручную.")

    def close_and_continue(self):
        self.finish_manual("manual_required", "Окно проверки закрыто вручную без подтверждения результата.")

    def close_and_emit(self, result, continue_queue):
        self._pending_result = result
        self._pending_continue_queue = continue_queue
        if continue_queue:
            previous_service_id = result[-1].get("service_id", "") if isinstance(result, list) and result else result.get("service_id", "")
            self.logger.info("Service check queue waiting for visible cleanup: previous_service_id=%s", previous_service_id)
        self.close()

    def emit_completed(self, result, continue_queue):
        if self.emitted:
            return
        self.emitted = True
        if isinstance(result, dict) and result.get("manual") and continue_queue:
            self.logger.info("Service check queue continue after manual result: service_id=%s", result.get("service_id", ""))
        self.completed.emit(result, continue_queue)

    def cleanup(self):
        service_id = self.service.get("id", "")
        if self._cleaned_up:
            return
        self._cleaned_up = True
        view = getattr(self, "view", None)
        self.view = None
        self.page = None
        safe_delete_web_view(view, logger=self.logger, context=f"ServiceCheckVisibleDialog service_id={service_id}", load_handler=self.on_loaded)
        self.logger.info("Service check visible cleanup completed: service_id=%s", service_id)
        self.cleanup_completed.emit(service_id)

    def closeEvent(self, event):
        if not self.emitted and self._pending_result is None:
            try:
                self.timeout_timer.stop()
            except Exception:
                pass
            service_id = self.service.get("id", "")
            self.logger.info("Service check visible manual result: service_id=%s status=manual_required", service_id)
            self._pending_result = make_service_result(
                self.service,
                status="manual_required",
                duration_ms=self.duration_ms(),
                warning=self.ssl_warning,
                manual=True,
                details="Окно проверки закрыто вручную без подтверждения результата.",
            )
            self._pending_continue_queue = True
            self.logger.info("Service check queue waiting for visible cleanup: previous_service_id=%s", service_id)
        self.cleanup()
        if self._pending_result is not None and not self.emitted:
            result = self._pending_result
            continue_queue = self._pending_continue_queue
            self._pending_result = None
            self.emit_completed(result, continue_queue)
        super().closeEvent(event)


class ExternalBrowserServiceCheckDialog(QDialog):
    completed = Signal(object, bool)

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = list(services or [])
        self.logger = get_logger()
        self.group = (self.services[0].get("session_group", "") if self.services else "") or "external_browser_group"
        self.setWindowTitle("Проверка во внешнем браузере")
        self.resize(620, 260)
        layout = QVBoxLayout(self)
        text = QLabel(
            f"Око открыло страницы группы {self.group} во внешнем браузере.\n"
            "Проверьте их вручную и подтвердите результат.\n\n"
            "Автоматическое управление внешним браузером недоступно."
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        row = QHBoxLayout()
        ok_button = QPushButton("Проверено успешно")
        error_button = QPushButton("Ошибка")
        skip_button = QPushButton("Пропустить")
        reopen_button = QPushButton("Открыть ещё раз")
        ok_button.setObjectName("PrimaryAction")
        ok_button.clicked.connect(lambda: self.finish_group("ok"))
        error_button.clicked.connect(lambda: self.finish_group("error"))
        skip_button.clicked.connect(lambda: self.finish_group("skipped"))
        reopen_button.clicked.connect(self.open_all_urls)
        row.addWidget(ok_button)
        row.addWidget(error_button)
        row.addWidget(skip_button)
        row.addWidget(reopen_button)
        layout.addLayout(row)

    def open_all_urls(self):
        total = len(self.services)
        for index, service in enumerate(self.services, start=1):
            service_id = service.get("id", "")
            self.logger.info("Service check external browser open requested: group=%s service_id=%s index=%s/%s", self.group, service_id, index, total)
            ok = QDesktopServices.openUrl(QUrl(service.get("url", "")))
            if ok:
                self.logger.info("Service check external browser URL opened: group=%s service_id=%s", self.group, service_id)
            else:
                self.logger.warning("Service check external browser open failed: group=%s service_id=%s reason=%s", self.group, service_id, "openUrl returned false")

    def finish_group(self, status):
        self.logger.info("Service check external browser group manual result: group=%s status=%s", self.group, status)
        result_status = "ok" if status == "ok" else ("skipped" if status == "skipped" else "manual_required")
        details = {
            "ok": "Проверено вручную во внешнем браузере.",
            "error": "Ошибка подтверждена вручную во внешнем браузере.",
            "skipped": "Проверка во внешнем браузере пропущена вручную.",
        }.get(status, "")
        results = [
            make_service_result(service, status=result_status, manual=True, details=details)
            for service in self.services
        ]
        self.logger.info("Service check external browser group finished: group=%s status=%s", self.group, status)
        self.completed.emit(results, True)
        self.accept()


class DutyTasksDialog(QDialog):
    def __init__(self, config, parent=None, on_changed=None):
        super().__init__(parent)
        self.config = config
        self.on_changed = on_changed
        self.setWindowTitle("Задачи дежурства")
        self.resize(820, 360)

        root = QVBoxLayout(self)
        title = QLabel("Задачи дежурства")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        settings = ensure_duty_mode_defaults(self.config)
        zabbix_enabled = bool(settings.get("check_zabbix_enabled", True))
        services_enabled = bool(settings.get("check_services_enabled", settings.get("duty_service_checks_enabled", False)))

        if zabbix_enabled:
            root.addWidget(self._build_task_group(
                task_type="zabbix",
                title="Задача для проверки Zabbix / графиков",
                link_label="Ссылка на задачу Zabbix / графиков",
                create_label="Создать задачу Zabbix / графиков",
            ))
        if services_enabled:
            root.addWidget(self._build_task_group(
                task_type="service_checks",
                title="Задача для проверки сервисов",
                link_label="Ссылка на задачу проверки сервисов",
                create_label="Создать задачу проверки сервисов",
            ))
        if not zabbix_enabled and not services_enabled:
            hint = QLabel("Сначала выберите, что проверять в дежурстве: Zabbix / проблемы и графики, Сервисы или оба варианта.")
            hint.setWordWrap(True)
            root.addWidget(hint)
        root.addStretch(1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        root.addLayout(close_row)

    def _build_task_group(self, task_type, title, link_label, create_label):
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        settings = ensure_duty_mode_defaults(self.config)
        stored_url = settings.get("duty_service_checks_task_url" if task_type == "service_checks" else "duty_zabbix_task_url", "")
        input_widget = QLineEdit()
        input_widget.setPlaceholderText("https://itsm.stdpr.ru/itsm/index.pl?...TicketID=... или номер задачи")
        input_widget.setText(stored_url)
        input_widget.setMinimumWidth(620)
        input_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(QLabel(link_label + ":"))
        layout.addWidget(input_widget)
        row = QHBoxLayout()
        attach_button = QPushButton("Привязать")
        attach_button.clicked.connect(lambda _checked=False, tt=task_type, field=input_widget: self._open_attach(tt, field.text().strip()))
        create_button = QPushButton(create_label)
        create_button.clicked.connect(lambda _checked=False, tt=task_type: self._open_create(tt))
        row.addWidget(attach_button)
        row.addWidget(create_button)
        row.addStretch(1)
        layout.addLayout(row)
        return group

    def _open_attach(self, task_type, url):
        if not str(url or "").strip():
            QMessageBox.warning(self, "Привязка задачи", "Введите ссылку или номер задачи.")
            return
        dialog = AttachExistingTaskDialog(self.config, parent=self, task_type=task_type)
        dialog.url_input.setText(url)
        QTimer.singleShot(0, dialog.bind_task_from_input)
        dialog.exec()
        if self.on_changed:
            self.on_changed()

    def _open_create(self, task_type):
        dialog = OtrsCreateTaskDialog(self.config, parent=self, task_type=task_type)
        dialog.exec()
        if self.on_changed:
            self.on_changed()


class DutyNoteDialog(QDialog):
    def __init__(self, duty_widget, note_kind, parent=None):
        super().__init__(parent)
        self.duty_widget = duty_widget
        self.note_kind = note_kind
        is_service = note_kind == "services"
        self.setWindowTitle("Проверка сервисов завершена" if is_service else "Проверка Zabbix / графиков завершена")
        self.resize(820, 560)
        note = duty_widget._current_note_text(note_kind)

        root = QVBoxLayout(self)
        title = QLabel(self.windowTitle())
        title.setObjectName("PageTitle")
        root.addWidget(title)
        summary = QLabel(duty_widget._current_note_summary(note_kind))
        summary.setWordWrap(True)
        root.addWidget(summary)
        root.addWidget(QLabel("Предпросмотр заметки"))
        preview = QTextBrowser()
        preview.setOpenExternalLinks(False)
        preview.anchorClicked.connect(lambda url: open_external_url(url.toString()))
        preview.setHtml(plain_text_to_safe_html_with_links(note))
        preview.setMinimumHeight(300)
        root.addWidget(preview)
        row = QHBoxLayout()
        send = QPushButton("Отправить заметку в задачу проверки сервисов" if is_service else "Отправить заметку в задачу Zabbix / графиков")
        send.setEnabled(bool(duty_widget._service_checks_task_number() if is_service else duty_widget._zabbix_task_number()))
        send.clicked.connect(self.send_note)
        copy = QPushButton("Скопировать заметку")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(note))
        skip = QPushButton("Не отправлять")
        skip.clicked.connect(self.accept)
        row.addWidget(send)
        row.addWidget(copy)
        row.addWidget(skip)
        root.addLayout(row)

    def _save_last_note(self):
        self.duty_widget._save_last_note(self.note_kind, self.duty_widget._current_note_text(self.note_kind))

    def send_note(self):
        self._save_last_note()
        if self.note_kind == "services":
            self.duty_widget.open_service_check_note()
        else:
            self.duty_widget.open_graph_check_note()
        self.accept()

    def accept(self):
        self._save_last_note()
        super().accept()


class DutyModeWidget(QWidget):
    def __init__(self, config, profiles, credentials=None, graph_card_finder=None, source_view_finder=None, active_product_getter=None, parent=None):
        super().__init__(parent)

        self.config = config
        self.profiles = profiles
        self.credentials = credentials or {}
        self.graph_card_finder = graph_card_finder
        self.source_view_finder = source_view_finder
        self.active_product_getter = active_product_getter
        self.logger = get_logger()
        self.hidden_trigger_views = []
        self._hidden_trigger_contexts = []
        self.duty_trigger_queue = []
        self.duty_trigger_running = False
        self._last_duty_trigger_check_finished_at = None
        self.duty_trigger_stats = {"total": 0, "ok": 0, "alert": 0, "errors": 0}
        self.duty_trigger_results = []
        self.check_graphs = []
        self.cards = []
        self.graph_check_overlay = None
        self.service_check_queue = []
        self.service_check_results = []
        self.service_check_running = False
        self.service_result_labels = {}
        self.hidden_service_views = []
        self.visible_service_dialog = None
        self.service_checks_launched_from_duty = False
        self.duty_zabbix_status = "ещё не выполнялась"
        self.duty_service_checks_status = "отключено"
        self.duty_current_stage = "завершено"
        self.duty_flow_running = False
        self.duty_flow_services_first = False
        self.duty_summary_dialog = None
        self.zabbix_problems_dialog = None
        self.detected_zabbix_problems = []
        self.selected_zabbix_problems_for_note = []
        self.graph_trigger_check_started_for_overlay = False
        self.duty_flow_queue = []
        self.duty_zabbix_problems_status = "Ожидает проверки"
        self.duty_zabbix_graphs_status = "Ожидает проверки"
        self.duty_zabbix_graph_statuses = {}

        self.audio_player = None
        self.audio_output = None

        self.last_hour_key = None
        self.skip_timer = QTimer(self)
        self.skip_timer.setSingleShot(True)
        self.skip_timer.timeout.connect(self.show_skip_reminder)

        self.last_check_at = None

        self.setObjectName("DutyModeShell")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)

        title = QLabel("Режим дежурства")
        title.setObjectName("PageTitle")

        self.msk_time_label = QLabel("")
        self.msk_time_label.setStyleSheet("font-size: 15px; font-weight: bold;")

        self.settings_button = QPushButton("Настройки")
        self.settings_button.setMinimumHeight(32)
        self.settings_button.setMinimumWidth(150)
        self.settings_button.setStyleSheet("padding: 5px 12px;")
        self.settings_button.clicked.connect(self.open_settings)

        self.tasks_button = QPushButton("Задачи дежурства")
        self.tasks_button.setMinimumHeight(32)
        self.tasks_button.setMinimumWidth(150)
        self.tasks_button.setStyleSheet("padding: 5px 12px;")
        self.tasks_button.clicked.connect(self.open_tasks_dialog)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.msk_time_label)
        header.addWidget(self.tasks_button)
        header.addWidget(self.settings_button)

        root.addLayout(header)

        state_group = QGroupBox("Состояние")
        state_group.setObjectName("DutyStatePanel")
        state_layout = QGridLayout(state_group)
        state_layout.setContentsMargins(10, 8, 10, 8)
        state_layout.setHorizontalSpacing(14)
        state_layout.setVerticalSpacing(6)
        state_layout.setColumnStretch(1, 1)
        state_layout.setColumnStretch(3, 1)

        self.duty_state_value = QLabel("")
        self.last_check_value = QLabel("ещё не выполнялась")
        self.zabbix_task_state_value = QLabel("")
        self.service_task_state_value = QLabel("")
        self.zabbix_status_value = QLabel(self.duty_zabbix_status)
        self.service_duty_status_value = QLabel(self.duty_service_checks_status)
        self.duty_stage_value = QLabel("Текущий этап: завершено")
        self.graphs_state_value = QLabel("")
        self.services_state_value = QLabel("")

        state_labels = [
            QLabel("Дежурство:"),
            QLabel("Последняя проверка:"),
            QLabel("Задача для проверки Zabbix / графиков:"),
            QLabel("Задача для проверки сервисов:"),
            QLabel("Статус Zabbix / графики:"),
            QLabel("Статус сервисы:"),
            QLabel("Текущий этап:"),
            QLabel("Графики:"),
            QLabel("Сервисы:"),
        ]
        for label in state_labels:
            label.setStyleSheet("font-weight: bold;")

        state_layout.addWidget(state_labels[0], 0, 0)
        state_layout.addWidget(self.duty_state_value, 0, 1)
        state_layout.addWidget(state_labels[1], 0, 2)
        state_layout.addWidget(self.last_check_value, 0, 3)
        state_layout.addWidget(state_labels[2], 1, 0)
        state_layout.addWidget(self.zabbix_task_state_value, 1, 1)
        state_layout.addWidget(state_labels[3], 1, 2)
        state_layout.addWidget(self.service_task_state_value, 1, 3)
        state_layout.addWidget(state_labels[4], 2, 0)
        state_layout.addWidget(self.zabbix_status_value, 2, 1)
        state_layout.addWidget(state_labels[5], 2, 2)
        state_layout.addWidget(self.service_duty_status_value, 2, 3)
        state_layout.addWidget(state_labels[6], 3, 0)
        state_layout.addWidget(self.duty_stage_value, 3, 1)
        state_layout.addWidget(state_labels[7], 3, 2)
        state_layout.addWidget(self.graphs_state_value, 3, 3)
        state_layout.addWidget(state_labels[8], 4, 0)
        state_layout.addWidget(self.services_state_value, 4, 1)
        root.addWidget(state_group)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        self.enable_button = QPushButton("")
        self.enable_button.setObjectName("PrimaryAction")
        self.enable_button.setMinimumHeight(38)
        self.enable_button.clicked.connect(self.toggle_enabled)

        self.check_triggers_button = QPushButton("Проверить выбранное")
        self.check_triggers_button.setMinimumHeight(34)
        self.check_triggers_button.clicked.connect(self.start_duty_check_flow)

        self.notify_now_button = QPushButton("Показать уведомление сейчас")
        self.notify_now_button.setMinimumHeight(34)
        self.notify_now_button.clicked.connect(lambda: self.show_notification("Нужно произвести проверку графиков."))

        actions_layout.addWidget(self.enable_button)
        actions_layout.addWidget(self.check_triggers_button)
        actions_layout.addWidget(self.notify_now_button)
        actions_layout.addStretch()
        root.addLayout(actions_layout)

        checks_group = QGroupBox("Что проверяем в дежурстве")
        checks_layout = QHBoxLayout(checks_group)
        self.duty_zabbix_enabled_checkbox = QCheckBox("Zabbix / проблемы и графики")
        self.duty_service_checks_enabled_checkbox = QCheckBox("Сервисы")
        self.duty_zabbix_enabled_checkbox.setChecked(bool(self.get_settings().get("check_zabbix_enabled", True)))
        self.duty_service_checks_enabled_checkbox.setChecked(bool(self.get_settings().get("check_services_enabled", self.get_settings().get("duty_service_checks_enabled", False))))
        self.duty_zabbix_enabled_checkbox.toggled.connect(self.set_duty_zabbix_enabled)
        self.duty_service_checks_enabled_checkbox.toggled.connect(self.set_duty_service_checks_enabled)
        checks_layout.addWidget(self.duty_zabbix_enabled_checkbox)
        checks_layout.addWidget(self.duty_service_checks_enabled_checkbox)
        checks_layout.addStretch(1)
        root.addWidget(checks_group)

        manual_group = QGroupBox("Заметка дежурного")
        manual_layout = QVBoxLayout(manual_group)
        self.manual_duty_note_text = str(self.get_settings().get("manual_duty_note", "") or "")
        self.manual_duty_note_view = QTextBrowser()
        self.manual_duty_note_view.setOpenExternalLinks(False)
        self.manual_duty_note_view.anchorClicked.connect(lambda url: open_external_url(url.toString()))
        self.manual_duty_note_view.setFixedHeight(95)
        self.manual_duty_note_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        manual_group.setMaximumHeight(165)
        manual_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.manual_duty_note_view.setToolTip("Дважды щёлкните, чтобы редактировать заметку. Ссылки открываются во внешнем браузере.")
        self.manual_duty_note_view.mouseDoubleClickEvent = lambda event: self.open_manual_duty_note_editor()
        manual_buttons = QHBoxLayout()
        save_manual = QPushButton("Сохранить"); save_manual.clicked.connect(self.save_manual_duty_note)
        copy_manual = QPushButton("Скопировать заметку"); copy_manual.clicked.connect(lambda: QApplication.clipboard().setText(self.manual_duty_note_text))
        clear_manual = QPushButton("Очистить"); clear_manual.clicked.connect(self.clear_manual_duty_note)
        manual_buttons.addWidget(save_manual); manual_buttons.addWidget(copy_manual); manual_buttons.addWidget(clear_manual); manual_buttons.addStretch(1)
        manual_layout.addWidget(self.manual_duty_note_view); manual_layout.addLayout(manual_buttons)
        root.addWidget(manual_group)

        panels = QHBoxLayout()
        services_group = QGroupBox("Проверка сервисов")
        services_layout = QVBoxLayout(services_group)
        self.check_services_button = QPushButton("Проверить сервисы")
        self.check_services_button.clicked.connect(self.run_service_checks)
        self.check_services_button.hide()
        self.service_note_button = QPushButton("Заметка ОТРС")
        self.service_note_button.clicked.connect(self.open_service_check_note)
        self.service_note_button.hide()
        self.service_task_hint_label = QLabel("")
        self.service_summary_label = QLabel("Проверка сервисов ещё не выполнялась."); self.service_summary_label.hide()
        self.service_results_list = QListWidget(); self.service_results_list.hide()
        self.service_status_panel = QTextBrowser(); self.service_status_panel.setOpenExternalLinks(False); self.service_status_panel.anchorClicked.connect(lambda url: open_external_url(url.toString())); self.service_status_panel.setMinimumHeight(360)
        services_layout.addWidget(self.service_status_panel, stretch=1)
        zabbix_group = QGroupBox("Zabbix / проблемы и графики")
        zabbix_layout = QVBoxLayout(zabbix_group)
        self.zabbix_status_panel = QTextBrowser(); self.zabbix_status_panel.setOpenExternalLinks(False); self.zabbix_status_panel.anchorClicked.connect(lambda url: open_external_url(url.toString())); self.zabbix_status_panel.setMinimumHeight(360)
        zabbix_layout.addWidget(self.zabbix_status_panel, stretch=1)
        panels.addWidget(services_group, 1); panels.addWidget(zabbix_group, 1)
        root.addLayout(panels, stretch=1)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        self.status_label.hide()

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.scroll.hide()

        self.content = QWidget()
        self.content.setMinimumWidth(0)
        self.content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.cards_layout = QVBoxLayout(self.content)
        self.cards_layout.setContentsMargins(0, 4, 0, 0)
        self.cards_layout.setSpacing(10)
        self.scroll.setWidget(self.content)


        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.tick)
        self.clock_timer.start(1000)

        self.update_enable_button()
        self.update_task_label()
        self.tick()
        self.load_check_graphs()
        self.render_empty_hint()
        self.render_service_results()
        self.update_manual_duty_note_preview()



    def _selected_duty_checks(self):
        settings = self.get_settings()
        queue = []
        if bool(settings.get("check_services_enabled", settings.get("duty_service_checks_enabled", False))):
            queue.append("services")
        if bool(settings.get("check_zabbix_enabled", True)):
            queue.append("zabbix")
        return queue

    def set_duty_zabbix_enabled(self, enabled):
        settings = self.get_settings()
        settings["check_zabbix_enabled"] = bool(enabled)
        save_config(self.config)
        self.update_dashboard_summary()

    def save_manual_duty_note(self):
        self.get_settings()["manual_duty_note"] = self.manual_duty_note_text
        save_config(self.config)
        self.update_manual_duty_note_preview()

    def clear_manual_duty_note(self):
        if QMessageBox.question(self, "Заметка дежурного", "Очистить заметку дежурного?") == QMessageBox.Yes:
            self.manual_duty_note_text = ""
            self.save_manual_duty_note()

    def open_manual_duty_note_editor(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Редактировать заметку дежурного")
        layout = QVBoxLayout(dialog)
        editor = QTextEdit()
        editor.setPlainText(self.manual_duty_note_text)
        editor.setMinimumSize(680, 260)
        layout.addWidget(editor)
        row = QHBoxLayout()
        save = QPushButton("Сохранить")
        cancel = QPushButton("Отмена")
        row.addStretch(1); row.addWidget(save); row.addWidget(cancel)
        layout.addLayout(row)
        save.clicked.connect(dialog.accept)
        cancel.clicked.connect(dialog.reject)
        if dialog.exec() == QDialog.Accepted:
            self.manual_duty_note_text = editor.toPlainText()
            self.save_manual_duty_note()

    def update_manual_duty_note_preview(self):
        if hasattr(self, "manual_duty_note_view"):
            text = self.manual_duty_note_text or "Дважды щёлкните здесь, чтобы добавить заметку дежурного."
            self.manual_duty_note_view.setHtml(plain_text_to_safe_html_with_links(text))

    def _current_note_text(self, note_kind):
        if note_kind == "services":
            return build_service_check_note_text(self.config, self.service_check_results)
        return self.build_graph_check_note_text()

    def _current_note_summary(self, note_kind):
        if note_kind == "services":
            stats = summarize_service_results(self.service_check_results)
            return f"Проверка сервисов завершена: OK={stats['ok']}, Ошибки={stats['errors']}, Таймауты={stats['timeouts']}"
        stats = self.duty_trigger_stats or {}
        return f"Проблемы Zabbix: {self.duty_zabbix_problems_status}. Графики дежурства: {self.duty_zabbix_graphs_status}. OK={stats.get('ok',0)}, ALERT={stats.get('alert',0)}, ошибки={stats.get('errors',0)}"

    def _save_last_note(self, note_kind, note_text):
        settings = self.get_settings()
        now = format_dt(datetime.now(MSK))
        if note_kind == "services":
            settings["last_service_check_note"] = str(note_text or "")
            settings["last_service_check_time"] = now
        else:
            settings["last_zabbix_check_note"] = str(note_text or "")
            settings["last_zabbix_check_time"] = now
        save_config(self.config)
        self.update_dashboard_summary()

    def _show_duty_note_dialog(self, note_kind):
        dialog = DutyNoteDialog(self, note_kind, parent=self)
        if note_kind == "services":
            dialog.finished.connect(lambda _r: self._after_service_note_dialog())
        else:
            dialog.finished.connect(lambda _r: self._finish_duty_summary_dialog())
        dialog.show(); dialog.raise_(); dialog.activateWindow()

    def _after_service_note_dialog(self):
        if self.duty_flow_queue and self.duty_flow_queue[0] == "zabbix":
            self._run_next_duty_queue_item()
        else:
            self._finish_duty_summary_dialog()

    def _run_next_duty_queue_item(self):
        if not self.duty_flow_queue:
            self._finish_duty_summary_dialog(); return
        item = self.duty_flow_queue.pop(0)
        if item == "services":
            self.service_checks_launched_from_duty = True
            self.duty_service_checks_status = "выполняется"
            self.duty_current_stage = "проверка сервисов"
            self.update_dashboard_summary()
            self.logger.info("Duty service checks started: task_number=%s", self._service_checks_task_number() or "not_set")
            self.run_service_checks(from_duty=True)
        elif item == "zabbix":
            self.start_duty_zabbix_stage()

    def _zabbix_problem_counts(self):
        problems = list(self.detected_zabbix_problems or [])
        active = [problem for problem in problems if str(problem.get("status", "ПРОБЛЕМА")) != "РЕШЕНО"]
        resolved = [problem for problem in problems if str(problem.get("status", "")) == "РЕШЕНО"]
        handled = [problem for problem in active if problem.get("handled")]
        return len(active), len(handled), len(resolved)

    def _render_status_panels(self):
        if not hasattr(self, "service_status_panel"):
            return
        settings = self.get_settings()
        service_enabled = bool(settings.get("check_services_enabled", settings.get("duty_service_checks_enabled", False)))
        if not service_enabled:
            service_html = "<b>Проверка сервисов не выбрана</b>"
        else:
            stats = summarize_service_results(self.service_check_results)
            service_task = self._task_summary_html("service_checks", self._service_checks_task_number())
            lines = [f"<b>Задача для проверки сервисов:</b> {service_task}", "Автозапуск в дежурстве: включён.", f"Проверка сервисов завершена: OK={stats['ok']}, Ошибки={stats['errors']}, Таймауты={stats['timeouts']}", "<br><b>Сервисы:</b>"]
            result_by_id = {r.get('service_id'): r for r in self.service_check_results}
            for service in self.service_settings().get("items", []):
                result = result_by_id.get(service.get("id")) or make_service_result(service, status="not_checked")
                label = service_result_display_label(result) + (" (SSL-сертификат принят)" if result.get("warning") else "")
                color = "#e8eef7"
                if result.get("status") in {"auth_error","load_error","error","ssl_error","autofill_error"}: color = "#ff5c5c"
                elif result.get("status") == "ok": color = "#7CFC98"
                elif result.get("status") in {"timeout", "manual_required", "skipped"} or (result.get("manual") and result.get("status") == "unknown"): color = "#f6d365"
                elif result.get("status") == "checking": color = "#58a6ff"
                lines.append(f'<span style="color:{color}">{service.get("name") or service.get("id")} — {label}</span>')
            note = settings.get("last_service_check_note", "")
            if note:
                lines.append("<br><b>Последняя заметка:</b><br>" + plain_text_to_safe_html_with_links(f"Заметка в {settings.get('last_service_check_time','')}:\n{note}"))
            service_html = "<br>".join(lines)
        self.service_status_panel.setHtml(service_html)
        z_enabled = bool(settings.get("check_zabbix_enabled", True))
        if not z_enabled:
            z_html = "<b>Проверка Zabbix не выбрана</b>"
        else:
            zabbix_task = self._task_summary_html("zabbix", self._zabbix_task_number())
            lines = [f"<b>Задача Zabbix / графики:</b> {zabbix_task}", f"Проблемы Zabbix — {self._zabbix_status_html(self.duty_zabbix_problems_status)}", f"Графики дежурства — {self._zabbix_status_html(self.duty_zabbix_graphs_status)}"]
            active_count, handled_count, resolved_count = self._zabbix_problem_counts()
            if active_count:
                lines.append(f"Замечены проблемы: {active_count}")
            if handled_count:
                lines.append(f"Уже обработаны: {handled_count}")
            if resolved_count:
                lines.append(f"Решено с прошлой проверки: {resolved_count}")
            if self.selected_zabbix_problems_for_note:
                lines.append(f"Добавлено в заметку: {len(self.selected_zabbix_problems_for_note)}")
            lines.append("<br><b>Графики:</b>")
            for i, item in enumerate(self.check_graphs, 1):
                graph_status = self.duty_zabbix_graph_statuses.get(item.get("id"), self.duty_zabbix_graphs_status)
                lines.append(f"{i}. {self._graph_note_title(item)} — {self._zabbix_status_html(graph_status)}")
            note = settings.get("last_zabbix_check_note", "")
            if note:
                lines.append("<br><b>Последняя заметка:</b><br>" + plain_text_to_safe_html_with_links(f"Заметка в {settings.get('last_zabbix_check_time','')}:\n{note}"))
            z_html = "<br>".join(lines)
        self.zabbix_status_panel.setHtml(z_html)

    def service_settings(self):
        return ensure_service_checks_defaults(self.config)

    def enabled_services(self):
        return [item for item in self.service_settings().get("items", []) if item.get("enabled", True)]

    def render_service_results(self):
        if not hasattr(self, "service_results_list"):
            return
        self.service_results_list.clear()
        self.service_result_labels = {}
        result_by_id = {item.get("service_id"): item for item in self.service_check_results}
        for service in self.service_settings().get("items", []):
            result = result_by_id.get(service.get("id")) or make_service_result(service, status="not_checked")
            label = f"{service.get('name') or service.get('id')} — {service_result_display_label(result)}"
            if result.get("warning"):
                label += " (SSL-сертификат принят)"
            if not service.get("enabled", True):
                label += " (выключен)"
            list_item = QListWidgetItem(label)
            if result.get("status") in {"auth_error", "load_error", "error", "ssl_error", "autofill_error"}:
                list_item.setForeground(QColor("#ff5c5c"))
            elif result.get("status") == "ok":
                list_item.setForeground(QColor("#7CFC98"))
            elif result.get("status") in {"timeout", "manual_required", "skipped"} or (result.get("manual") and result.get("status") == "unknown"):
                list_item.setForeground(QColor("#f6d365"))
            elif result.get("status") == "checking":
                list_item.setForeground(QColor("#58a6ff"))
            if result.get("error") or result.get("warning") or result.get("details"):
                list_item.setToolTip("\n".join(part for part in [result.get("details", ""), result.get("error", ""), result.get("warning", "")] if part))
            self.service_results_list.addItem(list_item)
        stats = summarize_service_results(self.service_check_results)
        if self.service_check_results:
            self.service_summary_label.setText(
                "Проверка сервисов завершена: "
                f"OK={stats['ok']}, Ошибки={stats['errors']}, Таймауты={stats['timeouts']}"
            )
        self._render_status_panels()

    def _set_service_check_running(self, running):
        self.service_check_running = bool(running)
        if hasattr(self, "check_services_button"):
            self.check_services_button.setEnabled(not running)

    def run_service_checks(self, from_duty=False):
        if from_duty:
            self.service_checks_launched_from_duty = True
        if self.service_check_running:
            self.service_summary_label.setText("Проверка сервисов уже выполняется.")
            return
        services = self.enabled_services()
        self.service_check_queue = list(services)
        self.service_check_results = []
        self.render_service_results()
        self.service_summary_label.setText(f"Запущена проверка сервисов: {len(services)} шт.")
        if from_duty:
            self.duty_service_checks_status = "выполняется"
            self.update_dashboard_summary()
        self._set_service_check_running(True)
        if not services:
            self._finish_service_checks()
            return
        self._run_next_service_check()

    def _run_next_service_check(self):
        if not self.service_check_queue:
            self._finish_service_checks()
            return
        service = self.service_check_queue.pop(0)
        if service.get("auth_type") == AUTH_EXTERNAL_BROWSER_GROUP:
            group_services = self._collect_external_browser_group(service)
            for grouped_service in group_services:
                self.service_check_results.append(make_service_result(grouped_service, status="checking"))
            self.render_service_results()
            self._run_external_browser_group(group_services)
            return
        group_services = [service]
        if service.get("session_group") and service.get("session_group_reuse_webview", False):
            group_name = service.get("session_group", "")
            group_services.extend(
                sorted(
                    [item for item in self.service_check_queue if item.get("session_group") == group_name and item.get("session_group_reuse_webview", False)],
                    key=lambda item: int(item.get("session_group_order", 0) or 0),
                )
            )
            group_ids = {id(item) for item in group_services[1:]}
            self.service_check_queue = [item for item in self.service_check_queue if id(item) not in group_ids]
        self.service_check_results.append(make_service_result(service, status="checking"))
        for grouped_service in group_services[1:]:
            self.service_check_results.append(make_service_result(grouped_service, status="checking"))
        self.render_service_results()
        try:
            if service.get("auth_type") == AUTH_VISIBLE_HTML_FORM:
                self._run_visible_service_check(service, group_services=group_services)
            else:
                self._run_single_service_check(service)
        except Exception as exc:
            self.logger.exception("Service check failed: service_id=%s", service.get("id", ""))
            self._finish_single_service_check(service, make_service_result(service, status="error", error=str(exc)))

    def _collect_external_browser_group(self, service):
        group_name = service.get("session_group", "") or service.get("id", "")
        services = [service]
        services.extend([item for item in self.service_check_queue if item.get("auth_type") == AUTH_EXTERNAL_BROWSER_GROUP and (item.get("session_group", "") or item.get("id", "")) == group_name])
        group_ids = {id(item) for item in services[1:]}
        self.service_check_queue = [item for item in self.service_check_queue if id(item) not in group_ids]
        return sorted(services, key=lambda item: int(item.get("session_group_order", 0) or 0))

    def _run_external_browser_group(self, services):
        group = (services[0].get("session_group", "") if services else "") or "external_browser_group"
        self.logger.info("Service check external browser group started: group=%s services_count=%s", group, len(services))
        dialog = ExternalBrowserServiceCheckDialog(services, parent=self)
        self.external_browser_dialog = dialog
        dialog.completed.connect(self._finish_visible_service_check)
        delay_ms = int(float(services[0].get("external_browser_open_delay_seconds", 1) or 1) * 1000) if services else 0
        for index, service in enumerate(services):
            QTimer.singleShot(index * delay_ms, lambda svc=service, idx=index + 1, total=len(services), dlg=dialog: self._open_external_browser_service(dlg, svc, idx, total))
        QTimer.singleShot(max(0, len(services) * delay_ms), lambda: self._show_external_browser_dialog(dialog, group))

    def _open_external_browser_service(self, dialog, service, index, total):
        group = dialog.group
        service_id = service.get("id", "")
        self.logger.info("Service check external browser open requested: group=%s service_id=%s index=%s/%s", group, service_id, index, total)
        ok = QDesktopServices.openUrl(QUrl(service.get("url", "")))
        if ok:
            self.logger.info("Service check external browser URL opened: group=%s service_id=%s", group, service_id)
        else:
            self.logger.warning("Service check external browser open failed: group=%s service_id=%s reason=%s", group, service_id, "openUrl returned false")

    def _show_external_browser_dialog(self, dialog, group):
        self.logger.info("Service check external browser manual confirmation required: group=%s", group)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _run_visible_service_check(self, service, group_services=None):
        if not service.get("url"):
            self._finish_single_service_check(service, make_service_result(service, status="load_error", error="URL проверки не указан"))
            return
        dialog = ServiceCheckVisibleDialog(service, parent=self, group_services=group_services)
        self.visible_service_dialog = dialog
        dialog.completed.connect(self._finish_visible_service_check)
        dialog.destroyed.connect(lambda _obj=None, d=dialog: self._clear_visible_dialog_if_current(d))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.start()

    def _finish_visible_service_check(self, result, continue_queue):
        results = result if isinstance(result, list) else [result]
        result_ids = {item.get("service_id") for item in results}
        self.service_check_results = [
            item for item in self.service_check_results
            if item.get("service_id") not in result_ids
        ]
        self.service_check_results.extend(results)
        self.render_service_results()
        if continue_queue:
            last_result = results[-1]
            if self.visible_service_dialog is not None and self.visible_service_dialog.service.get("id") == last_result.get("service_id"):
                self.visible_service_dialog = None
            next_service_id = self.service_check_queue[0].get("id", "") if self.service_check_queue else ""
            if next_service_id:
                self.logger.info("Service check queue opening next after cleanup: next_service_id=%s", next_service_id)
            QTimer.singleShot(0, self._run_next_service_check)
            return
        self.service_check_queue = []
        self._set_service_check_running(False)
        self.service_summary_label.setText(
            "Проверка остановлена: окно сервиса оставлено открытым для диагностики."
        )

    def _clear_visible_dialog_if_current(self, dialog):
        if self.visible_service_dialog is dialog:
            self.visible_service_dialog = None


    def _run_single_service_check(self, service):
        if not service.get("url"):
            self._finish_single_service_check(service, make_service_result(service, status="load_error", error="URL проверки не указан"))
            return
        started = datetime.now()
        context = {"service": service, "started": started, "timed_out": False, "load_finished": False, "finished": False}
        view = register_web_view(QWebEngineView())
        page = QWebEnginePage(view)
        view.setPage(page)
        self.hidden_service_views.append(view)
        timeout_ms = max(1, int(service.get("timeout_seconds", 15))) * 1000
        timer = QTimer(self)
        timer.setSingleShot(True)
        context["timer"] = timer

        def cleanup():
            try:
                timer.stop()
            except Exception:
                pass
            if view in self.hidden_service_views:
                self.hidden_service_views.remove(view)
            safe_delete_web_view(view, logger=self.logger, context="hidden WebView service check", load_handler=on_loaded)

        def duration_ms():
            return int((datetime.now() - started).total_seconds() * 1000)

        def finish(status, error="", html_text="", matched_success="", matched_error="", warning="", details=""):

            if context.get("finished"):
                return
            context["finished"] = True
            cleanup()
            result = make_service_result(
                service,
                status=status,
                error=error,
                matched_success_text=matched_success,
                matched_error_text=matched_error,
                page_excerpt=html_text,
                duration_ms=duration_ms(),
                warning=warning or context.get("ssl_warning", ""),
                details=details,
            )
            self._finish_single_service_check(service, result)

        def analyze_text(text):
            selector_result = context.get("result_selector_result") if isinstance(context.get("result_selector_result"), dict) else {}
            status, matched_success, matched_error, error = evaluate_service_check_page(service, text, loaded=True, selector_result=selector_result)
            details = error if status == "ok" and str(error).startswith("Успешный признак найден по CSS selector:") else ""
            if status == "ok" and service.get("auth_type") == AUTH_HTML_FORM:
                start_logout_flow(text, matched_success, matched_error, details)
                return
            finish(status, error="" if details else error, html_text=text, matched_success=matched_success, matched_error=matched_error, details=details)

        def start_logout_flow(html_text, matched_success, matched_error, login_details):
            service_id = service.get("id", "")
            context["logout_html_text"] = html_text
            context["logout_matched_success"] = matched_success
            context["logout_matched_error"] = matched_error
            self.logger.info("Service check logout started: service_id=%s", service_id)
            if not service.get("logout_button_selector"):
                self.logger.warning("Service check logout failed: service_id=%s reason=%s", service_id, "missing_logout_button_selector")
                finish("manual_required", error="Вход выполнен, но selector кнопки выхода не указан.", html_text=html_text, matched_success=matched_success, matched_error=matched_error, details="Вход выполнен, но автоматический выход не подтверждён.")
                return
            if service.get("logout_menu_selector"):
                self.logger.info("Service check logout menu click: service_id=%s selector=%s", service_id, service.get("logout_menu_selector"))
                page.runJavaScript(build_click_selector_js(service.get("logout_menu_selector")), after_logout_menu_click)
                return
            click_logout_button()

        def after_logout_menu_click(result):
            service_id = service.get("id", "")
            result, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
            if parse_error is not None or not result.get("ok"):
                self.logger.warning("Service check logout failed: service_id=%s reason=%s", service_id, "logout_menu_not_found")
                finish("manual_required", error="Вход выполнен, но меню выхода не найдено.", html_text=context.get("logout_html_text", ""), matched_success=context.get("logout_matched_success", ""), matched_error=context.get("logout_matched_error", ""), details="Вход выполнен, но автоматический выход не подтверждён.")
                return
            self.logger.info("Service check logout menu opened: service_id=%s", service_id)
            context["logout_menu_deadline"] = datetime.now() + timedelta(seconds=max(1, int(service.get("logout_menu_wait_seconds", 5))))
            wait_logout_button()

        def wait_logout_button():
            if context.get("finished"):
                return
            page.runJavaScript(build_wait_selector_js([service.get("logout_button_selector", "")]), after_wait_logout_button)

        def after_wait_logout_button(result):
            service_id = service.get("id", "")
            result, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
            if parse_error is None and result.get("found"):
                click_logout_button()
                return
            if datetime.now() >= context.get("logout_menu_deadline", datetime.now()):
                self.logger.warning("Service check logout timeout: service_id=%s", service_id)
                finish("manual_required", error="Вход выполнен, но кнопка выхода не появилась после открытия меню.", html_text=context.get("logout_html_text", ""), matched_success=context.get("logout_matched_success", ""), matched_error=context.get("logout_matched_error", ""), details="Вход выполнен, но автоматический выход не подтверждён.")
                return
            QTimer.singleShot(500, wait_logout_button)

        def click_logout_button():
            service_id = service.get("id", "")
            self.logger.info("Service check logout button click: service_id=%s selector=%s", service_id, service.get("logout_button_selector", ""))
            page.runJavaScript(build_click_selector_js(service.get("logout_button_selector", "")), after_logout_button_click)

        def after_logout_button_click(result):
            service_id = service.get("id", "")
            result, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
            if parse_error is not None or not result.get("ok"):
                self.logger.warning("Service check logout failed: service_id=%s reason=%s", service_id, "logout_button_not_found")
                finish("manual_required", error="Вход выполнен, но кнопка выхода не найдена.", html_text=context.get("logout_html_text", ""), matched_success=context.get("logout_matched_success", ""), matched_error=context.get("logout_matched_error", ""), details="Вход выполнен, но автоматический выход не подтверждён.")
                return
            context["logout_deadline"] = datetime.now() + timedelta(seconds=max(1, int(service.get("logout_wait_seconds", 10))))
            QTimer.singleShot(500, check_logout_success)

        def check_logout_success():
            if context.get("finished"):
                return
            page.runJavaScript(build_wait_selector_js(service.get("logout_success_selectors", [])), after_logout_success_selectors)

        def after_logout_success_selectors(result):
            service_id = service.get("id", "")
            result, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
            if parse_error is None and result.get("found"):
                self.logger.info("Service check logout success: service_id=%s", service_id)
                finish("ok", html_text=context.get("logout_html_text", ""), matched_success=context.get("logout_matched_success", ""), matched_error=context.get("logout_matched_error", ""), details="Вход выполнен, сервис работает, выход выполнен")
                return
            page.runJavaScript("document.body ? document.body.innerText : ''", after_logout_success_text)

        def after_logout_success_text(text):
            service_id = service.get("id", "")
            lowered = str(text or "").casefold()
            for marker in service.get("logout_success_texts", []):
                if str(marker).casefold() in lowered:
                    self.logger.info("Service check logout success: service_id=%s", service_id)
                    finish("ok", html_text=context.get("logout_html_text", ""), matched_success=context.get("logout_matched_success", ""), matched_error=context.get("logout_matched_error", ""), details="Вход выполнен, сервис работает, выход выполнен")
                    return
            if datetime.now() >= context.get("logout_deadline", datetime.now()):
                self.logger.warning("Service check logout timeout: service_id=%s", service_id)
                finish("manual_required", error="Вход выполнен, но автоматический выход не подтверждён.", html_text=context.get("logout_html_text", ""), matched_success=context.get("logout_matched_success", ""), matched_error=context.get("logout_matched_error", ""), details="Вход выполнен, но автоматический выход не подтверждён.")
                return
            QTimer.singleShot(500, check_logout_success)

        def after_result_selector_check(result):
            if context.get("finished"):
                return
            service_id = service.get("id", "")
            result, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
            if parse_error is not None:
                self.logger.warning("Service check result selector parse failed: service_id=%s reason=%s", service_id, parse_error.get("error", "invalid_result"))
                result = {}
            context["result_selector_result"] = result
            success_found = bool(result.get("success_found"))
            error_found = bool(result.get("error_found"))
            self.logger.info("Service check result selector check: service_id=%s success_found=%s error_found=%s", service_id, success_found, error_found)
            if success_found:
                self.logger.info("Service check result success selector matched: service_id=%s selector=%s", service_id, result.get("matched_success_selector", ""))
            if error_found:
                self.logger.info("Service check result error selector matched: service_id=%s selector=%s", service_id, result.get("matched_error_selector", ""))
            page.runJavaScript("document.body ? document.body.innerText : ''", analyze_text)

        def read_text_after_login():
            if context.get("finished"):
                return
            page.runJavaScript(build_result_selector_check_js(service), after_result_selector_check)

        def after_login_js(result):
            service_id = service.get("id", "")
            self.logger.info("Service check autofill callback received: service_id=%s result_type=%s", service_id, type(result).__name__)
            result, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
            if parse_error is not None:
                self.logger.warning(
                    "Service check autofill failed: service_id=%s reason=%s",
                    service_id,
                    parse_error.get("error", "invalid_result"),
                )
                finish("autofill_error", error=build_autofill_error_message(service, parse_error))
                return
            if not result.get("ok"):
                if not result.get("error"):
                    self.logger.warning(
                        "Service check autofill raw result invalid: service_id=%s result_type=%s result_repr=%s",
                        service_id,
                        type(result).__name__,
                        safe_autofill_result_repr(result),
                    )
                finish("autofill_error", error=build_autofill_error_message(service, result))
                return
            QTimer.singleShot(max(0, int(service.get("post_login_delay_ms", 1500))), read_text_after_login)

        def autofill_wait_seconds():
            try:
                return max(1, int(service.get("autofill_wait_seconds") or service.get("timeout_seconds", 15)))
            except Exception:
                return 15

        def run_hidden_autofill():
            if context.get("finished"):
                return
            creds = load_service_credentials(service.get("id", ""))
            js = self._make_service_login_js(service, creds)
            service_id = service.get("id", "")
            self.logger.info("Service check autofill script length: service_id=%s length=%s", service_id, len(js))
            head, tail = safe_autofill_script_preview(js, creds)
            self.logger.info("Service check autofill script preview: service_id=%s head=%s tail=%s", service_id, head, tail)
            page.runJavaScript(js, after_login_js)

        def start_autofill_wait():
            context["autofill_wait_attempt"] = 0
            context["autofill_wait_deadline"] = datetime.now() + timedelta(seconds=autofill_wait_seconds())
            self.logger.info("Service check autofill wait started: service_id=%s", service.get("id", ""))
            check_autofill_form_presence()

        def check_autofill_form_presence():
            if context.get("finished") or context.get("timed_out"):
                return
            context["autofill_wait_attempt"] = int(context.get("autofill_wait_attempt", 0)) + 1
            page.runJavaScript(build_auth_form_presence_js(service), after_autofill_wait_js)

        def after_autofill_wait_js(result):
            if context.get("finished") or context.get("timed_out"):
                return
            service_id = service.get("id", "")
            result, parse_error = normalize_service_autofill_result(self.logger, service_id, result)
            if parse_error is not None:
                self.logger.warning("Service check autofill wait failed: service_id=%s reason=%s", service_id, parse_error.get("error", "invalid_result"))
                finish("autofill_error", error=build_autofill_error_message(service, parse_error))
                return
            diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else result
            login_found = bool(diagnostics.get("login_found"))
            password_found = bool(diagnostics.get("password_found"))
            submit_found = bool(diagnostics.get("submit_found"))
            self.logger.info(
                "Service check autofill wait attempt: service_id=%s attempt=%s login_found=%s password_found=%s submit_found=%s",
                service_id,
                context.get("autofill_wait_attempt", 0),
                login_found,
                password_found,
                submit_found,
            )
            if login_found and password_found and submit_found:
                self.logger.info("Service check autofill form ready: service_id=%s", service_id)
                run_hidden_autofill()
                return
            if datetime.now() >= context.get("autofill_wait_deadline"):
                self.logger.warning("Service check autofill wait timeout: service_id=%s", service_id)
                wait_result = dict(result)
                wait_result["error"] = "missing_form_elements"
                wait_result["missing"] = [name for name, found in (("login", login_found), ("password", password_found), ("submit", submit_found)) if not found]
                finish("autofill_error", error=build_autofill_error_message(service, wait_result))
                return
            QTimer.singleShot(500, check_autofill_form_presence)

        def on_loaded(ok):
            if context.get("timed_out"):
                return
            context["load_finished"] = True
            if not ok:
                finish("load_error", error="Страница не загрузилась")
                return
            if service.get("auth_type") == AUTH_HTML_FORM:
                start_autofill_wait()
            else:
                read_text_after_login()

        def on_timeout():
            context["timed_out"] = True
            finish("timeout", error=f"страница не загрузилась за {service.get('timeout_seconds', 15)} секунд")

        def on_certificate_error(error):
            service_id = service.get("id", "")
            service_name = service.get("name", "")
            service_url = service.get("url", "")
            self.logger.warning(
                "Service check SSL error: service_id=%s name=%s url=%s",
                service_id,
                service_name,
                service_url,
            )
            allow_insecure_ssl = bool(service.get("allow_insecure_ssl", False))
            description = ""
            try:
                description = str(error.description() or "")
            except Exception:
                description = ""
            if allow_insecure_ssl:
                self.logger.warning("Service check SSL error accepted by config: service_id=%s", service_id)
                context["ssl_warning"] = "SSL-сертификат был принят как внутренний/самоподписанный."
                try:
                    error.acceptCertificate()
                except Exception:
                    self.logger.exception("Service check SSL accept failed: service_id=%s", service_id)
                    finish("ssl_error", error="Ошибка SSL-сертификата: не удалось принять сертификат сервиса.")
                return

            self.logger.warning("Service check SSL error rejected: service_id=%s", service_id)
            try:
                error.rejectCertificate()
            except Exception:
                pass
            detail = "Ошибка SSL-сертификата: проверьте сертификат сервиса или включите “Разрешить внутренний/самоподписанный SSL-сертификат” в настройках сервиса."
            if description:
                detail += f" Подробности: {description}"
            finish("ssl_error", error=detail)

        try:
            page.certificateError.connect(on_certificate_error)
        except Exception:
            self.logger.warning("Service check certificateError signal is not available")

        timer.timeout.connect(on_timeout)
        view.loadFinished.connect(on_loaded)
        timer.start(timeout_ms)
        view.load(QUrl(service.get("url", "")))

    def _make_service_login_js(self, service, creds):
        return build_auth_form_js(service, creds, blur_fields=True)

    def _finish_single_service_check(self, service, result):
        self.service_check_results = [item for item in self.service_check_results if item.get("service_id") != service.get("id")]
        self.service_check_results.append(result)
        self.render_service_results()
        QTimer.singleShot(0, self._run_next_service_check)

    def _finish_service_checks(self):
        self._set_service_check_running(False)
        stats = summarize_service_results(self.service_check_results)
        service_status = "выполнено" if stats.get("errors", 0) == 0 and stats.get("timeouts", 0) == 0 else "требуется внимание"
        self.service_summary_label.setText(
            "Проверка сервисов завершена: "
            f"OK={stats['ok']}, Ошибки={stats['errors']}, Таймауты={stats['timeouts']}"
        )
        self.logger.info("Service checks finished: total=%s ok=%s errors=%s timeouts=%s", stats["total"], stats["ok"], stats["errors"], stats["timeouts"])
        if self.service_checks_launched_from_duty:
            self.duty_service_checks_status = service_status
            self.logger.info(
                "Duty service checks finished: status=%s ok=%s errors=%s timeouts=%s",
                service_status,
                stats["ok"],
                stats["errors"],
                stats["timeouts"],
            )
            self.service_checks_launched_from_duty = False
            self._show_duty_note_dialog("services")

    def open_service_check_note(self):
        task_url = (self.get_settings().get("duty_service_checks_task_url") or self.service_settings().get("otrs_task_url", "")).strip()
        if not task_url:
            QMessageBox.warning(
                self,
                "Проверка сервисов",
                "Задача ОТРС для проверки сервисов не указана.\nУкажите задачу в настройках проверки сервисов.",
            )
            return
        note_text = build_service_check_note_text(self.config, self.service_check_results)
        dialog = OtrsNoteDialog(
            config=self.config,
            note_text=note_text,
            parent=self,
            saved_log_message="Service check OTRS note saved",
            initial_note_url=task_url,
        )
        dialog.exec()

    def get_settings(self):
        return ensure_duty_mode_defaults(self.config)

    def update_enable_button(self):
        enabled = self.get_settings().get("enabled", False)
        self.enable_button.setText("Выключить дежурство" if enabled else "Включить дежурство")
        self.check_triggers_button.setVisible(not enabled)
        self.notify_now_button.setVisible(not enabled)
        self.update_dashboard_summary()

    def _zabbix_task_number(self):
        settings = self.get_settings()
        return (settings.get("duty_zabbix_task_number") or settings.get("current_ticket_number") or "").strip()

    def _service_checks_task_number(self):
        return self.get_settings().get("duty_service_checks_task_number", "").strip()

    def _task_summary(self, number):
        return f"№{number}" if number else "не привязана"


    def _duty_task_url(self, task_type):
        settings = self.get_settings()
        if task_type == "service_checks":
            url = str(settings.get("duty_service_checks_task_url", "") or "").strip()
            ticket_id = str(settings.get("duty_service_checks_task_id", "") or "").strip()
        else:
            url = str(settings.get("duty_zabbix_task_url") or settings.get("current_ticket_url") or "").strip()
            ticket_id = str(settings.get("duty_zabbix_task_id") or settings.get("current_ticket_id") or "").strip()
        if url:
            return url
        if ticket_id:
            base = str(settings.get("otrs", {}).get("note_url_base", "") or "").strip()
            if base:
                return base + ticket_id
        return ""

    def _task_summary_html(self, task_type, number):
        summary = self._task_summary(number)
        url = self._duty_task_url(task_type)
        if not url or not number:
            return summary
        import html
        escaped_url = html.escape(url, quote=True)
        escaped_summary = html.escape(summary, quote=True)
        return f'<a href="{escaped_url}">{escaped_summary}</a>'

    def _zabbix_status_html(self, status):
        return zabbix_status_html(status)

    def _graphs_count(self):
        self.load_check_graphs()
        return len(self.check_graphs)

    def update_dashboard_summary(self):
        settings = self.get_settings()
        enabled = settings.get("enabled", False)

        service_enabled = bool(settings.get("check_services_enabled", settings.get("duty_service_checks_enabled", False)))
        if not service_enabled and self.duty_service_checks_status not in {"выполняется", "выполнено", "ошибка", "требуется внимание"}:
            self.duty_service_checks_status = "отключено"

        self.duty_state_value.setText("включено" if enabled else "выключено")
        self.zabbix_task_state_value.setText(self._task_summary(self._zabbix_task_number()))
        self.service_task_state_value.setText(self._task_summary(self._service_checks_task_number()))
        self.zabbix_status_value.setText(self.duty_zabbix_status)
        self.service_duty_status_value.setText(self.duty_service_checks_status if service_enabled else "отключено")
        if hasattr(self, "duty_stage_value"):
            self.duty_stage_value.setText("Текущий этап: " + self.duty_current_stage)
        if hasattr(self, "duty_service_checks_enabled_checkbox"):
            self.duty_service_checks_enabled_checkbox.blockSignals(True)
            self.duty_service_checks_enabled_checkbox.setChecked(service_enabled)
            self.duty_service_checks_enabled_checkbox.blockSignals(False)
        if hasattr(self, "duty_zabbix_enabled_checkbox"):
            self.duty_zabbix_enabled_checkbox.blockSignals(True)
            self.duty_zabbix_enabled_checkbox.setChecked(bool(settings.get("check_zabbix_enabled", True)))
            self.duty_zabbix_enabled_checkbox.blockSignals(False)
        if hasattr(self, "service_task_hint_label"):
            self.service_task_hint_label.setText(
                f"Задача для проверки сервисов: {self._task_summary(self._service_checks_task_number())}. "
                f"Автозапуск в дежурстве: {'включён' if service_enabled else 'отключён'}."
            )
        self.last_check_value.setText(
            self.last_check_at.strftime("%H:%M:%S")
            if self.last_check_at
            else "ещё не выполнялась"
        )
        self.graphs_state_value.setText(str(self._graphs_count()))
        if hasattr(self, "services_state_value"):
            self.services_state_value.setText(str(len(self.enabled_services())))
        self._render_status_panels()

    def update_task_label(self):
        self.update_dashboard_summary()

    def set_duty_service_checks_enabled(self, enabled):
        settings = self.get_settings()
        settings["duty_service_checks_enabled"] = bool(enabled)
        settings["check_services_enabled"] = bool(enabled)
        save_config(self.config)
        self.duty_service_checks_status = "отключено" if not enabled else "ожидает проверки"
        self.update_dashboard_summary()

    def open_tasks_dialog(self):
        dialog = DutyTasksDialog(self.config, parent=self, on_changed=self.refresh_after_settings)
        dialog.exec()
        self.refresh_after_settings()

    def toggle_enabled(self):
        settings = self.get_settings()
        was_enabled = settings.get("enabled", False)
        if not was_enabled and not self._selected_duty_checks():
            if not self._ask_duty_check_selection():
                return
        settings["enabled"] = not was_enabled
        save_config(self.config)
        self.update_enable_button()

        if settings["enabled"] and not was_enabled:
            self.ask_duty_task_flow()


    def disable_for_shutdown(self):
        settings = self.get_settings()
        if not settings.get("enabled", False):
            return

        settings["enabled"] = False
        save_config(self.config)
        self.update_enable_button()

    def ask_duty_task_flow(self):
        """При заступлении на дежурство открываем раздельную привязку задач."""
        self.open_tasks_dialog()

    def attach_existing_task(self, task_type="zabbix"):
        dialog = AttachExistingTaskDialog(
            config=self.config,
            parent=self,
            task_type=task_type,
        )
        dialog.exec()
        self.update_task_label()

    def open_base_duty_task(self, task_type="zabbix"):
        dialog = OtrsCreateTaskDialog(
            config=self.config,
            parent=self,
            task_type=task_type,
        )
        dialog.exec()
        self.update_task_label()

    def open_settings(self):
        dialog = DutySettingsDialog(
            config=self.config,
            on_saved_callback=self.refresh_after_settings,
            parent=self
        )
        dialog.exec()
        self.refresh_after_settings()

    def refresh_after_settings(self):
        self.load_check_graphs()
        self.update_enable_button()
        self.update_task_label()

    def tick(self):
        now = datetime.now(MSK)
        self.msk_time_label.setText("МСК: " + now.strftime("%H:%M:%S"))

        settings = self.get_settings()

        if not settings.get("enabled", False):
            return

        if not settings.get("hourly_notification", True):
            return

        hour_key = now.strftime("%Y-%m-%d %H")

        if now.minute == 0 and now.second <= 2 and self.last_hour_key != hour_key:
            self.last_hour_key = hour_key
            self.show_notification("Нужно произвести проверку графиков.")

    def play_sound(self):
        settings = self.get_settings()
        sound_path = settings.get("sound_path", "")

        if MULTIMEDIA_AVAILABLE and sound_path:
            try:
                self.audio_player = QMediaPlayer(self)
                self.audio_output = QAudioOutput(self)
                self.audio_output.setVolume(0.75)
                self.audio_player.setAudioOutput(self.audio_output)
                self.audio_player.setSource(QUrl.fromLocalFile(sound_path))
                self.audio_player.play()
                return
            except Exception:
                pass

        try:
            from PySide6.QtWidgets import QApplication
            QApplication.beep()
        except Exception:
            pass

    def show_notification(self, text):
        self.play_sound()

        dialog = DutyNotificationDialog(text, parent=self)
        dialog.exec()

        if dialog.result_action == "check":
            if self.skip_timer.isActive():
                self.skip_timer.stop()
                self.status_label.setText("Отложенный таймер отменён: проверка начата вручную.")
            self.start_duty_check_flow()
        elif dialog.result_action == "skip":
            minutes = int(self.get_settings().get("skip_minutes", 5))
            self.status_label.setText(f"Проверка отложена на {minutes} минут.")
            self.skip_timer.start(minutes * 60 * 1000)

    def show_skip_reminder(self):
        self.show_notification("Пора все таки проверить графики")

    def all_graphs(self):
        result = []

        for product in self.config.get("products", []):
            product_name = product.get("name", "Продукт")

            for dashboard in product.get("dashboards", []):
                if dashboard.get("type") != "graphs_grid":
                    continue

                dashboard_name = dashboard.get("name", "Графики")
                zabbix_id = dashboard.get("zabbix_id")

                for index, graph in enumerate(dashboard.get("graphs", [])):
                    graph_id = graph.get("id") or f"{product_name}::{dashboard_name}::{index}::{graph.get('title', '')}"
                    result.append({
                        "id": graph_id,
                        "product": product_name,
                        "dashboard": dashboard_name,
                        "zabbix_id": zabbix_id,
                        "graph": graph,
                        "title": graph.get("title", "График"),
                    })

        return result

    def load_check_graphs(self):
        ids = set(self.get_settings().get("graph_ids", []))
        self.check_graphs = [g for g in self.all_graphs() if g["id"] in ids]

    def clear_cards(self):
        self.logger.info("Graph cards cleanup started")
        count = len(self.cards)
        self.cards = []

        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                if hasattr(widget, "cleanup"):
                    widget.cleanup()
                widget.setParent(None)
                widget.deleteLater()
        self.logger.info("Graph cards cleanup finished: count=%s", count)

    def render_empty_hint(self):
        self.clear_cards()

        self.update_dashboard_summary()
        hint = QLabel(
            "Графики дежурства не выбраны. Настройте их в разделе «Настройки дежурки»."
        )
        hint.setWordWrap(True)
        self.cards_layout.addWidget(hint)
        self.cards_layout.addStretch(1)

    def render_check_graph_cards(self):
        self.load_check_graphs()
        self.clear_cards()

        if not self.check_graphs:
            self.render_empty_hint()
            return False

        for item in self.check_graphs:
            profile = self.profiles.get(item.get("zabbix_id"))
            if not profile:
                label = QLabel(f"Не найден Zabbix profile: {item.get('zabbix_id')}")
                label.setWordWrap(True)
                label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                self.cards_layout.addWidget(label)
                continue

            card = DutyGraphCard(
                graph_config=item["graph"],
                profile=profile,
                credentials=self.credentials.get(item.get("zabbix_id"), {}),
                time_range=self.config.get("settings", {}).get("default_time_range", "1h"),
            )
            self.cards.append(card)
            self.cards_layout.addWidget(card, stretch=0)

        self.cards_layout.addStretch(1)
        self.update_dashboard_summary()
        return bool(self.cards)

    def _trigger_display_name(self, trigger):
        return str(trigger.get("display_name") or trigger.get("id") or "Триггер").strip()

    def _trigger_log_context(self, trigger):
        return {
            "id": trigger.get("id", ""),
            "display_name": trigger.get("display_name", ""),
            "source_product": trigger.get("source_product", ""),
            "source_section": trigger.get("source_section", ""),
            "target_product": trigger.get("target_product", ""),
            "target_section": trigger.get("target_section", ""),
            "target_graph_title": trigger.get("target_graph_title", ""),
        }

    def _status_message(self, status, result=None, trigger=None):
        status = str(status or "").upper()
        if result and str(result.get("message", "") or "").strip():
            if status in {"OK", "ALERT"}:
                return str(result.get("message", "")).strip()
        if status == "OK" and trigger:
            return str(trigger.get("ok_text") or DUTY_TRIGGER_STATUS_MESSAGES["OK"]).strip()
        return DUTY_TRIGGER_STATUS_MESSAGES.get(status, "Статус проверки сработок недоступен")

    def _find_duty_mode_target_card(self, trigger):
        target_title = normalize_lookup_text(trigger.get("target_graph_title", ""))
        if not target_title:
            return None

        for card in self.cards:
            graph_title = normalize_lookup_text(card.graph_config.get("title", ""))
            if graph_title == target_title:
                return card
        return None

    def _find_fallback_target_card(self, trigger):
        if not self.graph_card_finder:
            return None
        return self.graph_card_finder(
            trigger.get("target_product", ""),
            trigger.get("target_section", ""),
            trigger.get("target_graph_title", ""),
        )

    def _clear_duty_trigger_statuses(self):
        for card in self.cards:
            if hasattr(card, "clear_duty_trigger_status"):
                card.clear_duty_trigger_status()

    def _set_target_status(self, trigger, status, message):
        card = self._find_duty_mode_target_card(trigger)
        if card is not None:
            card.set_duty_trigger_status(status, message)
            self.logger.info(
                "Duty trigger rendered in duty mode graph card: id=%s display_name=%s status=%s target_found=True",
                trigger.get("id", ""),
                trigger.get("display_name", ""),
                status,
            )
            return True

        fallback_card = self._find_fallback_target_card(trigger)
        if fallback_card is not None:
            fallback_card.set_duty_trigger_status(status, message)
            self.logger.info(
                "Duty trigger rendered in fallback graph card: id=%s display_name=%s status=%s target_found=True",
                trigger.get("id", ""),
                trigger.get("display_name", ""),
                status,
            )
            return True

        self.logger.warning(
            "Duty trigger target not found: status=TARGET_NOT_FOUND context=%s",
            self._trigger_log_context(trigger),
        )
        self.status_label.setText(
            "Проверка триггеров выполнена, но один из целевых графиков не найден. "
            "Открой нужный раздел или проверь настройки триггеров."
        )
        return False

    def _set_zabbix_graph_status_for_trigger(self, trigger, status):
        target_title = normalize_lookup_text((trigger or {}).get("target_graph_title", ""))
        if not target_title:
            return
        status_text = str(status or "").upper()
        if status_text == "OK":
            panel_status = "Проверено"
        elif status_text == "ALERT":
            panel_status = "Требуется внимание"
        elif status_text == "NO_DATA":
            panel_status = "Нет данных"
        elif status_text in {"SOURCE_NOT_FOUND", "TARGET_NOT_FOUND"}:
            panel_status = "Ошибка"
        else:
            panel_status = "Ошибка"
        for item in self.check_graphs:
            graph_title = normalize_lookup_text(item.get("title") or item.get("graph", {}).get("title", ""))
            if graph_title == target_title:
                self.duty_zabbix_graph_statuses[item.get("id")] = panel_status
                return

    def _finalize_zabbix_graph_statuses_from_trigger_stats(self):
        stats = self.duty_trigger_stats or {}
        if stats.get("errors", 0):
            self.duty_zabbix_graphs_status = "Ошибка"
        elif stats.get("alert", 0):
            self.duty_zabbix_graphs_status = "Требуется внимание"
        else:
            self.duty_zabbix_graphs_status = "Проверено"
        keep_status_fragments = ("ошиб", "нет данных", "таймаут", "вним")
        for item in self.check_graphs:
            graph_id = item.get("id")
            current_status = str(self.duty_zabbix_graph_statuses.get(graph_id, "") or "")
            if any(fragment in current_status.casefold() for fragment in keep_status_fragments):
                continue
            self.duty_zabbix_graph_statuses[graph_id] = "Проверено"

    def _build_trigger_result_log(self, trigger, result, status):
        return {
            **self._trigger_log_context(trigger),
            "status": status,
            "duration_minutes": result.get("duration_minutes") if isinstance(result, dict) else None,
            "from_time": result.get("from_time") if isinstance(result, dict) else None,
            "to_time": result.get("to_time") if isinstance(result, dict) else None,
        }

    def _remember_duty_trigger_result(self, trigger, status, message, result=None, target_found=True):
        result = result if isinstance(result, dict) else {}
        self.duty_trigger_results.append({
            "trigger": dict(trigger or {}),
            "status": str(status or "").upper(),
            "message": str(message or ""),
            "target_found": bool(target_found),
            "duration_minutes": result.get("duration_minutes"),
            "from_time": result.get("from_time"),
            "to_time": result.get("to_time"),
        })

    def _graph_note_title(self, item):
        product = str(item.get("product") or "").strip()
        dashboard = str(item.get("dashboard") or "").strip()
        title = str(item.get("title") or item.get("graph", {}).get("title") or "График").strip()
        prefix = " / ".join(part for part in [product, dashboard] if part)
        return f"{prefix}: {title}" if prefix else title

    def _graph_note_url(self, item):
        graph = item.get("graph") or {}
        url = graph.get("open_url") or graph.get("zabbix_url") or graph.get("external_url") or graph.get("url") or ""
        if url and graph.get("use_time_range", True):
            return apply_time_range_to_url(url, self.config.get("duty_mode", {}).get("check_time_range", "1h"))
        return str(url or "")

    def _build_template_context(self):
        stats = self.duty_trigger_stats or {}
        checked_at = datetime.now(MSK)
        from_dt = self.last_check_at
        duration_minutes = ""
        if from_dt:
            duration_minutes = max(0, int((checked_at - from_dt).total_seconds() // 60))

        active_results = [item for item in self.duty_trigger_results if item.get("status") == "ALERT"]
        active_trigger_lines = [
            f"{item.get('trigger', {}).get('display_name') or item.get('trigger', {}).get('id') or 'Триггер'} — {item.get('status') or 'ALERT'}"
            for item in active_results
        ]
        active_triggers = format_numbered_lines(active_trigger_lines, empty_text="Не обнаружены")
        active_trigger_names = ", ".join(
            str(item.get("trigger", {}).get("display_name") or item.get("trigger", {}).get("id") or "Триггер")
            for item in active_results
        ) or "Не обнаружены"

        graph_titles = [self._graph_note_title(item) for item in self.check_graphs]
        graph_urls = [self._graph_note_url(item) for item in self.check_graphs]
        related_graphs = format_numbered_lines(graph_titles, empty_text="Не указаны")
        related_graph_links = format_numbered_lines(graph_urls, empty_text="Не указаны")

        problem_lines = []
        if active_results:
            problem_lines.extend(
                f"По графику “{title}” наблюдается отклонение."
                for title in graph_titles
            )
            problem_lines.extend(
                f"Активен триггер: {item.get('trigger', {}).get('display_name') or item.get('trigger', {}).get('id') or 'Триггер'}."
                for item in active_results
            )
        active_problems = format_numbered_lines(problem_lines, empty_text="Проблемы не обнаружены.")

        primary = active_results[0] if active_results else (self.duty_trigger_results[0] if self.duty_trigger_results else {})
        primary_trigger = primary.get("trigger", {}) if isinstance(primary, dict) else {}

        service_stats = summarize_service_results(self.service_check_results)
        zabbix_summary = f"OK={stats.get('ok', 0)}, ALERT={stats.get('alert', 0)}, ошибки={stats.get('errors', 0)}"
        service_summary = f"total={service_stats['total']}, OK={service_stats['ok']}, ошибки={service_stats['errors']}, таймауты={service_stats['timeouts']}"

        return {
            "date": checked_at.strftime("%Y-%m-%d"),
            "time": checked_at.strftime("%H:%M"),
            "datetime": format_dt(checked_at),
            "duty_mode": "дежурство",
            "operator": "",
            "zabbix_task_number": self._zabbix_task_number(),
            "zabbix_status": self.duty_zabbix_status,
            "zabbix_summary": zabbix_summary,
            "zabbix_started_at": format_dt(self.last_check_at),
            "zabbix_finished_at": format_dt(checked_at),
            "service_checks_task_number": self._service_checks_task_number(),
            "service_checks_status": self.duty_service_checks_status,
            "service_checks_total": service_stats["total"],
            "service_checks_ok": service_stats["ok"],
            "service_checks_errors": service_stats["errors"],
            "service_checks_timeouts": service_stats["timeouts"],
            "service_checks_summary": service_summary,
            "service_checks_started_at": format_dt(self.last_check_at),
            "service_checks_finished_at": format_dt(checked_at),
            "checked_at": format_dt(checked_at),
            "from_time": format_dt(from_dt),
            "to_time": format_dt(checked_at),
            "duration_minutes": duration_minutes,
            "ok_count": stats.get("ok", 0),
            "alert_count": stats.get("alert", 0),
            "error_count": stats.get("errors", 0),
            "active_triggers": active_triggers,
            "active_trigger_names": active_trigger_names,
            "active_problems": active_problems,
            "related_graphs": related_graphs,
            "related_graph_links": related_graph_links,
            "trigger_name": primary_trigger.get("display_name") or primary_trigger.get("id") or "",
            "trigger_status": primary.get("status", "") if isinstance(primary, dict) else "",
            "trigger_source_product": primary_trigger.get("source_product", ""),
            "trigger_source_section": primary_trigger.get("source_section", ""),
        }

    def mark_check_started(self):
        self.last_check_at = datetime.now(MSK)
        self.update_dashboard_summary()

    def _set_duty_trigger_check_running(self, running):
        self.duty_trigger_running = bool(running)
        if hasattr(self, "check_triggers_button"):
            self.check_triggers_button.setEnabled(not running)

    def _duty_trigger_cooldown_remaining(self):
        if self._last_duty_trigger_check_finished_at is None:
            return 0.0
        elapsed = (datetime.now(MSK) - self._last_duty_trigger_check_finished_at).total_seconds()
        return max(0.0, DUTY_TRIGGER_CHECK_COOLDOWN_SECONDS - elapsed)

    def _finish_duty_triggers_check(self):
        stats = self.duty_trigger_stats
        self._set_duty_trigger_check_running(False)
        self._last_duty_trigger_check_finished_at = datetime.now(MSK)
        zabbix_status = "ошибка" if stats.get("errors", 0) else ("требуется внимание" if stats.get("alert", 0) else "выполнено")
        self.duty_zabbix_status = zabbix_status
        if stats.get("alert", 0):
            self.status_label.setText(f"Замечены триггеры: {stats['alert']}. OK={stats['ok']}, ошибки={stats['errors']}.")
        elif stats.get("errors", 0):
            self.status_label.setText(f"Проверка триггеров завершена с ошибками: {stats['errors']}. OK={stats['ok']}.")
        else:
            self.status_label.setText(f"Всё в порядке. Проверка триггеров завершена: OK={stats['ok']}.")
        if self.duty_flow_running and self.duty_current_stage == "zabbix_graphs":
            self._finalize_zabbix_graph_statuses_from_trigger_stats()
        elif self.duty_flow_running:
            self.open_graph_check_overlay()
        self.logger.info("Duty Zabbix check finished: status=%s", zabbix_status)
        self.logger.info("Duty triggers check finished: stats=%s", stats)
        self.update_dashboard_summary()

    def _maybe_run_duty_service_checks_after_zabbix(self, zabbix_status):
        # Backward-compatible no-op: duty flow now runs service checks before Zabbix.
        if self.duty_flow_running:
            return
        self.finish_duty_check_flow()

    def start_duty_check_flow(self):
        if self.duty_flow_running or self.service_check_running or self.duty_trigger_running:
            self.logger.info("Duty check ignored: reason=already_running")
            self.status_label.setText("Дежурная проверка уже выполняется.")
            return
        queue = self._selected_duty_checks()
        if not queue:
            if not self._ask_duty_check_selection():
                return
            queue = self._selected_duty_checks()
            if not queue:
                return
        self.duty_flow_running = True
        self.duty_flow_queue = list(queue)
        self.duty_zabbix_status = "ожидает" if "zabbix" in queue else "отключено"
        self.duty_service_checks_status = "ожидает" if "services" in queue else "отключено"
        self.duty_zabbix_problems_status = "Ожидает проверки"
        self.duty_zabbix_graphs_status = "Ожидает проверки"
        self.duty_zabbix_graph_statuses = {item.get("id"): "Ожидает проверки" for item in self.check_graphs}
        self.detected_zabbix_problems = []
        self.selected_zabbix_problems_for_note = []
        self.logger.info("Duty check started")
        self.mark_check_started()
        self._run_next_duty_queue_item()

    def _ask_duty_check_selection(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Выберите, что проверять в режиме дежурства")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Выберите, что проверять в режиме дежурства"))
        z = QCheckBox("Zabbix / проблемы и графики")
        svc = QCheckBox("Сервисы")
        layout.addWidget(z); layout.addWidget(svc)
        row = QHBoxLayout()
        save = QPushButton("Сохранить и включить дежурство")
        cancel = QPushButton("Отмена")
        row.addWidget(save); row.addWidget(cancel); layout.addLayout(row)
        result = {"ok": False}
        def on_save():
            if not z.isChecked() and not svc.isChecked():
                QMessageBox.warning(dialog, "Режим дежурства", "Нужно выбрать хотя бы один тип проверки")
                return
            settings = self.get_settings()
            settings["check_zabbix_enabled"] = z.isChecked()
            settings["check_services_enabled"] = svc.isChecked()
            settings["duty_service_checks_enabled"] = svc.isChecked()
            save_config(self.config)
            result["ok"] = True
            dialog.accept()
        save.clicked.connect(on_save); cancel.clicked.connect(dialog.reject)
        dialog.exec()
        self.update_dashboard_summary()
        return result["ok"]


    def _active_duty_product_name(self):
        if callable(self.active_product_getter):
            try:
                product = str(self.active_product_getter() or "").strip()
                if product and product != "Дежурство":
                    return product
            except Exception:
                self.logger.exception("Duty active product getter failed")
        for item in self.check_graphs:
            product = str(item.get("product", "") or "").strip()
            if product:
                return product
        return ""

    def _preferred_duty_zabbix_profile(self):
        for item in self.check_graphs:
            zabbix_id = str(item.get("zabbix_id", "") or "").strip()
            if zabbix_id:
                return zabbix_id
        return ""

    def _open_zabbix_problems_stage(self):
        self.load_check_graphs()
        product_name = self._active_duty_product_name()
        zabbix_profile = self._preferred_duty_zabbix_profile()
        url, page, _product = find_problems_page_url(self.config, product_name=product_name, zabbix_profile=zabbix_profile)
        if not url:
            self.duty_zabbix_problems_status = "Ошибка: URL не найден"
            self.duty_zabbix_status = "ошибка"
            self.status_label.setText("Не найден URL страницы проблем Zabbix для текущего продукта.")
            self.update_dashboard_summary()
            QMessageBox.warning(
                self,
                "Проблемы Zabbix",
                "Не найден URL страницы проблем Zabbix для текущего продукта.\n"
                "Проверьте настройки продукта: должна быть включённая страница типа problems_page.",
            )
            self.finish_duty_check_flow()
            return
        zabbix_id = str((page or {}).get("zabbix_id") or (page or {}).get("zabbix_profile") or (page or {}).get("zabbix_profile_id") or zabbix_profile or "").strip()
        profile = self.profiles.get(zabbix_id)
        credentials = self.credentials.get(zabbix_id, {}) if zabbix_id else {}
        self.duty_zabbix_problems_status = "Открыто для проверки"
        self.update_dashboard_summary()
        dialog = ZabbixProblemsDialog(url, profile=profile, credentials=credentials, config=self.config, parent=self)
        self.zabbix_problems_dialog = dialog
        dialog.problemsDetected.connect(self._remember_detected_zabbix_problems)
        dialog.problemsSelected.connect(self._remember_selected_zabbix_problems)
        dialog.confirmed.connect(self._finish_zabbix_problems_stage)
        dialog.finished.connect(lambda _result: setattr(self, "zabbix_problems_dialog", None))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _remember_detected_zabbix_problems(self, problems):
        self.detected_zabbix_problems = list(problems or [])
        active_count, _handled_count, _resolved_count = self._zabbix_problem_counts()
        if active_count:
            self.duty_zabbix_problems_status = "Требуется внимание"
        self.update_dashboard_summary()

    def _remember_selected_zabbix_problems(self, problems):
        self.selected_zabbix_problems_for_note = list(problems or [])
        if self.detected_zabbix_problems or self.selected_zabbix_problems_for_note:
            self.duty_zabbix_problems_status = "Требуется внимание"
        self.update_dashboard_summary()

    def _finish_zabbix_problems_stage(self):
        active_count, _handled_count, _resolved_count = self._zabbix_problem_counts()
        self.duty_zabbix_problems_status = "Требуется внимание" if active_count else "Проверено"
        self.load_check_graphs()
        if not self.check_graphs:
            self.duty_zabbix_graphs_status = "Ошибка: графики не выбраны"
            self.duty_zabbix_status = "ошибка"
            self.update_dashboard_summary()
            QMessageBox.warning(
                self,
                "Zabbix / графики",
                "Графики дежурства не выбраны. Настройте их в разделе «Настройки дежурки».",
            )
            self.finish_duty_check_flow()
            return
        self.duty_zabbix_graphs_status = "Открыто для проверки"
        self.duty_zabbix_graph_statuses = {item.get("id"): "Открыто для проверки" for item in self.check_graphs}
        self.update_dashboard_summary()
        self.open_graph_check_overlay(run_triggers_after_open=True)

    def start_duty_zabbix_stage(self):
        self.duty_current_stage = "zabbix_problems"
        self.duty_zabbix_status = "выполняется"
        self.duty_zabbix_problems_status = "Ожидает проверки"
        self.duty_zabbix_graphs_status = "Ожидает проверки"
        self.duty_trigger_stats = {"total": 0, "ok": 0, "alert": 0, "errors": 0}
        self.duty_trigger_results = []
        self.detected_zabbix_problems = []
        self.selected_zabbix_problems_for_note = []
        self.graph_trigger_check_started_for_overlay = False
        self.status_label.setText("Текущий этап: Zabbix / проблемы")
        self.update_dashboard_summary()
        self.logger.info("Duty Zabbix check started: task_number=%s", self._zabbix_task_number() or "not_set")
        self._open_zabbix_problems_stage()

    def finish_duty_check_flow(self):
        self.duty_current_stage = "zabbix_note"
        self.logger.info("Duty check finished")
        self.update_dashboard_summary()
        self._show_duty_note_dialog("zabbix")

    def open_duty_summary_dialog(self):
        self.finish_duty_check_flow()

    def _finish_duty_summary_dialog(self):
        self.duty_current_stage = "завершено"
        self.duty_flow_running = False
        self.duty_flow_services_first = False
        self.duty_summary_dialog = None
        self.zabbix_problems_dialog = None
        self.detected_zabbix_problems = []
        self.selected_zabbix_problems_for_note = []
        self.duty_flow_queue = []
        self.duty_zabbix_problems_status = "Ожидает проверки"
        self.duty_zabbix_graphs_status = "Ожидает проверки"
        self.update_dashboard_summary()

    def run_duty_triggers_check(self, part_of_duty_flow=False):
        if self.duty_trigger_running or self._hidden_trigger_contexts or self.hidden_trigger_views:
            self.status_label.setText("Проверка уже выполняется")
            self.logger.info("Duty trigger manual check skipped: check already running")
            return

        cooldown_remaining = self._duty_trigger_cooldown_remaining()
        if cooldown_remaining > 0 and not part_of_duty_flow:
            self.status_label.setText(
                "Проверка триггеров недавно завершилась. "
                f"Повторите через {cooldown_remaining:.0f} сек."
            )
            self.logger.info(
                "Duty trigger check skipped: cooldown active remaining_seconds=%.1f",
                cooldown_remaining,
            )
            if part_of_duty_flow:
                self._finalize_zabbix_graph_statuses_from_trigger_stats()
                self.update_dashboard_summary()
            return

        trigger_settings = ensure_duty_triggers_defaults(self.config)
        if not trigger_settings.get("enabled", True):
            self.status_label.setText("Проверка триггеров отключена в настройках.")
            self.logger.info("Duty triggers check skipped: disabled")
            if part_of_duty_flow:
                self._finalize_zabbix_graph_statuses_from_trigger_stats()
                self.update_dashboard_summary()
            return

        enabled_triggers = [
            trigger for trigger in trigger_settings.get("items", [])
            if trigger.get("enabled", True)
        ]
        if not part_of_duty_flow:
            self.logger.info("Duty check started")
            self.logger.info("Duty service checks enabled: value=false")
            self.logger.info("Duty service checks skipped: reason=disabled")
            self.logger.info("Duty Zabbix check started: task_number=%s", self._zabbix_task_number() or "not_set")
            self.duty_flow_running = True
            self.duty_current_stage = "проверка Zabbix / графиков"
            self.mark_check_started()
        self.logger.info("Duty trigger manual check started: enabled_count=%s", len(enabled_triggers))
        self.duty_zabbix_status = "выполняется"
        if self.duty_flow_running and part_of_duty_flow:
            self.duty_current_stage = "zabbix_graphs"
            self.duty_zabbix_graphs_status = "Открыто для проверки"
        self.status_label.setText(f"Запущена проверка триггеров: {len(enabled_triggers)} шт.")

        if not self.cards:
            self.render_check_graph_cards()
        self._clear_duty_trigger_statuses()

        self.duty_trigger_queue = list(enabled_triggers)
        self.duty_trigger_stats = {"total": len(enabled_triggers), "ok": 0, "alert": 0, "errors": 0}
        self.duty_trigger_results = []
        if not enabled_triggers:
            self._finish_duty_triggers_check()
            return

        self._set_duty_trigger_check_running(True)
        self._run_next_duty_trigger()

    def _run_next_duty_trigger(self):
        if not self.duty_trigger_queue:
            self._finish_duty_triggers_check()
            return

        trigger = self.duty_trigger_queue.pop(0)
        try:
            self._run_single_duty_trigger(trigger)
        except Exception as exc:
            self.logger.exception(
                "Duty trigger finished with error: id=%s reason=%s",
                trigger.get("id", ""),
                exc,
            )
            self._finish_trigger_without_html(trigger, "ERROR", reason=str(exc))

    def _run_single_duty_trigger(self, trigger):
        self.logger.info(
            "Duty trigger started: context=%s",
            self._trigger_log_context(trigger),
        )
        dashboard = find_dashboard_by_product_section(
            self.config,
            trigger.get("source_product", ""),
            trigger.get("source_section", ""),
        )
        if not dashboard:
            self.logger.warning(
                "Duty trigger source not found: id=%s display_name=%s source_product=%s source_section=%s",
                trigger.get("id", ""),
                trigger.get("display_name", ""),
                trigger.get("source_product", ""),
                trigger.get("source_section", ""),
            )
            self._finish_trigger_without_html(trigger, "SOURCE_NOT_FOUND")
            return

        source_url = build_dashboard_source_url(
            dashboard,
            self.config.get("settings", {}).get("default_time_range", "1h"),
            trigger.get("mode", ""),
        )
        if not source_url:
            self.logger.warning(
                "Duty trigger source URL not found: id=%s display_name=%s source_product=%s source_section=%s",
                trigger.get("id", ""),
                trigger.get("display_name", ""),
                trigger.get("source_product", ""),
                trigger.get("source_section", ""),
            )
            self._finish_trigger_without_html(trigger, "SOURCE_NOT_FOUND")
            return

        fresh_source_url = add_duty_trigger_cache_buster(source_url)
        self.logger.info(
            "Duty trigger source fresh load requested: id=%s display_name=%s source_product=%s source_section=%s has_url=%s",
            trigger.get("id", ""),
            trigger.get("display_name", ""),
            trigger.get("source_product", ""),
            trigger.get("source_section", ""),
            bool(fresh_source_url),
        )

        self._load_hidden_source_view(trigger, dashboard, fresh_source_url)

    def _load_hidden_source_view(self, trigger, dashboard, source_url):
        zabbix_id = dashboard.get("zabbix_id")
        profile = self.profiles.get(zabbix_id)
        if profile is None:
            self.logger.warning(
                "Duty trigger source profile not found: id=%s zabbix_id=%s",
                trigger.get("id", ""),
                zabbix_id,
            )
            self._finish_trigger_without_html(trigger, "SOURCE_NOT_FOUND")
            return

        view = register_web_view(QWebEngineView(self))
        view.setVisible(False)
        page = QWebEnginePage(profile, view)
        view.setPage(page)

        context = {
            "view": view,
            "page": page,
            "trigger": trigger,
            "source_url": source_url,
            "load_handler": None,
            "timeout_timer": QTimer(self),
            "read_timer": QTimer(self),
            "completed": False,
            "cleanup_started": False,
        }
        context["timeout_timer"].setSingleShot(True)
        context["read_timer"].setSingleShot(True)
        self.hidden_trigger_views.append(view)
        self._hidden_trigger_contexts.append(context)

        def on_timeout(ctx=context):
            if ctx.get("completed"):
                return
            ctx["completed"] = True
            t = ctx.get("trigger") or {}
            self.logger.error(
                "Duty trigger hidden WebView timeout: id=%s display_name=%s timeout_ms=%s source_url_present=%s",
                t.get("id", ""),
                t.get("display_name", ""),
                DUTY_TRIGGER_HIDDEN_WEBVIEW_TIMEOUT_MS,
                bool(ctx.get("source_url")),
            )
            self.logger.error("Duty trigger finished with error: id=%s reason=timeout", t.get("id", ""))
            self._cleanup_hidden_view(ctx)
            self._finish_trigger_without_html(t, "ERROR", reason="timeout")

        def read_html(ctx=context):
            if ctx.get("completed"):
                return
            try:
                current_page = ctx.get("page")
                if current_page is None:
                    raise RuntimeError("hidden WebView page is not available")
                current_page.toHtml(lambda html, ctx=ctx: self._after_hidden_duty_trigger_html(ctx, html))
            except Exception as exc:
                if ctx.get("completed"):
                    return
                ctx["completed"] = True
                t = ctx.get("trigger") or {}
                self.logger.exception(
                    "Duty trigger finished with error: id=%s reason=%s",
                    t.get("id", ""),
                    exc,
                )
                self._cleanup_hidden_view(ctx)
                self._finish_trigger_without_html(t, "ERROR", reason=str(exc))

        def on_loaded(ok, ctx=context, zid=zabbix_id):
            if ctx.get("completed"):
                return
            t = ctx.get("trigger") or {}
            if not ok:
                ctx["completed"] = True
                self.logger.warning("Duty trigger hidden source load failed: id=%s", t.get("id", ""))
                self._cleanup_hidden_view(ctx)
                self._finish_trigger_without_html(t, "SOURCE_NOT_FOUND")
                return

            try:
                current_page = ctx.get("page")
                if current_page is None:
                    raise RuntimeError("hidden WebView page is not available")
                js = make_zabbix_login_js(
                    self.credentials.get(zid, {}).get("login", ""),
                    self.credentials.get(zid, {}).get("password", ""),
                )
                if js:
                    current_page.runJavaScript(js)
                self.logger.info(
                    "Duty trigger waiting before HTML read: id=%s display_name=%s delay_ms=%s",
                    t.get("id", ""),
                    t.get("display_name", ""),
                    DUTY_TRIGGER_HTML_READ_DELAY_MS,
                )
                ctx["read_timer"].timeout.connect(read_html)
                ctx["read_timer"].start(DUTY_TRIGGER_HTML_READ_DELAY_MS)
            except Exception as exc:
                if ctx.get("completed"):
                    return
                ctx["completed"] = True
                self.logger.exception(
                    "Duty trigger finished with error: id=%s reason=%s",
                    t.get("id", ""),
                    exc,
                )
                self._cleanup_hidden_view(ctx)
                self._finish_trigger_without_html(t, "ERROR", reason=str(exc))

        context["load_handler"] = on_loaded
        context["timeout_timer"].timeout.connect(on_timeout)
        self.logger.info(
            "Duty trigger hidden WebView loading source: id=%s display_name=%s has_cache_buster=%s timeout_ms=%s",
            trigger.get("id", ""),
            trigger.get("display_name", ""),
            "_oko_trigger_check_ts=" in source_url,
            DUTY_TRIGGER_HIDDEN_WEBVIEW_TIMEOUT_MS,
        )
        view.loadFinished.connect(on_loaded)
        context["timeout_timer"].start(DUTY_TRIGGER_HIDDEN_WEBVIEW_TIMEOUT_MS)
        view.load(QUrl(source_url))

    def _cleanup_hidden_view(self, context_or_view):
        context = context_or_view if isinstance(context_or_view, dict) else None
        view = context_or_view if context is None else context.get("view")
        trigger = (context or {}).get("trigger") or {}
        trigger_id = trigger.get("id", "")

        if context is not None and context.get("cleanup_started"):
            return
        if context is not None:
            context["cleanup_started"] = True

        self.logger.info("Duty trigger hidden WebView cleanup started: id=%s", trigger_id)

        if context is not None:
            for timer_name in ("timeout_timer", "read_timer"):
                timer = context.get(timer_name)
                if timer is not None:
                    try:
                        timer.stop()
                    except Exception:
                        pass
                    try:
                        timer.deleteLater()
                    except Exception:
                        pass

        def delete_objects(ctx=context, hidden_view=view, tid=trigger_id):
            load_handler = (ctx or {}).get("load_handler")
            safe_delete_web_view(
                hidden_view,
                logger=self.logger,
                context=f"Duty trigger hidden WebView id={tid}",
                load_handler=load_handler,
            )
            if hidden_view in self.hidden_trigger_views:
                self.hidden_trigger_views.remove(hidden_view)
            if ctx in self._hidden_trigger_contexts:
                self._hidden_trigger_contexts.remove(ctx)
            if ctx is not None:
                ctx["view"] = None
                ctx["page"] = None
                ctx["load_handler"] = None
                ctx["timeout_timer"] = None
                ctx["read_timer"] = None
            self.logger.info("Duty trigger hidden WebView cleanup finished: id=%s", tid)

        QTimer.singleShot(0, delete_objects)

    def _after_hidden_duty_trigger_html(self, context, html):
        if context.get("completed"):
            return
        context["completed"] = True
        trigger = dict(context.get("trigger") or {})
        trigger["_source_url"] = context.get("source_url", "")
        self._cleanup_hidden_view(context)
        try:
            self._after_duty_trigger_html(trigger, html)
        except Exception as exc:
            self.logger.exception(
                "Duty trigger finished with error: id=%s reason=%s",
                trigger.get("id", ""),
                exc,
            )
            self._finish_trigger_without_html(trigger, "ERROR", reason=str(exc))

    def _finish_trigger_without_html(self, trigger, status, reason=None):
        message = self._status_message(status, trigger=trigger)
        target_found = self._set_target_status(trigger, status, message)
        self._set_zabbix_graph_status_for_trigger(trigger, status if target_found else "TARGET_NOT_FOUND")
        if status == "TARGET_NOT_FOUND" or not target_found:
            final_status = "TARGET_NOT_FOUND"
        else:
            final_status = status
        self.duty_trigger_stats["errors"] += 1
        self._remember_duty_trigger_result(trigger, final_status, message, target_found=target_found)
        if reason:
            self.logger.warning(
                "Duty trigger finished without HTML: %s target_found=%s html_received=False reason=%s",
                self._build_trigger_result_log(trigger, {}, final_status),
                target_found,
                reason,
            )
        else:
            self.logger.warning(
                "Duty trigger finished without HTML: %s target_found=%s html_received=False",
                self._build_trigger_result_log(trigger, {}, final_status),
                target_found,
            )
        QTimer.singleShot(0, self._run_next_duty_trigger)

    def _after_duty_trigger_html(self, trigger, html):
        html = html or ""
        plain_text = re.sub(r"<[^>]+>", " ", html)
        plain_text = " ".join(plain_text.split())
        diagnostics = diagnose_metric_html(html, trigger.get("metric_title", ""))
        has_login_form = diagnostics.get("has_login_form", False)
        metric_title_present = diagnostics.get("metric_title_present", False)
        self.logger.info(
            "Duty trigger source HTML diagnostics: id=%s display_name=%s source_product=%s source_section=%s source_url_present=%s target_product=%s target_section=%s target_graph_title=%s html_received=%s html_length=%s plain_text_length=%s has_login_form=%s metric_title_present=%s",
            trigger.get("id", ""),
            trigger.get("display_name", ""),
            trigger.get("source_product", ""),
            trigger.get("source_section", ""),
            bool(trigger.get("_source_url", "") or html),
            trigger.get("target_product", ""),
            trigger.get("target_section", ""),
            trigger.get("target_graph_title", ""),
            bool(html.strip()),
            len(html),
            len(plain_text),
            has_login_form,
            metric_title_present,
        )
        self.logger.info(
            "Duty trigger parse diagnostics: id=%s tables_count=%s matched_table=%s rows_count=%s parseable_rows_count=%s timestamp_parse_errors=%s value_cells_missing=%s",
            trigger.get("id", ""),
            diagnostics.get("tables_count"),
            diagnostics.get("matched_table"),
            diagnostics.get("rows_count"),
            diagnostics.get("parseable_rows_count"),
            diagnostics.get("timestamp_parse_errors"),
            diagnostics.get("value_cells_missing"),
        )
        if not html.strip():
            result = {"status": "NO_DATA", "message": DUTY_TRIGGER_STATUS_MESSAGES["NO_DATA"], "no_data_reason": "html_empty"}
        elif has_login_form:
            result = {"status": "NO_DATA", "message": DUTY_TRIGGER_STATUS_MESSAGES["NO_DATA"], "no_data_reason": "login_page_detected"}
        else:
            trigger_settings = ensure_duty_triggers_defaults(self.config)
            result = evaluate_stagnation_trigger(
                html,
                metric_title=trigger.get("metric_title", ""),
                mode=trigger.get("mode", "mode_1"),
                ok_text=trigger.get("ok_text", DUTY_TRIGGER_STATUS_MESSAGES["OK"]),
                alert_template=trigger.get("alert_template", "С {from_time} по {to_time} отсутствуют сработки."),
                day_start=trigger_settings.get("day_start", "06:00"),
                day_end=trigger_settings.get("day_end", "00:00"),
                day_threshold_minutes=int(trigger_settings.get("day_threshold_minutes", 90)),
                night_threshold_minutes=int(trigger_settings.get("night_threshold_minutes", 180)),
                mode1_night_silence_start=trigger_settings.get("mode1_night_silence_start", "01:00"),
                mode1_night_silence_end=trigger_settings.get("mode1_night_silence_end", "05:30"),
            )

        status = str(result.get("status", "NO_DATA") or "NO_DATA").upper()
        if status == "NO_DATA":
            if not result.get("no_data_reason"):
                result["no_data_reason"] = diagnostics.get("no_data_reason", "unknown")
            self.logger.warning(
                "Duty trigger NO_DATA reason=%s id=%s display_name=%s",
                result.get("no_data_reason"),
                trigger.get("id", ""),
                trigger.get("display_name", ""),
            )
            result["message"] = DUTY_TRIGGER_STATUS_MESSAGES["NO_DATA"]
        elif status == "PARSE_ERROR":
            result["message"] = DUTY_TRIGGER_STATUS_MESSAGES["PARSE_ERROR"]
        message = self._status_message(status, result=result, trigger=trigger)
        target_found = self._set_target_status(trigger, status, message)
        self._set_zabbix_graph_status_for_trigger(trigger, status if target_found else "TARGET_NOT_FOUND")

        if status == "OK":
            self.duty_trigger_stats["ok"] += 1
        elif status == "ALERT":
            self.duty_trigger_stats["alert"] += 1
        else:
            self.duty_trigger_stats["errors"] += 1
        if not target_found:
            self.duty_trigger_stats["errors"] += 1

        self._remember_duty_trigger_result(trigger, status if target_found else "TARGET_NOT_FOUND", message, result=result, target_found=target_found)

        self.logger.info(
            "Duty trigger finished: %s target_found=%s html_received=%s",
            self._build_trigger_result_log(trigger, result, status if target_found else "TARGET_NOT_FOUND"),
            target_found,
            bool(html.strip()),
        )
        QTimer.singleShot(0, self._run_next_duty_trigger)

    def start_check(self):
        if self.skip_timer.isActive():
            self.skip_timer.stop()

        self.load_check_graphs()
        if not self.check_graphs:
            QMessageBox.warning(
                self,
                "Режим дежурства",
                "Не выбраны графики для проверки. Настройте их в разделе «Настройки дежурки»."
            )
            return False

        self.open_graph_check_overlay()
        self.mark_check_started()
        self.status_label.setText("Идёт проверка графиков в overlay-панели.")
        return True

    def open_graph_check_overlay(self, run_triggers_after_open=False):
        if self.graph_check_overlay is not None:
            try:
                self.graph_check_overlay.close()
            except Exception:
                pass

        self.graph_check_overlay = GraphCheckOverlayDialog(
            graphs=self.check_graphs,
            config=self.config,
            profiles=self.profiles,
            credentials=self.credentials,
            parent=self,
        )
        self.graph_check_overlay.confirmed.connect(self._finish_zabbix_graphs_from_overlay)
        self.graph_check_overlay.finished.connect(lambda _result: setattr(self, "graph_check_overlay", None))
        self.graph_check_overlay.destroyed.connect(lambda: setattr(self, "graph_check_overlay", None))
        self.cards = self.graph_check_overlay.cards
        self.graph_check_overlay.show()
        self.graph_check_overlay.raise_()
        self.graph_check_overlay.activateWindow()
        if run_triggers_after_open:
            self.graph_trigger_check_started_for_overlay = True
            QTimer.singleShot(1500, lambda: self.run_duty_triggers_check(part_of_duty_flow=True))



    def _finish_zabbix_graphs_from_overlay(self):
        if self.duty_trigger_running or self._hidden_trigger_contexts or self.hidden_trigger_views:
            QMessageBox.warning(self, "Проверка графиков", "Проверка триггеров графиков ещё выполняется.")
            return
        if self.duty_trigger_results:
            self._finalize_zabbix_graph_statuses_from_trigger_stats()
        else:
            self.duty_zabbix_graphs_status = "Проверено"
        final_statuses = {}
        keep_status_fragments = ("ошиб", "нет данных", "таймаут", "вним")
        for item in self.check_graphs:
            graph_id = item.get("id")
            current_status = str(self.duty_zabbix_graph_statuses.get(graph_id, "") or "")
            if any(fragment in current_status.casefold() for fragment in keep_status_fragments):
                final_statuses[graph_id] = current_status
            else:
                final_statuses[graph_id] = "Проверено"
        self.duty_zabbix_graph_statuses = final_statuses
        self.duty_zabbix_status = "требуется внимание" if self.duty_zabbix_graphs_status == "Требуется внимание" else ("ошибка" if "ошиб" in self.duty_zabbix_graphs_status.casefold() else "выполнено")
        self.update_dashboard_summary()
        if self.graph_check_overlay is not None:
            self.graph_check_overlay.close()
        if self.duty_flow_running:
            self.finish_duty_check_flow()
        else:
            self.open_graph_check_note()

    def _bound_task_details(self):
        settings = self.get_settings()
        ticket_number = (settings.get("duty_zabbix_task_number") or settings.get("current_ticket_number", "")).strip()
        ticket_id = settings.get("current_ticket_id", "").strip()
        ticket_url = settings.get("current_ticket_url", "").strip()

        if not ticket_id and ticket_url:
            match = re.search(r"[?;]TicketID=([^;&?#]+)", ticket_url)
            if match:
                ticket_id = match.group(1).strip()
                settings["current_ticket_id"] = ticket_id
                save_config(self.config)

        return ticket_number, ticket_id, ticket_url

    def build_graph_check_note_text(self):
        template = get_otrs_graph_check_template(self.config)
        context = self._build_template_context()
        note_text = render_template(template.get("text", ""), context)
        problems_block = format_zabbix_problems_note_block(self.selected_zabbix_problems_for_note)
        if problems_block:
            note_text = (note_text.rstrip() + "\n\n" + problems_block).strip()
        return note_text

    def open_graph_check_note(self):
        self.logger.info("Duty graph check note requested")
        ticket_number, ticket_id, ticket_url = self._bound_task_details()

        if not any([ticket_number, ticket_id, ticket_url]):
            self.logger.info("Duty graph check note skipped: no bound task")
            QMessageBox.warning(
                self,
                "Задача дежурства",
                "Задача дежурства не привязана. Включите режим дежурства и создайте или привяжите задачу."
            )
            return

        if not ticket_id:
            otrs = self.get_settings().setdefault("otrs", {})
            note_template = otrs.get("note_url_template", "").strip()
            if "{ticket_number}" not in note_template:
                self.logger.info("Duty graph check note skipped: no bound task")
                QMessageBox.warning(
                    self,
                    "Задача дежурства",
                    "У привязанной задачи не найден TicketID. Откройте или привяжите задачу ОТРС с TicketID."
                )
                return

        note_text = self.build_graph_check_note_text()
        dialog = OtrsNoteDialog(
            config=self.config,
            note_text=note_text,
            parent=self,
            on_saved_callback=self._after_graph_check_note_saved,
            saved_log_message="Duty graph check note saved",
        )
        self.logger.info(
            "Duty graph check note opened: ticket_number=%s ticket_id=%s",
            ticket_number or "",
            ticket_id or "",
        )
        dialog.exec()

    def _after_graph_check_note_saved(self):
        if self.graph_check_overlay is not None:
            self.graph_check_overlay.close()

    def success_check(self):
        if self.skip_timer.isActive():
            self.skip_timer.stop()

        text = "Показатели в пределах нормы. Отклонений не обнаружено."

        self.mark_check_started()
        self.status_label.setText("Проверка выполнена: показатели в пределах нормы.")

        dialog = OtrsNoteDialog(
            config=self.config,
            note_text=text,
            parent=self
        )
        dialog.exec()

    def problem_check(self):
        self.load_check_graphs()

        if not self.check_graphs:
            QMessageBox.warning(self, "Есть проблема", "Нет выбранных графиков для проверки.")
            return

        graphs = [item["graph"] for item in self.check_graphs]
        dialog = ProblemTemplateDialog(graphs, config=self.config, parent=self)
        dialog.exec()
