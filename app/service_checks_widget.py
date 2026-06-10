"""UI for configuring service/product checks."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config import save_config
from app.credentials import load_service_credentials, save_service_credentials
from app.service_checks import (
    AUTH_HTML_FORM,
    AUTH_NONE,
    AUTH_WEBENGINE_SESSION,
    default_service_item,
    ensure_service_checks_defaults,
    parse_text_markers,
    unique_service_id,
)


AUTH_LABELS = [
    ("Без авторизации", AUTH_NONE),
    ("HTML-форма", AUTH_HTML_FORM),
    ("Использовать существующую сессию WebEngine", AUTH_WEBENGINE_SESSION),
]


class ServiceChecksSettingsWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.settings = ensure_service_checks_defaults(self.config)
        self.current_index = -1
        self._loading = False

        root = QVBoxLayout(self)
        title = QLabel("Проверка сервисов")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        actions = QHBoxLayout()
        add_button = QPushButton("Добавить продукт")
        add_button.setObjectName("PrimaryAction")
        add_button.clicked.connect(self.add_service)
        delete_button = QPushButton("Удалить продукт")
        delete_button.clicked.connect(self.delete_service)
        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self.save)
        actions.addWidget(add_button)
        actions.addWidget(delete_button)
        actions.addWidget(save_button)
        actions.addStretch(1)
        root.addLayout(actions)

        splitter = QSplitter(Qt.Horizontal)
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self.select_service)
        splitter.addWidget(self.list_widget)

        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)

        general = QGroupBox("Карточка выбранного продукта")
        general_form = QFormLayout(general)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("FacePay")
        self.enabled_input = QCheckBox("Включён")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.local")
        self.timeout_input = QSpinBox()
        self.timeout_input.setRange(1, 300)
        self.timeout_input.setSuffix(" сек")
        self.otrs_task_url_input = QLineEdit()
        self.otrs_task_url_input.setPlaceholderText("https://itsm...Action=AgentTicketNote;TicketID=...")
        general_form.addRow("Задача ОТРС для проверки сервисов:", self.otrs_task_url_input)
        general_form.addRow("Название продукта:", self.name_input)
        general_form.addRow("Состояние:", self.enabled_input)
        general_form.addRow("URL проверки:", self.url_input)
        general_form.addRow("Таймаут:", self.timeout_input)
        form_layout.addWidget(general)

        auth = QGroupBox("Авторизация")
        auth_form = QFormLayout(auth)
        self.auth_type_input = QComboBox()
        for label, value in AUTH_LABELS:
            self.auth_type_input.addItem(label, value)
        self.login_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.login_selector_input = QLineEdit()
        self.login_selector_input.setPlaceholderText('input[name="login"]')
        self.password_selector_input = QLineEdit()
        self.password_selector_input.setPlaceholderText('input[type="password"]')
        self.submit_selector_input = QLineEdit()
        self.submit_selector_input.setPlaceholderText('button[type="submit"]')
        self.post_login_delay_input = QSpinBox()
        self.post_login_delay_input.setRange(0, 60)
        self.post_login_delay_input.setSuffix(" сек")
        auth_form.addRow("Тип авторизации:", self.auth_type_input)
        auth_form.addRow("Логин:", self.login_input)
        auth_form.addRow("Пароль:", self.password_input)
        auth_form.addRow("CSS selector поля логина:", self.login_selector_input)
        auth_form.addRow("CSS selector поля пароля:", self.password_selector_input)
        auth_form.addRow("CSS selector кнопки входа:", self.submit_selector_input)
        auth_form.addRow("Задержка после входа:", self.post_login_delay_input)
        hint = QLabel('Укажите CSS selector HTML-элемента на странице авторизации. Например: input[name="username"], #password, button[type="submit"].')
        hint.setWordWrap(True)
        auth_form.addRow("Подсказка:", hint)
        form_layout.addWidget(auth)

        markers = QGroupBox("Признаки результата")
        markers_form = QFormLayout(markers)
        self.success_texts_input = QTextEdit()
        self.success_texts_input.setPlaceholderText("Главная; Выход; Профиль; Dashboard")
        self.success_texts_input.setMaximumHeight(80)
        self.error_texts_input = QTextEdit()
        self.error_texts_input.setPlaceholderText("Ошибка авторизации; Неверный пароль; Access denied; Login failed")
        self.error_texts_input.setMaximumHeight(80)
        markers_form.addRow("Текст успеха:", self.success_texts_input)
        markers_form.addRow("Текст ошибки:", self.error_texts_input)
        form_layout.addWidget(markers)
        form_layout.addStretch(1)
        splitter.addWidget(form_container)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        self._connect_changes()
        self.refresh_list()
        if self.settings.get("items"):
            self.list_widget.setCurrentRow(0)

    def _connect_changes(self):
        for widget in (self.name_input, self.url_input, self.login_selector_input, self.password_selector_input, self.submit_selector_input):
            widget.textChanged.connect(self.update_current_from_form)
        self.otrs_task_url_input.textChanged.connect(lambda text: self.settings.__setitem__("otrs_task_url", text.strip()))
        self.enabled_input.toggled.connect(self.update_current_from_form)
        self.timeout_input.valueChanged.connect(self.update_current_from_form)
        self.auth_type_input.currentIndexChanged.connect(self.update_current_from_form)
        self.post_login_delay_input.valueChanged.connect(self.update_current_from_form)
        self.success_texts_input.textChanged.connect(self.update_current_from_form)
        self.error_texts_input.textChanged.connect(self.update_current_from_form)
        self.login_input.textChanged.connect(self.update_credentials)
        self.password_input.textChanged.connect(self.update_credentials)

    def refresh_list(self):
        self.list_widget.clear()
        for item in self.settings.get("items", []):
            suffix = "" if item.get("enabled", True) else " (выключен)"
            self.list_widget.addItem(f"{item.get('name') or item.get('id')}{suffix}")

    def current_item(self):
        items = self.settings.get("items", [])
        if 0 <= self.current_index < len(items):
            return items[self.current_index]
        return None

    def select_service(self, index):
        self.current_index = index
        item = self.current_item()
        self._loading = True
        enabled = item is not None
        for widget in (self.name_input, self.enabled_input, self.url_input, self.timeout_input, self.auth_type_input, self.login_input, self.password_input, self.login_selector_input, self.password_selector_input, self.submit_selector_input, self.post_login_delay_input, self.success_texts_input, self.error_texts_input):
            widget.setEnabled(enabled)
        self.otrs_task_url_input.setText(self.settings.get("otrs_task_url", ""))
        if item:
            self.name_input.setText(item.get("name", ""))
            self.enabled_input.setChecked(item.get("enabled", True))
            self.url_input.setText(item.get("url", ""))
            self.timeout_input.setValue(int(item.get("timeout_seconds", 15)))
            idx = self.auth_type_input.findData(item.get("auth_type", AUTH_NONE))
            self.auth_type_input.setCurrentIndex(max(0, idx))
            creds = load_service_credentials(item.get("id", ""))
            self.login_input.setText(creds.get("login", ""))
            self.password_input.setText(creds.get("password", ""))
            self.login_selector_input.setText(item.get("login_selector", ""))
            self.password_selector_input.setText(item.get("password_selector", ""))
            self.submit_selector_input.setText(item.get("submit_selector", ""))
            self.post_login_delay_input.setValue(int(item.get("post_login_delay_ms", 1500)) // 1000)
            self.success_texts_input.setPlainText("; ".join(item.get("success_texts", [])))
            self.error_texts_input.setPlainText("; ".join(item.get("error_texts", [])))
        self._loading = False

    def add_service(self):
        items = self.settings.setdefault("items", [])
        item = default_service_item(unique_service_id("service", items))
        items.append(item)
        self.refresh_list()
        self.list_widget.setCurrentRow(len(items) - 1)

    def delete_service(self):
        if self.current_item() is None:
            return
        if QMessageBox.question(self, "Удалить продукт", "Удалить выбранный продукт?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.settings["items"].pop(self.current_index)
        self.current_index = -1
        self.refresh_list()
        if self.settings["items"]:
            self.list_widget.setCurrentRow(0)

    def update_current_from_form(self, *args):
        if self._loading:
            return
        item = self.current_item()
        if not item:
            return
        old_id = item.get("id", "")
        item["name"] = self.name_input.text().strip() or "Новый продукт"
        item["id"] = unique_service_id(old_id or item["name"], self.settings.get("items", []), current_id=old_id)
        item["enabled"] = self.enabled_input.isChecked()
        item["url"] = self.url_input.text().strip()
        item["timeout_seconds"] = int(self.timeout_input.value())
        item["auth_type"] = self.auth_type_input.currentData() or AUTH_NONE
        item["login_selector"] = self.login_selector_input.text().strip()
        item["password_selector"] = self.password_selector_input.text().strip()
        item["submit_selector"] = self.submit_selector_input.text().strip()
        item["post_login_delay_ms"] = int(self.post_login_delay_input.value()) * 1000
        item["success_texts"] = parse_text_markers(self.success_texts_input.toPlainText())
        item["error_texts"] = parse_text_markers(self.error_texts_input.toPlainText())
        index = self.current_index
        self.refresh_list()
        self.current_index = index
        self.list_widget.setCurrentRow(index)

    def update_credentials(self):
        if self._loading:
            return
        item = self.current_item()
        if not item:
            return
        save_service_credentials(item.get("id", ""), self.login_input.text(), self.password_input.text())

    def save(self):
        self.update_current_from_form()
        if self.current_item():
            self.update_credentials()
        ensure_service_checks_defaults(self.config)
        save_config(self.config)
        QMessageBox.information(self, "Проверка сервисов", "Настройки проверки сервисов сохранены.")
