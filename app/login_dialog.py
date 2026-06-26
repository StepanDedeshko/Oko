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
    QVBoxLayout,
)

from app.app_info import APP_NAME
from app.app_users import authenticate_user, create_user, has_users
from app.credentials import load_saved_credentials
from app.logger import get_logger
from app.screen_utils import center_widget_on_screen


FIRST_SETUP_MESSAGE = (
    "Первичная настройка Око.\n"
    "Создайте первого администратора приложения."
)
FIRST_SETUP_SHORT_MESSAGE = "Создайте первого администратора Око."
GITHUB_RELEASES_URL = "https://github.com/StepanDedeshko/Oko/releases"


class LoginDialog(QDialog):
    """
    Окно входа в Око.

    Здесь вводятся только логин и пароль приложения Око.
    Доступы Zabbix, ОТРС и сервисов настраиваются в разделе «Профиль».
    """

    def __init__(self, config, preferred_screen=None):
        super().__init__()

        self.config = config
        self.preferred_screen = preferred_screen
        self.credentials = load_saved_credentials()
        self.current_user = None
        self.theme_name = self.config.get("settings", {}).get("theme", "mass_effect")
        self.logger = get_logger()
        self.first_owner_setup = not has_users()

        self.setWindowTitle(f"Вход в {APP_NAME}")
        self.resize(440, 260)

        root = QVBoxLayout(self)
        root.setSpacing(12)

        title_text = (
            "Первый запуск: создайте администратора Око"
            if self.first_owner_setup
            else "Вход в Око"
        )
        title = QLabel(title_text)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        root.addWidget(title)

        hint = QLabel(
            "Учётки Zabbix, ОТРС и сервисов вводятся после входа в разделе «Профиль»."
            if not self.first_owner_setup
            else "Первый пользователь получит роль владельца/администратора."
        )
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        root.addWidget(hint)

        account_box = QGroupBox("Учётная запись Око")
        form = QFormLayout(account_box)

        self.login_input = QLineEdit()
        self.login_input.setPlaceholderText("Логин")

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Пароль")
        self.password_input.setEchoMode(QLineEdit.Password)

        form.addRow("Логин:", self.login_input)
        form.addRow("Пароль:", self.password_input)

        self.confirm_password_input = None
        if self.first_owner_setup:
            self.confirm_password_input = QLineEdit()
            self.confirm_password_input.setPlaceholderText("Повторите пароль")
            self.confirm_password_input.setEchoMode(QLineEdit.Password)
            form.addRow("Повтор пароля:", self.confirm_password_input)

        root.addWidget(account_box)

        buttons = QHBoxLayout()
        login_button = QPushButton("Создать администратора" if self.first_owner_setup else "Войти")
        cancel_button = QPushButton("Отмена")

        login_button.setDefault(True)
        login_button.clicked.connect(self.accept_login)
        cancel_button.clicked.connect(self.reject)
        self.login_input.returnPressed.connect(self.accept_login)
        self.password_input.returnPressed.connect(self.accept_login)
        if self.confirm_password_input is not None:
            self.confirm_password_input.returnPressed.connect(self.accept_login)

        buttons.addStretch()
        buttons.addWidget(login_button)
        buttons.addWidget(cancel_button)
        root.addLayout(buttons)

        center_widget_on_screen(self, self.preferred_screen)
        self.apply_theme_style()

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
        """)

    def accept_login(self):
        login = self.login_input.text().strip()
        password = self.password_input.text()

        if not login:
            QMessageBox.warning(self, "Вход в Око", "Введите логин.")
            return

        if not password:
            QMessageBox.warning(self, "Вход в Око", "Введите пароль.")
            return

        if self.first_owner_setup:
            confirm_password = self.confirm_password_input.text() if self.confirm_password_input is not None else ""
            if password != confirm_password:
                QMessageBox.warning(self, "Первичная настройка", "Пароли не совпадают.")
                return

            try:
                self.current_user = create_user(login, password, role="owner", display_name=login)
            except Exception as exc:
                QMessageBox.warning(self, "Первичная настройка", str(exc))
                return

            self.config["_current_user"] = self.current_user
            self.logger.info("Oko first owner created: login=%s role=%s", self.current_user.get("login"), self.current_user.get("role"))
            self.accept()
            return

        user = authenticate_user(login, password)
        if not user:
            QMessageBox.warning(self, "Вход в Око", "Неверный логин или пароль.")
            return

        self.current_user = user
        self.config["_current_user"] = self.current_user
        self.credentials = load_saved_credentials()
        self.logger.info("Oko user logged in: login=%s role=%s", user.get("login"), user.get("role"))
        self.accept()
