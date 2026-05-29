
import json
import os
import sys

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QPushButton,
    QStackedWidget,
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
    def __init__(self, page=None, zabbix_ids=None, index=0, on_delete=None, parent=None):
        super().__init__(parent)
        self.original_page = clone(page or {"name": "", "type": "dashboard_page", "url": "", "zabbix_id": "zbx_product_1", "enabled": True})
        self.graph_rows = []
        self.mode_rows = []
        self.on_delete = on_delete
        self.setTitle(f"Страница {index + 1}")

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.name = QLineEdit(self.original_page.get("name", ""))
        self.name.setPlaceholderText("Название страницы")
        self.enabled = QCheckBox("Включена")
        self.enabled.setChecked(self.original_page.get("enabled", True))
        self.type_combo = QComboBox()
        for label, value in PAGE_TYPES:
            self.type_combo.addItem(label, value)
        page_type = self.original_page.get("type", "dashboard_page")
        if page_type == "simple_page":
            page_type = "dashboard_page"
        type_index = self.type_combo.findData(page_type)
        self.type_combo.setCurrentIndex(max(0, type_index))

        self.zabbix_id = QComboBox()
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
        self.graphs_group.setVisible(page_type == "graphs_grid")
        self.modes_group.setVisible(page_type == "mode_pages")
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

        if self.type_combo.currentData() == "graphs_grid":
            page["graphs"] = [row.value() for row in self.graph_rows if row.value().get("title") or row.value().get("url")]
        if self.type_combo.currentData() == "mode_pages":
            page["modes"] = [row.value() for row in self.mode_rows if row.value().get("name") or row.value().get("url")]
        return page


class ProductCardWidget(QGroupBox):
    def __init__(self, product=None, zabbix_ids=None, index=0, on_delete=None, parent=None):
        super().__init__(parent)
        self.original_product = clone(product or {"name": "", "enabled": True, "dashboards": []})
        self.zabbix_ids = zabbix_ids or []
        self.page_cards = []
        self.on_delete = on_delete
        self.setTitle(f"Продукт {index + 1}")

        root = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(self.original_product.get("name", ""))
        self.name.setPlaceholderText("Название продукта")
        self.enabled = QCheckBox("Включён")
        self.enabled.setChecked(self.original_product.get("enabled", True))
        form.addRow("Название продукта:", self.name)
        form.addRow("Состояние:", self.enabled)
        root.addLayout(form)

        buttons = QHBoxLayout()
        add_page = QPushButton("Добавить страницу")
        add_page.clicked.connect(self.add_page)
        delete = QPushButton("Удалить продукт")
        delete.clicked.connect(self.delete_requested)
        buttons.addWidget(add_page)
        buttons.addStretch()
        buttons.addWidget(delete)
        root.addLayout(buttons)

        self.pages_layout = QVBoxLayout()
        root.addLayout(self.pages_layout)

        for page in self.original_product.get("dashboards", []) or []:
            self.add_page(page)

    def delete_requested(self):
        if self.on_delete:
            self.on_delete(self)

    def add_page(self, page=None):
        card = PageCardWidget(page, self.zabbix_ids, len(self.page_cards), self.remove_page, self)
        self.page_cards.append(card)
        self.pages_layout.addWidget(card)

    def remove_page(self, card):
        if QMessageBox.question(self, "Удалить страницу", "Удалить эту страницу?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.page_cards.remove(card)
        card.deleteLater()

    def value(self):
        product = clone(self.original_product)
        product.update({
            "name": self.name.text().strip(),
            "enabled": self.enabled.isChecked(),
            "dashboards": [card.value() for card in self.page_cards],
        })
        return product


class ProductsWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)
        self.product_cards = []
        self.zabbix_ids = [instance.get("id", "") for instance in self.config.get("zabbix_instances", []) if instance.get("id")]

        root = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("Продукты и страницы")
        title.setObjectName("PageTitle")
        add = QPushButton("Добавить продукт")
        add.clicked.connect(self.add_product)
        save = QPushButton("Сохранить")
        save.clicked.connect(self.save)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(add)
        header.addWidget(save)
        root.addLayout(header)

        hint = QLabel("Настраивай продукты, страницы, графики и режимы прямо в карточках. Нерелевантные блоки скрываются по выбранному типу страницы.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, stretch=1)

        self.container = QWidget()
        self.products_layout = QVBoxLayout(self.container)
        self.products_layout.setSpacing(14)
        scroll.setWidget(self.container)

        for product in self.config.get("products", []) or []:
            self.add_product(product)
        self.products_layout.addStretch(1)

    def add_product(self, product=None):
        if self.products_layout.count() and self.products_layout.itemAt(self.products_layout.count() - 1).spacerItem():
            self.products_layout.takeAt(self.products_layout.count() - 1)
        card = ProductCardWidget(product, self.zabbix_ids, len(self.product_cards), self.remove_product, self)
        self.product_cards.append(card)
        self.products_layout.addWidget(card)
        self.products_layout.addStretch(1)

    def remove_product(self, card):
        name = card.name.text().strip() or "Без названия"
        if QMessageBox.question(self, "Удалить продукт", f"Удалить продукт «{name}»?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.product_cards.remove(card)
        card.deleteLater()

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
        products = [card.value() for card in self.product_cards]
        errors = self.validate(products)
        if errors:
            QMessageBox.warning(self, "Продукты и страницы", "\n".join(errors))
            return
        self.config["products"] = products
        save_config(self.config)
        QMessageBox.information(self, "Продукты и страницы", "Настройки сохранены. После изменения структуры перезапусти приложение, чтобы меню пересобралось.")
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
        self.section_indexes = {}

        root = QVBoxLayout(self)
        self.title = QLabel("Настройки")
        self.title.setObjectName("PageTitle")
        root.addWidget(self.title)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, stretch=1)

        self.add_section("Профиль", ProfileWidget(self.config))
        self.add_section("Продукты и страницы", ProductsWidget(self.config))
        self.add_section("Тема", ThemeWidget(self.config))
        self.add_section("Заметки", NotesWidget(self.config))
        self.update_widget = UpdateWidget(self.config, request_application_restart)
        self.add_section("Обновление", self.update_widget)
        self.add_section("Режим разработчика", DiagnosticsWidget(self.config))

        self.open_section("Продукты и страницы")

    def add_section(self, section_name, widget):
        self.section_indexes[section_name] = self.stack.addWidget(widget)

    def open_section(self, section_name):
        index = self.section_indexes.get(section_name)
        if index is None:
            index = self.section_indexes.get("Продукты и страницы", 0)
            section_name = "Продукты и страницы"
        self.stack.setCurrentIndex(index)
        self.title.setText(section_name)

    def check_for_updates(self, interactive=False, auto_start_install=False):
        if hasattr(self, "update_widget") and self.update_widget:
            self.update_widget.check_for_updates(
                interactive=interactive,
                auto_start_install=auto_start_install,
            )



class HomePageWidget(QWidget):
    SETTINGS_SECTIONS = [
        "Профиль",
        "Продукты и страницы",
        "Тема",
        "Заметки",
        "Обновление",
        "Режим разработчика",
    ]

    def __init__(self, config, open_duty_callback=None, open_settings_callback=None, update_check_callback=None, parent=None):
        super().__init__(parent)
        self.config = ensure_home_defaults(config)
        self.open_duty_callback = open_duty_callback
        self.open_settings_callback = open_settings_callback
        self.update_check_callback = update_check_callback

        root = QVBoxLayout(self)

        title = QLabel(APP_NAME)
        title.setObjectName("HomeTitle")
        root.addWidget(title)

        subtitle = QLabel("Главная страница-меню: выбери нужный раздел настроек или перейди в режим дежурства.")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        grid = QGridLayout()
        grid.setSpacing(14)
        for index, section_name in enumerate(self.SETTINGS_SECTIONS):
            button = QPushButton(section_name)
            button.setMinimumHeight(96)
            button.setToolTip(f"Открыть раздел «{section_name}»")
            button.clicked.connect(lambda checked=False, name=section_name: self.open_settings_section(name))
            grid.addWidget(button, index // 3, index % 3)
        root.addLayout(grid)

        row = QHBoxLayout()
        duty = QPushButton("Перейти в режим дежурства")
        duty.clicked.connect(self.open_duty)
        row.addWidget(duty)
        row.addStretch()
        root.addLayout(row)
        root.addStretch(1)

        footer = QLabel(f"Версия: {APP_VERSION}\n{APP_DESCRIPTION}")
        footer.setObjectName("AppFooter")
        footer.setWordWrap(True)
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("font-size: 11px; opacity: 0.75; padding: 6px;")
        root.addWidget(footer)

        self.fade_in()

    def open_settings_section(self, section_name):
        if self.open_settings_callback:
            self.open_settings_callback(section_name)

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
