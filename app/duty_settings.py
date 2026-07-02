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
    QStackedWidget,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import default_trigger_item, ensure_duty_mode_defaults, ensure_duty_triggers_defaults, save_config
from app.duty_zabbix import (
    import_zabbix_trigger_catalog_from_xlsx,
    load_zabbix_trigger_catalog,
    save_zabbix_trigger_catalog,
)
from app.logger import get_logger
from app.safe_widgets import NoWheelComboBox, NoWheelSpinBox
from app.screen_utils import available_geometry_for_widget, center_widget_on_screen, safe_window_size
from app.permissions import ensure_duty_links, get_duty_link, set_duty_link


TRIGGER_MODES = {
    "mode_1": "Правило проверки 1",
    "mode_2": "Правило проверки 2",
}

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class DutyTriggerEditDialog(QDialog):
    def __init__(self, trigger=None, parent=None, config=None):
        super().__init__(parent)
        self.setWindowTitle("Триггер дежурства")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.setSizeGripEnabled(True)
        self.trigger = deepcopy(trigger) if trigger else default_trigger_item()
        self.config = config or {}

        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

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
        scroll.setWidget(form_widget)
        root.addWidget(scroll, stretch=1)

        hint = QLabel("Поля source/target можно оставить пустыми на этапе настройки. Триггер не будет готов к работе до полной привязки source → target.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.apply_safe_dialog_geometry()

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
        combo.setMinimumContentsLength(12)
        combo.setSizeAdjustPolicy(NoWheelComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumWidth(180)
        combo.setMaximumWidth(520)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.view().setTextElideMode(Qt.ElideRight)
        return combo


    def apply_safe_dialog_geometry(self):
        available = available_geometry_for_widget(self.parentWidget() or self)
        size, minimum = safe_window_size(
            available,
            desired_width=760,
            desired_height=620,
            margin=80,
            min_width=520,
            min_height=420,
        )
        self.setMinimumSize(minimum)
        self.resize(size)
        center_widget_on_screen(self, screen=None, margin=40)

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
    def __init__(self, config, on_saved_callback=None, show_title=True):
        super().__init__()

        self.logger = get_logger()
        self.logger.info("Открыты настройки триггеров дежурства")

        self.config = config
        self.on_saved_callback = on_saved_callback
        self.trigger_items = deepcopy(self.duty_triggers_settings().get("items", []))
        self.zabbix_trigger_catalog_entries = load_zabbix_trigger_catalog(config=self.config, logger=self.logger)
        self.section_indexes = {}

        root = QVBoxLayout(self)
        root.setSpacing(10)

        if show_title:
            title = QLabel("Настройки дежурки")
            title.setObjectName("PageTitle")
            root.addWidget(title)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, stretch=1)

        self.menu_index = self.stack.addWidget(self.create_menu_page())
        self.add_section_page("Основное", self.build_general_section)
        self.add_section_page("ОТРС", self.build_otrs_section)
        self.add_section_page("Графики", self.build_graphs_section)
        self.add_section_page("Триггеры", self.build_triggers_ui)
        self.add_section_page("Триггеры Zabbix", self.build_zabbix_trigger_catalog_ui)
        self.add_section_page("Пороги", self.build_thresholds_ui)

        buttons = QHBoxLayout()

        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self.save)

        buttons.addWidget(save_button)
        buttons.addStretch()
        root.addLayout(buttons)

        self.load_graphs()
        self.reload_trigger_list()

    def create_menu_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        hint = QLabel("Выберите раздел настроек дежурки.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        for section_name in ["Основное", "ОТРС", "Графики", "Триггеры", "Триггеры Zabbix", "Пороги"]:
            button = QPushButton(section_name)
            button.setMinimumHeight(56)
            button.clicked.connect(lambda checked=False, name=section_name: self.open_section(name))
            layout.addWidget(button)

        layout.addStretch(1)
        return page

    def add_section_page(self, section_name, builder):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setSpacing(10)

        back = QPushButton("← Назад к настройкам дежурки")
        back.clicked.connect(self.open_menu)
        outer.addWidget(back)

        title = QLabel(section_name)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(10)
        builder(layout)

        if section_name not in {"Графики", "Триггеры", "Триггеры Zabbix"}:
            layout.addStretch(1)

        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)
        self.section_indexes[section_name] = self.stack.addWidget(page)

    def open_menu(self):
        self.stack.setCurrentIndex(self.menu_index)

    def open_section(self, section_name):
        index = self.section_indexes.get(section_name)
        if index is not None:
            self.stack.setCurrentIndex(index)

    def build_general_section(self, root):
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

        links_box = QGroupBox("Рабочие ссылки дежурки")
        links_form = QFormLayout(links_box)
        self.live_zabbix_url_input = QLineEdit(get_duty_link(self.config, "live_zabbix_url"))
        self.live_zabbix_url_input.setPlaceholderText("URL страницы Live Zabbix Monitor")
        self.redmine_create_url_input = QLineEdit(get_duty_link(self.config, "redmine_create_url"))
        self.redmine_create_url_input.setPlaceholderText("URL создания Redmine-задачи из Live Zabbix")
        self.otrs_create_url_link_input = QLineEdit(get_duty_link(self.config, "otrs_create_url"))
        self.otrs_create_url_link_input.setPlaceholderText("URL создания задачи ОТРС")
        self.mm_otrs_create_url_input = QLineEdit(get_duty_link(self.config, "mm_otrs_create_url"))
        self.mm_otrs_create_url_input.setPlaceholderText("URL создания задачи ОТРС ММ")
        links_form.addRow("Live Zabbix Monitor:", self.live_zabbix_url_input)
        links_form.addRow("Redmine из Live Zabbix:", self.redmine_create_url_input)
        links_form.addRow("ОТРС:", self.otrs_create_url_link_input)
        links_form.addRow("ОТРС ММ:", self.mm_otrs_create_url_input)
        root.addWidget(links_box)

        self.duty_service_checks_enabled_checkbox = QCheckBox("Проверять сервисы в режиме дежурства")
        self.duty_service_checks_enabled_checkbox.setChecked(bool(self.settings().get("duty_service_checks_enabled", False)))
        self.duty_service_checks_enabled_checkbox.setToolTip(
            "Если выключено, при дежурной проверке графиков/Zabbix проверка сервисов запускаться не будет."
        )
        root.addWidget(self.duty_service_checks_enabled_checkbox)

        service_checks_hint = QLabel(
            "Если выключено, при дежурной проверке графиков/Zabbix проверка сервисов запускаться не будет."
        )
        service_checks_hint.setWordWrap(True)
        root.addWidget(service_checks_hint)

    def build_otrs_section(self, root):
        access_hint = QLabel("Логин и пароль ОТРС настраиваются в разделе «Профиль».")
        access_hint.setWordWrap(True)
        root.addWidget(access_hint)

        otrs_row = QHBoxLayout()
        otrs_row.addWidget(QLabel("URL создания задачи ОТРС:"))

        self.otrs_create_url = QLineEdit()
        self.otrs_create_url.setText(get_duty_link(self.config, "otrs_create_url") or self.settings().get("otrs_create_url", ""))
        self.otrs_create_url.setPlaceholderText("Редактируется в подразделе «Основное» выше")
        self.otrs_create_url.setReadOnly(True)

        otrs_row.addWidget(self.otrs_create_url, stretch=1)
        root.addLayout(otrs_row)

        subject_box = QGroupBox("Ожидаемые темы задач")
        subject_form = QFormLayout(subject_box)

        self.zabbix_expected_title_input = QLineEdit()
        self.zabbix_expected_title_input.setText(self.settings().get("duty_zabbix_expected_task_title", "Дежурная проверка Zabbix / графиков"))
        self.zabbix_expected_title_input.setPlaceholderText("Например: Дежурная проверка Zabbix / графиков")
        subject_form.addRow("Ожидаемая тема задачи Zabbix / графиков:", self.zabbix_expected_title_input)

        self.service_checks_expected_title_input = QLineEdit()
        self.service_checks_expected_title_input.setText(self.settings().get("duty_service_checks_expected_task_title", "Дежурная проверка сервисов"))
        self.service_checks_expected_title_input.setPlaceholderText("Например: Дежурная проверка сервисов")
        subject_form.addRow("Ожидаемая тема задачи проверки сервисов:", self.service_checks_expected_title_input)

        root.addWidget(subject_box)

        task_box = QGroupBox("Задачи дежурства")
        task_form = QFormLayout(task_box)

        self.duty_zabbix_task_number_input = QLineEdit()
        self.duty_zabbix_task_number_input.setText(self.settings().get("duty_zabbix_task_number", ""))
        self.duty_zabbix_task_number_input.setPlaceholderText("Например: 123456")
        task_form.addRow("№ задачи для Zabbix / графиков:", self.duty_zabbix_task_number_input)

        self.duty_service_checks_task_number_input = QLineEdit()
        self.duty_service_checks_task_number_input.setText(self.settings().get("duty_service_checks_task_number", ""))
        self.duty_service_checks_task_number_input.setPlaceholderText("Например: 654321")
        task_form.addRow("№ задачи для проверки сервисов:", self.duty_service_checks_task_number_input)

        task_hint = QLabel("Задача для проверки Zabbix / графиков и задача для проверки сервисов хранятся отдельно.")
        task_hint.setWordWrap(True)
        task_form.addRow(task_hint)
        root.addWidget(task_box)

        self.otrs_auto_submit_checkbox = QCheckBox("Автоматически нажимать кнопку «Вход»")
        self.otrs_auto_submit_checkbox.setChecked(self.settings().get("otrs_auto_submit_login", False))
        root.addWidget(self.otrs_auto_submit_checkbox)

    def build_graphs_section(self, root):
        hint = QLabel("Выбери графики, которые должны открываться при дежурной проверке.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.graph_list = QListWidget()
        root.addWidget(self.graph_list, stretch=1)

    def settings(self):
        settings = ensure_duty_mode_defaults(self.config)
        ensure_duty_links(self.config)
        settings.setdefault("otrs_create_url", get_duty_link(self.config, "otrs_create_url") or settings.get("otrs", {}).get("create_url", ""))
        return settings

    def duty_triggers_settings(self):
        return ensure_duty_triggers_defaults(self.config)

    def build_triggers_ui(self, root):
        self.triggers_enabled_checkbox = QCheckBox("Включить триггеры дежурства")
        self.triggers_enabled_checkbox.setChecked(self.duty_triggers_settings().get("enabled", True))
        root.addWidget(self.triggers_enabled_checkbox)

        self.trigger_list = QListWidget()
        root.addWidget(self.trigger_list, stretch=1)

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
        root.addLayout(trigger_buttons)

    def build_zabbix_trigger_catalog_ui(self, root):
        hint = QLabel("Импортируйте XLSX-каталог триггеров Zabbix и включайте только те шаблоны, которые должны участвовать в фильтрации проблем.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        actions = QHBoxLayout()
        import_button = QPushButton("Загрузить XLSX со списком триггеров")
        import_button.clicked.connect(self.import_zabbix_trigger_catalog)
        clear_button = QPushButton("Очистить каталог")
        clear_button.clicked.connect(self.clear_zabbix_trigger_catalog)
        enable_all = QPushButton("Включить все")
        enable_all.clicked.connect(lambda: self.set_all_zabbix_catalog_enabled(True))
        disable_all = QPushButton("Отключить все")
        disable_all.clicked.connect(lambda: self.set_all_zabbix_catalog_enabled(False))
        actions.addWidget(import_button)
        actions.addWidget(clear_button)
        actions.addWidget(enable_all)
        actions.addWidget(disable_all)
        actions.addStretch(1)
        root.addLayout(actions)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Поиск:"))
        self.zabbix_catalog_search = QLineEdit()
        self.zabbix_catalog_search.setPlaceholderText("Триггер, описание или категория")
        self.zabbix_catalog_search.textChanged.connect(self.reload_zabbix_trigger_catalog_table)
        search_row.addWidget(self.zabbix_catalog_search, stretch=1)
        root.addLayout(search_row)

        self.zabbix_catalog_empty_label = QLabel("Каталог триггеров не загружен.")
        self.zabbix_catalog_empty_label.setWordWrap(True)
        root.addWidget(self.zabbix_catalog_empty_label)

        self.zabbix_catalog_table = QTableWidget(0, 5)
        self.zabbix_catalog_table.setHorizontalHeaderLabels(["Включён", "Категория", "Триггер", "Описание", "Листы"])
        self.zabbix_catalog_table.setWordWrap(True)
        self.zabbix_catalog_table.itemChanged.connect(self.on_zabbix_catalog_item_changed)
        root.addWidget(self.zabbix_catalog_table, stretch=1)
        self.reload_zabbix_trigger_catalog_table()

    def import_zabbix_trigger_catalog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Загрузить XLSX со списком триггеров",
            "",
            "Excel (*.xlsx);;Все файлы (*)",
        )
        if not file_path:
            return
        try:
            imported = import_zabbix_trigger_catalog_from_xlsx(file_path)
        except Exception as exc:
            QMessageBox.warning(self, "Триггеры Zabbix", f"Не удалось импортировать XLSX:\n{exc}")
            return
        self.zabbix_trigger_catalog_entries = imported
        self.persist_zabbix_trigger_catalog()
        self.reload_zabbix_trigger_catalog_table()
        QMessageBox.information(self, "Триггеры Zabbix", f"Импортировано триггеров: {len(imported)}")

    def persist_zabbix_trigger_catalog(self):
        save_zabbix_trigger_catalog(self.zabbix_trigger_catalog_entries, config=self.config)
        save_config(self.config)

    def clear_zabbix_trigger_catalog(self):
        if not self.zabbix_trigger_catalog_entries:
            return
        reply = QMessageBox.question(self, "Триггеры Zabbix", "Очистить каталог триггеров Zabbix?", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.zabbix_trigger_catalog_entries = []
        self.persist_zabbix_trigger_catalog()
        self.reload_zabbix_trigger_catalog_table()

    def set_all_zabbix_catalog_enabled(self, enabled):
        for entry in self.zabbix_trigger_catalog_entries:
            entry.enabled = bool(enabled)
        self.persist_zabbix_trigger_catalog()
        self.reload_zabbix_trigger_catalog_table()

    def _filtered_zabbix_catalog_entries(self):
        query = " ".join((self.zabbix_catalog_search.text() if hasattr(self, "zabbix_catalog_search") else "").casefold().split())
        if not query:
            return list(self.zabbix_trigger_catalog_entries)
        result = []
        for entry in self.zabbix_trigger_catalog_entries:
            haystack = " ".join([entry.name, entry.description, entry.category]).casefold()
            if query in haystack:
                result.append(entry)
        return result

    def reload_zabbix_trigger_catalog_table(self):
        if not hasattr(self, "zabbix_catalog_table"):
            return
        entries = self._filtered_zabbix_catalog_entries()
        self.zabbix_catalog_table.blockSignals(True)
        self.zabbix_catalog_table.setRowCount(0)
        for entry in entries:
            row = self.zabbix_catalog_table.rowCount()
            self.zabbix_catalog_table.insertRow(row)
            enabled_item = QTableWidgetItem("")
            enabled_item.setFlags(enabled_item.flags() | Qt.ItemIsUserCheckable)
            enabled_item.setCheckState(Qt.Checked if entry.enabled else Qt.Unchecked)
            enabled_item.setData(Qt.UserRole, entry.id)
            self.zabbix_catalog_table.setItem(row, 0, enabled_item)
            for col, value in enumerate([entry.category, entry.name, entry.description, ", ".join(entry.source_sheets)], start=1):
                item = QTableWidgetItem(str(value or ""))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.zabbix_catalog_table.setItem(row, col, item)
        self.zabbix_catalog_table.resizeColumnsToContents()
        self.zabbix_catalog_table.blockSignals(False)
        self.zabbix_catalog_empty_label.setVisible(not self.zabbix_trigger_catalog_entries)

    def on_zabbix_catalog_item_changed(self, item):
        if item.column() != 0:
            return
        entry_id = item.data(Qt.UserRole)
        for entry in self.zabbix_trigger_catalog_entries:
            if entry.id == entry_id:
                entry.enabled = item.checkState() == Qt.Checked
                self.persist_zabbix_trigger_catalog()
                break

    def build_thresholds_ui(self, root):
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
        root.addLayout(thresholds)

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
        settings["otrs_create_url"] = self.otrs_create_url_link_input.text().strip()
        set_duty_link(self.config, "otrs_create_url", settings["otrs_create_url"])
        set_duty_link(self.config, "live_zabbix_url", self.live_zabbix_url_input.text().strip())
        set_duty_link(self.config, "redmine_create_url", self.redmine_create_url_input.text().strip())
        set_duty_link(self.config, "mm_otrs_create_url", self.mm_otrs_create_url_input.text().strip())
        settings["duty_zabbix_expected_task_title"] = self.zabbix_expected_title_input.text().strip() or "Дежурная проверка Zabbix / графиков"
        settings["duty_service_checks_expected_task_title"] = self.service_checks_expected_title_input.text().strip() or "Дежурная проверка сервисов"
        settings["expected_ticket_subject"] = settings["duty_zabbix_expected_task_title"]
        settings["expected_service_checks_ticket_subject"] = settings["duty_service_checks_expected_task_title"]
        self.logger.info("Duty Zabbix expected task title saved")
        self.logger.info("Duty service checks expected task title saved")
        settings["duty_service_checks_enabled"] = self.duty_service_checks_enabled_checkbox.isChecked()
        settings["duty_zabbix_task_number"] = self.duty_zabbix_task_number_input.text().strip()
        settings["duty_service_checks_task_number"] = self.duty_service_checks_task_number_input.text().strip()
        for prefix in ("duty_zabbix_task", "duty_service_checks_task"):
            if not settings.get(f"{prefix}_number", ""):
                for key in ("id", "url", "system", "status", "linked_at", "session_id"):
                    settings[f"{prefix}_{key}"] = ""
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
        save_zabbix_trigger_catalog(self.zabbix_trigger_catalog_entries, config=self.config)

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
