from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
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
from app.config import save_config
from app.screen_utils import center_widget_on_screen
from app.credentials import load_saved_credentials, save_credentials


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

        self.setWindowTitle(f"Вход в {APP_NAME}")
        self.resize(560, 520)

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

        for instance in self.config.get("zabbix_instances", []):
            if not instance.get("enabled", True):
                continue

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
            empty = QLabel("В config.json нет включённых Zabbix.")
            empty.setWordWrap(True)
            zabbix_layout.addWidget(empty)

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

    def accept_login(self):
        if not self.inputs:
            QMessageBox.warning(self, "Ошибка", "В config.json нет включённых Zabbix.")
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
