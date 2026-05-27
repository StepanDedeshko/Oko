
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config import save_config


class DutyModeSettingsWidget(QWidget):
    def __init__(self, config, on_saved_callback=None):
        super().__init__()

        self.config = config
        self.on_saved_callback = on_saved_callback

        root = QVBoxLayout(self)

        title = QLabel("Настройки режима дежурства")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        self.enabled_checkbox = QCheckBox("Включить режим дежурства")
        self.enabled_checkbox.setChecked(self.settings().get("enabled", False))
        root.addWidget(self.enabled_checkbox)

        row = QHBoxLayout()
        row.addWidget(QLabel("Повтор после пропуска, минут:"))

        self.skip_minutes = QSpinBox()
        self.skip_minutes.setMinimum(1)
        self.skip_minutes.setMaximum(120)
        self.skip_minutes.setValue(int(self.settings().get("skip_minutes", 5)))

        row.addWidget(self.skip_minutes)
        row.addStretch()
        root.addLayout(row)

        sound_row = QHBoxLayout()

        self.sound_label = QLabel(self.settings().get("sound_path", "") or "Звук не выбран")
        self.sound_label.setWordWrap(True)

        choose_sound = QPushButton("Выбрать звук")
        choose_sound.clicked.connect(self.choose_sound)

        clear_sound = QPushButton("Убрать звук")
        clear_sound.clicked.connect(self.clear_sound)

        sound_row.addWidget(QLabel("Звук уведомления:"))
        sound_row.addWidget(self.sound_label, stretch=1)
        sound_row.addWidget(choose_sound)
        sound_row.addWidget(clear_sound)
        root.addLayout(sound_row)

        otrs_row = QHBoxLayout()
        otrs_row.addWidget(QLabel("URL создания задачи ОТРС:"))

        self.otrs_create_url = QLineEdit()
        self.otrs_create_url.setText(self.settings().get("otrs_create_url", ""))
        self.otrs_create_url.setPlaceholderText("https://.../otrs/index.pl?Action=AgentTicketPhone")

        otrs_row.addWidget(self.otrs_create_url, stretch=1)
        root.addLayout(otrs_row)

        subject_row = QHBoxLayout()
        subject_row.addWidget(QLabel("Ожидаемая тема задачи:"))

        self.expected_subject_input = QLineEdit()
        self.expected_subject_input.setText(self.settings().get("expected_ticket_subject", "Проверка Zabbix (Важных IT-сервисов)"))
        self.expected_subject_input.setPlaceholderText("Например: Проверка Zabbix (Важных IT-сервисов)")

        subject_row.addWidget(self.expected_subject_input, stretch=1)
        root.addLayout(subject_row)

        self.otrs_login_enabled_checkbox = QCheckBox("Сохранять и подставлять логин/пароль ОТРС")
        self.otrs_login_enabled_checkbox.setChecked(self.settings().get("otrs_login_enabled", False))
        root.addWidget(self.otrs_login_enabled_checkbox)

        otrs_login_row = QHBoxLayout()
        otrs_login_row.addWidget(QLabel("Логин ОТРС:"))

        self.otrs_login_input = QLineEdit()
        self.otrs_login_input.setText(self.settings().get("otrs_login", ""))
        self.otrs_login_input.setPlaceholderText("Логин")

        otrs_login_row.addWidget(self.otrs_login_input, stretch=1)
        root.addLayout(otrs_login_row)

        otrs_password_row = QHBoxLayout()
        otrs_password_row.addWidget(QLabel("Пароль ОТРС:"))

        self.otrs_password_input = QLineEdit()
        self.otrs_password_input.setEchoMode(QLineEdit.Password)
        self.otrs_password_input.setText(self.settings().get("otrs_password", ""))
        self.otrs_password_input.setPlaceholderText("Пароль")

        otrs_password_row.addWidget(self.otrs_password_input, stretch=1)
        root.addLayout(otrs_password_row)

        self.otrs_auto_submit_checkbox = QCheckBox("Автоматически нажимать кнопку «Вход»")
        self.otrs_auto_submit_checkbox.setChecked(self.settings().get("otrs_auto_submit_login", False))
        root.addWidget(self.otrs_auto_submit_checkbox)

        hint = QLabel("Выбери графики, которые должны открываться при дежурной проверке.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.graph_list = QListWidget()
        root.addWidget(self.graph_list, stretch=1)

        buttons = QHBoxLayout()

        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self.save)

        buttons.addWidget(save_button)
        buttons.addStretch()
        root.addLayout(buttons)

        self.load_graphs()

    def settings(self):
        settings = self.config.setdefault("duty_mode", {})
        settings.setdefault("enabled", False)
        settings.setdefault("hourly_notification", True)
        settings.setdefault("skip_minutes", 5)
        settings.setdefault("sound_path", "")
        settings.setdefault("otrs_create_url", "")
        settings.setdefault("expected_ticket_subject", "Проверка Zabbix (Важных IT-сервисов)")
        settings.setdefault("otrs_login_enabled", False)
        settings.setdefault("otrs_login", "")
        settings.setdefault("otrs_password", "")
        settings.setdefault("otrs_auto_submit_login", False)
        settings.setdefault("graph_ids", [])
        return settings

    def graph_id(self, product_name, dashboard_name, index, graph):
        return graph.get("id") or f"{product_name}::{dashboard_name}::{index}::{graph.get('title', '')}"

    def all_graphs(self):
        result = []

        for product in self.config.get("products", []):
            product_name = product.get("name", "Продукт")

            for dashboard in product.get("dashboards", []):
                if dashboard.get("type") != "graphs_grid":
                    continue

                dashboard_name = dashboard.get("name", "Графики")

                for index, graph in enumerate(dashboard.get("graphs", [])):
                    graph_id = self.graph_id(product_name, dashboard_name, index, graph)
                    result.append((graph_id, product_name, dashboard_name, graph))

        return result

    def load_graphs(self):
        selected = set(self.settings().get("graph_ids", []))
        self.graph_list.clear()

        for graph_id, product_name, dashboard_name, graph in self.all_graphs():
            title = graph.get("title", "График")
            item = QListWidgetItem(f"{product_name} → {dashboard_name} → {title}")
            item.setData(Qt.UserRole, graph_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if graph_id in selected else Qt.Unchecked)
            self.graph_list.addItem(item)

    def choose_sound(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выбери звук уведомления",
            "",
            "Аудио (*.mp3 *.wav *.ogg *.m4a);;Все файлы (*)"
        )

        if file_path:
            self.sound_label.setText(file_path)

    def clear_sound(self):
        self.sound_label.setText("")

    def selected_graph_ids(self):
        ids = []

        for index in range(self.graph_list.count()):
            item = self.graph_list.item(index)
            if item.checkState() == Qt.Checked:
                ids.append(item.data(Qt.UserRole))

        return ids

    def save(self):
        settings = self.settings()
        settings["enabled"] = self.enabled_checkbox.isChecked()
        settings["skip_minutes"] = int(self.skip_minutes.value())
        settings["sound_path"] = self.sound_label.text().strip()
        if settings["sound_path"] == "Звук не выбран":
            settings["sound_path"] = ""
        settings["otrs_create_url"] = self.otrs_create_url.text().strip()
        settings["expected_ticket_subject"] = self.expected_subject_input.text().strip() or "Проверка Zabbix (Важных IT-сервисов)"
        settings["otrs_login_enabled"] = self.otrs_login_enabled_checkbox.isChecked()
        settings["otrs_login"] = self.otrs_login_input.text().strip()
        settings["otrs_password"] = self.otrs_password_input.text()
        settings["otrs_auto_submit_login"] = self.otrs_auto_submit_checkbox.isChecked()
        settings["graph_ids"] = self.selected_graph_ids()

        save_config(self.config)

        QMessageBox.information(self, "Режим дежурства", "Настройки сохранены.")

        if self.on_saved_callback:
            self.on_saved_callback()
