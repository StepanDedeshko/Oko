from copy import deepcopy
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import default_trigger_item, ensure_duty_triggers_defaults, save_config
from app.logger import get_logger
from app.safe_widgets import NoWheelComboBox, NoWheelSpinBox


TRIGGER_MODES = {
    "mode_1": "Правило проверки 1",
    "mode_2": "Правило проверки 2",
}

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class DutyTriggerEditDialog(QDialog):
    def __init__(self, trigger=None, parent=None, config=None):
        super().__init__(parent)
        self.setWindowTitle("Триггер дежурства")
        self.trigger = deepcopy(trigger) if trigger else default_trigger_item()
        self.config = config or {}

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.id_input = QLineEdit(self.trigger.get("id", ""))
        self.enabled_checkbox = QCheckBox("Триггер включён")
        self.enabled_checkbox.setChecked(self.trigger.get("enabled", True))
        self.display_name_input = QLineEdit(self.trigger.get("display_name", ""))
        self.source_product_input = self.create_combo_line([p.get("name", "") for p in self.config.get("products", [])], self.trigger.get("source_product", ""))
        self.source_section_input = self.create_combo_line([], self.trigger.get("source_section", ""))
        self.metric_title_input = self.create_combo_line([], self.trigger.get("metric_title", ""))
        self.target_product_input = self.create_combo_line([p.get("name", "") for p in self.config.get("products", [])], self.trigger.get("target_product", ""))
        self.target_section_input = self.create_combo_line([], self.trigger.get("target_section", ""))
        self.target_graph_title_input = self.create_combo_line([], self.trigger.get("target_graph_title", ""))
        self.source_product_input.currentTextChanged.connect(lambda: self.refresh_section_combo(self.source_product_input, self.source_section_input, self.metric_title_input))
        self.source_section_input.currentTextChanged.connect(lambda: self.refresh_graph_combo(self.source_product_input, self.source_section_input, self.metric_title_input))
        self.target_product_input.currentTextChanged.connect(lambda: self.refresh_section_combo(self.target_product_input, self.target_section_input, self.target_graph_title_input))
        self.target_section_input.currentTextChanged.connect(lambda: self.refresh_graph_combo(self.target_product_input, self.target_section_input, self.target_graph_title_input))
        self.refresh_section_combo(self.source_product_input, self.source_section_input, self.metric_title_input, self.trigger.get("source_section", ""))
        self.refresh_graph_combo(self.source_product_input, self.source_section_input, self.metric_title_input, self.trigger.get("metric_title", ""))
        self.refresh_section_combo(self.target_product_input, self.target_section_input, self.target_graph_title_input, self.trigger.get("target_section", ""))
        self.refresh_graph_combo(self.target_product_input, self.target_section_input, self.target_graph_title_input, self.trigger.get("target_graph_title", ""))
        self.mode_combo = NoWheelComboBox()
        for mode, label in TRIGGER_MODES.items():
            self.mode_combo.addItem(label, mode)
        mode_index = self.mode_combo.findData(self.trigger.get("mode", "mode_1"))
        self.mode_combo.setCurrentIndex(max(0, mode_index))
        self.ok_text_input = QLineEdit(self.trigger.get("ok_text", ""))
        self.alert_template_input = QLineEdit(self.trigger.get("alert_template", ""))

        form.addRow("ID:", self.id_input)
        form.addRow("Состояние:", self.enabled_checkbox)
        form.addRow("Название:", self.display_name_input)
        form.addRow("Продукт-источник:", self.source_product_input)
        form.addRow("Раздел/страница-источник:", self.source_section_input)
        form.addRow("Название метрики:", self.metric_title_input)
        form.addRow("Целевой продукт:", self.target_product_input)
        form.addRow("Целевой раздел:", self.target_section_input)
        form.addRow("Целевой график:", self.target_graph_title_input)
        form.addRow("Режим:", self.mode_combo)
        form.addRow("Текст нормы:", self.ok_text_input)
        form.addRow("Шаблон тревоги:", self.alert_template_input)
        root.addLayout(form)

        hint = QLabel("Поля source/target можно оставить пустыми на этапе настройки. Триггер не будет готов к работе до полной привязки source → target.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def create_combo_line(self, values, current):
        combo = NoWheelComboBox()
        combo.setEditable(True)
        seen = set()
        for value in values:
            value = str(value or "").strip()
            if value and value not in seen:
                combo.addItem(value)
                seen.add(value)
        combo.setCurrentText(str(current or ""))
        return combo

    def combo_text(self, combo):
        return combo.currentText().strip()

    def find_product(self, name):
        for product in self.config.get("products", []):
            if product.get("name", "") == name:
                return product
        return None

    def find_dashboard(self, product_name, section_name):
        product = self.find_product(product_name)
        if not product:
            return None
        for dashboard in product.get("dashboards", []):
            if dashboard.get("name", "") == section_name:
                return dashboard
        return None

    def refresh_section_combo(self, product_combo, section_combo, graph_combo, current=None):
        selected = current if current is not None else section_combo.currentText()
        section_combo.blockSignals(True)
        section_combo.clear()
        product = self.find_product(product_combo.currentText())
        if product:
            for dashboard in product.get("dashboards", []):
                section_combo.addItem(dashboard.get("name", ""))
        section_combo.setCurrentText(str(selected or ""))
        section_combo.blockSignals(False)
        self.refresh_graph_combo(product_combo, section_combo, graph_combo)

    def refresh_graph_combo(self, product_combo, section_combo, graph_combo, current=None):
        selected = current if current is not None else graph_combo.currentText()
        graph_combo.blockSignals(True)
        graph_combo.clear()
        dashboard = self.find_dashboard(product_combo.currentText(), section_combo.currentText())
        if dashboard:
            for graph in dashboard.get("graphs", []) or []:
                graph_combo.addItem(graph.get("title", ""))
            for mode in dashboard.get("modes", []) or []:
                if isinstance(mode, dict):
                    graph_combo.addItem(mode.get("name", ""))
        graph_combo.setCurrentText(str(selected or ""))
        graph_combo.blockSignals(False)

    def result_trigger(self):
        return {
            "id": self.id_input.text().strip(),
            "enabled": self.enabled_checkbox.isChecked(),
            "display_name": self.display_name_input.text().strip(),
            "source_product": self.combo_text(self.source_product_input),
            "source_section": self.combo_text(self.source_section_input),
            "metric_title": self.combo_text(self.metric_title_input),
            "target_product": self.combo_text(self.target_product_input),
            "target_section": self.combo_text(self.target_section_input),
            "target_graph_title": self.combo_text(self.target_graph_title_input),
            "mode": self.mode_combo.currentData(),
            "ok_text": self.ok_text_input.text().strip(),
            "alert_template": self.alert_template_input.text().strip(),
        }

    def accept(self):
        trigger = self.result_trigger()
        errors = validate_trigger(trigger)
        if errors:
            QMessageBox.warning(self, "Триггер дежурства", "\n".join(errors))
            return
        super().accept()


class DutyModeSettingsWidget(QWidget):
    def __init__(self, config, on_saved_callback=None):
        super().__init__()

        self.logger = get_logger()
        self.logger.info("Открыты настройки триггеров дежурства")

        self.config = config
        self.on_saved_callback = on_saved_callback
        self.trigger_items = deepcopy(self.duty_triggers_settings().get("items", []))

        root = QVBoxLayout(self)

        title = QLabel("Настройки режима дежурства")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        self.enabled_checkbox = QCheckBox("Включить режим дежурства")
        self.enabled_checkbox.setChecked(self.settings().get("enabled", False))
        root.addWidget(self.enabled_checkbox)

        row = QHBoxLayout()
        row.addWidget(QLabel("Повтор после пропуска, минут:"))

        self.skip_minutes = NoWheelSpinBox()
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

        access_hint = QLabel("Доступы к ОТРС и Zabbix настраиваются в разделе «Профиль».")
        access_hint.setWordWrap(True)
        root.addWidget(access_hint)

        self.otrs_auto_submit_checkbox = QCheckBox("Автоматически нажимать кнопку «Вход»")
        self.otrs_auto_submit_checkbox.setChecked(self.settings().get("otrs_auto_submit_login", False))
        root.addWidget(self.otrs_auto_submit_checkbox)

        hint = QLabel("Выбери графики, которые должны открываться при дежурной проверке.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.graph_list = QListWidget()
        root.addWidget(self.graph_list, stretch=1)

        self.build_triggers_ui(root)

        buttons = QHBoxLayout()

        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self.save)

        buttons.addWidget(save_button)
        buttons.addStretch()
        root.addLayout(buttons)

        self.load_graphs()
        self.reload_trigger_list()

    def settings(self):
        settings = self.config.setdefault("duty_mode", {})
        settings.setdefault("enabled", False)
        settings.setdefault("hourly_notification", True)
        settings.setdefault("skip_minutes", 5)
        settings.setdefault("sound_path", "")
        settings.setdefault("otrs_create_url", "")
        settings.setdefault("expected_ticket_subject", "Проверка Zabbix (Важных IT-сервисов)")
        settings.setdefault("otrs_auto_submit_login", False)
        settings.setdefault("graph_ids", [])
        return settings

    def duty_triggers_settings(self):
        return ensure_duty_triggers_defaults(self.config)

    def build_triggers_ui(self, root):
        group = QGroupBox("Триггеры дежурства source → target")
        layout = QVBoxLayout(group)

        self.triggers_enabled_checkbox = QCheckBox("Включить триггеры дежурства")
        self.triggers_enabled_checkbox.setChecked(self.duty_triggers_settings().get("enabled", True))
        layout.addWidget(self.triggers_enabled_checkbox)

        thresholds = QFormLayout()
        trigger_settings = self.duty_triggers_settings()
        self.day_start_input = QLineEdit(trigger_settings.get("day_start", "06:00"))
        self.day_end_input = QLineEdit(trigger_settings.get("day_end", "00:00"))
        self.day_threshold_input = NoWheelSpinBox()
        self.day_threshold_input.setMinimum(1)
        self.day_threshold_input.setMaximum(24 * 60)
        self.day_threshold_input.setValue(int(trigger_settings.get("day_threshold_minutes", 90)))
        self.night_threshold_input = NoWheelSpinBox()
        self.night_threshold_input.setMinimum(1)
        self.night_threshold_input.setMaximum(24 * 60)
        self.night_threshold_input.setValue(int(trigger_settings.get("night_threshold_minutes", 180)))
        self.mode1_silence_start_input = QLineEdit(trigger_settings.get("mode1_night_silence_start", "01:00"))
        self.mode1_silence_end_input = QLineEdit(trigger_settings.get("mode1_night_silence_end", "05:30"))

        thresholds.addRow("Начало дня (HH:MM):", self.day_start_input)
        thresholds.addRow("Конец дня (HH:MM):", self.day_end_input)
        thresholds.addRow("Дневной порог, минут:", self.day_threshold_input)
        thresholds.addRow("Ночной порог, минут:", self.night_threshold_input)
        thresholds.addRow("Начало ночного окна тишины mode_1:", self.mode1_silence_start_input)
        thresholds.addRow("Конец ночного окна тишины mode_1:", self.mode1_silence_end_input)
        layout.addLayout(thresholds)

        self.trigger_list = QListWidget()
        layout.addWidget(self.trigger_list)

        trigger_buttons = QHBoxLayout()
        add_button = QPushButton("Добавить триггер")
        edit_button = QPushButton("Редактировать триггер")
        delete_button = QPushButton("Удалить триггер")
        add_button.clicked.connect(self.add_trigger)
        edit_button.clicked.connect(self.edit_trigger)
        delete_button.clicked.connect(self.delete_trigger)
        trigger_buttons.addWidget(add_button)
        trigger_buttons.addWidget(edit_button)
        trigger_buttons.addWidget(delete_button)
        trigger_buttons.addStretch()
        layout.addLayout(trigger_buttons)

        root.addWidget(group)

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

    def reload_trigger_list(self):
        self.trigger_list.clear()
        for index, trigger in enumerate(self.trigger_items):
            name = trigger.get("display_name") or trigger.get("id") or f"Триггер {index + 1}"
            mode_label = TRIGGER_MODES.get(trigger.get("mode"), trigger.get("mode", ""))
            state = "вкл" if trigger.get("enabled", True) else "выкл"
            item = QListWidgetItem(f"{name} — {mode_label} — {state}")
            item.setData(Qt.UserRole, index)
            self.trigger_list.addItem(item)

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

    def selected_trigger_index(self):
        item = self.trigger_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def next_trigger_id(self):
        existing = {trigger.get("id") for trigger in self.trigger_items}
        number = len(self.trigger_items) + 1
        while f"trigger_{number}" in existing:
            number += 1
        return f"trigger_{number}"

    def add_trigger(self):
        trigger = default_trigger_item(self.next_trigger_id(), "mode_1")
        dialog = DutyTriggerEditDialog(trigger, self, self.config)
        if dialog.exec() != QDialog.Accepted:
            return
        self.trigger_items.append(dialog.result_trigger())
        self.reload_trigger_list()
        self.logger.info("Добавлен триггер дежурства: %s", self.trigger_items[-1].get("id"))

    def edit_trigger(self):
        index = self.selected_trigger_index()
        if index is None:
            QMessageBox.information(self, "Триггеры дежурства", "Выберите триггер для редактирования.")
            return
        dialog = DutyTriggerEditDialog(self.trigger_items[index], self, self.config)
        if dialog.exec() != QDialog.Accepted:
            return
        self.trigger_items[index] = dialog.result_trigger()
        self.reload_trigger_list()
        self.trigger_list.setCurrentRow(index)
        self.logger.info("Изменён триггер дежурства: %s", self.trigger_items[index].get("id"))

    def delete_trigger(self):
        index = self.selected_trigger_index()
        if index is None:
            QMessageBox.information(self, "Триггеры дежурства", "Выберите триггер для удаления.")
            return
        trigger_id = self.trigger_items[index].get("id")
        reply = QMessageBox.question(
            self,
            "Триггеры дежурства",
            f"Удалить триггер «{trigger_id}»?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.trigger_items.pop(index)
        self.reload_trigger_list()
        self.logger.info("Удалён триггер дежурства: %s", trigger_id)

    def validate_triggers_settings(self):
        errors = []
        time_fields = {
            "начало дня": self.day_start_input.text().strip(),
            "конец дня": self.day_end_input.text().strip(),
            "начало ночного окна тишины mode_1": self.mode1_silence_start_input.text().strip(),
            "конец ночного окна тишины mode_1": self.mode1_silence_end_input.text().strip(),
        }
        for label, value in time_fields.items():
            if not TIME_RE.match(value):
                errors.append(f"Поле «{label}» должно быть в формате HH:MM.")

        if int(self.day_threshold_input.value()) <= 0:
            errors.append("Дневной порог должен быть больше 0.")
        if int(self.night_threshold_input.value()) <= 0:
            errors.append("Ночной порог должен быть больше 0.")

        for index, trigger in enumerate(self.trigger_items, start=1):
            for error in validate_trigger(trigger):
                errors.append(f"Триггер {index}: {error}")

        return errors

    def save(self):
        trigger_errors = self.validate_triggers_settings()
        if trigger_errors:
            QMessageBox.warning(self, "Триггеры дежурства", "\n".join(trigger_errors))
            return

        incomplete = [
            trigger.get("id", "")
            for trigger in self.trigger_items
            if not all([
                trigger.get("source_product", "").strip(),
                trigger.get("source_section", "").strip(),
                trigger.get("target_product", "").strip(),
                trigger.get("target_section", "").strip(),
                trigger.get("target_graph_title", "").strip(),
            ])
        ]
        if incomplete:
            QMessageBox.information(
                self,
                "Триггеры дежурства",
                "Некоторые триггеры сохранены без полной привязки source → target и не будут готовы к работе до заполнения всех полей.",
            )

        settings = self.settings()
        settings["enabled"] = self.enabled_checkbox.isChecked()
        settings["skip_minutes"] = int(self.skip_minutes.value())
        settings["sound_path"] = self.sound_label.text().strip()
        if settings["sound_path"] == "Звук не выбран":
            settings["sound_path"] = ""
        settings["otrs_create_url"] = self.otrs_create_url.text().strip()
        settings["expected_ticket_subject"] = self.expected_subject_input.text().strip() or "Проверка Zabbix (Важных IT-сервисов)"
        settings["otrs_auto_submit_login"] = self.otrs_auto_submit_checkbox.isChecked()
        settings["graph_ids"] = self.selected_graph_ids()

        trigger_settings = self.duty_triggers_settings()
        trigger_settings["enabled"] = self.triggers_enabled_checkbox.isChecked()
        trigger_settings["day_start"] = self.day_start_input.text().strip()
        trigger_settings["day_end"] = self.day_end_input.text().strip()
        trigger_settings["day_threshold_minutes"] = int(self.day_threshold_input.value())
        trigger_settings["night_threshold_minutes"] = int(self.night_threshold_input.value())
        trigger_settings["mode1_night_silence_start"] = self.mode1_silence_start_input.text().strip()
        trigger_settings["mode1_night_silence_end"] = self.mode1_silence_end_input.text().strip()
        trigger_settings["items"] = deepcopy(self.trigger_items)

        save_config(self.config)
        self.logger.info("Сохранены настройки триггеров дежурства")

        QMessageBox.information(self, "Режим дежурства", "Настройки сохранены.")

        if self.on_saved_callback:
            self.on_saved_callback()


def validate_trigger(trigger):
    errors = []
    if not trigger.get("id", "").strip():
        errors.append("ID должен быть непустым.")
    if not trigger.get("metric_title", "").strip():
        errors.append("Название метрики должно быть непустым.")
    if trigger.get("mode") not in TRIGGER_MODES:
        errors.append("Режим должен быть mode_1 или mode_2.")
    return errors
