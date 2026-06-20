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
    QScrollArea,
    QSizePolicy,
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
    AUTH_EXISTING_SESSION,
    AUTH_EXTERNAL_BROWSER_GROUP,
    AUTH_VISIBLE_HTML_FORM,
    default_service_item,
    ensure_service_checks_defaults,
    format_service_actions,
    normalize_service_actions,
    parse_selector_markers,
    parse_text_markers,
    unique_service_id,
)


AUTH_LABELS = [
    ("Без авторизации", AUTH_NONE),
    ("HTML-форма", AUTH_HTML_FORM),
    ("HTML-форма в видимом окне", AUTH_VISIBLE_HTML_FORM),
    ("Внешний браузер / общая сессия / ручная проверка", AUTH_EXTERNAL_BROWSER_GROUP),
    ("Использовать существующую сессию WebEngine", AUTH_EXISTING_SESSION),
]


def _make_limited_text_edit(placeholder, minimum_height=60, maximum_height=100):
    editor = QTextEdit()
    editor.setPlaceholderText(placeholder)
    editor.setMinimumHeight(minimum_height)
    editor.setMaximumHeight(maximum_height)
    editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return editor


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

        self.form_scroll = QScrollArea()
        self.form_scroll.setObjectName("ServiceCheckFormScrollArea")
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.form_scroll.setFrameShape(QScrollArea.NoFrame)

        form_container = QWidget()
        form_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        form_layout = QVBoxLayout(form_container)
        form_layout.setContentsMargins(0, 0, 8, 0)

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
        self.allow_insecure_ssl_input = QCheckBox("Разрешить внутренний/самоподписанный SSL-сертификат")
        self.allow_http_error_load_input = QCheckBox("Разрешить продолжать проверку при HTTP-ошибке загрузки, если форма найдена")
        self.session_group_input = QLineEdit()
        self.session_group_input.setPlaceholderText("sensitive_group_1")
        self.session_group_order_input = QSpinBox()
        self.session_group_order_input.setRange(0, 999)
        self.session_group_login_owner_input = QCheckBox("Первый сервис группы: выполнять вход")
        self.session_group_logout_owner_input = QCheckBox("Последний сервис группы: выполнять выход")
        self.external_browser_open_delay_input = QSpinBox()
        self.external_browser_open_delay_input.setRange(0, 60)
        self.external_browser_open_delay_input.setSuffix(" сек")
        self.external_browser_manual_confirm_input = QCheckBox("Показывать ручное подтверждение")
        self.otrs_task_url_input = QLineEdit()
        self.otrs_task_url_input.setPlaceholderText("https://itsm...Action=AgentTicketNote;TicketID=...")
        general_form.addRow("Задача ОТРС для проверки сервисов:", self.otrs_task_url_input)
        general_form.addRow("Название продукта:", self.name_input)
        general_form.addRow("Состояние:", self.enabled_input)
        general_form.addRow("URL проверки:", self.url_input)
        general_form.addRow("Таймаут:", self.timeout_input)
        general_form.addRow("SSL:", self.allow_insecure_ssl_input)
        general_form.addRow("HTTP-ошибка загрузки:", self.allow_http_error_load_input)
        general_form.addRow("Группа общей сессии:", self.session_group_input)
        general_form.addRow("Порядок в группе:", self.session_group_order_input)
        general_form.addRow("Вход группы:", self.session_group_login_owner_input)
        general_form.addRow("Выход группы:", self.session_group_logout_owner_input)
        general_form.addRow("Пауза открытия во внешнем браузере:", self.external_browser_open_delay_input)
        general_form.addRow("Ручное подтверждение:", self.external_browser_manual_confirm_input)
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

        self.visible_window_group = QGroupBox("Видимое окно проверки")
        visible_form = QFormLayout(self.visible_window_group)
        self.visible_close_success_input = QCheckBox("Закрывать окно после успешной проверки")
        self.visible_close_error_input = QCheckBox("Закрывать окно при ошибке")
        self.visible_close_delay_input = QSpinBox()
        self.visible_close_delay_input.setRange(0, 120)
        self.visible_close_delay_input.setSuffix(" сек")
        visible_form.addRow("Успех:", self.visible_close_success_input)
        visible_form.addRow("Ошибка:", self.visible_close_error_input)
        visible_form.addRow("Задержка перед закрытием:", self.visible_close_delay_input)
        form_layout.addWidget(self.visible_window_group)

        logout = QGroupBox("Выход после успешной проверки")
        logout_form = QFormLayout(logout)
        self.logout_menu_selector_input = QLineEdit()
        self.logout_menu_selector_input.setPlaceholderText(".user-menu, button.profile")
        self.logout_button_selector_input = QLineEdit()
        self.logout_button_selector_input.setPlaceholderText("button.logout, a[href*=logout]")
        self.logout_success_selectors_input = _make_limited_text_edit("form.login\nbutton[type=submit]")
        self.logout_success_texts_input = _make_limited_text_edit("Войти; Авторизация; Login")
        self.logout_menu_wait_input = QSpinBox()
        self.logout_menu_wait_input.setRange(1, 60)
        self.logout_menu_wait_input.setSuffix(" сек")
        self.logout_wait_input = QSpinBox()
        self.logout_wait_input.setRange(1, 120)
        self.logout_wait_input.setSuffix(" сек")
        logout_form.addRow("CSS selector кнопки раскрытия меню выхода:", self.logout_menu_selector_input)
        logout_form.addRow("CSS selector кнопки “Выйти”:", self.logout_button_selector_input)
        logout_form.addRow("CSS selectors признаков успешного выхода:", self.logout_success_selectors_input)
        logout_form.addRow("Тексты признаков успешного выхода:", self.logout_success_texts_input)
        logout_form.addRow("Ожидание появления меню выхода:", self.logout_menu_wait_input)
        logout_form.addRow("Ожидание завершения выхода:", self.logout_wait_input)
        markers = QGroupBox("Признаки результата")
        markers_form = QFormLayout(markers)
        self.success_texts_input = _make_limited_text_edit("Главная; Выход; Профиль; Dashboard")
        self.error_texts_input = _make_limited_text_edit("Ошибка авторизации; Неверный пароль; Access denied; Login failed")
        self.success_selectors_input = _make_limited_text_edit(".account-menu\nbutton.logout\n[data-test=dashboard]")
        self.error_selectors_input = _make_limited_text_edit(".login-error\n.el-message--error\n.alert-danger")
        markers_form.addRow("Текст успеха:", self.success_texts_input)
        markers_form.addRow("Текст ошибки:", self.error_texts_input)
        markers_form.addRow("CSS selectors признаков успеха:", self.success_selectors_input)
        markers_form.addRow("CSS selectors признаков ошибки:", self.error_selectors_input)
        form_layout.addWidget(markers)

        actions_group = QGroupBox("Мини-тест после входа")
        actions_form = QFormLayout(actions_group)
        self.post_login_actions_input = _make_limited_text_edit(
            "click | .menu | 5 | 500 | Открыть меню\n"
            "wait_selector | .section-ready | 10 | 0 | Проверить раздел",
            minimum_height=80,
            maximum_height=120,
        )
        actions_hint = QLabel("Формат: type | selector/text | timeout_seconds | delay_ms | description. Типы: click, wait_selector, wait_text, delay.")
        actions_hint.setWordWrap(True)
        actions_form.addRow("Шаги мини-теста:", self.post_login_actions_input)
        actions_form.addRow("Подсказка:", actions_hint)
        form_layout.addWidget(actions_group)

        logout_actions_group = QGroupBox("Сценарий выхода")
        logout_actions_form = QFormLayout(logout_actions_group)
        self.logout_actions_input = _make_limited_text_edit(
            "click | .profile | 5 | 500 | Открыть профиль\n"
            "click | .logout | 5 | 500 | Нажать Выйти\n"
            "click | .confirm-yes | 5 | 500 | Подтвердить выход",
            minimum_height=80,
            maximum_height=120,
        )
        logout_actions_hint = QLabel("Если сценарий выхода заполнен, он используется вместо старых полей меню/кнопки выхода.")
        logout_actions_hint.setWordWrap(True)
        logout_actions_form.addRow("Шаги выхода:", self.logout_actions_input)
        logout_actions_form.addRow("Подсказка:", logout_actions_hint)
        form_layout.addWidget(logout_actions_group)
        form_layout.addWidget(logout)
        form_layout.addStretch(1)
        self.form_scroll.setWidget(form_container)
        splitter.addWidget(self.form_scroll)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        self._connect_changes()
        self.refresh_list()
        if self.settings.get("items"):
            self.list_widget.setCurrentRow(0)
        self.update_visible_window_visibility()

    def _connect_changes(self):
        for widget in (self.name_input, self.url_input, self.login_selector_input, self.password_selector_input, self.submit_selector_input):
            widget.textChanged.connect(self.update_current_from_form)
        self.otrs_task_url_input.textChanged.connect(lambda text: self.settings.__setitem__("otrs_task_url", text.strip()))
        self.enabled_input.toggled.connect(self.update_current_from_form)
        self.allow_insecure_ssl_input.toggled.connect(self.update_current_from_form)
        self.allow_http_error_load_input.toggled.connect(self.update_current_from_form)
        self.session_group_input.textChanged.connect(self.update_current_from_form)
        self.session_group_order_input.valueChanged.connect(self.update_current_from_form)
        self.session_group_login_owner_input.toggled.connect(self.update_current_from_form)
        self.session_group_logout_owner_input.toggled.connect(self.update_current_from_form)
        self.external_browser_open_delay_input.valueChanged.connect(self.update_current_from_form)
        self.external_browser_manual_confirm_input.toggled.connect(self.update_current_from_form)
        self.timeout_input.valueChanged.connect(self.update_current_from_form)
        self.auth_type_input.currentIndexChanged.connect(self.on_auth_type_changed)
        self.post_login_delay_input.valueChanged.connect(self.update_current_from_form)
        self.visible_close_success_input.toggled.connect(self.update_current_from_form)
        self.visible_close_error_input.toggled.connect(self.update_current_from_form)
        self.visible_close_delay_input.valueChanged.connect(self.update_current_from_form)
        self.success_texts_input.textChanged.connect(self.update_current_from_form)
        self.error_texts_input.textChanged.connect(self.update_current_from_form)
        self.success_selectors_input.textChanged.connect(self.update_current_from_form)
        self.error_selectors_input.textChanged.connect(self.update_current_from_form)
        self.post_login_actions_input.textChanged.connect(self.update_current_from_form)
        self.logout_actions_input.textChanged.connect(self.update_current_from_form)
        self.logout_menu_selector_input.textChanged.connect(self.update_current_from_form)
        self.logout_button_selector_input.textChanged.connect(self.update_current_from_form)
        self.logout_success_selectors_input.textChanged.connect(self.update_current_from_form)
        self.logout_success_texts_input.textChanged.connect(self.update_current_from_form)
        self.logout_menu_wait_input.valueChanged.connect(self.update_current_from_form)
        self.logout_wait_input.valueChanged.connect(self.update_current_from_form)
        self.login_input.textChanged.connect(self.update_credentials)
        self.password_input.textChanged.connect(self.update_credentials)

    def on_auth_type_changed(self, *args):
        self.update_visible_window_visibility()
        self.update_current_from_form()

    def update_visible_window_visibility(self):
        is_visible = self.auth_type_input.currentData() == AUTH_VISIBLE_HTML_FORM
        self.visible_window_group.setVisible(is_visible)
        is_external = self.auth_type_input.currentData() == AUTH_EXTERNAL_BROWSER_GROUP
        for widget in (self.login_input, self.password_input, self.login_selector_input, self.password_selector_input, self.submit_selector_input, self.post_login_actions_input, self.logout_actions_input):
            widget.setEnabled(not is_external and self.current_item() is not None)

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
        for widget in (self.name_input, self.enabled_input, self.url_input, self.timeout_input, self.allow_insecure_ssl_input, self.allow_http_error_load_input, self.session_group_input, self.session_group_order_input, self.session_group_login_owner_input, self.session_group_logout_owner_input, self.external_browser_open_delay_input, self.external_browser_manual_confirm_input, self.auth_type_input, self.login_input, self.password_input, self.login_selector_input, self.password_selector_input, self.submit_selector_input, self.post_login_delay_input, self.visible_close_success_input, self.visible_close_error_input, self.visible_close_delay_input, self.success_texts_input, self.error_texts_input, self.success_selectors_input, self.error_selectors_input, self.post_login_actions_input, self.logout_actions_input, self.logout_menu_selector_input, self.logout_button_selector_input, self.logout_success_selectors_input, self.logout_success_texts_input, self.logout_menu_wait_input, self.logout_wait_input):
            widget.setEnabled(enabled)
        self.otrs_task_url_input.setText(self.settings.get("otrs_task_url", ""))
        if item:
            self.name_input.setText(item.get("name", ""))
            self.enabled_input.setChecked(item.get("enabled", True))
            self.url_input.setText(item.get("url", ""))
            self.timeout_input.setValue(int(item.get("timeout_seconds", 15)))
            self.allow_insecure_ssl_input.setChecked(bool(item.get("allow_insecure_ssl", False)))
            self.allow_http_error_load_input.setChecked(bool(item.get("allow_http_error_load", False)))
            self.session_group_input.setText(item.get("session_group", ""))
            self.session_group_order_input.setValue(int(item.get("session_group_order", 0)))
            self.session_group_login_owner_input.setChecked(bool(item.get("session_group_login_owner", False)))
            self.session_group_logout_owner_input.setChecked(bool(item.get("session_group_logout_owner", False)))
            self.external_browser_open_delay_input.setValue(int(float(item.get("external_browser_open_delay_seconds", 1))))
            self.external_browser_manual_confirm_input.setChecked(bool(item.get("external_browser_manual_confirm", True)))
            idx = self.auth_type_input.findData(item.get("auth_type", AUTH_NONE))
            self.auth_type_input.setCurrentIndex(max(0, idx))
            self.visible_close_success_input.setChecked(bool(item.get("visible_window_close_on_success", True)))
            self.visible_close_error_input.setChecked(bool(item.get("visible_window_close_on_error", False)))
            self.visible_close_delay_input.setValue(int(item.get("visible_window_close_delay_seconds", 3)))
            creds = load_service_credentials(item.get("id", ""))
            self.login_input.setText(creds.get("login", ""))
            self.password_input.setText(creds.get("password", ""))
            self.login_selector_input.setText(item.get("login_selector", ""))
            self.password_selector_input.setText(item.get("password_selector", ""))
            self.submit_selector_input.setText(item.get("submit_selector", ""))
            self.post_login_delay_input.setValue(int(item.get("post_login_delay_ms", 1500)) // 1000)
            self.success_texts_input.setPlainText("; ".join(item.get("success_texts", [])))
            self.error_texts_input.setPlainText("; ".join(item.get("error_texts", [])))
            self.success_selectors_input.setPlainText("\n".join(item.get("success_selectors", [])))
            self.error_selectors_input.setPlainText("\n".join(item.get("error_selectors", [])))
            self.post_login_actions_input.setPlainText(format_service_actions(item.get("post_login_actions", [])))
            self.logout_actions_input.setPlainText(format_service_actions(item.get("logout_actions", [])))
            self.logout_menu_selector_input.setText(item.get("logout_menu_selector", ""))
            self.logout_button_selector_input.setText(item.get("logout_button_selector", ""))
            self.logout_success_selectors_input.setPlainText("\n".join(item.get("logout_success_selectors", [])))
            self.logout_success_texts_input.setPlainText("; ".join(item.get("logout_success_texts", [])))
            self.logout_menu_wait_input.setValue(int(item.get("logout_menu_wait_seconds", 5)))
            self.logout_wait_input.setValue(int(item.get("logout_wait_seconds", 10)))
        self._loading = False
        self.update_visible_window_visibility()

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
        item["allow_insecure_ssl"] = self.allow_insecure_ssl_input.isChecked()
        item["allow_http_error_load"] = self.allow_http_error_load_input.isChecked()
        item["session_group"] = self.session_group_input.text().strip()
        item["session_group_order"] = int(self.session_group_order_input.value())
        item["session_group_login_owner"] = self.session_group_login_owner_input.isChecked()
        item["session_group_logout_owner"] = self.session_group_logout_owner_input.isChecked()
        item["session_group_reuse_webview"] = bool(item["session_group"])
        item["external_browser_open_delay_seconds"] = int(self.external_browser_open_delay_input.value())
        item["external_browser_manual_confirm"] = self.external_browser_manual_confirm_input.isChecked()
        item["external_browser_open_mode"] = "tabs"
        item["auth_type"] = self.auth_type_input.currentData() or AUTH_NONE
        item["visible_window_close_on_success"] = self.visible_close_success_input.isChecked()
        item["visible_window_close_on_error"] = self.visible_close_error_input.isChecked()
        item["visible_window_close_delay_seconds"] = int(self.visible_close_delay_input.value())
        item["login_selector"] = self.login_selector_input.text().strip()
        item["password_selector"] = self.password_selector_input.text().strip()
        item["submit_selector"] = self.submit_selector_input.text().strip()
        item["post_login_delay_ms"] = int(self.post_login_delay_input.value()) * 1000
        item["success_texts"] = parse_text_markers(self.success_texts_input.toPlainText())
        item["error_texts"] = parse_text_markers(self.error_texts_input.toPlainText())
        item["success_selectors"] = parse_selector_markers(self.success_selectors_input.toPlainText())
        item["error_selectors"] = parse_selector_markers(self.error_selectors_input.toPlainText())
        item["post_login_actions"] = normalize_service_actions(self.post_login_actions_input.toPlainText())
        item["logout_actions"] = normalize_service_actions(self.logout_actions_input.toPlainText())
        item["logout_menu_selector"] = self.logout_menu_selector_input.text().strip()
        item["logout_button_selector"] = self.logout_button_selector_input.text().strip()
        item["logout_success_selectors"] = parse_selector_markers(self.logout_success_selectors_input.toPlainText())
        item["logout_success_texts"] = parse_text_markers(self.logout_success_texts_input.toPlainText())
        item["logout_menu_wait_seconds"] = int(self.logout_menu_wait_input.value())
        item["logout_wait_seconds"] = int(self.logout_wait_input.value())
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
