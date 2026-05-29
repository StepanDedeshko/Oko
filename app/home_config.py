
import json
import os
import sys

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from app.config import save_config
from app.credentials import load_saved_credentials, save_credentials, clear_saved_credentials
from app.theme import get_available_themes
from app.app_info import APP_NAME, APP_VERSION, APP_DESCRIPTION
from app.update_widget import UpdateWidget
from app.diagnostics_widget import DiagnosticsWidget


def clone(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def ensure_home_defaults(config):
    config.setdefault("products", [])
    settings = config.setdefault("settings", {})
    settings.setdefault("theme", "dark")
    settings.setdefault("home_notes", "")

    duty = config.setdefault("duty_mode", {})
    duty.setdefault("otrs_login_enabled", False)
    duty.setdefault("otrs_login", "")
    duty.setdefault("otrs_password", "")
    duty.setdefault("otrs_auto_submit_login", False)
    duty.setdefault("expected_ticket_subject", "Проверка Zabbix (Важных IT-сервисов)")
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



PAGE_TYPES = [
    ("Графики Zabbix", "graphs_grid"),
    ("Проблемы", "problems_page"),
    ("Страница с режимами", "mode_pages"),
    ("Простая страница/ссылка", "simple_page"),
    ("Обычная страница", "dashboard_page"),
]


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


class GraphRowWidget(QWidget):
    def __init__(self, graph=None, index=0, on_delete=None, parent=None):
        super().__init__(parent)
        self.on_delete = on_delete
        graph = graph or {}

        group = QGroupBox(f"График {index + 1}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(group)

        form = QFormLayout(group)
        self.enabled = QCheckBox("Включён")
        self.enabled.setChecked(graph.get("enabled", True))
        self.title = QLineEdit(graph.get("title", ""))
        self.title.setPlaceholderText("Название графика")
        self.url = QLineEdit(graph.get("url", ""))
        self.url.setPlaceholderText("URL графика")
        self.open_url = QLineEdit(graph.get("open_url") or graph.get("zabbix_url") or graph.get("external_url") or "")
        self.open_url.setPlaceholderText("URL кнопки «Открыть в Zabbix» — необязательно")
        self.use_time_range = QCheckBox("Применять период к URL графика")
        self.use_time_range.setChecked(graph.get("use_time_range", True))
        delete = QPushButton("Удалить график")
        delete.clicked.connect(self.delete_requested)

        form.addRow("", self.enabled)
        form.addRow("Название:", self.title)
        form.addRow("URL:", self.url)
        form.addRow("URL открытия:", self.open_url)
        form.addRow("", self.use_time_range)
        form.addRow("", delete)

    def delete_requested(self):
        if self.on_delete:
            self.on_delete(self)

    def value(self):
        graph = {
            "enabled": self.enabled.isChecked(),
            "title": self.title.text().strip(),
            "url": self.url.text().strip(),
            "use_time_range": self.use_time_range.isChecked(),
        }
        open_url = self.open_url.text().strip()
        if open_url:
            graph["open_url"] = open_url
        return graph


class ModeRowWidget(QWidget):
    def __init__(self, mode=None, index=0, on_delete=None, parent=None):
        super().__init__(parent)
        self.on_delete = on_delete
        mode = mode or {}

        group = QGroupBox(f"Режим {index + 1}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(group)

        form = QFormLayout(group)
        self.name = QLineEdit(mode.get("name") or mode.get("title") or f"Режим {index + 1}")
        self.name.setPlaceholderText("Например: День")
        self.url = QLineEdit(mode.get("url", "") if isinstance(mode, dict) else str(mode or ""))
        self.url.setPlaceholderText("URL режима")
        delete = QPushButton("Удалить режим")
        delete.clicked.connect(self.delete_requested)

        form.addRow("Название:", self.name)
        form.addRow("URL:", self.url)
        form.addRow("", delete)

    def delete_requested(self):
        if self.on_delete:
            self.on_delete(self)

    def value(self):
        return {
            "name": self.name.text().strip(),
            "url": self.url.text().strip(),
        }


class PageEditorDialog(QDialog):
    def __init__(self, page=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Страница")
        self.resize(820, 700)
        self.page = clone(page or {"name": "", "type": "simple_page", "url": "", "zabbix_id": "zbx_product_1", "enabled": True})
        self.graph_rows = []
        self.mode_rows = []

        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, stretch=1)

        body = QWidget()
        scroll.setWidget(body)
        body_layout = QVBoxLayout(body)

        form = QFormLayout()
        self.name_input = QLineEdit(self.page.get("name", ""))
        self.enabled_checkbox = QCheckBox("Страница включена")
        self.enabled_checkbox.setChecked(self.page.get("enabled", True))
        self.type_combo = QComboBox()
        for label, value in PAGE_TYPES:
            self.type_combo.addItem(label, value)
        idx = self.type_combo.findData(self.page.get("type", "simple_page"))
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.zabbix_id_input = QLineEdit(self.page.get("zabbix_id", "zbx_product_1"))
        self.url_input = QLineEdit(self.page.get("url", ""))
        self.url_input.setPlaceholderText("URL страницы, если применимо")

        form.addRow("Название страницы/раздела:", self.name_input)
        form.addRow("Состояние:", self.enabled_checkbox)
        form.addRow("Тип страницы:", self.type_combo)
        form.addRow("Zabbix profile:", self.zabbix_id_input)
        form.addRow("URL:", self.url_input)
        body_layout.addLayout(form)

        self.graphs_group = QGroupBox("Графики")
        graphs_layout = QVBoxLayout(self.graphs_group)
        add_graph = QPushButton("Добавить график")
        add_graph.clicked.connect(self.add_graph)
        graphs_layout.addWidget(add_graph)
        self.graphs_container = QWidget()
        self.graphs_layout = QVBoxLayout(self.graphs_container)
        graphs_layout.addWidget(self.graphs_container)
        body_layout.addWidget(self.graphs_group)

        self.modes_group = QGroupBox("Режимы")
        modes_layout = QVBoxLayout(self.modes_group)
        add_mode = QPushButton("Добавить режим")
        add_mode.clicked.connect(self.add_mode)
        modes_layout.addWidget(add_mode)
        self.modes_container = QWidget()
        self.modes_layout = QVBoxLayout(self.modes_container)
        modes_layout.addWidget(self.modes_container)
        body_layout.addWidget(self.modes_group)
        body_layout.addStretch()

        for graph in normalize_item_list(self.page.get("graphs", []), "title", "График"):
            self.add_graph(graph)
        for mode in normalize_item_list(self.page.get("modes", []), "name", "Режим"):
            self.add_mode(mode)

        self.type_combo.currentIndexChanged.connect(self.update_type_fields)
        self.update_type_fields()

        row = QHBoxLayout()
        save = QPushButton("Сохранить страницу")
        save.clicked.connect(self.accept_page)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        row.addWidget(save)
        row.addWidget(cancel)
        row.addStretch()
        root.addLayout(row)

    def add_graph(self, graph=None):
        row = GraphRowWidget(graph, len(self.graph_rows), self.remove_graph)
        self.graph_rows.append(row)
        self.graphs_layout.addWidget(row)

    def remove_graph(self, row):
        if QMessageBox.question(self, "Удалить", "Удалить этот график?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.graph_rows.remove(row)
        row.deleteLater()

    def add_mode(self, mode=None):
        row = ModeRowWidget(mode, len(self.mode_rows), self.remove_mode)
        self.mode_rows.append(row)
        self.modes_layout.addWidget(row)

    def remove_mode(self, row):
        if QMessageBox.question(self, "Удалить", "Удалить этот режим?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.mode_rows.remove(row)
        row.deleteLater()

    def update_type_fields(self):
        page_type = self.type_combo.currentData()
        self.graphs_group.setVisible(page_type == "graphs_grid")
        self.modes_group.setVisible(page_type == "mode_pages")
        self.url_input.setEnabled(page_type in {"simple_page", "dashboard_page", "problems_page"})

    def accept_page(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Страница", "Укажи название страницы.")
            return

        page_type = self.type_combo.currentData()
        page = clone(self.page)
        page.update({
            "name": name,
            "type": page_type,
            "enabled": self.enabled_checkbox.isChecked(),
            "zabbix_id": self.zabbix_id_input.text().strip() or "zbx_product_1",
        })

        url = self.url_input.text().strip()
        if url:
            page["url"] = url
        else:
            page.pop("url", None)

        if page_type == "graphs_grid":
            graphs = []
            for row in self.graph_rows:
                graph = row.value()
                if not graph["title"] and not graph["url"]:
                    continue
                if not graph["title"] or not graph["url"]:
                    QMessageBox.warning(self, "Графики", "У каждого графика должны быть название и URL.")
                    return
                graphs.append(graph)
            page["graphs"] = graphs
        else:
            page.pop("graphs", None)

        if page_type == "mode_pages":
            modes = []
            for row in self.mode_rows:
                mode = row.value()
                if not mode["name"] and not mode["url"]:
                    continue
                if not mode["name"] or not mode["url"]:
                    QMessageBox.warning(self, "Режимы", "У каждого режима должны быть название и URL.")
                    return
                modes.append(mode)
            page["modes"] = modes
        else:
            page.pop("modes", None)

        self.page = page
        self.accept()


class ProductEditorDialog(QDialog):
    def __init__(self, config, product_index=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.product_index = product_index
        self.setWindowTitle("Продукт")
        self.resize(780, 620)
        self.product = {"name": "", "enabled": True, "dashboards": []} if product_index is None else clone(config.get("products", [])[product_index])

        root = QVBoxLayout(self)
        form = QFormLayout()
        self.enabled_checkbox = QCheckBox("Продукт включён")
        self.enabled_checkbox.setChecked(self.product.get("enabled", True))
        self.name_input = QLineEdit(self.product.get("name", ""))
        self.name_input.setPlaceholderText("Название продукта")
        form.addRow("Название продукта:", self.name_input)
        form.addRow("Состояние:", self.enabled_checkbox)
        root.addLayout(form)

        header = QHBoxLayout()
        header.addWidget(QLabel("Страницы/разделы продукта"))
        header.addStretch()
        add = QPushButton("Добавить страницу")
        add.clicked.connect(self.add_page)
        header.addWidget(add)
        root.addLayout(header)

        self.pages_list = QListWidget()
        root.addWidget(self.pages_list, stretch=1)

        row = QHBoxLayout()
        edit = QPushButton("Редактировать выбранную страницу")
        edit.clicked.connect(self.edit_page)
        delete = QPushButton("Удалить страницу")
        delete.clicked.connect(self.delete_page)
        row.addWidget(edit)
        row.addWidget(delete)
        row.addStretch()
        root.addLayout(row)

        bottom = QHBoxLayout()
        save = QPushButton("Сохранить продукт")
        save.clicked.connect(self.save_product)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(save)
        bottom.addWidget(cancel)
        bottom.addStretch()
        root.addLayout(bottom)
        self.refresh()

    def refresh(self):
        self.pages_list.clear()
        for i, page in enumerate(self.product.get("dashboards", [])):
            item = QListWidgetItem(f"{page.get('name', 'Без названия')} — {page.get('type', '')}")
            item.setData(Qt.UserRole, i)
            self.pages_list.addItem(item)

    def selected_index(self):
        item = self.pages_list.currentItem()
        return None if not item else item.data(Qt.UserRole)

    def add_page(self):
        dialog = PageEditorDialog(parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.product.setdefault("dashboards", []).append(dialog.page)
            self.refresh()

    def edit_page(self):
        index = self.selected_index()
        if index is None:
            QMessageBox.warning(self, "Страница", "Выбери страницу.")
            return
        dialog = PageEditorDialog(self.product["dashboards"][index], parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.product["dashboards"][index] = dialog.page
            self.refresh()

    def delete_page(self):
        index = self.selected_index()
        if index is None:
            QMessageBox.warning(self, "Страница", "Выбери страницу.")
            return
        if QMessageBox.question(self, "Удалить", "Удалить выбранную страницу?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        del self.product["dashboards"][index]
        self.refresh()

    def save_product(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Продукт", "Укажи название продукта.")
            return
        self.product["name"] = name
        self.product["enabled"] = self.enabled_checkbox.isChecked()
        products = self.config.setdefault("products", [])
        if self.product_index is None:
            products.append(self.product)
        else:
            products[self.product_index] = self.product
        save_config(self.config)
        self.accept()


class ProductsWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        title = QLabel("Продукты и страницы")
        title.setObjectName("PageTitle")
        add = QPushButton("Добавить продукт")
        add.clicked.connect(self.add_product)
        top.addWidget(title)
        top.addStretch()
        top.addWidget(add)
        root.addLayout(top)

        hint = QLabel("Продукты, страницы, графики и режимы настраиваются через карточки. После изменения структуры перезапусти приложение, чтобы верхнее меню пересобралось.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.list_widget = QListWidget()
        root.addWidget(self.list_widget, stretch=1)

        buttons = QHBoxLayout()
        edit = QPushButton("Открыть карточку продукта")
        edit.clicked.connect(self.edit_product)
        delete = QPushButton("Удалить продукт")
        delete.clicked.connect(self.delete_product)
        buttons.addWidget(edit)
        buttons.addWidget(delete)
        buttons.addStretch()
        root.addLayout(buttons)
        self.refresh()

    def refresh(self):
        self.list_widget.clear()
        for i, product in enumerate(self.config.get("products", [])):
            count = len(product.get("dashboards", []))
            state = "вкл" if product.get("enabled", True) else "выкл"
            item = QListWidgetItem(f"Продукт: {product.get('name', 'Без названия')} — страниц: {count} — {state}")
            item.setData(Qt.UserRole, i)
            self.list_widget.addItem(item)

    def selected_index(self):
        item = self.list_widget.currentItem()
        return None if not item else item.data(Qt.UserRole)

    def add_product(self):
        dialog = ProductEditorDialog(self.config, None, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            request_application_restart(self, "Изменены продукты или страницы. Меню и страницы пересобираются при запуске.")

    def edit_product(self):
        index = self.selected_index()
        if index is None:
            QMessageBox.warning(self, "Продукт", "Выбери продукт.")
            return
        dialog = ProductEditorDialog(self.config, index, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            request_application_restart(self, "Изменены продукты или страницы. Меню и страницы пересобираются при запуске.")

    def delete_product(self):
        index = self.selected_index()
        if index is None:
            QMessageBox.warning(self, "Продукт", "Выбери продукт.")
            return
        name = self.config.get("products", [])[index].get("name", "Без названия")
        answer = QMessageBox.question(self, "Удалить", f"Удалить продукт «{name}»?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            del self.config["products"][index]
            save_config(self.config)
            self.refresh()
            request_application_restart(self, "Изменены продукты или страницы. Меню и страницы пересобираются при запуске.")


class ProfileWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)
        self.saved_zabbix_credentials = load_saved_credentials()
        self.zabbix_inputs = {}

        duty = self.config.setdefault("duty_mode", {})

        root = QVBoxLayout(self)
        title = QLabel("Профиль и доступы")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        otrs_box = QGroupBox("ОТРС")
        otrs_layout = QFormLayout(otrs_box)

        self.enabled = QCheckBox("Сохранять и подставлять логин/пароль ОТРС")
        self.enabled.setChecked(duty.get("otrs_login_enabled", False))

        self.login = QLineEdit(duty.get("otrs_login", ""))
        self.password = QLineEdit(duty.get("otrs_password", ""))
        self.password.setEchoMode(QLineEdit.Password)

        self.auto = QCheckBox("Автоматически нажимать «Вход»")
        self.auto.setChecked(duty.get("otrs_auto_submit_login", False))

        self.subject = QLineEdit(duty.get("expected_ticket_subject", "Проверка Zabbix (Важных IT-сервисов)"))

        otrs_layout.addRow("", self.enabled)
        otrs_layout.addRow("Логин ОТРС:", self.login)
        otrs_layout.addRow("Пароль ОТРС:", self.password)
        otrs_layout.addRow("", self.auto)
        otrs_layout.addRow("Ожидаемая тема задачи:", self.subject)

        root.addWidget(otrs_box)

        zbx_box = QGroupBox("Zabbix")
        zbx_layout = QVBoxLayout(zbx_box)

        zbx_hint = QLabel("Сохранённые доступы Zabbix.")
        zbx_hint.setWordWrap(True)
        zbx_hint.setMaximumHeight(34)
        zbx_layout.addWidget(zbx_hint)

        for instance in self.config.get("zabbix_instances", []):
            if not instance.get("enabled", True):
                continue

            zabbix_id = instance.get("id")
            name = instance.get("name", zabbix_id)
            saved = self.saved_zabbix_credentials.get(zabbix_id, {})

            group = QGroupBox(name)
            form = QFormLayout(group)

            login_input = QLineEdit(saved.get("login", ""))
            login_input.setPlaceholderText("Логин Zabbix")

            password_input = QLineEdit(saved.get("password", ""))
            password_input.setEchoMode(QLineEdit.Password)
            password_input.setPlaceholderText("Пароль Zabbix")

            form.addRow("URL:", QLabel(instance.get("base_url", "")))
            form.addRow("Логин:", login_input)
            form.addRow("Пароль:", password_input)

            self.zabbix_inputs[zabbix_id] = {
                "login": login_input,
                "password": password_input,
                "name": name,
            }

            zbx_layout.addWidget(group)

        if not self.zabbix_inputs:
            empty = QLabel("В config.json нет включённых Zabbix-инстансов.")
            empty.setWordWrap(True)
            zbx_layout.addWidget(empty)

        root.addWidget(zbx_box)

        buttons = QHBoxLayout()

        save = QPushButton("Сохранить все доступы")
        save.clicked.connect(self.save)

        clear = QPushButton("Удалить сохранённые Zabbix-пароли")
        clear.clicked.connect(self.clear_zabbix_credentials)

        buttons.addWidget(save)
        buttons.addWidget(clear)
        buttons.addStretch()

        root.addLayout(buttons)

    def save(self):
        duty = self.config.setdefault("duty_mode", {})
        duty["otrs_login_enabled"] = self.enabled.isChecked()
        duty["otrs_login"] = self.login.text().strip()
        duty["otrs_password"] = self.password.text()
        duty["otrs_auto_submit_login"] = self.auto.isChecked()
        duty["expected_ticket_subject"] = self.subject.text().strip() or "Проверка Zabbix (Важных IT-сервисов)"

        zabbix_credentials = {}

        for zabbix_id, widgets in self.zabbix_inputs.items():
            zabbix_credentials[zabbix_id] = {
                "login": widgets["login"].text().strip(),
                "password": widgets["password"].text(),
            }

        if zabbix_credentials:
            save_credentials(zabbix_credentials)

        save_config(self.config)
        QMessageBox.information(self, "Профиль", "Доступы сохранены.")

    def clear_zabbix_credentials(self):
        clear_saved_credentials()

        for widgets in self.zabbix_inputs.values():
            widgets["login"].clear()
            widgets["password"].clear()

        QMessageBox.information(self, "Профиль", "Сохранённые Zabbix-пароли удалены.")



class ThemeWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)

        root = QVBoxLayout(self)

        title = QLabel("Тема оформления")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        hint = QLabel("Все темы приложения теперь находятся здесь, на Главной странице.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.combo = QComboBox()
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
        title = QLabel("Заметки")
        title.setObjectName("PageTitle")
        root.addWidget(title)
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



class AppSettingsWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)
        root = QVBoxLayout(self)
        title = QLabel("Настройки")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(ProfileWidget(self.config), "Профиль")
        tabs.addTab(ProductsWidget(self.config), "Продукты и страницы")
        tabs.addTab(ThemeWidget(self.config), "Тема")
        tabs.addTab(NotesWidget(self.config), "Заметки")
        self.update_widget = UpdateWidget(self.config, request_application_restart)
        tabs.addTab(self.update_widget, "Обновление")
        tabs.addTab(DiagnosticsWidget(self.config), "Режим разработчика")
        root.addWidget(tabs, stretch=1)

    def check_for_updates(self, interactive=False, auto_start_install=False):
        if hasattr(self, "update_widget") and self.update_widget:
            self.update_widget.check_for_updates(
                interactive=interactive,
                auto_start_install=auto_start_install,
            )



class HomePageWidget(QWidget):
    def __init__(self, config, open_duty_callback=None, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)
        self.open_duty_callback = open_duty_callback

        root = QVBoxLayout(self)

        title = QLabel(APP_NAME)
        title.setObjectName("HomeTitle")
        root.addWidget(title)

        subtitle = QLabel("Главная страница: профиль, доступы, продукты, страницы, тема и заметки.")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        row = QHBoxLayout()
        duty = QPushButton("Перейти в режим дежурства")
        duty.clicked.connect(self.open_duty)
        row.addWidget(duty)
        row.addStretch()
        root.addLayout(row)

        tabs = QTabWidget()
        tabs.addTab(ProfileWidget(self.config), "Профиль")
        tabs.addTab(ProductsWidget(self.config), "Продукты и страницы")
        tabs.addTab(ThemeWidget(self.config), "Тема")
        tabs.addTab(NotesWidget(self.config), "Заметки")
        self.update_widget = UpdateWidget(self.config, request_application_restart)
        tabs.addTab(self.update_widget, "Обновление")
        tabs.addTab(DiagnosticsWidget(self.config), "Режим разработчика")
        root.addWidget(tabs, stretch=1)

        footer = QLabel(f"Версия: {APP_VERSION}\n{APP_DESCRIPTION}")
        footer.setObjectName("AppFooter")
        footer.setWordWrap(True)
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("font-size: 11px; opacity: 0.75; padding: 6px;")
        root.addWidget(footer)

        self.fade_in()

    def open_duty(self):
        if self.open_duty_callback:
            self.open_duty_callback()

    def check_for_updates(self, interactive=False, auto_start_install=False):
        if hasattr(self, "update_widget") and self.update_widget:
            self.update_widget.check_for_updates(
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
