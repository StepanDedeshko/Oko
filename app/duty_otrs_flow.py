"""Dedicated OTRS duty task creation and binding flow."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import parse_qs, urlparse


from app.config import ensure_duty_mode_defaults, save_config
from app.logger import get_logger

TASK_ZABBIX = "zabbix"
TASK_SERVICES = "service_checks"
DEFAULT_CREATE_URL = "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentNewTicketForm;NewTicketFormID=6"
DEFAULT_NOTE_URL_BASE = "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketNote;TicketID="


@dataclass(frozen=True)
class OtrsTaskBinding:
    task_type: str
    ticket_id: str
    ticket_number: str
    ticket_url: str

    def as_dict(self) -> dict:
        return {
            "task_type": self.task_type,
            "ticket_id": self.ticket_id,
            "ticket_number": self.ticket_number,
            "ticket_url": self.ticket_url,
            "system": "otrs",
            "id": self.ticket_id,
            "number": self.ticket_number,
            "url": self.ticket_url,
        }


def normalize_task_type(task_type: str) -> str:
    return TASK_SERVICES if task_type == TASK_SERVICES else TASK_ZABBIX


def extract_ticket_id_from_url(url: str) -> str:
    raw = str(url or "")
    parsed = urlparse(raw)
    query = parsed.query or ""
    if parsed.params:
        query = f"{query}&{parsed.params}" if query else parsed.params
    params = parse_qs(query.replace(";", "&"), keep_blank_values=True)
    for key, values in params.items():
        if key.casefold() == "ticketid" and values:
            return str(values[0]).strip()
    match = re.search(r"[?;&]TicketID=([^;&?#]+)", raw, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def parse_otrs_ticket_number(*texts: str) -> str:
    patterns = [
        r"Заявка\s*#\s*(\d{5,})",
        r"Заявка\s*№\s*(\d{5,})",
        r"(?:Добавить\s+заметку\s+к\s+)?Заявка\s*#\s*(\d{5,})",
        r"\b(\d{5,})\s*-\s*Подробно\s*-\s*Заявки\s*-\s*Service\s*Desk\b",
    ]
    for text in texts:
        source = re.sub(r"\s+", " ", str(text or "")).strip()
        for pattern in patterns:
            match = re.search(pattern, source, re.IGNORECASE)
            if match:
                return match.group(1).strip()
    return ""


def ticket_number_read_js() -> str:
    return r"""
    (function() {
        function clean(text) { return String(text || '').replace(/\s+/g, ' ').trim(); }
        const selectors = ['h1', '.Header h1', '.Headline h1'];
        const candidates = [];
        for (const selector of selectors) {
            for (const el of Array.from(document.querySelectorAll(selector))) {
                candidates.push(clean(el.innerText || el.textContent || ''));
            }
        }
        candidates.push(clean(document.title || ''));
        candidates.push(clean(document.body ? (document.body.innerText || document.body.textContent || '') : ''));
        const patterns = [
            /Заявка\s*#\s*(\d{5,})/i,
            /Заявка\s*№\s*(\d{5,})/i,
            /(?:Добавить\s+заметку\s+к\s+)?Заявка\s*#\s*(\d{5,})/i,
            /\b(\d{5,})\s*-\s*Подробно\s*-\s*Заявки\s*-\s*Service\s*Desk\b/i
        ];
        for (const text of candidates) {
            for (const pattern of patterns) {
                const match = text.match(pattern);
                if (match && match[1]) {
                    return {ticketNumber: String(match[1]).trim(), source: text.slice(0, 800)};
                }
            }
        }
        return {ticketNumber: '', source: candidates.join(' | ').slice(0, 1200)};
    })();
    """


def save_otrs_task_binding(settings: dict, binding: OtrsTaskBinding | dict) -> dict:
    data = binding.as_dict() if isinstance(binding, OtrsTaskBinding) else dict(binding or {})
    task_type = normalize_task_type(data.get("task_type", TASK_ZABBIX))
    ticket_id = str(data.get("ticket_id") or data.get("id") or "").strip()
    ticket_number = str(data.get("ticket_number") or data.get("number") or "").strip()
    ticket_url = str(data.get("ticket_url") or data.get("url") or "").strip()

    if task_type == TASK_SERVICES:
        settings["duty_service_checks_task_id"] = ticket_id
        settings["duty_service_checks_task_url"] = ticket_url
        settings["duty_service_checks_task_number"] = ticket_number
        settings["duty_service_checks_task_system"] = "otrs"
    else:
        settings["current_ticket_id"] = ticket_id
        settings["current_ticket_url"] = ticket_url
        settings["current_ticket_number"] = ticket_number
        settings["duty_zabbix_task_id"] = ticket_id
        settings["duty_zabbix_task_url"] = ticket_url
        settings["duty_zabbix_task_number"] = ticket_number
        settings["duty_zabbix_task_system"] = "otrs"
    return settings


def visible_task_status(settings: dict, task_type: str, reading_number: bool = False) -> str:
    settings = settings or {}
    if normalize_task_type(task_type) == TASK_SERVICES:
        number = str(settings.get("duty_service_checks_task_number", "") or "").strip()
        ticket_id = str(settings.get("duty_service_checks_task_id", "") or "").strip()
    else:
        number = str(settings.get("duty_zabbix_task_number") or settings.get("current_ticket_number") or "").strip()
        ticket_id = str(settings.get("duty_zabbix_task_id") or settings.get("current_ticket_id") or "").strip()
    if number:
        return f"№{number}"
    if ticket_id and reading_number:
        return "ищу номер заявки..."
    return "не привязана"


def make_note_url_by_ticket_id(config: dict, ticket_id: str) -> str:
    settings = ensure_duty_mode_defaults(config)
    otrs = settings.setdefault("otrs", {})
    base = str(otrs.get("note_url_base") or DEFAULT_NOTE_URL_BASE).strip() or DEFAULT_NOTE_URL_BASE
    return base + str(ticket_id or "").strip()


def open_otrs_task_flow(config: dict, parent=None, task_type: str = TASK_ZABBIX) -> dict:
    dialog = OtrsCreateTaskDialog(config, parent=parent, task_type=task_type)
    dialog.exec()
    return dialog.binding.as_dict() if dialog.binding else {}



def _build_otrs_create_task_dialog_class():
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtGui import QColor
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

    from app.credentials import load_otrs_credentials
    from app.webengine_lifecycle import register_web_view, run_javascript_if_alive, safe_delete_web_view

    class _OtrsCreateTaskDialog(QDialog):
        def __init__(self, config, parent=None, task_type: str = TASK_ZABBIX):
            super().__init__(parent)
            self.config = config
            self.task_type = normalize_task_type(task_type)
            self.logger = get_logger()
            self.binding: OtrsTaskBinding | None = None
            self.pending_ticket_id = ""
            self.pending_ticket_url = ""
            self.detect_attempt = 0
            self.max_detect_attempts = 8
            self._cleaned_up = False

            self.setWindowTitle("Создать задачу проверки сервисов" if self.task_type == TASK_SERVICES else "Создать задачу Zabbix / графиков")
            self.resize(1280, 850)
            root = QVBoxLayout(self)
            title = QLabel(self.windowTitle())
            title.setObjectName("PageTitle")
            root.addWidget(title)
            hint = QLabel("Создай задачу ОТРС. После перехода в созданную задачу Око поймает TicketID и прочитает видимый номер заявки.")
            hint.setWordWrap(True)
            root.addWidget(hint)
            row = QHBoxLayout()
            self.url_input = QLineEdit()
            self.url_input.setText(self.get_otrs_settings().get("create_url", DEFAULT_CREATE_URL))
            open_button = QPushButton("Открыть страницу создания")
            open_button.clicked.connect(self.load_create_page)
            row.addWidget(QLabel("URL создания:"))
            row.addWidget(self.url_input, stretch=1)
            row.addWidget(open_button)
            root.addLayout(row)
            self.status_label = QLabel("Ожидание.")
            self.status_label.setWordWrap(True)
            root.addWidget(self.status_label)
            self.view = register_web_view(QWebEngineView())
            self.page = QWebEnginePage(self.view)
            try:
                self.page.setBackgroundColor(QColor("#0b0b0b"))
            except Exception:
                pass
            self.view.setPage(self.page)
            self.view.loadFinished.connect(self.on_loaded)
            self.view.urlChanged.connect(self.on_url_changed)
            root.addWidget(self.view, stretch=1)
            self.load_create_page()

        def get_settings(self):
            return ensure_duty_mode_defaults(self.config)

        def get_otrs_settings(self):
            settings = self.get_settings()
            otrs = settings.setdefault("otrs", {})
            otrs.setdefault("create_url", DEFAULT_CREATE_URL)
            otrs.setdefault("note_url_base", DEFAULT_NOTE_URL_BASE)
            otrs.setdefault("note_url_template", "")
            return otrs

        def load_create_page(self):
            url = self.url_input.text().strip()
            if not url:
                QMessageBox.warning(self, "ОТРС", "URL создания задачи не указан.")
                return
            self.get_otrs_settings()["create_url"] = url
            save_config(self.config)
            self.status_label.setText("Открываю страницу создания задачи ОТРС...")
            self.view.load(QUrl(url))

        def inject_otrs_login_if_needed(self):
            settings = self.get_settings()
            if not settings.get("otrs_login_enabled", False):
                return
            creds = load_otrs_credentials(self.config)
            login = str(creds.get("login", "") or "")
            password = str(creds.get("password", "") or "")
            if not login or not password:
                return
            auto_submit = bool(settings.get("otrs_auto_submit_login", False))
            def js_string(value):
                return str(value).replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
            js = f"""
            (function() {{
                const user = document.querySelector('#User');
                const password = document.querySelector('#Password');
                const button = document.querySelector('#LoginButton');
                if (!user || !password) return 'no-login-form';
                user.value = '{js_string(login)}'; user.dispatchEvent(new Event('input', {{bubbles: true}})); user.dispatchEvent(new Event('change', {{bubbles: true}}));
                password.value = '{js_string(password)}'; password.dispatchEvent(new Event('input', {{bubbles: true}})); password.dispatchEvent(new Event('change', {{bubbles: true}}));
                if ({str(auto_submit).lower()} && button) {{ setTimeout(() => button.click(), 500); return 'filled-and-submitted'; }}
                return 'filled';
            }})();
            """
            run_javascript_if_alive(self.view, js)

        def on_loaded(self, ok):
            if ok:
                self.inject_otrs_login_if_needed()
                ticket_id = extract_ticket_id_from_url(self.view.url().toString())
                if ticket_id:
                    self._start_number_detection(ticket_id, self.view.url().toString())
                else:
                    self.status_label.setText("Страница загружена. Создай задачу ОТРС — после перехода начну искать номер заявки.")
            else:
                self.status_label.setText("Страница не загрузилась.")

        def on_url_changed(self, qurl):
            url = qurl.toString()
            ticket_id = extract_ticket_id_from_url(url)
            if ticket_id and ticket_id != self.pending_ticket_id:
                self._start_number_detection(ticket_id, url)

        def _start_number_detection(self, ticket_id: str, ticket_url: str):
            self.pending_ticket_id = ticket_id
            self.pending_ticket_url = ticket_url
            self.detect_attempt = 0
            self.status_label.setText("ищу номер заявки...")
            QTimer.singleShot(1200, self.try_detect_ticket_number)

        def try_detect_ticket_number(self):
            self.detect_attempt += 1
            run_javascript_if_alive(self.view, ticket_number_read_js(), self.after_detect_ticket_number)

        def after_detect_ticket_number(self, result):
            number = ""
            if isinstance(result, dict):
                number = str(result.get("ticketNumber", "") or "").strip()
            if not number and self.detect_attempt < self.max_detect_attempts:
                self.status_label.setText("ищу номер заявки...")
                QTimer.singleShot(2000, self.try_detect_ticket_number)
                return
            if not number:
                self.status_label.setText("TicketID найден, но номер заявки не прочитан. Задача не привязана как видимая.")
                return
            binding = OtrsTaskBinding(self.task_type, self.pending_ticket_id, number, self.pending_ticket_url or self.view.url().toString())
            save_otrs_task_binding(self.get_settings(), binding)
            save_config(self.config)
            self.binding = binding
            self.status_label.setText(f"Задача привязана: №{number}")
            self.logger.info("Duty OTRS task binding saved: task_type=%s ticket_id=%s ticket_number=%s", self.task_type, self.pending_ticket_id, number)
            QMessageBox.information(self, "ОТРС", f"Задача привязана: №{number}")
            self.accept()

        def cleanup(self):
            if self._cleaned_up:
                return
            self._cleaned_up = True
            view = getattr(self, "view", None)
            self.view = None
            self.page = None
            safe_delete_web_view(view, logger=self.logger, context="OtrsCreateTaskDialog", load_handler=self.on_loaded)

        def closeEvent(self, event):
            self.cleanup()
            super().closeEvent(event)

    return _OtrsCreateTaskDialog


class OtrsCreateTaskDialog:
    def __new__(cls, *args, **kwargs):
        dialog_class = _build_otrs_create_task_dialog_class()
        return dialog_class(*args, **kwargs)
