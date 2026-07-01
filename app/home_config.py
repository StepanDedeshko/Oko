from app.app_users import ROLE_ADMIN, ROLE_OWNER, ROLE_USER, ROLE_CUSTOM, create_user, load_users, set_user_password, update_user

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QInputDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QSizePolicy,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QApplication,
    QListWidget,
    QListWidgetItem,
)

from app.config import (
    CONFIG_PATH,
    default_settings_export_filename,
    export_settings_file,
    import_settings_file,
    load_settings_export,
    save_config,
)
from app.templates import (
    OTRS_GRAPH_CHECK_TEMPLATE_KEY,
    OTRS_SERVICE_CHECK_TEMPLATE_KEY,
    REDMINE_TASK_TEMPLATE_KEY,
    REDMINE_SPECIAL_TASK_TEMPLATE_KEY,
    OTRS_TEMPLATE_EXAMPLE,
    REDMINE_ALL_GRAPHS_EXAMPLE,
    REDMINE_COLLAPSE_EXAMPLE,
    REDMINE_GRAPH_VARIABLE_DETAILS,
    OTRS_VARIABLE_DETAILS,
    SERVICE_CHECK_VARIABLE_DETAILS,
    DEFAULT_OTRS_SERVICE_CHECK_TEMPLATE_TEXT,
    reset_otrs_service_check_template,
    ensure_templates_defaults,
    reset_otrs_graph_check_template,
    preview_otrs_template,
    preview_redmine_template,
    reset_redmine_task_template,
    reset_redmine_special_task_template,
    variable_details_text,
)
from app.credentials import OTRS_CREDENTIALS_KEY, LEGACY_OTRS_CREDENTIALS_KEY, load_otrs_credentials, load_saved_credentials, save_credentials
from app.theme import get_available_themes
from app.app_info import APP_NAME, APP_VERSION, APP_DESCRIPTION
from app.update_widget import UpdateWidget
from app.diagnostics_widget import DiagnosticsWidget
from app.duty_settings import DutyModeSettingsWidget
from app.service_checks_widget import ServiceChecksSettingsWidget
from app.credentials import load_service_group_credentials, save_service_group_credentials, save_service_credentials
from app.credentials import default_encrypted_profile_export_filename, export_profile_credentials_encrypted_file, import_profile_credentials_encrypted_file
from app.safe_widgets import NoWheelComboBox
from app.service_checks import ensure_service_checks_defaults
from app.live_zabbix import DEFAULT_REDMINE_LOGIN_URL, ensure_live_monitor_defaults


def clone(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


from app.permissions import (
    ALL_SECTION_PERMISSIONS, SECTION_NAMES, can_open_section, visible_sections_for_user,
    normalize_user_permissions, build_user_settings_export, ensure_duty_links, get_duty_link, set_duty_link,
)

def ensure_home_defaults(config):
    config.setdefault("products", [])
    settings = config.setdefault("settings", {})
    settings.setdefault("theme", "dark")
    settings.setdefault("home_notes", "")

    duty = config.setdefault("duty_mode", {})
    duty.setdefault("otrs_login_enabled", False)
    duty.setdefault("otrs_auto_submit_login", False)
    duty.setdefault("duty_zabbix_expected_task_title", duty.get("expected_ticket_subject", "Дежурная проверка Zabbix / графиков"))
    duty.setdefault("duty_service_checks_expected_task_title", "Дежурная проверка сервисов")
    duty.setdefault("expected_ticket_subject", duty.get("duty_zabbix_expected_task_title", "Дежурная проверка Zabbix / графиков"))
    ensure_service_checks_defaults(config)
    ensure_duty_links(config)
    if config.get("_current_user"):
        config["_current_user"] = normalize_user_permissions(config.get("_current_user"))
    return config



def restart_application():
    """
    Перезапуск текущего приложения тем же Python-интерпретатором.
    Работает для portable-запуска через run_terminal.sh/python main.py.
    """
    python = sys.executable
    args = sys.argv[:]

    try:
        QApplication.quit()
    except Exception:
        pass

    os.execl(python, python, *args)


def request_application_restart(parent=None, reason=None):
    """
    Общий механизм для всех настроек, которые требуют перезапуск.

    Использовать после сохранения изменений, если без перезапуска
    приложение не сможет корректно пересобрать интерфейс/меню/тему.
    """
    message = "Изменения требуют перезапуска приложения."

    if reason:
        message += f"\n\nПричина: {reason}"

    message += "\n\nПерезапустить сейчас?"

    answer = QMessageBox.question(
        parent,
        "Требуется перезапуск",
        message,
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
    )

    if answer == QMessageBox.Yes:
        restart_application()

    return answer == QMessageBox.Yes


# Старое имя оставлено для совместимости с уже написанными вызовами.
def ask_restart_required(parent=None, reason=None):
    return request_application_restart(parent=parent, reason=reason)


DEVELOPER_PASSWORD_HASH_KEY = "developer_mode_password_hash"
DEVELOPER_PASSWORD_SALT_KEY = "developer_mode_password_salt"


def _developer_password_digest(password, salt_hex):
    password_bytes = str(password or "").encode("utf-8")
    try:
        salt = bytes.fromhex(str(salt_hex or ""))
    except ValueError:
        salt = b""

    if not salt:
        salt = os.urandom(16)

    digest = hashlib.pbkdf2_hmac("sha256", password_bytes, salt, 120_000)
    return salt.hex(), digest.hex()


def _verify_developer_password(password, salt_hex, expected_digest):
    if not expected_digest:
        return False

    _salt, digest = _developer_password_digest(password, salt_hex)
    return hmac.compare_digest(str(digest), str(expected_digest))


class LiveZabbixDeveloperSettingsWidget(QGroupBox):
    def __init__(self, config, parent=None):
        super().__init__("Live Zabbix Monitor", parent)
        self.config = config
        self.settings = ensure_live_monitor_defaults(self.config)

        root = QVBoxLayout(self)

        hint = QLabel(
            "Технические настройки Live Zabbix Monitor. "
            "Обычному пользователю они скрыты, чтобы случайно не сломать мониторинг."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = QFormLayout()

        self.url_input = QLineEdit(
            self.settings.get("problems_url")
            or self.settings.get("url")
            or ""
        )
        self.url_input.setPlaceholderText("URL страницы Zabbix Problems")

        self.interval_input = QSpinBox()
        self.interval_input.setRange(60, 3600)
        self.interval_input.setSuffix(" сек")
        interval = int(self.settings.get("poll_interval_seconds", 60) or 60)
        self.interval_input.setValue(max(60, interval))

        self.profile_input = QLineEdit(
            self.settings.get("zabbix_profile_id")
            or self.settings.get("profile_id")
            or "zbx_product_1"
        )
        self.profile_input.setPlaceholderText("zbx_product_1")

        self.show_diagnostics_checkbox = QCheckBox(
            "Показывать в Live Zabbix кнопки DOM/WebView и JSON-диагностику"
        )
        self.show_diagnostics_checkbox.setChecked(
            bool(
                self.settings.get("show_live_zabbix_diagnostics", False)
                or self.settings.get("show_developer_tools", False)
            )
        )

        self.url_input.setReadOnly(True)
        form.addRow("URL Zabbix Problems (редактируется в Настройки → Ссылки):", self.url_input)
        form.addRow("Интервал опроса:", self.interval_input)
        form.addRow("Профиль Zabbix:", self.profile_input)
        form.addRow("", self.show_diagnostics_checkbox)
        self.mm_otrs_create_url_input = QLineEdit()
        self.mm_otrs_create_url_input.setText(str(self.settings.get("mm_otrs_create_url", "") or ""))
        self.mm_otrs_create_url_input.setPlaceholderText("https://itsm... URL создания задачи ОТРС ММ")
        self.mm_otrs_create_url_input.setReadOnly(True)
        form.addRow("URL создания задачи ОТРС ММ (Настройки → Ссылки):", self.mm_otrs_create_url_input)

        root.addLayout(form)

        buttons = QHBoxLayout()
        save_button = QPushButton("Сохранить настройки Live Zabbix")
        save_button.clicked.connect(self.save_settings)
        buttons.addWidget(save_button)
        buttons.addStretch(1)
        root.addLayout(buttons)

    def save_settings(self):
        url = self.url_input.text().strip()
        profile_id = self.profile_input.text().strip() or "zbx_product_1"
        interval = max(60, int(self.interval_input.value()))

        self.settings["problems_url"] = url
        self.settings["url"] = url
        self.settings["poll_interval_seconds"] = interval
        self.settings["zabbix_profile_id"] = profile_id
        self.settings["profile_id"] = profile_id
        self.settings["show_live_zabbix_diagnostics"] = self.show_diagnostics_checkbox.isChecked()
        self.settings["mm_otrs_create_url"] = self.mm_otrs_create_url_input.text().strip()

        save_config(self.config)

        QMessageBox.information(
            self,
            "Live Zabbix Monitor",
            "Настройки Live Zabbix сохранены. Для полного применения перезапустите приложение."
        )


class DeveloperToolsWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        self.live_zabbix_settings = LiveZabbixDeveloperSettingsWidget(self.config, self)
        root.addWidget(self.live_zabbix_settings)

        self.diagnostics = DiagnosticsWidget(self.config)
        root.addWidget(self.diagnostics, stretch=1)


class LinksSettingsWidget(QWidget):
    """Единый раздел технических URL: Настройки → Ссылки."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)
        root = QVBoxLayout(self)
        title = QLabel("Ссылки")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        hint = QLabel(
            "Здесь редактируются технические URL, которые используются дежуркой, Redmine, ОТРС, "
            "Live Zabbix Monitor, шаблонами и проверкой сервисов. Старые поля в профиле, шаблонах "
            "и режиме разработчика больше не являются основным местом редактирования."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)
        form = QFormLayout()
        self.redmine_create_url_input = QLineEdit(get_duty_link(self.config, "redmine_create_url"))
        self.redmine_login_url_input = QLineEdit(str(ensure_live_monitor_defaults(self.config).get("redmine_login_url") or DEFAULT_REDMINE_LOGIN_URL))
        self.mm_otrs_create_url_input = QLineEdit(get_duty_link(self.config, "mm_otrs_create_url"))
        self.zabbix_problems_url_input = QLineEdit(get_duty_link(self.config, "live_zabbix_url"))
        form.addRow("URL создания задачи Redmine:", self.redmine_create_url_input)
        form.addRow("URL окна авторизации Redmine:", self.redmine_login_url_input)
        form.addRow("URL создания задачи ОТРС ММ:", self.mm_otrs_create_url_input)
        form.addRow("URL Zabbix Problems:", self.zabbix_problems_url_input)
        root.addLayout(form)
        save = QPushButton("Сохранить ссылки")
        save.setObjectName("PrimaryAction")
        save.clicked.connect(self.save_links)
        root.addWidget(save)
        root.addStretch(1)

    def save_links(self):
        redmine_create = self.redmine_create_url_input.text().strip()
        redmine_login = self.redmine_login_url_input.text().strip() or DEFAULT_REDMINE_LOGIN_URL
        mm_otrs = self.mm_otrs_create_url_input.text().strip()
        zabbix = self.zabbix_problems_url_input.text().strip()
        set_duty_link(self.config, "redmine_create_url", redmine_create)
        set_duty_link(self.config, "mm_otrs_create_url", mm_otrs)
        set_duty_link(self.config, "live_zabbix_url", zabbix)
        live = ensure_live_monitor_defaults(self.config)
        live["redmine_login_url"] = redmine_login
        live["redmine_create_url"] = redmine_create
        live["mm_otrs_create_url"] = mm_otrs
        live["problems_url"] = zabbix
        live["url"] = zabbix
        templates = ensure_templates_defaults(self.config)
        if REDMINE_TASK_TEMPLATE_KEY in templates:
            templates[REDMINE_TASK_TEMPLATE_KEY]["create_url"] = redmine_create
        if REDMINE_SPECIAL_TASK_TEMPLATE_KEY in templates:
            templates[REDMINE_SPECIAL_TASK_TEMPLATE_KEY]["create_url"] = redmine_create
        save_config(self.config)
        QMessageBox.information(self, "Ссылки", "Ссылки сохранены.")


class DeveloperModeGateWidget(QWidget):
    """
    Локальная защита режима разработчика.

    Пароль не хранится в открытом виде: в config сохраняются salt + PBKDF2 hash.
    Это защита от случайного входа обычного пользователя в технические настройки.
    """

    def __init__(self, config, protected_widget, parent=None):
        super().__init__(parent)
        self.config = config
        self.protected_widget = protected_widget

        root = QVBoxLayout(self)
        self.stack = QStackedWidget()
        root.addWidget(self.stack)

        self.login_page = QWidget()
        login_layout = QVBoxLayout(self.login_page)
        login_layout.setContentsMargins(16, 16, 16, 16)
        login_layout.setSpacing(10)

        self.title_label = QLabel("Режим разработчика")
        self.title_label.setObjectName("PageTitle")
        self.hint_label = QLabel()
        self.hint_label.setWordWrap(True)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Пароль режима разработчика")
        self.password_input.returnPressed.connect(self._submit_password)

        self.submit_button = QPushButton()
        self.submit_button.clicked.connect(self._submit_password)

        login_layout.addWidget(self.title_label)
        login_layout.addWidget(self.hint_label)
        login_layout.addWidget(self.password_input)
        login_layout.addWidget(self.submit_button)
        login_layout.addStretch(1)

        self.unlocked_page = QWidget()
        unlocked_layout = QVBoxLayout(self.unlocked_page)
        unlocked_layout.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        unlocked_title = QLabel("Режим разработчика открыт")
        unlocked_title.setObjectName("PageTitle")
        lock_button = QPushButton("Заблокировать")
        lock_button.clicked.connect(self._lock)
        top.addWidget(unlocked_title)
        top.addStretch(1)
        top.addWidget(lock_button)

        unlocked_layout.addLayout(top)
        unlocked_layout.addWidget(self.protected_widget, stretch=1)

        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.unlocked_page)

        self._refresh_login_text()
        self._lock()

    def _settings(self):
        return self.config.setdefault("settings", {})

    def _has_password(self):
        settings = self._settings()
        return bool(settings.get(DEVELOPER_PASSWORD_HASH_KEY) and settings.get(DEVELOPER_PASSWORD_SALT_KEY))

    def _refresh_login_text(self):
        if self._has_password():
            self.hint_label.setText(
                "Введите пароль, чтобы открыть диагностику и технические настройки. "
                "Обычному пользователю этот раздел не нужен."
            )
            self.submit_button.setText("Войти")
        else:
            self.hint_label.setText(
                "Пароль режима разработчика ещё не создан. "
                "Введите новый пароль, чтобы защитить технические настройки."
            )
            self.submit_button.setText("Создать пароль и войти")

    def _submit_password(self):
        password = self.password_input.text()

        if len(password) < 4:
            QMessageBox.warning(self, "Режим разработчика", "Пароль должен быть не короче 4 символов.")
            return

        settings = self._settings()

        if not self._has_password():
            salt_hex, digest = _developer_password_digest(password, "")
            settings[DEVELOPER_PASSWORD_SALT_KEY] = salt_hex
            settings[DEVELOPER_PASSWORD_HASH_KEY] = digest
            save_config(self.config)
            QMessageBox.information(self, "Режим разработчика", "Пароль режима разработчика создан.")
            self._unlock()
            return

        if _verify_developer_password(
            password,
            settings.get(DEVELOPER_PASSWORD_SALT_KEY, ""),
            settings.get(DEVELOPER_PASSWORD_HASH_KEY, ""),
        ):
            self._unlock()
            return

        QMessageBox.warning(self, "Режим разработчика", "Неверный пароль.")

    def _unlock(self):
        self.password_input.clear()
        self.stack.setCurrentWidget(self.unlocked_page)

    def _lock(self):
        self._refresh_login_text()
        self.password_input.clear()
        self.stack.setCurrentWidget(self.login_page)
        self.password_input.setFocus()



PAGE_TYPES = [
    ("graphs_grid", "graphs_grid"),
    ("problems_page", "problems_page"),
    ("dashboard_page", "dashboard_page"),
    ("mode_pages", "mode_pages"),
]
URL_PAGE_TYPES = {"problems_page", "dashboard_page"}


def normalize_item_list(items, title_key, default_prefix):
    """
    Приводит старые списки строк и новые списки объектов к виду для UI.
    В config сохраняем обычные dict-объекты, чтобы старые настройки продолжали читаться.
    """
    result = []
    for index, item in enumerate(items or []):
        if isinstance(item, str):
            result.append({title_key: f"{default_prefix} {index + 1}", "url": item})
        elif isinstance(item, dict):
            normalized = clone(item)
            normalized.setdefault(title_key, item.get("name") or item.get("title") or f"{default_prefix} {index + 1}")
            normalized.setdefault("url", "")
            result.append(normalized)
    return result



class GraphInlineRow(QWidget):
    def __init__(self, graph=None, index=0, on_delete=None, parent=None):
        super().__init__(parent)
        self.original_graph = clone(graph or {})
        self.on_delete = on_delete

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(8)

        label = QLabel(f"График {index + 1}")
        label.setMinimumWidth(72)
        self.enabled = QCheckBox("Включён")
        self.enabled.setChecked(self.original_graph.get("enabled", True))
        self.title = QLineEdit(self.original_graph.get("title", ""))
        self.title.setPlaceholderText("Название графика")
        self.url = QLineEdit(self.original_graph.get("url", ""))
        self.url.setPlaceholderText("URL графика")
        self.open_url = QLineEdit(
            self.original_graph.get("open_url")
            or self.original_graph.get("zabbix_url")
            or self.original_graph.get("external_url")
            or ""
        )
        self.open_url.setPlaceholderText("URL открытия в Zabbix")
        delete = QPushButton("Удалить график")
        delete.clicked.connect(self.delete_requested)

        root.addWidget(label)
        root.addWidget(self.title, stretch=2)
        root.addWidget(self.url, stretch=3)
        root.addWidget(self.open_url, stretch=3)
        root.addWidget(self.enabled)
        root.addWidget(delete)

    def delete_requested(self):
        if self.on_delete:
            self.on_delete(self)

    def value(self):
        graph = clone(self.original_graph)
        graph.update({
            "enabled": self.enabled.isChecked(),
            "title": self.title.text().strip(),
            "url": self.url.text().strip(),
        })
        open_url = self.open_url.text().strip()
        if open_url:
            graph["open_url"] = open_url
        else:
            graph.pop("open_url", None)
        graph.setdefault("use_time_range", self.original_graph.get("use_time_range", True))
        return graph


class ModeInlineRow(QWidget):
    def __init__(self, mode=None, index=0, on_delete=None, parent=None):
        super().__init__(parent)
        self.original_mode = clone(mode or {}) if isinstance(mode, dict) else {"url": str(mode or "")}
        self.on_delete = on_delete

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(8)

        label = QLabel(f"Режим {index + 1}")
        label.setMinimumWidth(72)
        self.name = QLineEdit(self.original_mode.get("name") or self.original_mode.get("title") or f"Режим {index + 1}")
        self.name.setPlaceholderText("Название режима")
        self.url = QLineEdit(self.original_mode.get("url", ""))
        self.url.setPlaceholderText("URL режима")
        delete = QPushButton("Удалить режим")
        delete.clicked.connect(self.delete_requested)

        root.addWidget(label)
        root.addWidget(self.name, stretch=2)
        root.addWidget(self.url, stretch=5)
        root.addWidget(delete)

    def delete_requested(self):
        if self.on_delete:
            self.on_delete(self)

    def value(self):
        mode = clone(self.original_mode)
        mode.update({
            "name": self.name.text().strip(),
            "url": self.url.text().strip(),
        })
        return mode


class PageCardWidget(QGroupBox):
    def __init__(self, page=None, zabbix_ids=None, index=0, on_delete=None, parent=None, show_related=True):
        super().__init__(parent)
        self.original_page = clone(page or {"name": "", "type": "dashboard_page", "url": "", "zabbix_id": "zbx_product_1", "enabled": True})
        self.graph_rows = []
        self.mode_rows = []
        self.on_delete = on_delete
        self.show_related = show_related
        self.setTitle(f"Страница {index + 1}")

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.name = QLineEdit(self.original_page.get("name", ""))
        self.name.setPlaceholderText("Название страницы")
        self.enabled = QCheckBox("Включена")
        self.enabled.setChecked(self.original_page.get("enabled", True))
        self.type_combo = NoWheelComboBox()
        for label, value in PAGE_TYPES:
            self.type_combo.addItem(label, value)
        page_type = self.original_page.get("type", "dashboard_page")
        if page_type == "simple_page":
            page_type = "dashboard_page"
        type_index = self.type_combo.findData(page_type)
        self.type_combo.setCurrentIndex(max(0, type_index))

        self.zabbix_id = NoWheelComboBox()
        self.zabbix_id.setEditable(True)
        for zabbix_id in zabbix_ids or []:
            self.zabbix_id.addItem(zabbix_id)
        self.zabbix_id.setCurrentText(self.original_page.get("zabbix_id", "zbx_product_1"))

        self.url_label = QLabel("URL:")
        self.url = QLineEdit(self.original_page.get("url", ""))
        self.url.setPlaceholderText("URL страницы")
        delete = QPushButton("Удалить страницу")
        delete.clicked.connect(self.delete_requested)

        form.addRow("Название страницы:", self.name)
        form.addRow("Состояние:", self.enabled)
        form.addRow("Тип страницы:", self.type_combo)
        form.addRow("Профиль Zabbix:", self.zabbix_id)
        form.addRow(self.url_label, self.url)
        form.addRow("", delete)
        root.addLayout(form)

        self.graphs_group = QGroupBox("Графики")
        graphs_root = QVBoxLayout(self.graphs_group)
        graph_buttons = QHBoxLayout()
        add_graph = QPushButton("Добавить график")
        add_graph.clicked.connect(self.add_graph)
        graph_buttons.addWidget(add_graph)
        graph_buttons.addStretch()
        graphs_root.addLayout(graph_buttons)
        self.graphs_layout = QVBoxLayout()
        graphs_root.addLayout(self.graphs_layout)
        root.addWidget(self.graphs_group)

        self.modes_group = QGroupBox("Режимы")
        modes_root = QVBoxLayout(self.modes_group)
        mode_buttons = QHBoxLayout()
        add_mode = QPushButton("Добавить режим")
        add_mode.clicked.connect(self.add_mode)
        mode_buttons.addWidget(add_mode)
        mode_buttons.addStretch()
        modes_root.addLayout(mode_buttons)
        self.modes_layout = QVBoxLayout()
        modes_root.addLayout(self.modes_layout)
        root.addWidget(self.modes_group)

        for graph in normalize_item_list(self.original_page.get("graphs", []), "title", "График"):
            self.add_graph(graph)
        for mode in normalize_item_list(self.original_page.get("modes", []), "name", "Режим"):
            self.add_mode(mode)

        self.type_combo.currentIndexChanged.connect(self.update_type_fields)
        self.update_type_fields()

    def delete_requested(self):
        if self.on_delete:
            self.on_delete(self)

    def add_graph(self, graph=None):
        row = GraphInlineRow(graph, len(self.graph_rows), self.remove_graph, self)
        self.graph_rows.append(row)
        self.graphs_layout.addWidget(row)

    def remove_graph(self, row):
        if QMessageBox.question(self, "Удалить график", "Удалить этот график?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.graph_rows.remove(row)
        row.deleteLater()

    def add_mode(self, mode=None):
        row = ModeInlineRow(mode, len(self.mode_rows), self.remove_mode, self)
        self.mode_rows.append(row)
        self.modes_layout.addWidget(row)

    def remove_mode(self, row):
        if QMessageBox.question(self, "Удалить режим", "Удалить этот режим?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.mode_rows.remove(row)
        row.deleteLater()

    def update_type_fields(self):
        page_type = self.type_combo.currentData()
        self.graphs_group.setVisible(self.show_related and page_type == "graphs_grid")
        self.modes_group.setVisible(self.show_related and page_type == "mode_pages")
        show_url = page_type in URL_PAGE_TYPES
        self.url_label.setVisible(show_url)
        self.url.setVisible(show_url)

    def value(self):
        page = clone(self.original_page)
        page.update({
            "name": self.name.text().strip(),
            "enabled": self.enabled.isChecked(),
            "type": self.type_combo.currentData(),
            "zabbix_id": self.zabbix_id.currentText().strip() or "zbx_product_1",
        })
        if self.type_combo.currentData() in URL_PAGE_TYPES:
            url = self.url.text().strip()
            if url:
                page["url"] = url
            else:
                page.pop("url", None)

        if self.type_combo.currentData() == "graphs_grid" and self.show_related:
            page["graphs"] = [row.value() for row in self.graph_rows if row.value().get("title") or row.value().get("url")]
        if self.type_combo.currentData() == "mode_pages" and self.show_related:
            page["modes"] = [row.value() for row in self.mode_rows if row.value().get("name") or row.value().get("url")]
        return page


class ProductCardWidget(QGroupBox):
    def __init__(self, product=None, index=0, on_open=None, on_delete=None, parent=None):
        super().__init__(parent)
        self.product = product or {"name": "", "enabled": True, "dashboards": []}
        self.index = index
        self.on_open = on_open
        self.on_delete = on_delete

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(6)

        self.status_label = QLabel()
        self.status_label.setWordWrap(False)
        root.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(8)
        open_button = QPushButton("Открыть")
        open_button.clicked.connect(self.open_requested)
        delete_button = QPushButton("Удалить")
        delete_button.clicked.connect(self.delete_requested)
        buttons.addWidget(open_button)
        buttons.addStretch()
        buttons.addWidget(delete_button)
        root.addLayout(buttons)
        self.refresh()

    def refresh(self):
        name = self.product.get("name") or f"Продукт {self.index + 1}"
        enabled = "включён" if self.product.get("enabled", True) else "выключен"
        pages_count = len(self.product.get("dashboards", []) or [])
        self.setTitle(name)
        self.status_label.setText(f"Статус: {enabled}\nСтраниц: {pages_count}")

    def open_requested(self):
        if self.on_open:
            self.on_open(self.index)

    def delete_requested(self):
        if self.on_delete:
            self.on_delete(self.index)


class PageRelationsGroup(QGroupBox):
    def __init__(self, title, row_factory, add_label, page_card, items=None, parent=None):
        super().__init__(title, parent)
        self.page_card = page_card
        self.row_factory = row_factory
        self.rows = []

        root = QVBoxLayout(self)
        buttons = QHBoxLayout()
        add_button = QPushButton(add_label)
        add_button.clicked.connect(self.add_row)
        buttons.addWidget(add_button)
        buttons.addStretch()
        root.addLayout(buttons)

        self.rows_layout = QVBoxLayout()
        root.addLayout(self.rows_layout)
        for item in items or []:
            self.add_row(item)

    def add_row(self, item=None):
        row = self.row_factory(item, len(self.rows), self.remove_row, self)
        self.rows.append(row)
        self.rows_layout.addWidget(row)

    def remove_row(self, row):
        if QMessageBox.question(self, "Удалить", "Удалить эту строку?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.rows.remove(row)
        row.deleteLater()

    def values(self):
        result = []
        for row in self.rows:
            value = row.value()
            if value.get("title") or value.get("name") or value.get("url"):
                result.append(value)
        return result


class ProductDetailWidget(QWidget):
    def __init__(self, product, zabbix_ids=None, on_back=None, on_save=None, parent=None):
        super().__init__(parent)
        self.product = clone(product or {"name": "", "enabled": True, "dashboards": []})
        self.zabbix_ids = zabbix_ids or []
        self.on_back = on_back
        self.on_save = on_save
        self.page_cards = []
        self.graph_groups = []
        self.mode_groups = []
        self.current_section = "Страницы"

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        back_button = QPushButton("← Назад к продуктам")
        back_button.clicked.connect(self.back_requested)
        self.title_label = QLabel("Продукт")
        self.title_label.setObjectName("PageTitle")
        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self.save_requested)
        top.addWidget(back_button)
        top.addWidget(self.title_label)
        top.addStretch()
        top.addWidget(save_button)
        root.addLayout(top)

        form = QFormLayout()
        self.name = QLineEdit(self.product.get("name", ""))
        self.name.setPlaceholderText("Название продукта")
        self.name.textChanged.connect(self.update_title)
        self.enabled = QCheckBox("Включён")
        self.enabled.setChecked(self.product.get("enabled", True))
        form.addRow("Название продукта:", self.name)
        form.addRow("Состояние:", self.enabled)
        root.addLayout(form)
        self.update_title()

        nav = QHBoxLayout()
        self.pages_button = QPushButton("Страницы")
        self.graphs_button = QPushButton("Графики")
        self.modes_button = QPushButton("Режимы")
        self.pages_button.clicked.connect(lambda: self.show_section("Страницы"))
        self.graphs_button.clicked.connect(lambda: self.show_section("Графики"))
        self.modes_button.clicked.connect(lambda: self.show_section("Режимы"))
        nav.addWidget(self.pages_button)
        nav.addWidget(self.graphs_button)
        nav.addWidget(self.modes_button)
        nav.addStretch()
        add_page = QPushButton("Добавить страницу")
        add_page.clicked.connect(self.add_page)
        nav.addWidget(add_page)
        root.addLayout(nav)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, stretch=1)
        self.pages_page = self.make_scroll_page()
        self.graphs_page = self.make_scroll_page()
        self.modes_page = self.make_scroll_page()
        self.stack.addWidget(self.pages_page["scroll"])
        self.stack.addWidget(self.graphs_page["scroll"])
        self.stack.addWidget(self.modes_page["scroll"])

        for page in self.product.get("dashboards", []) or []:
            self.add_page(page, rebuild=False)
        self.rebuild_relation_sections()
        self.show_section("Страницы")

    def make_scroll_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(12)
        scroll.setWidget(container)
        return {"scroll": scroll, "container": container, "layout": layout}

    def update_title(self):
        self.title_label.setText(self.name.text().strip() or "Новый продукт")

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def add_page(self, page=None, rebuild=True):
        if self.pages_page["layout"].count() and self.pages_page["layout"].itemAt(self.pages_page["layout"].count() - 1).spacerItem():
            self.pages_page["layout"].takeAt(self.pages_page["layout"].count() - 1)
        card = PageCardWidget(page, self.zabbix_ids, len(self.page_cards), self.remove_page, self, show_related=False)
        # На вкладке «Страницы» оставляем только компактные параметры страницы.
        card.type_combo.currentIndexChanged.connect(self.rebuild_relation_sections)
        self.page_cards.append(card)
        self.pages_page["layout"].addWidget(card)
        self.pages_page["layout"].addStretch(1)
        if rebuild:
            self.rebuild_relation_sections()

    def remove_page(self, card):
        if QMessageBox.question(self, "Удалить страницу", "Удалить эту страницу?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.page_cards.remove(card)
        card.deleteLater()
        self.rebuild_relation_sections()

    def sync_relations_to_pages(self):
        for group in self.graph_groups:
            group.page_card.original_page["graphs"] = group.values()
        for group in self.mode_groups:
            group.page_card.original_page["modes"] = group.values()

    def rebuild_relation_sections(self):
        self.sync_relations_to_pages()
        self.clear_layout(self.graphs_page["layout"])
        self.clear_layout(self.modes_page["layout"])
        self.graph_groups = []
        self.mode_groups = []

        for page_index, page_card in enumerate(self.page_cards, start=1):
            page = page_card.value()
            page_name = page.get("name") or f"Страница {page_index}"
            if page.get("type") == "graphs_grid":
                group = PageRelationsGroup(
                    f"{page_name} — графики",
                    GraphInlineRow,
                    "Добавить график",
                    page_card,
                    normalize_item_list(page.get("graphs", []), "title", "График"),
                    self,
                )
                self.graph_groups.append(group)
                self.graphs_page["layout"].addWidget(group)
            if page.get("type") == "mode_pages":
                group = PageRelationsGroup(
                    f"{page_name} — режимы",
                    ModeInlineRow,
                    "Добавить режим",
                    page_card,
                    normalize_item_list(page.get("modes", []), "name", "Режим"),
                    self,
                )
                self.mode_groups.append(group)
                self.modes_page["layout"].addWidget(group)

        if not self.graph_groups:
            empty = QLabel("В продукте нет страниц типа graphs_grid.")
            empty.setWordWrap(True)
            self.graphs_page["layout"].addWidget(empty)
        if not self.mode_groups:
            empty = QLabel("В продукте нет страниц типа mode_pages.")
            empty.setWordWrap(True)
            self.modes_page["layout"].addWidget(empty)
        self.graphs_page["layout"].addStretch(1)
        self.modes_page["layout"].addStretch(1)

    def show_section(self, section_name):
        self.sync_relations_to_pages()
        if section_name in {"Графики", "Режимы"}:
            self.rebuild_relation_sections()
        self.current_section = section_name
        if section_name == "Страницы":
            self.stack.setCurrentIndex(0)
        elif section_name == "Графики":
            self.stack.setCurrentIndex(1)
        else:
            self.stack.setCurrentIndex(2)

    def value(self):
        self.sync_relations_to_pages()
        product = clone(self.product)
        product.update({
            "name": self.name.text().strip(),
            "enabled": self.enabled.isChecked(),
            "dashboards": [card.value() for card in self.page_cards],
        })
        return product

    def back_requested(self):
        if self.on_back:
            self.on_back(self.value())

    def save_requested(self):
        if self.on_save:
            self.on_save(self.value())


class ProductsWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)
        self.products = clone(self.config.get("products", []) or [])
        self.product_cards = []
        self.current_product_index = None
        self.zabbix_ids = [instance.get("id", "") for instance in self.config.get("zabbix_instances", []) if instance.get("id")]

        root = QVBoxLayout(self)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, stretch=1)

        self.list_screen = QWidget()
        list_root = QVBoxLayout(self.list_screen)
        header = QHBoxLayout()
        add = QPushButton("Добавить продукт")
        add.clicked.connect(self.add_product)
        save = QPushButton("Сохранить")
        save.clicked.connect(self.save)
        header.addStretch()
        header.addWidget(add)
        header.addWidget(save)
        list_root.addLayout(header)

        hint = QLabel("Сначала выбери продукт. Страницы, графики, режимы и URL открываются на следующем уровне.")
        hint.setWordWrap(True)
        list_root.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        list_root.addWidget(scroll, stretch=1)
        self.products_container = QWidget()
        self.products_layout = QVBoxLayout(self.products_container)
        self.products_layout.setSpacing(12)
        scroll.setWidget(self.products_container)
        self.stack.addWidget(self.list_screen)

        self.detail_screen = None
        self.rebuild_product_tiles()

    def rebuild_product_tiles(self):
        while self.products_layout.count():
            item = self.products_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.product_cards = []
        for index, product in enumerate(self.products):
            card = ProductCardWidget(product, index, self.open_product, self.delete_product, self)
            self.product_cards.append(card)
            self.products_layout.addWidget(card)
        self.products_layout.addStretch(1)

    def add_product(self):
        self.products.append({"name": "Новый продукт", "enabled": True, "dashboards": []})
        self.rebuild_product_tiles()
        self.open_product(len(self.products) - 1)

    def delete_product(self, index):
        product = self.products[index]
        name = product.get("name") or f"Продукт {index + 1}"
        if QMessageBox.question(self, "Удалить продукт", f"Удалить продукт «{name}»?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.products.pop(index)
        self.rebuild_product_tiles()

    def open_product(self, index):
        self.current_product_index = index
        if self.detail_screen is not None:
            self.stack.removeWidget(self.detail_screen)
            self.detail_screen.deleteLater()
        self.detail_screen = ProductDetailWidget(
            self.products[index],
            self.zabbix_ids,
            on_back=self.return_to_products,
            on_save=self.save_product_detail,
            parent=self,
        )
        self.stack.addWidget(self.detail_screen)
        self.stack.setCurrentWidget(self.detail_screen)

    def return_to_products(self, product):
        if self.current_product_index is not None:
            self.products[self.current_product_index] = product
        self.rebuild_product_tiles()
        self.stack.setCurrentWidget(self.list_screen)

    def save_product_detail(self, product):
        if self.current_product_index is not None:
            self.products[self.current_product_index] = product
        self.save()

    def validate(self, products):
        errors = []
        for product_index, product in enumerate(products, start=1):
            if not product.get("name", "").strip():
                errors.append(f"Продукт {product_index}: укажи название продукта.")
            for page_index, page in enumerate(product.get("dashboards", []), start=1):
                if not page.get("name", "").strip():
                    errors.append(f"Продукт {product_index}, страница {page_index}: укажи название страницы.")
                if page.get("type") == "graphs_grid":
                    for graph_index, graph in enumerate(page.get("graphs", []), start=1):
                        if not graph.get("title", "").strip() or not graph.get("url", "").strip():
                            errors.append(f"Продукт {product_index}, страница {page_index}, график {graph_index}: нужны название и URL.")
                if page.get("type") == "mode_pages":
                    for mode_index, mode in enumerate(page.get("modes", []), start=1):
                        if not mode.get("name", "").strip() or not mode.get("url", "").strip():
                            errors.append(f"Продукт {product_index}, страница {page_index}, режим {mode_index}: нужны название и URL.")
        return errors

    def save(self):
        if self.detail_screen is not None and self.stack.currentWidget() is self.detail_screen and self.current_product_index is not None:
            self.products[self.current_product_index] = self.detail_screen.value()
        errors = self.validate(self.products)
        if errors:
            QMessageBox.warning(self, "Продукты и страницы", "\n".join(errors))
            return
        self.config["products"] = clone(self.products)
        save_config(self.config)
        self.rebuild_product_tiles()
        QMessageBox.information(self, "Продукты и страницы", "Настройки сохранены. После изменения структуры перезапусти приложение, чтобы меню пересобралось.")
        request_application_restart(self, "Изменены продукты или страницы. Меню и страницы пересобираются при запуске.")


class ProfileWidget(QWidget):
    def __init__(self, config, logout_callback=None, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)
        self.logout_callback = logout_callback
        self.saved_credentials = load_saved_credentials()
        self.saved_zabbix_credentials = self.saved_credentials
        self.zabbix_inputs = {}
        self.service_group_inputs = {}

        duty = self.config.setdefault("duty_mode", {})
        otrs_credentials = load_otrs_credentials(self.config)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        account_actions = QGroupBox("Аккаунт Око")
        account_actions_layout = QVBoxLayout(account_actions)

        logout_hint = QLabel("Выход удалит сохранённый вход на этом компьютере. Остальные настройки и доступы не удаляются.")
        logout_hint.setWordWrap(True)
        account_actions_layout.addWidget(logout_hint)

        self.logout_button = QPushButton("Выйти из аккаунта Око")
        self.logout_button.setObjectName("DangerAction")
        self.logout_button.clicked.connect(self.logout_from_profile)
        account_actions_layout.addWidget(self.logout_button)

        root.addWidget(account_actions)

        def add_section_title(title_text):
            label = QLabel(title_text)
            label.setStyleSheet("font-size: 17px; font-weight: 700; margin-top: 12px;")
            root.addWidget(label)
            return label

        def add_caption(text):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setStyleSheet("font-size: 14px; font-weight: 700; padding-top: 8px; border: none;")
            root.addWidget(label)
            return label

        def add_labeled_password_pair(login_value="", password_value="", login_placeholder="Введите логин", password_placeholder="Введите пароль"):
            login_row = QHBoxLayout()
            login_row.setSpacing(10)

            login_label = QLabel("Логин:")
            login_label.setMinimumWidth(90)
            login_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            login_input = QLineEdit(login_value)
            login_input.setPlaceholderText(login_placeholder)
            login_input.setMinimumHeight(40)
            login_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            login_row.addWidget(login_label)
            login_row.addWidget(login_input, stretch=1)
            root.addLayout(login_row)

            password_row = QHBoxLayout()
            password_row.setSpacing(10)

            password_label = QLabel("Пароль:")
            password_label.setMinimumWidth(90)
            password_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            password_input = QLineEdit(password_value)
            password_input.setEchoMode(QLineEdit.Password)
            password_input.setPlaceholderText(password_placeholder)
            password_input.setMinimumHeight(40)
            password_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            password_row.addWidget(password_label)
            password_row.addWidget(password_input, stretch=1)
            root.addLayout(password_row)

            return login_input, password_input

        add_section_title("ОТРС")

        self.enabled = QCheckBox("Подставлять сохранённые доступы ОТРС")
        self.enabled.setChecked(duty.get("otrs_login_enabled", False))
        root.addWidget(self.enabled)

        self.login, self.password = add_labeled_password_pair(
            otrs_credentials.get("login", ""),
            otrs_credentials.get("password", ""),
            "Логин ОТРС",
            "Пароль ОТРС",
        )

        add_section_title("Zabbix")

        enabled_zabbix_instances = [
            instance
            for instance in self.config.get("zabbix_instances", [])
            if instance.get("enabled", True)
        ]

        first_saved_zabbix = {}
        for instance in enabled_zabbix_instances:
            saved = self.saved_zabbix_credentials.get(instance.get("id"), {})
            if saved.get("login") or saved.get("password"):
                first_saved_zabbix = saved
                break

        self.zabbix_common_login, self.zabbix_common_password = add_labeled_password_pair(
            first_saved_zabbix.get("login", ""),
            first_saved_zabbix.get("password", ""),
            "Логин Zabbix",
            "Пароль Zabbix",
        )

        self.zabbix_inputs = {
            instance.get("id"): {
                "login": self.zabbix_common_login,
                "password": self.zabbix_common_password,
                "name": instance.get("name", instance.get("id")),
            }
            for instance in enabled_zabbix_instances
            if instance.get("id")
        }

        if not self.zabbix_inputs:
            empty = QLabel("В config.json нет включённых Zabbix-инстансов.")
            empty.setWordWrap(True)
            root.addWidget(empty)

        add_section_title("Redmine")

        redmine_settings = ensure_live_monitor_defaults(self.config)
        redmine_url_row = QHBoxLayout()
        redmine_url_row.setSpacing(10)
        redmine_url_label = QLabel("Login URL (Настройки → Ссылки):")
        redmine_url_label.setMinimumWidth(90)
        redmine_url_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.redmine_login_url_input = QLineEdit(str(redmine_settings.get("redmine_login_url") or DEFAULT_REDMINE_LOGIN_URL))
        self.redmine_login_url_input.setPlaceholderText(DEFAULT_REDMINE_LOGIN_URL)
        self.redmine_login_url_input.setReadOnly(True)
        self.redmine_login_url_input.setMinimumHeight(40)
        self.redmine_login_url_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        redmine_url_row.addWidget(redmine_url_label)
        redmine_url_row.addWidget(self.redmine_login_url_input, stretch=1)
        root.addLayout(redmine_url_row)

        self.redmine_save_credentials_checkbox = QCheckBox("Сохранять логин и пароль Redmine")
        self.redmine_save_credentials_checkbox.setChecked(bool(redmine_settings.get("redmine_save_credentials", False)))
        root.addWidget(self.redmine_save_credentials_checkbox)

        self.redmine_username_input, self.redmine_password_input = add_labeled_password_pair(
            str(redmine_settings.get("redmine_username") or ""),
            str(redmine_settings.get("redmine_password") or ""),
            "Логин Redmine",
            "Пароль Redmine",
        )

        add_section_title("Сервисы")

        service_settings = ensure_service_checks_defaults(self.config)
        service_groups = service_settings.get("credential_groups", [])

        for group in service_groups:
            group_id = group.get("id", "")
            group_name = group.get("name", group_id)
            creds = load_service_group_credentials(group_id)

            add_caption(group_name)

            login_input, password_input = add_labeled_password_pair(
                creds.get("login", ""),
                creds.get("password", ""),
                "Введите логин",
                "Введите пароль",
            )

            self.service_group_inputs[group_id] = {
                "login": login_input,
                "password": password_input,
                "name": group_name,
            }

        if not service_groups:
            empty = QLabel("Сервисы для отдельного доступа ещё не настроены администратором.")
            empty.setWordWrap(True)
            root.addWidget(empty)

        buttons = QHBoxLayout()

        save = QPushButton("Сохранить все доступы")
        save.clicked.connect(self.save)

        clear = QPushButton("Удалить сохранённые Zabbix-пароли")
        clear.clicked.connect(self.clear_zabbix_credentials)

        buttons.addWidget(save)
        buttons.addWidget(clear)
        buttons.addStretch()

        root.addLayout(buttons)
        root.addStretch(1)

    def save(self):
        duty = self.config.setdefault("duty_mode", {})
        duty["otrs_login_enabled"] = self.enabled.isChecked()
        for legacy_key in ("otrs_" + "login", "otrs_" + "password"):
            duty.pop(legacy_key, None)

        credentials = load_saved_credentials()
        credentials.pop(LEGACY_OTRS_CREDENTIALS_KEY, None)
        credentials[OTRS_CREDENTIALS_KEY] = {
            "login": self.login.text().strip(),
            "password": self.password.text(),
        }

        for zabbix_id, widgets in self.zabbix_inputs.items():
            credentials[zabbix_id] = {
                "login": widgets["login"].text().strip(),
                "password": widgets["password"].text(),
            }

        save_credentials(credentials)

        redmine_settings = ensure_live_monitor_defaults(self.config)
        redmine_settings["redmine_login_url"] = self.redmine_login_url_input.text().strip() or DEFAULT_REDMINE_LOGIN_URL
        redmine_settings["redmine_save_credentials"] = self.redmine_save_credentials_checkbox.isChecked()
        if redmine_settings["redmine_save_credentials"]:
            redmine_settings["redmine_username"] = self.redmine_username_input.text().strip()
            redmine_settings["redmine_password"] = self.redmine_password_input.text()
        else:
            redmine_settings["redmine_username"] = ""
            redmine_settings["redmine_password"] = ""

        service_settings = ensure_service_checks_defaults(self.config)
        service_ids_by_group = {
            group.get("id", ""): list(group.get("service_ids", []) or [])
            for group in service_settings.get("credential_groups", [])
        }

        for group_id, widgets in self.service_group_inputs.items():
            group_login = widgets["login"].text().strip()
            group_password = widgets["password"].text()

            save_service_group_credentials(group_id, group_login, group_password)

            # Безопасная совместимость:
            # движок проверки сервисов остаётся старым и берёт service_check::<service_id>.
            # Профиль только раскладывает логин/пароль группы по сервисам этой группы.
            for service_id in service_ids_by_group.get(group_id, []):
                save_service_credentials(service_id, group_login, group_password)

        save_config(self.config)
        QMessageBox.information(self, "Профиль", "Доступы сохранены.")

    def clear_zabbix_credentials(self):
        credentials = load_saved_credentials()

        for zabbix_id in self.zabbix_inputs:
            credentials.pop(zabbix_id, None)

        save_credentials(credentials)

        for widgets in self.zabbix_inputs.values():
            widgets["login"].clear()
            widgets["password"].clear()

        QMessageBox.information(self, "Профиль", "Сохранённые Zabbix-пароли удалены.")

    def logout_from_profile(self):
        if self.logout_callback:
            self.logout_callback()
        else:
            QMessageBox.warning(
                self,
                "Выход из аккаунта",
                "Обработчик выхода не подключён. Перезапустите приложение и попробуйте снова.",
            )


class ThemeWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)

        root = QVBoxLayout(self)

        hint = QLabel("Все темы приложения теперь находятся здесь, на Главной странице.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.combo = NoWheelComboBox()
        for theme_name, theme_label in get_available_themes():
            self.combo.addItem(theme_label, theme_name)

        current = self.config.setdefault("settings", {}).get("theme", "mass_effect")
        idx = self.combo.findData(current)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)

        form = QFormLayout()
        form.addRow("Тема:", self.combo)
        root.addLayout(form)

        save = QPushButton("Сохранить тему")
        save.clicked.connect(self.save)
        root.addWidget(save)

        hint2 = QLabel("Для полного применения темы приложение предложит перезапуск.")
        hint2.setWordWrap(True)
        root.addWidget(hint2)
        root.addStretch()

    def save(self):
        self.config.setdefault("settings", {})["theme"] = self.combo.currentData()
        save_config(self.config)
        request_application_restart(
            self,
            "Изменена тема оформления. Для полного применения темы нужен перезапуск."
        )


class NotesWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)
        root = QVBoxLayout(self)
        self.text = QTextEdit()
        self.text.setPlainText(self.config.setdefault("settings", {}).get("home_notes", ""))
        self.text.setPlaceholderText("Рабочие заметки, ссылки, подсказки по дежурству...")
        root.addWidget(self.text, stretch=1)
        save = QPushButton("Сохранить заметки")
        save.clicked.connect(self.save)
        root.addWidget(save)

    def save(self):
        self.config.setdefault("settings", {})["home_notes"] = self.text.toPlainText()
        save_config(self.config)
        QMessageBox.information(self, "Заметки", "Сохранено.")



class SettingsTransferWidget(QWidget):
    """Export/import common app settings and personal credentials separately."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)

        root = QVBoxLayout(self)

        settings_group = QGroupBox("Общие настройки приложения")
        settings_layout = QVBoxLayout(settings_group)

        settings_hint = QLabel(
            "Экспорт переносит продукты, страницы, графики, duty triggers, шаблоны и тему. "
            "Логины, пароли, токены, cookie, session и другие auth-данные не сохраняются."
        )
        settings_hint.setWordWrap(True)
        settings_layout.addWidget(settings_hint)

        settings_actions = QHBoxLayout()
        export_button = QPushButton("Экспорт общих настроек")
        export_button.clicked.connect(self.export_settings)
        import_button = QPushButton("Импорт общих настроек")
        import_button.clicked.connect(self.import_settings)
        settings_actions.addWidget(export_button)
        settings_actions.addWidget(import_button)
        settings_actions.addStretch(1)
        settings_layout.addLayout(settings_actions)

        profile_group = QGroupBox("Личный профиль / доступы")
        profile_layout = QVBoxLayout(profile_group)

        profile_hint = QLabel(
            "Экспорт профиля переносит только ваши сохранённые доступы: ОТРС, Zabbix, "
            "отдельные доступы сервисов и группы сервисов. Он не меняет продукты, селекторы, "
            "признаки входа, дежурку, шаблоны и общие настройки. Файл профиля содержит личные "
            "доступы — храните его как секретный."
        )
        profile_hint.setWordWrap(True)
        profile_layout.addWidget(profile_hint)

        profile_actions = QHBoxLayout()
        export_profile = QPushButton("Экспорт моего профиля")
        export_profile.clicked.connect(self.export_profile)
        import_profile = QPushButton("Импорт моего профиля")
        import_profile.clicked.connect(self.import_profile)
        profile_actions.addWidget(export_profile)
        profile_actions.addWidget(import_profile)
        profile_actions.addStretch(1)
        profile_layout.addLayout(profile_actions)

        root.addWidget(settings_group)
        root.addWidget(profile_group)
        root.addStretch(1)

    def export_settings(self):
        default_path = CONFIG_PATH.parent / default_settings_export_filename()
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт общих настроек",
            str(default_path),
            "JSON (*.json);;Все файлы (*)",
        )
        if not selected_path:
            return

        try:
            destination = export_settings_file(self.config, selected_path)
            QMessageBox.information(self, "Экспорт общих настроек", f"Настройки экспортированы:\n{destination}")
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка экспорта", f"Не удалось экспортировать настройки:\n{exc}")

    def import_settings(self):
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Импорт общих настроек",
            str(CONFIG_PATH.parent),
            "JSON (*.json);;Все файлы (*)",
        )
        if not selected_path:
            return

        try:
            load_settings_export(selected_path)
        except Exception:
            QMessageBox.warning(
                self,
                "Ошибка импорта",
                "Ошибка импорта: файл повреждён или имеет неподдерживаемый формат.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Импорт общих настроек",
            "Текущие общие настройки будут заменены импортированными.\n"
            "Личные доступы не будут изменены.\n"
            "Перед импортом будет создана резервная копия текущего config.\n"
            "Продолжить?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            import_settings_file(selected_path)
            QMessageBox.information(
                self,
                "Импорт общих настроек",
                "Общие настройки импортированы.\nПерезапустите приложение для применения изменений.",
            )
        except Exception:
            QMessageBox.warning(
                self,
                "Ошибка импорта",
                "Ошибка импорта: файл повреждён или имеет неподдерживаемый формат.",
            )

    def export_profile(self):
        default_path = CONFIG_PATH.parent / default_encrypted_profile_export_filename()
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт моего профиля",
            str(default_path),
            "Защищённый профиль Око (*.okoenc);;Все файлы (*)",
        )
        if not selected_path:
            return

        password, ok = QInputDialog.getText(
            self,
            "Пароль профиля",
            "Задайте пароль для файла .okoenc:",
            QLineEdit.Password,
        )
        if not ok:
            return
        if not password:
            QMessageBox.warning(self, "Экспорт моего профиля", "Пароль файла профиля не может быть пустым.")
            return

        confirm, ok = QInputDialog.getText(
            self,
            "Повтор пароля",
            "Повторите пароль для файла .okoenc:",
            QLineEdit.Password,
        )
        if not ok:
            return
        if password != confirm:
            QMessageBox.warning(self, "Экспорт моего профиля", "Пароли не совпадают.")
            return

        try:
            destination = export_profile_credentials_encrypted_file(selected_path, password)
            QMessageBox.information(
                self,
                "Экспорт моего профиля",
                f"Личный профиль экспортирован:\\n{destination}\\n\\nДля импорта потребуется заданный пароль.",
            )
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка экспорта профиля", f"Не удалось экспортировать профиль:\\n{exc}")

    def import_profile(self):
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Импорт моего профиля",
            str(CONFIG_PATH.parent),
            "Защищённый профиль Око (*.okoenc);;Все файлы (*)",
        )
        if not selected_path:
            return

        answer = QMessageBox.question(
            self,
            "Импорт моего профиля",
            "Будут импортированы только личные доступы.\\n"
            "Продукты, селекторы, признаки входа, дежурка, шаблоны и общие настройки не изменятся.\\n"
            "Существующие доступы с такими же ключами будут заменены.\\n"
            "Продолжить?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        password, ok = QInputDialog.getText(
            self,
            "Пароль профиля",
            "Введите пароль от файла .okoenc:",
            QLineEdit.Password,
        )
        if not ok:
            return
        if not password:
            QMessageBox.warning(self, "Импорт моего профиля", "Пароль файла профиля не может быть пустым.")
            return

        try:
            count = import_profile_credentials_encrypted_file(selected_path, password)
            QMessageBox.information(
                self,
                "Импорт моего профиля",
                f"Личный профиль импортирован. Обновлено записей доступов: {count}.\\n"
                "Для применения в уже открытых вкладках перезапустите приложение.",
            )
        except Exception:
            QMessageBox.warning(
                self,
                "Ошибка импорта профиля",
                "Не удалось импортировать профиль. Проверьте пароль или выберите корректный файл .okoenc.",
            )


class TemplatesWidget(QWidget):
    """Редактор пользовательских шаблонов без хранения credentials."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)
        ensure_templates_defaults(self.config)

        root = QVBoxLayout(self)
        hint = QLabel(
            "Шаблоны хранят только тексты, URL и идентификаторы настроек. "
            "Не сохраняйте здесь пароли, токены, cookie, credentials и приватные ключи."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        variables_hint = QLabel(
            "Переменные можно вставлять в текст шаблона. "
            "При создании заметки или задачи они будут автоматически заменены на реальные значения."
        )
        variables_hint.setWordWrap(True)
        root.addWidget(variables_hint)

        tabs = QHBoxLayout()
        self.stack = QStackedWidget()
        self.tab_buttons = []
        for title, builder in [
            ("Заметки ОТРС", self._build_otrs_tab),
            ("ОТРС: Проверка сервисов", self._build_service_otrs_tab),
            ("Задачи Redmine", self._build_redmine_tab),
            ("Переменные", self._build_variables_tab),
            ("Примеры", self._build_examples_tab),
        ]:
            button = QPushButton(title)
            button.setObjectName("SecondaryAction")
            button.clicked.connect(lambda checked=False, name=title: self.open_tab(name))
            tabs.addWidget(button)
            self.tab_buttons.append((title, button))
            self.stack.addWidget(builder())
        tabs.addStretch(1)
        root.addLayout(tabs)
        root.addWidget(self.stack, stretch=1)
        self.open_tab("Заметки ОТРС")

    def open_tab(self, title):
        for index, (name, button) in enumerate(self.tab_buttons):
            is_current = name == title
            button.setEnabled(not is_current)
            if is_current:
                self.stack.setCurrentIndex(index)

    def _build_otrs_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        templates = ensure_templates_defaults(self.config)
        current = templates[OTRS_GRAPH_CHECK_TEMPLATE_KEY]

        form = QFormLayout()
        self.otrs_name_input = QLineEdit(current.get("name", ""))
        self.otrs_text_input = QTextEdit()
        self.otrs_text_input.setPlainText(current.get("text", ""))
        self.otrs_text_input.setMinimumHeight(260)
        form.addRow("Название шаблона:", self.otrs_name_input)
        form.addRow("Текст шаблона:", self.otrs_text_input)
        layout.addLayout(form)

        actions = QHBoxLayout()
        save_button = QPushButton("Сохранить шаблон ОТРС")
        save_button.setObjectName("PrimaryAction")
        save_button.clicked.connect(self.save_otrs_template)
        preview_button = QPushButton("Предпросмотр")
        preview_button.clicked.connect(self.preview_otrs_template)
        reset_button = QPushButton("Сбросить по умолчанию")
        reset_button.clicked.connect(self.reset_otrs_template)
        actions.addWidget(save_button)
        actions.addWidget(preview_button)
        actions.addWidget(reset_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        layout.addWidget(self._readonly_box("Доступные переменные", variable_details_text(OTRS_VARIABLE_DETAILS), minimum_height=220))
        layout.addWidget(self._readonly_box("Пример", OTRS_TEMPLATE_EXAMPLE))
        return page


    def _build_service_otrs_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        templates = ensure_templates_defaults(self.config)
        current = templates[OTRS_SERVICE_CHECK_TEMPLATE_KEY]

        form = QFormLayout()
        self.service_otrs_name_input = QLineEdit(current.get("name", ""))
        self.service_otrs_text_input = QTextEdit()
        self.service_otrs_text_input.setPlainText(current.get("text", ""))
        self.service_otrs_text_input.setMinimumHeight(260)
        form.addRow("Название шаблона:", self.service_otrs_name_input)
        form.addRow("Текст шаблона:", self.service_otrs_text_input)
        layout.addLayout(form)

        actions = QHBoxLayout()
        save_button = QPushButton("Сохранить шаблон проверки сервисов")
        save_button.setObjectName("PrimaryAction")
        save_button.clicked.connect(self.save_service_otrs_template)
        reset_button = QPushButton("Сбросить по умолчанию")
        reset_button.clicked.connect(self.reset_service_otrs_template)
        actions.addWidget(save_button)
        actions.addWidget(reset_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        layout.addWidget(self._readonly_box("Доступные переменные", variable_details_text(SERVICE_CHECK_VARIABLE_DETAILS), minimum_height=220))
        layout.addWidget(self._readonly_box("Пример", DEFAULT_OTRS_SERVICE_CHECK_TEMPLATE_TEXT.strip()))
        return page

    def _build_redmine_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        templates = ensure_templates_defaults(self.config)
        current = templates[REDMINE_TASK_TEMPLATE_KEY]
        special = templates[REDMINE_SPECIAL_TASK_TEMPLATE_KEY]

        form = QFormLayout()
        self.redmine_create_url_input = QLineEdit(get_duty_link(self.config, "redmine_create_url") or current.get("create_url", ""))
        self.redmine_create_url_input.setReadOnly(True)
        self.redmine_subject_input = QLineEdit(current.get("subject_template", ""))
        self.redmine_description_input = QTextEdit()
        self.redmine_description_input.setPlainText(current.get("description_template", ""))
        self.redmine_description_input.setMinimumHeight(220)
        self.redmine_tracker_input = QLineEdit(str(current.get("tracker_id", "")))
        self.redmine_priority_input = QLineEdit(str(current.get("priority_id", "")))
        self.redmine_project_input = QLineEdit(current.get("project", ""))
        self.redmine_special_subject_input = QLineEdit(special.get("subject_template", ""))
        self.redmine_special_description_input = QTextEdit()
        self.redmine_special_description_input.setPlainText(special.get("description_template", ""))
        self.redmine_special_description_input.setMinimumHeight(180)

        form.addRow("URL создания задачи Redmine (Настройки → Ссылки):", self.redmine_create_url_input)
        form.addRow("Шаблон темы:", self.redmine_subject_input)
        form.addRow("Шаблон описания:", self.redmine_description_input)
        form.addRow("tracker_id:", self.redmine_tracker_input)
        form.addRow("priority_id:", self.redmine_priority_input)
        form.addRow("project identifier/project URL:", self.redmine_project_input)
        form.addRow("Тема спец. триггеров:", self.redmine_special_subject_input)
        form.addRow("Описание спец. триггеров:", self.redmine_special_description_input)
        layout.addLayout(form)

        actions = QHBoxLayout()
        save_button = QPushButton("Сохранить шаблон Redmine")
        save_button.setObjectName("PrimaryAction")
        save_button.clicked.connect(self.save_redmine_template)
        preview_button = QPushButton("Предпросмотр")
        preview_button.clicked.connect(self.preview_redmine_template)
        reset_button = QPushButton("Сбросить по умолчанию")
        reset_button.clicked.connect(self.reset_redmine_template)
        actions.addWidget(save_button)
        actions.addWidget(preview_button)
        actions.addWidget(reset_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        layout.addWidget(self._readonly_box("Доступные переменные", variable_details_text(REDMINE_GRAPH_VARIABLE_DETAILS), minimum_height=260))
        redmine_warning = QLabel("Для специальных триггеров используйте обычные ссылки ({special_graph_links}); inline-картинки вида !url! не вставляются автоматически.")
        redmine_warning.setWordWrap(True)
        layout.addWidget(redmine_warning)
        layout.addWidget(self._readonly_box("Примеры вставки графиков", REDMINE_COLLAPSE_EXAMPLE + "\n" + REDMINE_ALL_GRAPHS_EXAMPLE))
        period_hint = QLabel("Скриншоты графиков для Redmine должны формироваться за период 3 часа.")
        period_hint.setWordWrap(True)
        layout.addWidget(period_hint)
        return page

    def _build_variables_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._readonly_box("Переменные заметки ОТРС", variable_details_text(OTRS_VARIABLE_DETAILS), minimum_height=260))
        layout.addWidget(self._readonly_box("Переменные проверки сервисов", variable_details_text(SERVICE_CHECK_VARIABLE_DETAILS), minimum_height=260))
        layout.addWidget(self._readonly_box("Переменные Redmine для графиков", variable_details_text(REDMINE_GRAPH_VARIABLE_DETAILS), minimum_height=300))
        redmine_warning = QLabel("Для специальных триггеров используйте обычные ссылки ({special_graph_links}); inline-картинки вида !url! не вставляются автоматически.")
        redmine_warning.setWordWrap(True)
        layout.addWidget(redmine_warning)
        layout.addStretch(1)
        return page

    def _build_examples_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._readonly_box("Пример заметки ОТРС", OTRS_TEMPLATE_EXAMPLE))
        layout.addWidget(self._readonly_box("Пример Redmine collapse-картинки", REDMINE_COLLAPSE_EXAMPLE))
        layout.addWidget(self._readonly_box("Пример всех графиков для Redmine", REDMINE_ALL_GRAPHS_EXAMPLE))
        period_hint = QLabel("Скриншоты графиков для Redmine должны формироваться за период 3 часа.")
        period_hint.setWordWrap(True)
        layout.addWidget(period_hint)
        layout.addStretch(1)
        return page

    def _readonly_box(self, title, text, minimum_height=120):
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(text)
        editor.setMinimumHeight(minimum_height)
        layout.addWidget(editor)
        return box

    def _show_preview_dialog(self, title, text):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(760, 560)
        layout = QVBoxLayout(dialog)
        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(text)
        layout.addWidget(editor, stretch=1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        copy_button = buttons.addButton("Скопировать", QDialogButtonBox.ActionRole)
        buttons.rejected.connect(dialog.reject)
        copy_button.clicked.connect(lambda: QApplication.clipboard().setText(editor.toPlainText()))
        layout.addWidget(buttons)
        dialog.exec()

    def preview_otrs_template(self):
        preview_text = preview_otrs_template(self.otrs_text_input.toPlainText())
        self._show_preview_dialog("Предпросмотр заметки ОТРС", preview_text)

    def preview_redmine_template(self):
        preview_text = preview_redmine_template(
            self.redmine_subject_input.text(),
            self.redmine_description_input.toPlainText(),
        )
        self._show_preview_dialog("Предпросмотр задачи Redmine", preview_text)

    def confirm_template_reset(self):
        answer = QMessageBox.question(
            self,
            "Сбросить шаблон?",
            "Сбросить шаблон?\n"
            "Текущий текст будет заменён шаблоном по умолчанию.\n"
            "Продолжить?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    def save_otrs_template(self):
        templates = ensure_templates_defaults(self.config)
        templates[OTRS_GRAPH_CHECK_TEMPLATE_KEY] = {
            "name": self.otrs_name_input.text().strip() or "Заметка ОТРС: проверка графиков",
            "text": self.otrs_text_input.toPlainText(),
        }
        save_config(self.config)
        QMessageBox.information(self, "Шаблоны", "Шаблон заметки ОТРС сохранён.")

    def reset_otrs_template(self):
        if not self.confirm_template_reset():
            return
        template = reset_otrs_graph_check_template(self.config)
        self.otrs_name_input.setText(template.get("name", ""))
        self.otrs_text_input.setPlainText(template.get("text", ""))
        save_config(self.config)
        QMessageBox.information(self, "Шаблоны", "Шаблон заметки ОТРС сброшен по умолчанию.")


    def save_service_otrs_template(self):
        templates = ensure_templates_defaults(self.config)
        templates[OTRS_SERVICE_CHECK_TEMPLATE_KEY] = {
            "name": self.service_otrs_name_input.text().strip() or "ОТРС: Проверка сервисов",
            "text": self.service_otrs_text_input.toPlainText(),
        }
        save_config(self.config)
        QMessageBox.information(self, "Шаблоны", "Шаблон заметки проверки сервисов сохранён.")

    def reset_service_otrs_template(self):
        if not self.confirm_template_reset():
            return
        template = reset_otrs_service_check_template(self.config)
        self.service_otrs_name_input.setText(template.get("name", ""))
        self.service_otrs_text_input.setPlainText(template.get("text", ""))
        save_config(self.config)
        QMessageBox.information(self, "Шаблоны", "Шаблон проверки сервисов сброшен по умолчанию.")

    def save_redmine_template(self):
        templates = ensure_templates_defaults(self.config)
        current = templates[REDMINE_TASK_TEMPLATE_KEY]
        special = templates[REDMINE_SPECIAL_TASK_TEMPLATE_KEY]
        current.update({
            "name": "Задача Redmine",
            "create_url": self.redmine_create_url_input.text().strip(),
            "subject_template": self.redmine_subject_input.text().strip(),
            "description_template": self.redmine_description_input.toPlainText(),
            "tracker_id": self.redmine_tracker_input.text().strip(),
            "priority_id": self.redmine_priority_input.text().strip(),
            "project": self.redmine_project_input.text().strip(),
        })
        special = templates[REDMINE_SPECIAL_TASK_TEMPLATE_KEY]
        special.update({
            "name": "Задача Redmine: специальные триггеры с графиками",
            "create_url": self.redmine_create_url_input.text().strip(),
            "subject_template": self.redmine_special_subject_input.text().strip(),
            "description_template": self.redmine_special_description_input.toPlainText(),
            "tracker_id": self.redmine_tracker_input.text().strip(),
            "priority_id": self.redmine_priority_input.text().strip(),
            "project": self.redmine_project_input.text().strip(),
        })
        save_config(self.config)
        QMessageBox.information(self, "Шаблоны", "Шаблон задачи Redmine сохранён.")

    def reset_redmine_template(self):
        if not self.confirm_template_reset():
            return
        template = reset_redmine_task_template(self.config)
        special = reset_redmine_special_task_template(self.config)
        self.redmine_create_url_input.setText(template.get("create_url", ""))
        self.redmine_subject_input.setText(template.get("subject_template", ""))
        self.redmine_description_input.setPlainText(template.get("description_template", ""))
        self.redmine_tracker_input.setText(str(template.get("tracker_id", "")))
        self.redmine_priority_input.setText(str(template.get("priority_id", "")))
        self.redmine_project_input.setText(template.get("project", ""))
        self.redmine_special_subject_input.setText(special.get("subject_template", ""))
        self.redmine_special_description_input.setPlainText(special.get("description_template", ""))
        save_config(self.config)
        QMessageBox.information(self, "Шаблоны", "Шаблон задачи Redmine сброшен по умолчанию.")


class ChangelogWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText(self.load_changelog())
        root.addWidget(self.text, stretch=1)

    def load_changelog(self):
        changelog_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "CHANGELOG.md")
        )
        if not os.path.exists(changelog_path):
            return "Файл CHANGELOG.md не найден."

        with open(changelog_path, "r", encoding="utf-8") as changelog_file:
            return changelog_file.read()




def is_admin_user(user):
    return str((user or {}).get("role", "") or "") in {ROLE_OWNER, ROLE_ADMIN}


class AdministrationWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.current_user = self.config.get("_current_user") or {}

        root = QVBoxLayout(self)
        root.setSpacing(10)

        title = QLabel("Администрирование")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        hint = QLabel(
            "Раздел доступен администраторам Око. Здесь создаются пользователи и дополнительные администраторы. "
            "Пароли входа в Око не показываются открытым текстом, можно только задать новый пароль. "
            "Защита не позволит отключить или понизить последнего администратора; для owner/admin права admin/developer сохраняются автоматически."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        current = QLabel(
            f"Текущий пользователь: {self.current_user.get('login', 'неизвестно')} "
            f"({self.current_user.get('role', 'без роли')})"
        )
        current.setWordWrap(True)
        root.addWidget(current)

        users_box = QGroupBox("Пользователи")
        users_layout = QVBoxLayout(users_box)

        self.user_select = QComboBox()
        self.user_select.currentIndexChanged.connect(self.load_selected_user)
        users_layout.addWidget(self.user_select)

        edit_form = QFormLayout()
        self.edit_display_name_input = QLineEdit()
        self.edit_role_input = QComboBox()
        self._fill_role_combo(self.edit_role_input)
        self.edit_active_input = QCheckBox("Активен")
        self.edit_active_input.setChecked(True)
        edit_form.addRow("Имя:", self.edit_display_name_input)
        edit_form.addRow("Роль:", self.edit_role_input)
        edit_form.addRow("Статус:", self.edit_active_input)
        users_layout.addLayout(edit_form)

        self.role_guard_hint = QLabel(
            "Owner/admin всегда сохраняют доступ к администрированию и режиму разработчика. "
            "Последнего администратора нельзя отключить или понизить."
        )
        self.role_guard_hint.setWordWrap(True)
        users_layout.addWidget(self.role_guard_hint)

        self.permissions_list = QListWidget()
        for permission, title in SECTION_NAMES.items():
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, permission)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.permissions_list.addItem(item)
        users_layout.addWidget(QLabel("Доступные разделы:"))
        users_layout.addWidget(self.permissions_list)

        self.service_groups_list = QListWidget()
        self.service_groups_list.setToolTip("Группы доступов берутся из технических настроек проверки сервисов.")
        users_layout.addWidget(QLabel("Доступные группы сервисов:"))
        users_layout.addWidget(self.service_groups_list)

        user_actions = QHBoxLayout()
        update_button = QPushButton("Сохранить изменения пользователя")
        update_button.clicked.connect(self.update_selected_user)
        export_button = QPushButton("Экспортировать конфиг пользователя")
        export_button.clicked.connect(self.export_selected_user_config)
        user_actions.addWidget(update_button)
        user_actions.addWidget(export_button)
        user_actions.addStretch()
        users_layout.addLayout(user_actions)

        password_form = QFormLayout()
        self.reset_password_input = QLineEdit()
        self.reset_password_input.setEchoMode(QLineEdit.Password)
        self.reset_password_input.setPlaceholderText("Новый пароль входа в Око")
        self.reset_password_confirm_input = QLineEdit()
        self.reset_password_confirm_input.setEchoMode(QLineEdit.Password)
        self.reset_password_confirm_input.setPlaceholderText("Повторите новый пароль")
        password_form.addRow("Новый пароль:", self.reset_password_input)
        password_form.addRow("Повтор:", self.reset_password_confirm_input)
        users_layout.addLayout(password_form)

        reset_button = QPushButton("Сбросить пароль выбранному пользователю")
        reset_button.clicked.connect(self.reset_selected_user_password)
        users_layout.addWidget(reset_button)

        root.addWidget(users_box)

        create_box = QGroupBox("Создать пользователя")
        create_form = QFormLayout(create_box)

        self.new_login_input = QLineEdit()
        self.new_login_input.setPlaceholderText("login")
        self.new_display_name_input = QLineEdit()
        self.new_display_name_input.setPlaceholderText("Имя пользователя")
        self.new_password_input = QLineEdit()
        self.new_password_input.setEchoMode(QLineEdit.Password)
        self.new_password_input.setPlaceholderText("Пароль входа в Око")
        self.new_password_confirm_input = QLineEdit()
        self.new_password_confirm_input.setEchoMode(QLineEdit.Password)
        self.new_password_confirm_input.setPlaceholderText("Повторите пароль")
        self.new_role_input = QComboBox()
        self._fill_role_combo(self.new_role_input)

        create_form.addRow("Логин:", self.new_login_input)
        create_form.addRow("Имя:", self.new_display_name_input)
        create_form.addRow("Пароль:", self.new_password_input)
        create_form.addRow("Повтор:", self.new_password_confirm_input)
        create_form.addRow("Роль:", self.new_role_input)
        self.new_service_groups_list = QListWidget()
        self.new_service_groups_list.setToolTip("Выберите группы сервисов, которые будут доступны пользователю после создания.")
        create_form.addRow("Группы сервисов:", self.new_service_groups_list)
        self._reload_create_service_groups()

        create_button = QPushButton("Создать")
        create_button.clicked.connect(self.create_new_user)
        create_form.addRow("", create_button)

        root.addWidget(create_box)
        root.addStretch(1)

        self.refresh_users()

    def _fill_role_combo(self, combo):
        combo.clear()
        combo.addItem("Агент", ROLE_USER)
        combo.addItem("Custom", ROLE_CUSTOM)
        combo.addItem("Администратор", ROLE_ADMIN)
        combo.addItem("Владелец", ROLE_OWNER)

    def _set_combo_data(self, combo, value):
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return
        combo.setCurrentIndex(0)

    def _users(self):
        return load_users().get("users", [])

    def _selected_login(self):
        return self.user_select.currentData()

    def _find_user(self, login):
        wanted = str(login or "").casefold()
        for user in self._users():
            key = str(user.get("login_key") or user.get("login", "")).casefold()
            if key == wanted:
                return user
        return None

    def refresh_users(self):
        selected = self._selected_login()

        self.user_select.blockSignals(True)
        self.user_select.clear()

        for user in self._users():
            login = user.get("login", "")
            role = user.get("role", ROLE_USER)
            status = "активен" if user.get("active", True) else "отключён"
            self.user_select.addItem(f"{login} — {role} — {status}", login)

        self.user_select.blockSignals(False)

        if selected:
            for index in range(self.user_select.count()):
                if self.user_select.itemData(index) == selected:
                    self.user_select.setCurrentIndex(index)
                    break

        self.load_selected_user()

    def load_selected_user(self):
        user = self._find_user(self._selected_login())
        if not user:
            self.edit_display_name_input.clear()
            self._set_combo_data(self.edit_role_input, ROLE_USER)
            self.edit_active_input.setChecked(False)
            self._set_checked_values(self.permissions_list, [])
            self._reload_service_groups([])
            return

        normalized = normalize_user_permissions(user)
        self.edit_display_name_input.setText(str(user.get("display_name", "") or user.get("login", "")))
        self._set_combo_data(self.edit_role_input, str(user.get("role", ROLE_USER)))
        self.edit_active_input.setChecked(bool(user.get("active", True)))
        self._set_checked_values(self.permissions_list, normalized.get("section_permissions", []))
        self._reload_service_groups(normalized.get("service_group_ids", []))


    def _checked_values(self, widget):
        values = []
        for index in range(widget.count()):
            item = widget.item(index)
            if item.checkState() == Qt.Checked:
                values.append(item.data(Qt.UserRole))
        return values

    def _set_checked_values(self, widget, values):
        allowed = set(values or [])
        for index in range(widget.count()):
            item = widget.item(index)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in allowed else Qt.Unchecked)

    def _reload_create_service_groups(self):
        if not hasattr(self, "new_service_groups_list"):
            return
        self.new_service_groups_list.clear()
        groups = (self.config.get("service_checks", {}) or {}).get("credential_groups", []) or []
        for group in groups:
            group_id = str(group.get("id", "") or "")
            if not group_id:
                continue
            item = QListWidgetItem(str(group.get("name", "") or group_id))
            item.setData(Qt.UserRole, group_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.new_service_groups_list.addItem(item)

    def _reload_service_groups(self, selected):
        selected = set(selected or [])
        self.service_groups_list.clear()
        groups = (self.config.get("service_checks", {}) or {}).get("credential_groups", []) or []
        for group in groups:
            group_id = str(group.get("id", "") or "")
            if not group_id:
                continue
            item = QListWidgetItem(str(group.get("name", "") or group_id))
            item.setData(Qt.UserRole, group_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if group_id in selected else Qt.Unchecked)
            self.service_groups_list.addItem(item)

    def export_selected_user_config(self):
        user = self._find_user(self._selected_login())
        if not user:
            QMessageBox.warning(self, "Администрирование", "Выберите пользователя.")
            return
        default_path = CONFIG_PATH.parent / f"oko_user_{user.get('login', 'agent')}_settings.json"
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт конфигурации пользователя",
            str(default_path),
            "JSON (*.json);;Все файлы (*)",
        )
        if not selected_path:
            return
        try:
            payload = build_user_settings_export(self.config, user)
            with open(selected_path, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            QMessageBox.warning(self, "Администрирование", f"Не удалось экспортировать конфиг пользователя:\n{exc}")
            return
        QMessageBox.information(self, "Администрирование", f"Конфиг пользователя экспортирован:\n{selected_path}")

    def create_new_user(self):
        login = self.new_login_input.text().strip()
        display_name = self.new_display_name_input.text().strip()
        password = self.new_password_input.text()
        confirm = self.new_password_confirm_input.text()
        role = self.new_role_input.currentData() or ROLE_USER

        if password != confirm:
            QMessageBox.warning(self, "Администрирование", "Пароли не совпадают.")
            return

        try:
            created = create_user(login, password, role=role, display_name=display_name)
            update_user(created.get("login", login), service_group_ids=self._checked_values(self.new_service_groups_list))
        except Exception as exc:
            QMessageBox.warning(self, "Администрирование", str(exc))
            return

        self.new_login_input.clear()
        self.new_display_name_input.clear()
        self.new_password_input.clear()
        self.new_password_confirm_input.clear()
        self._reload_create_service_groups()
        self.refresh_users()
        QMessageBox.information(self, "Администрирование", "Пользователь создан.")

    def update_selected_user(self):
        login = self._selected_login()
        if not login:
            QMessageBox.warning(self, "Администрирование", "Выберите пользователя.")
            return

        try:
            updated = update_user(
                login,
                role=self.edit_role_input.currentData() or ROLE_USER,
                active=self.edit_active_input.isChecked(),
                display_name=self.edit_display_name_input.text().strip(),
                section_permissions=self._checked_values(self.permissions_list),
                service_group_ids=self._checked_values(self.service_groups_list),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Администрирование", str(exc))
            return

        current_login = str((self.config.get("_current_user") or {}).get("login", "")).casefold()
        if current_login == str(updated.get("login", "")).casefold():
            self.config["_current_user"] = updated
            self.current_user = updated

        self.refresh_users()
        QMessageBox.information(self, "Администрирование", "Пользователь обновлён.")

    def reset_selected_user_password(self):
        login = self._selected_login()
        if not login:
            QMessageBox.warning(self, "Администрирование", "Выберите пользователя.")
            return

        password = self.reset_password_input.text()
        confirm = self.reset_password_confirm_input.text()

        if password != confirm:
            QMessageBox.warning(self, "Администрирование", "Пароли не совпадают.")
            return

        try:
            set_user_password(login, password)
        except Exception as exc:
            QMessageBox.warning(self, "Администрирование", str(exc))
            return

        self.reset_password_input.clear()
        self.reset_password_confirm_input.clear()
        QMessageBox.information(self, "Администрирование", "Пароль обновлён.")


class SettingsMenuWidget(QWidget):
    """Compact menu for the Settings container."""

    def __init__(self, section_names, open_section_callback, parent=None):
        super().__init__(parent)
        self.section_names = list(section_names or [])
        self.open_section_callback = open_section_callback

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        hint = QLabel("Выберите подраздел настроек.")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        root.addWidget(hint)
        root.addStretch(1)

        center_row = QHBoxLayout()
        center_row.addStretch(1)
        menu = QWidget()
        menu.setObjectName("MenuCard")
        menu.setStyleSheet("QWidget#MenuCard { background: rgba(14, 25, 38, 150); border: 1px solid rgba(101, 214, 255, 80); border-radius: 18px; }")
        menu.setMaximumWidth(560)
        menu.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        menu_layout = QVBoxLayout(menu)
        menu_layout.setSpacing(12)
        menu_layout.setContentsMargins(18, 18, 18, 18)
        for section_name in self.section_names:
            button = QPushButton(section_name)
            button.setObjectName("SecondaryAction")
            button.setMinimumHeight(52)
            button.setMaximumWidth(520)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.clicked.connect(lambda checked=False, name=section_name: self.open_section_callback(name))
            menu_layout.addWidget(button)
        center_row.addWidget(menu)
        illustration_path = Path(__file__).resolve().parent.parent / "assets" / "ui" / "home_illustration.png"
        if illustration_path.exists():
            illustration = QLabel()
            illustration.setObjectName("HomeIllustration")
            illustration.setPixmap(QPixmap(str(illustration_path)).scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            illustration.setAlignment(Qt.AlignCenter)
            center_row.addSpacing(28)
            center_row.addWidget(illustration)
        center_row.addStretch(1)
        root.addLayout(center_row)
        root.addStretch(2)

class AppSettingsWidget(QWidget):
    def __init__(self, config, logout_callback=None, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)
        self.logout_callback = logout_callback
        self.section_indexes = {}
        self.settings_menu_index = None
        self.settings_menu_sections = []

        root = QVBoxLayout(self)
        self.title = QLabel("Настройки")
        self.title.setObjectName("PageTitle")
        root.addWidget(self.title)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, stretch=1)

        self.update_widget = UpdateWidget(self.config, request_application_restart, show_title=False)
        candidates = [
            ("Перенос настроек", lambda: SettingsTransferWidget(self.config)),
            ("Настройки дежурки", lambda: DutyModeSettingsWidget(self.config, show_title=False)),
            ("Проверка сервисов", lambda: ServiceChecksSettingsWidget(self.config)),
            ("Шаблоны", lambda: TemplatesWidget(self.config)),
            ("Что нового", lambda: ChangelogWidget()),
            ("Тема", lambda: ThemeWidget(self.config)),
            ("Продукты и страницы", lambda: ProductsWidget(self.config)),
            ("Ссылки", lambda: LinksSettingsWidget(self.config)),
            ("Профиль", lambda: ProfileWidget(self.config, logout_callback=self.logout_callback)),
            ("Администрирование", lambda: AdministrationWidget(self.config)),
            ("Заметки", lambda: NotesWidget(self.config)),
            ("Обновление", lambda: self.update_widget),
            ("Режим разработчика", lambda: DeveloperModeGateWidget(self.config, DeveloperToolsWidget(self.config))),
        ]
        settings_section_names = [
            "Перенос настроек",
            "Настройки дежурки",
            "Проверка сервисов",
            "Шаблоны",
            "Что нового",
            "Тема",
            "Продукты и страницы",
            "Ссылки",
        ]
        for name, factory in candidates:
            if can_open_section(self.config.get("_current_user"), name):
                self.add_section(name, factory())
                if name in settings_section_names:
                    self.settings_menu_sections.append(name)

        self.settings_menu_index = self.stack.insertWidget(0, SettingsMenuWidget(self.settings_menu_sections, self.open_section))
        self.section_indexes = {name: index + 1 for name, index in self.section_indexes.items()}
        if can_open_section(self.config.get("_current_user"), "Настройки"):
            self.open_section(None)
        else:
            self.open_section(next(iter(self.section_indexes), None))

    def add_section(self, section_name, widget):
        self.section_indexes[section_name] = self.stack.addWidget(widget)

    def rebuild_profile_section(self):
        index = self.section_indexes.get("Профиль")
        if index is None:
            return
        old_widget = self.stack.widget(index)
        new_widget = ProfileWidget(self.config, logout_callback=self.logout_callback)
        self.stack.removeWidget(old_widget)
        old_widget.deleteLater()
        self.section_indexes["Профиль"] = self.stack.insertWidget(index, new_widget)

    def open_section(self, section_name=None):
        if not section_name or section_name == "Настройки":
            if self.settings_menu_index is None or not can_open_section(self.config.get("_current_user"), "Настройки"):
                QMessageBox.warning(self, "Нет доступа", "Недостаточно прав для открытия раздела.")
                return
            self.stack.setCurrentIndex(self.settings_menu_index)
            self.title.setText("Настройки")
            return
        if section_name == "Профиль":
            self.rebuild_profile_section()
        index = self.section_indexes.get(section_name)
        if index is None or not can_open_section(self.config.get("_current_user"), section_name):
            QMessageBox.warning(self, "Нет доступа", "Недостаточно прав для открытия раздела.")
            fallback = next(iter(self.section_indexes), "Профиль")
            index = self.section_indexes.get(fallback, 0)
            section_name = fallback
        self.stack.setCurrentIndex(index)
        self.title.setText(section_name)

    def check_for_updates(self, interactive=False, auto_start_install=False):
        if hasattr(self, "update_widget") and self.update_widget:
            self.update_widget.check_for_updates(
                interactive=interactive,
                auto_start_install=auto_start_install,
            )

    def cleanup(self):
        if hasattr(self, "update_widget") and hasattr(self.update_widget, "cleanup"):
            self.update_widget.cleanup()



class HomePageWidget(QWidget):
    SETTINGS_SECTIONS = [
        "Профиль",
        "Настройки",
        "Администрирование",
        "Режим разработчика",
        "Тема",
        "Обновление",
    ]

    def __init__(self, config, open_duty_callback=None, open_settings_callback=None, update_check_callback=None, logout_callback=None, exit_callback=None, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)
        self.setObjectName("HomeShell")
        self.open_duty_callback = open_duty_callback
        self.open_settings_callback = open_settings_callback
        self.update_check_callback = update_check_callback
        self.logout_callback = logout_callback
        self.exit_callback = exit_callback

        root = QVBoxLayout(self)

        title = QLabel(APP_NAME)
        title.setObjectName("HomeTitle")
        root.addWidget(title)

        subtitle = QLabel("Главная страница-меню: выбери нужный раздел настроек или перейди в режим дежурства.")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        root.addStretch(1)
        center_row = QHBoxLayout()
        center_row.addStretch(1)
        menu = QWidget()
        menu.setObjectName("HomeMenuCard")
        menu.setStyleSheet("QWidget#HomeMenuCard { background: rgba(14, 25, 38, 155); border: 1px solid rgba(101, 214, 255, 85); border-radius: 20px; }")
        menu.setMaximumWidth(560)
        menu.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        tiles = QVBoxLayout(menu)
        tiles.setSpacing(12)
        tiles.setContentsMargins(18, 18, 18, 18)
        for action_name in self.visible_main_actions():
            button = QPushButton(action_name)
            button.setObjectName("PrimaryAction" if action_name == "Перейти в режим дежурства" else "SecondaryAction")
            button.setMinimumHeight(56)
            button.setMaximumWidth(520)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.setToolTip(f"Открыть раздел «{action_name}»")
            button.clicked.connect(lambda checked=False, name=action_name: self.open_main_action(name))
            tiles.addWidget(button)
        center_row.addWidget(menu)
        center_row.addStretch(1)
        root.addLayout(center_row)
        root.addStretch(2)

        footer = QLabel(f"Версия: {APP_VERSION}\n{APP_DESCRIPTION}")
        footer.setObjectName("AppFooter")
        footer.setWordWrap(True)
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("font-size: 11px; opacity: 0.75; padding: 6px;")
        root.addWidget(footer)

        self.fade_in()

    def visible_main_actions(self):
        user = normalize_user_permissions(self.config.get("_current_user"))
        role = str(user.get("role") or "agent")
        if role == ROLE_OWNER:
            return ["Перейти в режим дежурства", "Профиль", "Настройки", "Администрирование", "Режим разработчика", "Обновление", "Выход"]
        if role == ROLE_ADMIN:
            return ["Перейти в режим дежурства", "Профиль", "Настройки", "Обновление", "Выход"]
        return ["Перейти в режим дежурства", "Профиль", "Тема", "Обновление", "Выход"]

    def open_main_action(self, action_name):
        if action_name == "Перейти в режим дежурства":
            self.open_duty()
            return
        if action_name == "Выход":
            if self.exit_callback:
                self.exit_callback()
            else:
                QApplication.quit()
            return
        if action_name == "Настройки":
            if not can_open_section(self.config.get("_current_user"), "Настройки"):
                QMessageBox.warning(self, "Нет доступа", "Недостаточно прав для открытия раздела.")
                return
            if self.open_settings_callback:
                self.open_settings_callback(None)
            return
        if not can_open_section(self.config.get("_current_user"), action_name):
            QMessageBox.warning(self, "Нет доступа", "Недостаточно прав для открытия раздела.")
            return
        if self.open_settings_callback:
            self.open_settings_callback(action_name)

    def open_duty(self):
        if self.open_duty_callback:
            self.open_duty_callback()

    def check_for_updates(self, interactive=False, auto_start_install=False):
        if self.update_check_callback:
            self.update_check_callback(
                interactive=interactive,
                auto_start_install=auto_start_install,
            )

    def fade_in(self):
        try:
            self.setWindowOpacity(0.0)
            self.anim = QPropertyAnimation(self, b"windowOpacity")
            self.anim.setDuration(450)
            self.anim.setStartValue(0.0)
            self.anim.setEndValue(1.0)
            self.anim.setEasingCurve(QEasingCurve.OutCubic)
            self.anim.start()
        except Exception:
            pass
