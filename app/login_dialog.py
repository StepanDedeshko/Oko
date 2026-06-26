from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
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
from app.app_users import (
    authenticate_user,
    clear_remembered_user,
    create_user,
    has_users,
    load_remembered_user,
    save_remembered_user,
)
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
        self.remembered_user = None if self.first_owner_setup else load_remembered_user()

        self.setWindowTitle(f"Вход в {APP_NAME}")
        self.resize(460, 300)

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

        hint_text = (
            "Первый пользователь получит роль владельца/администратора."
            if self.first_owner_setup
            else "Учётки Zabbix, ОТРС и сервисов вводятся после входа в разделе «Профиль»."
        )
        if self.remembered_user:
            hint_text = (
                f"Сохранён вход: {self.remembered_user.get('login')} "
                f"({self.remembered_user.get('role')}). Вход выполнится автоматически."
            )

        self.hint = QLabel(hint_text)
        self.hint.setWordWrap(True)
        self.hint.setAlignment(Qt.AlignCenter)
        root.addWidget(self.hint)

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

        self.remember_checkbox = QCheckBox("Запомнить вход на этом компьютере")
        self.remember_checkbox.setChecked(True)
        if self.first_owner_setup:
            self.remember_checkbox.setToolTip("После создания администратора следующий запуск Око откроется без повторного ввода пароля.")
        form.addRow("", self.remember_checkbox)

        if self.remembered_user:
            self.login_input.setText(str(self.remembered_user.get("login", "")))
            self.password_input.setPlaceholderText("Используется сохранённый вход")
            self.password_input.setEnabled(False)

        root.addWidget(account_box)

        buttons = QHBoxLayout()

        self.login_button = QPushButton("Создать администратора" if self.first_owner_setup else "Войти")
        cancel_button = QPushButton("Отмена")
        forget_button = QPushButton("Забыть вход")
        forget_button.clicked.connect(self.forget_remembered_login)
        forget_button.setVisible(bool(self.remembered_user))

        self.login_button.setDefault(True)
        self.login_button.clicked.connect(self.accept_login)
        cancel_button.clicked.connect(self.reject)
        self.login_input.returnPressed.connect(self.accept_login)
        self.password_input.returnPressed.connect(self.accept_login)
        if self.confirm_password_input is not None:
            self.confirm_password_input.returnPressed.connect(self.accept_login)

        buttons.addWidget(forget_button)
        buttons.addStretch()
        buttons.addWidget(self.login_button)
        buttons.addWidget(cancel_button)
        root.addLayout(buttons)

        center_widget_on_screen(self, self.preferred_screen)
        self.apply_theme_style()

        if self.remembered_user:
            QTimer.singleShot(350, self.accept_remembered_login)

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

    def accept_remembered_login(self):
        user = load_remembered_user()
        if not user:
            self.forget_remembered_login(show_message=False)
            return

        self.current_user = user
        self.config["_current_user"] = self.current_user
        self.credentials = load_saved_credentials()
        self.logger.info("Oko remembered user logged in: login=%s role=%s", user.get("login"), user.get("role"))
        self.accept()

    def forget_remembered_login(self, show_message=True):
        clear_remembered_user()
        self.remembered_user = None
        self.password_input.setEnabled(True)
        self.password_input.clear()
        self.password_input.setPlaceholderText("Пароль")
        self.hint.setText("Сохранённый вход удалён. Введите логин и пароль.")
        if show_message:
            QMessageBox.information(self, "Вход в Око", "Сохранённый вход удалён.")

    def _save_remember_if_needed(self, login):
        if self.remember_checkbox.isChecked():
            try:
                save_remembered_user(login)
            except Exception:
                self.logger.exception("Failed to save remembered Oko login")
        else:
            clear_remembered_user()

    def accept_login(self):
        if self.remembered_user and not self.password_input.isEnabled():
            self.accept_remembered_login()
            return

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
                self._save_remember_if_needed(login)
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
        self._save_remember_if_needed(login)
        self.logger.info("Oko user logged in: login=%s role=%s", user.get("login"), user.get("role"))
        self.accept()
