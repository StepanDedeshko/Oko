from datetime import datetime, timedelta, timezone
import re

from PySide6.QtCore import QTimer, QUrl, QUrlQuery, Qt
from PySide6.QtGui import QDesktopServices, QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
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
from app.config import ensure_duty_triggers_defaults, save_config
from app.duty_settings import DutyModeSettingsWidget
from app.duty_triggers import evaluate_stagnation_trigger
from app.logger import get_logger
from app.time_range import apply_time_range_to_url


MSK = timezone(timedelta(hours=3))


DUTY_TRIGGER_STATUS_MESSAGES = {
    "OK": "Сработки поступают все в пределах нормы",
    "ALERT": "Обнаружено отсутствие сработок",
    "NO_DATA": "Нет данных для проверки сработок",
    "PARSE_ERROR": "Не удалось прочитать данные проверки сработок",
    "SOURCE_NOT_FOUND": "Источник данных для проверки не найден",
    "TARGET_NOT_FOUND": "Целевой график для проверки не найден",
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

        self.setWindowTitle("Дежурное уведомление")
        self.setWindowModality(Qt.ApplicationModal)
        self.resize(540, 190)

        root = QVBoxLayout(self)

        title = QLabel("Дежурное уведомление")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        message = QLabel(text)
        message.setWordWrap(True)
        message.setStyleSheet("font-size: 16px; padding: 8px;")
        root.addWidget(message)

        row = QHBoxLayout()

        check_button = QPushButton("Проверить")
        check_button.clicked.connect(self.choose_check)

        skip_button = QPushButton("Пропустить")
        skip_button.clicked.connect(self.choose_skip)

        row.addWidget(check_button)
        row.addWidget(skip_button)
        row.addStretch()

        root.addLayout(row)

    def choose_check(self):
        self.result_action = "check"
        self.accept()

    def choose_skip(self):
        self.result_action = "skip"
        self.accept()


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

    def __init__(self, config, parent=None):
        super().__init__(parent)

        self.config = config
        self.setWindowTitle("Привязать задачу дежурства")
        self.resize(1000, 720)

        root = QVBoxLayout(self)

        title = QLabel("Привязать уже созданную задачу")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        hint = QLabel(
            "Вставь полную ссылку на задачу ОТРС. "
            "Приложение сохранит TicketID и попробует прочитать номер заявки со страницы."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        row = QHBoxLayout()

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://itsm.stdpr.ru/itsm/index.pl?...TicketID=...")

        open_button = QPushButton("Открыть")
        open_button.clicked.connect(self.open_task_url)

        attach_button = QPushButton("Прикрепить")
        attach_button.clicked.connect(self.attach_task)

        manual_check_button = QPushButton("Проверить заголовок ещё раз")
        manual_check_button.clicked.connect(self.start_delayed_detect)

        row.addWidget(QLabel("Ссылка на задачу:"))
        row.addWidget(self.url_input, stretch=1)
        row.addWidget(open_button)
        row.addWidget(attach_button)
        row.addWidget(manual_check_button)

        root.addLayout(row)

        self.status_label = QLabel("Ожидание ссылки.")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.pending_ticket_id = ""
        self.pending_ticket_url = ""
        self.detect_attempt = 0
        self.max_detect_attempts = 8

        self.view = QWebEngineView()
        self.view.setStyleSheet("background-color: #0b0b0b; border: 0;")

        self.page = QWebEnginePage(self.view)
        try:
            self.page.setBackgroundColor(QColor("#0b0b0b"))
        except Exception:
            pass

        self.view.setPage(self.page)
        self.view.loadFinished.connect(self.on_loaded)

        root.addWidget(self.view, stretch=1)

    def get_settings(self):
        settings = self.config.setdefault("duty_mode", {})
        settings.setdefault("current_ticket_number", "")
        settings.setdefault("current_ticket_id", "")
        settings.setdefault("current_ticket_url", "")
        settings.setdefault("expected_ticket_subject", "Проверка Zabbix (Важных IT-сервисов)")
        return settings

    def inject_otrs_login_if_needed(self):
        settings = self.config.setdefault("duty_mode", {})

        if not settings.get("otrs_login_enabled", False):
            return

        login = str(settings.get("otrs_login", "") or "")
        password = str(settings.get("otrs_password", "") or "")
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
        url = self.url_input.text().strip()

        if not url:
            QMessageBox.warning(self, "Открыть задачу", "Вставь ссылку на задачу.")
            return

        ticket_id = self.extract_ticket_id_from_url(url)
        if ticket_id:
            self.pending_ticket_id = ticket_id
            self.pending_ticket_url = url

        self.status_label.setText("Открываю страницу задачи. После загрузки нажми «Прикрепить».")
        self.view.load(QUrl(url))

    def attach_task(self):
        """
        Привязка теперь НЕ перезагружает страницу.
        Она проверяет текущую активную страницу во встроенном браузере.
        """

        current_url = self.view.url().toString().strip()
        input_url = self.url_input.text().strip()

        # Приоритет — текущая открытая страница. Если она пустая, берём поле ссылки.
        url = current_url if current_url and current_url != "about:blank" else input_url

        if not url:
            QMessageBox.warning(
                self,
                "Привязка задачи",
                "Сначала вставь ссылку и нажми «Открыть», затем нажми «Прикрепить»."
            )
            return

        ticket_id = self.extract_ticket_id_from_url(url)

        if not ticket_id:
            QMessageBox.warning(
                self,
                "Привязка задачи",
                "В текущей открытой странице не найден TicketID=...\n\n"
                "Сначала открой ссылку на задачу кнопкой «Открыть»."
            )
            return

        self.pending_ticket_id = ticket_id
        self.pending_ticket_url = url
        self.url_input.setText(url)

        self.status_label.setText(
            f"Проверяю активную страницу. TicketID={ticket_id}. Страница НЕ перезагружается..."
        )

        self.start_delayed_detect()

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
            self.status_label.setText(
                f"Страница открыта. TicketID={ticket_id}. Нажми «Прикрепить», чтобы проверить заголовок и привязать задачу."
            )
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
                "Не могу начать проверку: на активной странице не найден TicketID. "
                "Сначала открой задачу кнопкой «Открыть»."
            )
            return

        self.pending_ticket_id = ticket_id
        self.pending_ticket_url = current_url or self.pending_ticket_url

        self.detect_attempt = 0
        self.status_label.setText("Жду 3 секунды и читаю заголовок активной страницы...")
        QTimer.singleShot(3000, self.detect_task_number_from_page)


    def normalize_text(self, text):
        return re.sub(r"\s+", " ", str(text or "")).strip()

    def subject_matches(self, subject):
        expected = self.get_settings().get(
            "expected_ticket_subject",
            "Проверка Zabbix (Важных IT-сервисов)"
        )

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
            expected = self.get_settings().get(
                "expected_ticket_subject",
                "Проверка Zabbix (Важных IT-сервисов)"
            )
            self.status_label.setText(
                "Номер заявки прочитан, но тема не совпадает с ожидаемой.\n\n"
                f"Найдена задача: Заявка#{number}\n"
                f"Тема: {subject}\n"
                f"Ожидалось: {expected}\n"
                f"Источник: {source_type}, селектор: {selector}\n\n"
                "Задача НЕ привязана."
            )
            QMessageBox.warning(
                self,
                "Проверь задачу",
                "Похоже, открыта не та задача.\n\n"
                f"Найдена: Заявка#{number}\n"
                f"Тема: {subject}\n\n"
                f"Ожидалось: {expected}\n\n"
                "Задача не привязана к дежурству."
            )
            return

        settings = self.get_settings()
        settings["current_ticket_number"] = number
        settings["current_ticket_id"] = ticket_id
        settings["current_ticket_url"] = ticket_url
        save_config(self.config)

        self.status_label.setText(
            f"Задача привязана: Заявка#{number}, TicketID={ticket_id}. Закрываю окно..."
        )
        self.accept()



class OtrsCreateTaskDialog(QDialog):
    """
    Простое окно создания базовой задачи ОТРС без автозаполнения.

    Пользователь вручную создаёт задачу в ОТРС, затем вводит номер задачи
    или пробует найти номер на странице.
    """

    def __init__(self, config, parent=None):
        super().__init__(parent)

        self.config = config

        self.setWindowTitle("Базовая задача дежурства ОТРС")
        self.resize(1280, 850)

        root = QVBoxLayout(self)

        title = QLabel("Базовая задача дежурства ОТРС")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        hint = QLabel(
            "Создай задачу в ОТРС вручную. После создания укажи номер задачи ниже. "
            "Приложение привяжет дежурство к этому номеру и будет использовать его для заметок."
        )
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
        self.ticket_number_input.setText(self.get_settings().get("current_ticket_number", ""))
        self.ticket_number_input.setPlaceholderText("Например: 202605261234567")

        find_number_button = QPushButton("Попробовать найти номер на странице")
        find_number_button.clicked.connect(self.try_detect_ticket_number)

        save_number_button = QPushButton("Привязать номер задачи")
        save_number_button.clicked.connect(self.save_ticket_number)

        task_row.addWidget(QLabel("Номер задачи:"))
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

        self.view = QWebEngineView()
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

    def get_settings(self):
        settings = self.config.setdefault("duty_mode", {})
        settings.setdefault("current_ticket_number", "")
        settings.setdefault("current_ticket_id", "")
        settings.setdefault("current_ticket_url", "")
        return settings

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

        login = str(settings.get("otrs_login", "") or "")
        password = str(settings.get("otrs_password", "") or "")
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

        if ticket_id:
            settings["current_ticket_id"] = ticket_id

        if ticket_url:
            settings["current_ticket_url"] = ticket_url

        if ticket_number:
            settings["current_ticket_number"] = ticket_number

        save_config(self.config)

        if show_message:
            parts = []
            if ticket_number:
                parts.append(f"№{ticket_number}")
            if ticket_id:
                parts.append(f"TicketID={ticket_id}")

            QMessageBox.information(
                self,
                "Задача дежурства",
                "Дежурство привязано к задаче: " + ", ".join(parts)
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

    def __init__(self, config, note_text, parent=None):
        super().__init__(parent)

        self.config = config
        self.note_text = note_text

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
        self.url_input.setText(self.build_note_url())

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

        self.view = QWebEngineView()
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

        login = str(settings.get("otrs_login", "") or "")
        password = str(settings.get("otrs_password", "") or "")
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
        if clicked:
            try:
                self.send_watch_timer.stop()
            except Exception:
                pass

            # Даём ОТРС время отправить форму и закрываем окно.
            QTimer.singleShot(1800, self.close)

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

        task_number = self.config.get("duty_mode", {}).get("current_ticket_number", "").strip()

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

        self.setObjectName("GraphCard")
        self.setMinimumHeight(430)
        self.setMinimumWidth(0)
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        title = QLabel(graph_config.get("title", "График"))
        title.setObjectName("PageTitle")
        title.setWordWrap(True)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        open_button = QPushButton("Открыть в Zabbix")
        open_button.clicked.connect(self.open_external)
        open_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.view = QWebEngineView()
        self.view.setMinimumWidth(0)
        self.view.setMinimumHeight(360)
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.view.setZoomFactor(0.85)
        self.view.setStyleSheet("background-color: #0b0b0b; border: 0;")

        self.page = QWebEnginePage(profile, self.view)
        try:
            self.page.setBackgroundColor(QColor("#0b0b0b"))
        except Exception:
            pass

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
        root.addWidget(self.view, stretch=1)
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
        self.view.load(QUrl(self.build_url()))

    def on_loaded(self, ok):
        if not ok:
            return

        js = make_zabbix_login_js(
            self.credentials.get("login", ""),
            self.credentials.get("password", "")
        )
        if js:
            self.view.page().runJavaScript(js)

    def open_external(self):
        url = self.build_open_url()
        if url:
            QDesktopServices.openUrl(QUrl(url))


class DutyModeWidget(QWidget):
    def __init__(self, config, profiles, credentials=None, graph_card_finder=None, source_view_finder=None, parent=None):
        super().__init__(parent)

        self.config = config
        self.profiles = profiles
        self.credentials = credentials or {}
        self.graph_card_finder = graph_card_finder
        self.source_view_finder = source_view_finder
        self.logger = get_logger()
        self.hidden_trigger_views = []
        self.duty_trigger_queue = []
        self.duty_trigger_running = False
        self.duty_trigger_stats = {"total": 0, "ok": 0, "alert": 0, "errors": 0}
        self.check_graphs = []
        self.cards = []

        self.audio_player = None
        self.audio_output = None

        self.last_hour_key = None
        self.skip_timer = QTimer(self)
        self.skip_timer.setSingleShot(True)
        self.skip_timer.timeout.connect(self.show_skip_reminder)

        root = QVBoxLayout(self)

        header = QHBoxLayout()

        title = QLabel("Режим дежурства")
        title.setObjectName("PageTitle")

        self.msk_time_label = QLabel("")
        self.msk_time_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.enable_button = QPushButton("")
        self.enable_button.clicked.connect(self.toggle_enabled)

        create_duty_task_button = QPushButton("Создать задачу дежурства")
        create_duty_task_button.clicked.connect(self.open_base_duty_task)

        attach_task_button = QPushButton("Привязать задачу")
        attach_task_button.clicked.connect(self.attach_existing_task)

        settings_button = QPushButton("Настроить режим дежурства")
        settings_button.clicked.connect(self.open_settings)

        notify_now_button = QPushButton("Показать уведомление сейчас")
        notify_now_button.clicked.connect(lambda: self.show_notification("Нужно произвести проверку графиков."))

        check_triggers_button = QPushButton("Проверить триггеры")
        check_triggers_button.clicked.connect(self.run_duty_triggers_check)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.msk_time_label)
        header.addWidget(self.enable_button)
        header.addWidget(create_duty_task_button)
        header.addWidget(attach_task_button)
        header.addWidget(settings_button)
        header.addWidget(check_triggers_button)
        header.addWidget(notify_now_button)

        root.addLayout(header)

        self.status_label = QLabel("Ожидание следующей проверки. При заступлении на дежурство создай базовую задачу ОТРС.")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.current_task_label = QLabel("")
        self.current_task_label.setWordWrap(True)
        root.addWidget(self.current_task_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self.scroll, stretch=1)

        self.content = QWidget()
        self.content.setMinimumWidth(0)
        self.content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.cards_layout = QVBoxLayout(self.content)
        self.cards_layout.setContentsMargins(6, 6, 6, 6)
        self.cards_layout.setSpacing(10)
        self.scroll.setWidget(self.content)

        bottom = QHBoxLayout()

        success_button = QPushButton("Проверка выполнена")
        success_button.clicked.connect(self.success_check)

        bottom.addWidget(success_button)
        bottom.addStretch()

        root.addLayout(bottom)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.tick)
        self.clock_timer.start(1000)

        self.update_enable_button()
        self.update_task_label()
        self.tick()
        self.load_check_graphs()
        self.render_empty_hint()

    def get_settings(self):
        settings = self.config.setdefault("duty_mode", {})
        settings.setdefault("enabled", False)
        settings.setdefault("hourly_notification", True)
        settings.setdefault("skip_minutes", 5)
        settings.setdefault("sound_path", "")
        settings.setdefault("current_ticket_number", "")
        settings.setdefault("current_ticket_id", "")
        settings.setdefault("current_ticket_url", "")
        settings.setdefault("expected_ticket_subject", "Проверка Zabbix (Важных IT-сервисов)")
        settings.setdefault("otrs_login_enabled", False)
        settings.setdefault("otrs_login", "")
        settings.setdefault("otrs_password", "")
        settings.setdefault("otrs_auto_submit_login", False)
        settings.setdefault("graph_ids", [])
        settings.setdefault("otrs", {})
        settings["otrs"].setdefault("create_url", "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentNewTicketForm;NewTicketFormID=6")
        settings["otrs"].setdefault("note_url_base", "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketNote;TicketID=")
        settings["otrs"].setdefault("note_url_template", "")
        return settings

    def update_enable_button(self):
        enabled = self.get_settings().get("enabled", False)
        self.enable_button.setText("Дежурство: ВКЛ" if enabled else "Дежурство: ВЫКЛ")

    def update_task_label(self):
        settings = self.get_settings()
        number = settings.get("current_ticket_number", "").strip()
        ticket_id = settings.get("current_ticket_id", "").strip()

        if number or ticket_id:
            parts = []
            if number:
                parts.append(f"№{number}")
            if ticket_id:
                parts.append(f"TicketID={ticket_id}")
            self.current_task_label.setText("Текущая задача дежурства: " + ", ".join(parts))
        else:
            self.current_task_label.setText("Текущая задача дежурства: не привязана")

    def toggle_enabled(self):
        settings = self.get_settings()
        was_enabled = settings.get("enabled", False)
        settings["enabled"] = not was_enabled
        save_config(self.config)
        self.update_enable_button()

        if settings["enabled"] and not was_enabled:
            self.ask_duty_task_flow()

    def ask_duty_task_flow(self):
        """
        При заступлении на дежурство спрашиваем,
        есть ли уже созданная задача.
        """
        has_task = QMessageBox.question(
            self,
            "Задача дежурства",
            "Задача для этого дежурства уже есть?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if has_task == QMessageBox.Yes:
            self.attach_existing_task()
            return

        create_task = QMessageBox.question(
            self,
            "Задача дежурства",
            "Создать новую задачу дежурства?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if create_task == QMessageBox.Yes:
            self.open_base_duty_task()

    def attach_existing_task(self):
        dialog = AttachExistingTaskDialog(
            config=self.config,
            parent=self
        )
        dialog.exec()
        self.update_task_label()

    def open_base_duty_task(self):
        dialog = OtrsCreateTaskDialog(
            config=self.config,
            parent=self
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
            if self.start_check():
                self.run_duty_triggers_check()
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
        self.cards = []

        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def render_empty_hint(self):
        self.clear_cards()

        hint = QLabel(
            "Здесь появятся графики для дежурной проверки. "
            "Нажми «Настроить режим дежурства» и выбери нужные графики."
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

    def _build_trigger_result_log(self, trigger, result, status):
        return {
            **self._trigger_log_context(trigger),
            "status": status,
            "duration_minutes": result.get("duration_minutes") if isinstance(result, dict) else None,
            "from_time": result.get("from_time") if isinstance(result, dict) else None,
            "to_time": result.get("to_time") if isinstance(result, dict) else None,
        }

    def run_duty_triggers_check(self):
        if self.duty_trigger_running:
            self.status_label.setText("Проверка триггеров уже выполняется.")
            return

        trigger_settings = ensure_duty_triggers_defaults(self.config)
        if not trigger_settings.get("enabled", True):
            self.status_label.setText("Проверка триггеров отключена в настройках.")
            self.logger.info("Duty triggers check skipped: disabled")
            return

        enabled_triggers = [
            trigger for trigger in trigger_settings.get("items", [])
            if trigger.get("enabled", True)
        ]
        self.logger.info("Duty trigger manual check started: enabled_count=%s", len(enabled_triggers))
        self.status_label.setText(f"Запущена проверка триггеров: {len(enabled_triggers)} шт.")

        if not self.cards:
            self.render_check_graph_cards()
        self._clear_duty_trigger_statuses()

        if not enabled_triggers:
            self.logger.info("Duty triggers check finished: stats=%s", {"total": 0, "ok": 0, "alert": 0, "errors": 0})
            return

        self.duty_trigger_queue = list(enabled_triggers)
        self.duty_trigger_stats = {"total": len(enabled_triggers), "ok": 0, "alert": 0, "errors": 0}
        self.duty_trigger_running = True
        self._run_next_duty_trigger()

    def _run_next_duty_trigger(self):
        if not self.duty_trigger_queue:
            stats = self.duty_trigger_stats
            self.duty_trigger_running = False
            self.status_label.setText(
                "Проверка триггеров завершена: "
                f"OK={stats['ok']}, ALERT={stats['alert']}, ошибки={stats['errors']}."
            )
            self.logger.info("Duty triggers check finished: stats=%s", stats)
            return

        trigger = self.duty_trigger_queue.pop(0)
        self._run_single_duty_trigger(trigger)

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

        view = QWebEngineView(self)
        view.setVisible(False)
        page = QWebEnginePage(profile, view)
        view.setPage(page)
        self.hidden_trigger_views.append(view)

        def on_loaded(ok, v=view, t=trigger, zid=zabbix_id):
            if not ok:
                self.logger.warning("Duty trigger hidden source load failed: id=%s", t.get("id", ""))
                self._cleanup_hidden_view(v)
                self._finish_trigger_without_html(t, "SOURCE_NOT_FOUND")
                return

            js = make_zabbix_login_js(
                self.credentials.get(zid, {}).get("login", ""),
                self.credentials.get(zid, {}).get("password", ""),
            )
            if js:
                v.page().runJavaScript(js)
            self.logger.info(
                "Duty trigger waiting before HTML read: id=%s display_name=%s delay_ms=1500",
                t.get("id", ""),
                t.get("display_name", ""),
            )
            QTimer.singleShot(1500, lambda v=v, t=t: v.page().toHtml(lambda html: self._after_hidden_duty_trigger_html(v, t, html)))

        self.logger.info(
            "Duty trigger hidden WebView loading source: id=%s display_name=%s has_cache_buster=%s",
            trigger.get("id", ""),
            trigger.get("display_name", ""),
            "_oko_trigger_check_ts=" in source_url,
        )
        view.loadFinished.connect(on_loaded)
        view.load(QUrl(source_url))

    def _cleanup_hidden_view(self, view):
        if view in self.hidden_trigger_views:
            self.hidden_trigger_views.remove(view)
        view.deleteLater()

    def _after_hidden_duty_trigger_html(self, view, trigger, html):
        self._cleanup_hidden_view(view)
        self._after_duty_trigger_html(trigger, html)

    def _finish_trigger_without_html(self, trigger, status):
        message = self._status_message(status, trigger=trigger)
        target_found = self._set_target_status(trigger, status, message)
        if status == "TARGET_NOT_FOUND" or not target_found:
            final_status = "TARGET_NOT_FOUND"
        else:
            final_status = status
        self.duty_trigger_stats["errors"] += 1
        self.logger.warning(
            "Duty trigger finished without HTML: %s target_found=%s html_received=False",
            self._build_trigger_result_log(trigger, {}, final_status),
            target_found,
        )
        QTimer.singleShot(0, self._run_next_duty_trigger)

    def _after_duty_trigger_html(self, trigger, html):
        html = html or ""
        self.logger.info(
            "Duty trigger HTML received: id=%s display_name=%s html_received=%s",
            trigger.get("id", ""),
            trigger.get("display_name", ""),
            bool(html),
        )
        if not html.strip():
            result = {"status": "NO_DATA", "message": DUTY_TRIGGER_STATUS_MESSAGES["NO_DATA"]}
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
            result["message"] = DUTY_TRIGGER_STATUS_MESSAGES["NO_DATA"]
        elif status == "PARSE_ERROR":
            result["message"] = DUTY_TRIGGER_STATUS_MESSAGES["PARSE_ERROR"]
        message = self._status_message(status, result=result, trigger=trigger)
        target_found = self._set_target_status(trigger, status, message)

        if status == "OK":
            self.duty_trigger_stats["ok"] += 1
        elif status == "ALERT":
            self.duty_trigger_stats["alert"] += 1
        else:
            self.duty_trigger_stats["errors"] += 1
        if not target_found:
            self.duty_trigger_stats["errors"] += 1

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

        if not self.render_check_graph_cards():
            QMessageBox.warning(
                self,
                "Режим дежурства",
                "Не выбраны графики для проверки. Нажми «Настроить режим дежурства»."
            )
            return False

        self.status_label.setText("Идёт проверка графиков.")
        return True

    def success_check(self):
        if self.skip_timer.isActive():
            self.skip_timer.stop()

        text = "Показатели в пределах нормы. Отклонений не обнаружено."

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
