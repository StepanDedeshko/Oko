from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.app_info import APP_NAME
from app.config import CONFIG_PATH, enabled_zabbix_instances, import_config_file, save_config
from app.screen_utils import center_widget_on_screen
from app.credentials import load_saved_credentials, save_credentials
from app.logger import get_logger

FIRST_SETUP_MESSAGE = (
    "Первичная настройка не завершена.\n"
    "В конфигурации нет включённых Zabbix-серверов.\n\n"
    "Для работы приложения импортируйте готовый config.json\n"
    "или настройте подключение вручную."
)
FIRST_SETUP_SHORT_MESSAGE = "Первичная настройка не завершена: нет включённых Zabbix-серверов."
GITHUB_RELEASES_URL = "https://github.com/StepanDedeshko/Oko/releases"


class LoginDialog(QDialog):
    """
    Упрощённое окно входа:
    - логин/пароль Zabbix;
    - логин/пароль ОТРС.
    """

    def __init__(self, config, preferred_screen=None):
        super().__init__()

        self.config = config
        self.preferred_screen = preferred_screen
        self.credentials = {}
        self.saved_credentials = load_saved_credentials()
        self.theme_name = self.config.get("settings", {}).get("theme", "mass_effect")
        self.logger = get_logger()

        self.setWindowTitle(f"Вход в {APP_NAME}")
        self.resize(620, 560)

        root = QVBoxLayout(self)

        is_first_run = not bool(self.saved_credentials)

        title_text = (
            "Для первого запуска просьба ввести логин и пароль"
            if is_first_run
            else "Введите логин и пароль"
        )

        title = QLabel(title_text)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, stretch=1)

        container = QWidget()
        form_layout = QVBoxLayout(container)
        scroll.setWidget(container)

        self.inputs = {}

        # Zabbix
        zabbix_box = QGroupBox("Zabbix")
        zabbix_layout = QVBoxLayout(zabbix_box)

        for instance in enabled_zabbix_instances(self.config):
            zabbix_id = instance.get("id")
            name = instance.get("name", zabbix_id)
            saved = self.saved_credentials.get(zabbix_id, {})

            group = QGroupBox(name)
            form = QFormLayout(group)

            login_input = QLineEdit()
            login_input.setPlaceholderText("Логин Zabbix")
            login_input.setText(saved.get("login", ""))

            password_input = QLineEdit()
            password_input.setPlaceholderText("Пароль Zabbix")
            password_input.setEchoMode(QLineEdit.Password)
            password_input.setText(saved.get("password", ""))

            form.addRow("Логин:", login_input)
            form.addRow("Пароль:", password_input)

            self.inputs[zabbix_id] = {
                "login": login_input,
                "password": password_input,
                "name": name
            }

            zabbix_layout.addWidget(group)

        if not self.inputs:
            self.logger.info("Первый запуск/первичная настройка: нет включённых Zabbix-серверов")
            zabbix_layout.addWidget(self.create_first_setup_widget())

        form_layout.addWidget(zabbix_box)

        # ОТРС
        duty = self.config.setdefault("duty_mode", {})

        otrs_box = QGroupBox("ОТРС")
        otrs_form = QFormLayout(otrs_box)

        self.otrs_login = QLineEdit()
        self.otrs_login.setPlaceholderText("Логин ОТРС")
        self.otrs_login.setText(duty.get("otrs_login", ""))

        self.otrs_password = QLineEdit()
        self.otrs_password.setPlaceholderText("Пароль ОТРС")
        self.otrs_password.setEchoMode(QLineEdit.Password)
        self.otrs_password.setText(duty.get("otrs_password", ""))

        otrs_form.addRow("Логин:", self.otrs_login)
        otrs_form.addRow("Пароль:", self.otrs_password)

        form_layout.addWidget(otrs_box)
        form_layout.addStretch(1)

        buttons = QHBoxLayout()
        login_button = QPushButton("Войти")
        cancel_button = QPushButton("Отмена")

        login_button.clicked.connect(self.accept_login)
        cancel_button.clicked.connect(self.reject)

        buttons.addStretch()
        buttons.addWidget(login_button)
        buttons.addWidget(cancel_button)
        root.addLayout(buttons)

        center_widget_on_screen(self, self.preferred_screen)
        self.apply_theme_style()

    def create_first_setup_widget(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(10)

        message = QLabel(FIRST_SETUP_MESSAGE)
        message.setObjectName("firstSetupMessage")
        message.setWordWrap(True)
        message.setTextInteractionFlags(Qt.TextSelectableByMouse)
        message.setStyleSheet("font-size: 14px; font-weight: 600; line-height: 140%;")
        layout.addWidget(message)

        actions = QHBoxLayout()
        import_button = QPushButton("Импортировать config.json")
        open_folder_button = QPushButton("Открыть папку приложения")
        instruction_button = QPushButton("Открыть инструкцию")

        import_button.clicked.connect(self.import_config)
        open_folder_button.clicked.connect(self.open_app_folder)
        instruction_button.clicked.connect(self.open_instruction)

        actions.addWidget(import_button)
        actions.addWidget(open_folder_button)
        actions.addWidget(instruction_button)
        layout.addLayout(actions)

        return widget

    def apply_theme_style(self):
        if self.theme_name != "light_standard":
            return

        self.setStyleSheet("""
            QDialog, QWidget { background-color: #f3f4f6; color: #111827; }
            QGroupBox {
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 8px;
                font-weight: 700;
            }
            QGroupBox::title { left: 10px; padding: 0 4px; color: #111827; }
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 6px 8px;
                color: #111827;
            }
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 6px 12px;
                color: #111827;
            }
            QPushButton:hover { border-color: #93c5fd; }
            QScrollArea { border: 1px solid #d1d5db; background-color: #ffffff; }
        """)

    def import_config(self):
        self.logger.info("Открыт импорт config.json")
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Импортировать config.json",
            str(CONFIG_PATH.parent),
            "JSON (*.json);;Все файлы (*)",
        )
        if not selected_path:
            return

        try:
            import_config_file(selected_path)
            QMessageBox.information(
                self,
                "Импорт config.json",
                "config.json импортирован. Перезапустите приложение.",
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Ошибка импорта config.json",
                f"Не удалось импортировать config.json:\n{exc}",
            )

    def open_app_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(CONFIG_PATH.parent)))

    def open_instruction(self):
        instruction_path = CONFIG_PATH.parent / "README_ПЕРВАЯ_УСТАНОВКА_LINUX.md"
        if instruction_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(instruction_path)))
            return

        if not QDesktopServices.openUrl(QUrl(GITHUB_RELEASES_URL)):
            QMessageBox.information(
                self,
                "Первичная настройка",
                FIRST_SETUP_MESSAGE,
            )

    def accept_login(self):
        if not self.inputs:
            QMessageBox.warning(self, "Первичная настройка", FIRST_SETUP_SHORT_MESSAGE)
            return

        for zabbix_id, widgets in self.inputs.items():
            login = widgets["login"].text().strip()
            password = widgets["password"].text()

            if not login or not password:
                QMessageBox.warning(
                    self,
                    "Ошибка",
                    f"Заполните логин и пароль для {widgets['name']}."
                )
                return

            self.credentials[zabbix_id] = {
                "login": login,
                "password": password
            }

        duty = self.config.setdefault("duty_mode", {})
        duty["otrs_login_enabled"] = True
        duty["otrs_login"] = self.otrs_login.text().strip()
        duty["otrs_password"] = self.otrs_password.text()

        save_credentials(self.credentials)
        save_config(self.config)

        self.accept()
