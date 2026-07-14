from __future__ import annotations

import json
import sys
from typing import Any

CANONICAL_LINKS_SCHEMA_VERSION = 1

LINK_KEYS = (
    "redmine_create_url",
    "otrs_create_url",
    "mm_otrs_create_url",
    "live_zabbix_url",
)

DEFAULT_LINK_VALUES = {
    "redmine_create_url": "",
    "otrs_create_url": "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentNewTicketForm;NewTicketFormID=6",
    "mm_otrs_create_url": "",
    "live_zabbix_url": "",
}

LEGACY_LINK_PATHS = {
    "live_zabbix_url": (
        ("live_zabbix_monitor", "problems_url"),
        ("live_zabbix_monitor", "url"),
        ("duty_mode", "live_zabbix_url"),
    ),
    "redmine_create_url": (
        ("duty_mode", "redmine_create_url"),
        ("live_zabbix_monitor", "redmine_create_url"),
        ("templates", "redmine_task", "create_url"),
        ("templates", "redmine_special_task", "create_url"),
    ),
    "otrs_create_url": (
        ("duty_mode", "otrs_create_url"),
        ("duty_mode", "otrs", "create_url"),
    ),
    "mm_otrs_create_url": (
        ("duty_mode", "mm_otrs_create_url"),
        ("live_zabbix_monitor", "mm_otrs_create_url"),
    ),
}

MIRROR_LINK_PATHS = {
    "live_zabbix_url": (
        ("live_zabbix_monitor", "problems_url"),
        ("live_zabbix_monitor", "url"),
        ("duty_mode", "live_zabbix_url"),
    ),
    "redmine_create_url": (
        ("duty_mode", "redmine_create_url"),
        ("live_zabbix_monitor", "redmine_create_url"),
        ("templates", "redmine_task", "create_url"),
        ("templates", "redmine_special_task", "create_url"),
    ),
    "otrs_create_url": (
        ("duty_mode", "otrs_create_url"),
        ("duty_mode", "otrs", "create_url"),
    ),
    "mm_otrs_create_url": (
        ("duty_mode", "mm_otrs_create_url"),
        ("live_zabbix_monitor", "mm_otrs_create_url"),
    ),
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _read_path(config: dict, path: tuple[str, ...]) -> str:
    current: Any = config
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return ""
        current = current.get(key)
    return _clean(current)


def _write_path(config: dict, path: tuple[str, ...], value: str) -> None:
    current = config
    for key in path[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[path[-1]] = value


def _first_product_problem_url(config: dict) -> str:
    for product in config.get("products", []) or []:
        if not isinstance(product, dict):
            continue
        for dashboard in product.get("dashboards", []) or []:
            if not isinstance(dashboard, dict):
                continue
            if dashboard.get("type") == "problems_page" and _clean(dashboard.get("url")):
                return _clean(dashboard.get("url"))
    return ""


def _legacy_value(config: dict, key: str) -> str:
    for path in LEGACY_LINK_PATHS.get(key, ()):
        value = _read_path(config, path)
        if value:
            return value
    if key == "live_zabbix_url":
        return _first_product_problem_url(config)
    return _clean(DEFAULT_LINK_VALUES.get(key, ""))


def _sync_legacy_mirrors(config: dict, links: dict) -> None:
    for key in LINK_KEYS:
        value = _clean(links.get(key))
        for path in MIRROR_LINK_PATHS.get(key, ()):
            _write_path(config, path, value)


def ensure_canonical_links(config: dict) -> dict:
    """Return the single source of truth for all shared technical URLs.

    The first 0.3.7 migration recovers values from every historic location,
    including Redmine template fields that older migrations missed. After the
    schema marker is stored, an explicitly cleared canonical value remains
    cleared and can no longer be resurrected by a stale legacy field.
    """
    links = config.setdefault("duty_links", {})
    if not isinstance(links, dict):
        links = {}
        config["duty_links"] = links

    try:
        schema_version = int(links.get("_schema_version", 0) or 0)
    except (TypeError, ValueError):
        schema_version = 0

    first_canonical_migration = schema_version < CANONICAL_LINKS_SCHEMA_VERSION
    for key in LINK_KEYS:
        has_key = key in links
        current = _clean(links.get(key))
        if not has_key or (first_canonical_migration and not current):
            recovered = _legacy_value(config, key)
            if recovered:
                links[key] = recovered
            else:
                links.setdefault(key, "")
        else:
            links[key] = current

    links["_schema_version"] = CANONICAL_LINKS_SCHEMA_VERSION
    _sync_legacy_mirrors(config, links)
    return links


def get_canonical_link(config: dict, key: str) -> str:
    if key not in LINK_KEYS:
        return ""
    links = ensure_canonical_links(config)
    return _clean(links.get(key))


def set_canonical_link(config: dict, key: str, value: str) -> None:
    if key not in LINK_KEYS:
        return
    links = ensure_canonical_links(config)
    links[key] = _clean(value)
    _sync_legacy_mirrors(config, links)


def _json_snapshot(config: dict) -> str:
    return json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def migrate_canonical_links(config: dict) -> bool:
    before = _json_snapshot(config)
    ensure_canonical_links(config)
    return before != _json_snapshot(config)


def _install_function_bindings() -> None:
    import app.permissions as permissions

    original_ensure = permissions.ensure_duty_links
    original_get = permissions.get_duty_link
    original_set = permissions.set_duty_link

    permissions.ensure_duty_links = ensure_canonical_links
    permissions.get_duty_link = get_canonical_link
    permissions.set_duty_link = set_canonical_link

    # Several modules imported these helpers directly before startup patching.
    # Replace only the exact original function objects, never unrelated names.
    for module in tuple(sys.modules.values()):
        if module is None:
            continue
        namespace = getattr(module, "__dict__", {})
        if namespace.get("ensure_duty_links") is original_ensure:
            namespace["ensure_duty_links"] = ensure_canonical_links
        if namespace.get("get_duty_link") is original_get:
            namespace["get_duty_link"] = get_canonical_link
        if namespace.get("set_duty_link") is original_set:
            namespace["set_duty_link"] = set_canonical_link


def _install_links_page_patch() -> None:
    import app.home_config as home_config

    cls = home_config.LinksSettingsWidget
    if getattr(cls, "_canonical_links_patched", False):
        return

    def __init__(self, config, parent=None):
        home_config.QWidget.__init__(self, parent)
        self.config = home_config.ensure_home_defaults(config)
        ensure_canonical_links(self.config)

        root = home_config.QVBoxLayout(self)
        title = home_config.QLabel("Ссылки")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        hint = home_config.QLabel(
            "Это единственное место редактирования общих рабочих URL. "
            "Live Zabbix, Redmine, ОТРС, ОТРС ММ, дежурка и шаблоны используют значения отсюда. "
            "Старые копии поддерживаются только внутри конфигурации для совместимости и не показываются в других разделах."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = home_config.QFormLayout()
        self.redmine_create_url_input = home_config.QLineEdit(get_canonical_link(self.config, "redmine_create_url"))
        live = home_config.ensure_live_monitor_defaults(self.config)
        self.redmine_login_url_input = home_config.QLineEdit(
            _clean(live.get("redmine_login_url")) or home_config.DEFAULT_REDMINE_LOGIN_URL
        )
        self.otrs_create_url_input = home_config.QLineEdit(get_canonical_link(self.config, "otrs_create_url"))
        self.mm_otrs_create_url_input = home_config.QLineEdit(get_canonical_link(self.config, "mm_otrs_create_url"))
        self.zabbix_problems_url_input = home_config.QLineEdit(get_canonical_link(self.config, "live_zabbix_url"))

        self.redmine_create_url_input.setPlaceholderText("URL создания задачи Redmine")
        self.redmine_login_url_input.setPlaceholderText("URL страницы входа Redmine")
        self.otrs_create_url_input.setPlaceholderText("URL создания обычной задачи ОТРС")
        self.mm_otrs_create_url_input.setPlaceholderText("URL создания задачи ОТРС ММ")
        self.zabbix_problems_url_input.setPlaceholderText("URL страницы Zabbix Problems")

        form.addRow("URL создания задачи Redmine:", self.redmine_create_url_input)
        form.addRow("URL окна авторизации Redmine:", self.redmine_login_url_input)
        form.addRow("URL создания задачи ОТРС:", self.otrs_create_url_input)
        form.addRow("URL создания задачи ОТРС ММ:", self.mm_otrs_create_url_input)
        form.addRow("URL Zabbix Problems:", self.zabbix_problems_url_input)
        root.addLayout(form)

        save = home_config.QPushButton("Сохранить ссылки")
        save.setObjectName("PrimaryAction")
        save.clicked.connect(self.save_links)
        root.addWidget(save)
        root.addStretch(1)

    def save_links(self):
        set_canonical_link(self.config, "redmine_create_url", self.redmine_create_url_input.text())
        set_canonical_link(self.config, "otrs_create_url", self.otrs_create_url_input.text())
        set_canonical_link(self.config, "mm_otrs_create_url", self.mm_otrs_create_url_input.text())
        set_canonical_link(self.config, "live_zabbix_url", self.zabbix_problems_url_input.text())

        live = home_config.ensure_live_monitor_defaults(self.config)
        live["redmine_login_url"] = (
            self.redmine_login_url_input.text().strip() or home_config.DEFAULT_REDMINE_LOGIN_URL
        )
        ensure_canonical_links(self.config)
        home_config.save_config(self.config)
        home_config.QMessageBox.information(
            self,
            "Ссылки",
            "Ссылки сохранены. Все модули будут использовать значения из этого раздела.",
        )

    cls.__init__ = __init__
    cls.save_links = save_links
    cls._canonical_links_patched = True


def _install_developer_page_patch() -> None:
    import app.home_config as home_config

    cls = home_config.LiveZabbixDeveloperSettingsWidget
    if getattr(cls, "_canonical_links_patched", False):
        return

    def __init__(self, config, parent=None):
        home_config.QGroupBox.__init__(self, "Live Zabbix Monitor", parent)
        self.config = config
        self.settings = home_config.ensure_live_monitor_defaults(self.config)

        root = home_config.QVBoxLayout(self)
        hint = home_config.QLabel(
            "Здесь остаются только технические параметры Live Zabbix Monitor. "
            "URL Zabbix Problems и URL ОТРС ММ редактируются в «Настройки → Ссылки»."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = home_config.QFormLayout()
        self.interval_input = home_config.QSpinBox()
        self.interval_input.setRange(60, 3600)
        self.interval_input.setSuffix(" сек")
        try:
            interval = int(self.settings.get("poll_interval_seconds", 60) or 60)
        except (TypeError, ValueError):
            interval = 60
        self.interval_input.setValue(max(60, min(3600, interval)))

        self.profile_input = home_config.QLineEdit(
            self.settings.get("zabbix_profile_id")
            or self.settings.get("profile_id")
            or "zbx_product_1"
        )
        self.profile_input.setPlaceholderText("zbx_product_1")

        self.show_diagnostics_checkbox = home_config.QCheckBox(
            "Показывать в Live Zabbix кнопки DOM/WebView и JSON-диагностику"
        )
        self.show_diagnostics_checkbox.setChecked(
            bool(
                self.settings.get("show_live_zabbix_diagnostics", False)
                or self.settings.get("show_developer_tools", False)
            )
        )

        form.addRow("Интервал опроса:", self.interval_input)
        form.addRow("Профиль Zabbix:", self.profile_input)
        form.addRow("", self.show_diagnostics_checkbox)
        root.addLayout(form)

        buttons = home_config.QHBoxLayout()
        save_button = home_config.QPushButton("Сохранить настройки Live Zabbix")
        save_button.clicked.connect(self.save_settings)
        buttons.addWidget(save_button)
        buttons.addStretch(1)
        root.addLayout(buttons)

    def save_settings(self):
        profile_id = self.profile_input.text().strip() or "zbx_product_1"
        interval = max(60, int(self.interval_input.value()))
        self.settings["poll_interval_seconds"] = interval
        self.settings["zabbix_profile_id"] = profile_id
        self.settings["profile_id"] = profile_id
        self.settings["show_live_zabbix_diagnostics"] = self.show_diagnostics_checkbox.isChecked()
        ensure_canonical_links(self.config)
        home_config.save_config(self.config)
        home_config.QMessageBox.information(
            self,
            "Live Zabbix Monitor",
            "Технические настройки Live Zabbix сохранены. Для полного применения перезапустите приложение.",
        )

    cls.__init__ = __init__
    cls.save_settings = save_settings
    cls._canonical_links_patched = True


def _prepare_hidden_duty_link_fields(widget) -> None:
    import app.duty_settings as duty_settings

    fields = (
        ("live_zabbix_url_input", "live_zabbix_url"),
        ("redmine_create_url_input", "redmine_create_url"),
        ("otrs_create_url_link_input", "otrs_create_url"),
        ("mm_otrs_create_url_input", "mm_otrs_create_url"),
    )
    for attr_name, key in fields:
        field = getattr(widget, attr_name, None)
        if field is None:
            field = duty_settings.QLineEdit(widget)
            field.hide()
            setattr(widget, attr_name, field)
        field.setText(get_canonical_link(widget.config, key))


def _install_duty_settings_patch() -> None:
    import app.duty_settings as duty_settings

    cls = duty_settings.DutyModeSettingsWidget
    if getattr(cls, "_canonical_links_patched", False):
        return

    original_save = cls.save

    def build_general_section(self, root):
        self.enabled_checkbox = duty_settings.QCheckBox("Включить режим дежурства")
        self.enabled_checkbox.setChecked(self.settings().get("enabled", False))
        root.addWidget(self.enabled_checkbox)

        row = duty_settings.QHBoxLayout()
        row.addWidget(duty_settings.QLabel("Повтор после пропуска, минут:"))
        self.skip_minutes = duty_settings.NoWheelSpinBox()
        self.skip_minutes.setMinimum(1)
        self.skip_minutes.setMaximum(120)
        self.skip_minutes.setValue(int(self.settings().get("skip_minutes", 5)))
        row.addWidget(self.skip_minutes)
        row.addStretch()
        root.addLayout(row)

        sound_row = duty_settings.QHBoxLayout()
        self.sound_label = duty_settings.QLabel(self.settings().get("sound_path", "") or "Звук не выбран")
        self.sound_label.setWordWrap(True)
        choose_sound = duty_settings.QPushButton("Выбрать звук")
        choose_sound.clicked.connect(self.choose_sound)
        clear_sound = duty_settings.QPushButton("Убрать звук")
        clear_sound.clicked.connect(self.clear_sound)
        sound_row.addWidget(duty_settings.QLabel("Звук уведомления:"))
        sound_row.addWidget(self.sound_label, stretch=1)
        sound_row.addWidget(choose_sound)
        sound_row.addWidget(clear_sound)
        root.addLayout(sound_row)

        links_hint = duty_settings.QLabel(
            "Рабочие URL Zabbix, Redmine, ОТРС и ОТРС ММ настраиваются только в разделе «Настройки → Ссылки»."
        )
        links_hint.setWordWrap(True)
        root.addWidget(links_hint)

        self.duty_service_checks_enabled_checkbox = duty_settings.QCheckBox(
            "Проверять сервисы в режиме дежурства"
        )
        self.duty_service_checks_enabled_checkbox.setChecked(
            bool(self.settings().get("duty_service_checks_enabled", False))
        )
        self.duty_service_checks_enabled_checkbox.setToolTip(
            "Если выключено, при дежурной проверке графиков/Zabbix проверка сервисов запускаться не будет."
        )
        root.addWidget(self.duty_service_checks_enabled_checkbox)

        service_checks_hint = duty_settings.QLabel(
            "Если выключено, при дежурной проверке графиков/Zabbix проверка сервисов запускаться не будет."
        )
        service_checks_hint.setWordWrap(True)
        root.addWidget(service_checks_hint)
        _prepare_hidden_duty_link_fields(self)

    def build_otrs_section(self, root):
        access_hint = duty_settings.QLabel(
            "Логин и пароль ОТРС настраиваются в разделе «Профиль», "
            "URL создания задачи — в разделе «Настройки → Ссылки»."
        )
        access_hint.setWordWrap(True)
        root.addWidget(access_hint)

        subject_box = duty_settings.QGroupBox("Ожидаемые темы задач")
        subject_form = duty_settings.QFormLayout(subject_box)

        self.zabbix_expected_title_input = duty_settings.QLineEdit()
        self.zabbix_expected_title_input.setText(
            self.settings().get(
                "duty_zabbix_expected_task_title",
                "Дежурная проверка Zabbix / графиков",
            )
        )
        self.zabbix_expected_title_input.setPlaceholderText(
            "Например: Дежурная проверка Zabbix / графиков"
        )
        subject_form.addRow(
            "Ожидаемая тема задачи Zabbix / графиков:",
            self.zabbix_expected_title_input,
        )

        self.service_checks_expected_title_input = duty_settings.QLineEdit()
        self.service_checks_expected_title_input.setText(
            self.settings().get(
                "duty_service_checks_expected_task_title",
                "Дежурная проверка сервисов",
            )
        )
        self.service_checks_expected_title_input.setPlaceholderText(
            "Например: Дежурная проверка сервисов"
        )
        subject_form.addRow(
            "Ожидаемая тема задачи проверки сервисов:",
            self.service_checks_expected_title_input,
        )
        root.addWidget(subject_box)

        task_box = duty_settings.QGroupBox("Задачи дежурства")
        task_form = duty_settings.QFormLayout(task_box)

        self.duty_zabbix_task_number_input = duty_settings.QLineEdit()
        self.duty_zabbix_task_number_input.setText(
            self.settings().get("duty_zabbix_task_number", "")
        )
        self.duty_zabbix_task_number_input.setPlaceholderText("Например: 123456")
        task_form.addRow(
            "№ задачи для Zabbix / графиков:",
            self.duty_zabbix_task_number_input,
        )

        self.duty_service_checks_task_number_input = duty_settings.QLineEdit()
        self.duty_service_checks_task_number_input.setText(
            self.settings().get("duty_service_checks_task_number", "")
        )
        self.duty_service_checks_task_number_input.setPlaceholderText("Например: 654321")
        task_form.addRow(
            "№ задачи для проверки сервисов:",
            self.duty_service_checks_task_number_input,
        )

        task_hint = duty_settings.QLabel(
            "Задача для проверки Zabbix / графиков и задача для проверки сервисов хранятся отдельно."
        )
        task_hint.setWordWrap(True)
        task_form.addRow(task_hint)
        root.addWidget(task_box)

        self.otrs_auto_submit_checkbox = duty_settings.QCheckBox(
            "Автоматически нажимать кнопку «Вход»"
        )
        self.otrs_auto_submit_checkbox.setChecked(
            self.settings().get("otrs_auto_submit_login", False)
        )
        root.addWidget(self.otrs_auto_submit_checkbox)

    def save(self):
        # An already opened duty page must never restore stale URL copies after
        # the user saves newer values on the Links page.
        _prepare_hidden_duty_link_fields(self)
        return original_save(self)

    cls.build_general_section = build_general_section
    cls.build_otrs_section = build_otrs_section
    cls.save = save
    cls._canonical_links_patched = True


def _install_templates_patch() -> None:
    import app.home_config as home_config
    import app.templates as templates

    original_get_redmine_task_template = templates.get_redmine_task_template

    def get_redmine_task_template(config, special=False):
        result = original_get_redmine_task_template(config, special=special)
        result["create_url"] = get_canonical_link(config, "redmine_create_url")
        return result

    templates.get_redmine_task_template = get_redmine_task_template

    live_widget = sys.modules.get("app.live_zabbix_widget")
    if live_widget is not None:
        live_widget.get_redmine_task_template = get_redmine_task_template

    cls = home_config.TemplatesWidget
    if getattr(cls, "_canonical_links_patched", False):
        return

    original_save_redmine_template = cls.save_redmine_template
    original_reset_redmine_template = cls.reset_redmine_template

    def _build_redmine_tab(self):
        page = home_config.QWidget()
        layout = home_config.QVBoxLayout(page)
        current_templates = home_config.ensure_templates_defaults(self.config)
        current = current_templates[home_config.REDMINE_TASK_TEMPLATE_KEY]
        special = current_templates[home_config.REDMINE_SPECIAL_TASK_TEMPLATE_KEY]

        source_hint = home_config.QLabel(
            "URL создания задачи Redmine настраивается только в разделе «Настройки → Ссылки»."
        )
        source_hint.setWordWrap(True)
        layout.addWidget(source_hint)

        form = home_config.QFormLayout()
        self.redmine_create_url_input = home_config.QLineEdit(
            get_canonical_link(self.config, "redmine_create_url"),
            self,
        )
        self.redmine_create_url_input.hide()

        self.redmine_subject_input = home_config.QLineEdit(
            current.get("subject_template", "")
        )
        self.redmine_description_input = home_config.QTextEdit()
        self.redmine_description_input.setPlainText(
            current.get("description_template", "")
        )
        self.redmine_description_input.setMinimumHeight(220)
        self.redmine_tracker_input = home_config.QLineEdit(
            str(current.get("tracker_id", ""))
        )
        self.redmine_priority_input = home_config.QLineEdit(
            str(current.get("priority_id", ""))
        )
        self.redmine_project_input = home_config.QLineEdit(
            current.get("project", "")
        )
        self.redmine_special_subject_input = home_config.QLineEdit(
            special.get("subject_template", "")
        )
        self.redmine_special_description_input = home_config.QTextEdit()
        self.redmine_special_description_input.setPlainText(
            special.get("description_template", "")
        )
        self.redmine_special_description_input.setMinimumHeight(180)

        form.addRow("Шаблон темы:", self.redmine_subject_input)
        form.addRow("Шаблон описания:", self.redmine_description_input)
        form.addRow("tracker_id:", self.redmine_tracker_input)
        form.addRow("priority_id:", self.redmine_priority_input)
        form.addRow("project identifier/project URL:", self.redmine_project_input)
        form.addRow("Тема спец. триггеров:", self.redmine_special_subject_input)
        form.addRow(
            "Описание спец. триггеров:",
            self.redmine_special_description_input,
        )
        layout.addLayout(form)

        actions = home_config.QHBoxLayout()
        save_button = home_config.QPushButton("Сохранить шаблон Redmine")
        save_button.setObjectName("PrimaryAction")
        save_button.clicked.connect(self.save_redmine_template)
        preview_button = home_config.QPushButton("Предпросмотр")
        preview_button.clicked.connect(self.preview_redmine_template)
        reset_button = home_config.QPushButton("Сбросить по умолчанию")
        reset_button.clicked.connect(self.reset_redmine_template)
        actions.addWidget(save_button)
        actions.addWidget(preview_button)
        actions.addWidget(reset_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        layout.addWidget(
            self._readonly_box(
                "Доступные переменные",
                home_config.variable_details_text(
                    home_config.REDMINE_GRAPH_VARIABLE_DETAILS
                ),
                minimum_height=260,
            )
        )
        redmine_warning = home_config.QLabel(
            "Для специальных триггеров используйте обычные ссылки ({special_graph_links}); "
            "inline-картинки вида !url! не вставляются автоматически."
        )
        redmine_warning.setWordWrap(True)
        layout.addWidget(redmine_warning)
        layout.addWidget(
            self._readonly_box(
                "Примеры вставки графиков",
                home_config.REDMINE_COLLAPSE_EXAMPLE
                + "\n"
                + home_config.REDMINE_ALL_GRAPHS_EXAMPLE,
            )
        )
        period_hint = home_config.QLabel(
            "Скриншоты графиков для Redmine должны формироваться за период 3 часа."
        )
        period_hint.setWordWrap(True)
        layout.addWidget(period_hint)
        return page

    def save_redmine_template(self):
        self.redmine_create_url_input.setText(
            get_canonical_link(self.config, "redmine_create_url")
        )
        result = original_save_redmine_template(self)
        ensure_canonical_links(self.config)
        home_config.save_config(self.config)
        return result

    def reset_redmine_template(self):
        canonical_url = get_canonical_link(self.config, "redmine_create_url")
        result = original_reset_redmine_template(self)
        current_templates = home_config.ensure_templates_defaults(self.config)
        current_templates[home_config.REDMINE_TASK_TEMPLATE_KEY][
            "create_url"
        ] = canonical_url
        current_templates[home_config.REDMINE_SPECIAL_TASK_TEMPLATE_KEY][
            "create_url"
        ] = canonical_url
        self.redmine_create_url_input.setText(canonical_url)
        home_config.save_config(self.config)
        return result

    cls._build_redmine_tab = _build_redmine_tab
    cls.save_redmine_template = save_redmine_template
    cls.reset_redmine_template = reset_redmine_template
    cls._canonical_links_patched = True


def _install_live_monitor_patch() -> None:
    import app.live_zabbix_widget as live_widget

    cls = live_widget.LiveZabbixMonitorWidget
    if getattr(cls, "_canonical_links_patched", False):
        return

    original_save_monitor_settings = cls.save_monitor_settings
    original_open_configured_url = cls.open_configured_url

    def problems_url(self):
        return get_canonical_link(self.config, "live_zabbix_url")

    def _refresh_hidden_url(self):
        if getattr(self, "url_input", None) is not None:
            self.url_input.setText(
                get_canonical_link(self.config, "live_zabbix_url")
            )

    def save_monitor_settings(self):
        _refresh_hidden_url(self)
        return original_save_monitor_settings(self)

    def open_configured_url(self):
        _refresh_hidden_url(self)
        return original_open_configured_url(self)

    cls.problems_url = problems_url
    cls.save_monitor_settings = save_monitor_settings
    cls.open_configured_url = open_configured_url
    cls._canonical_links_patched = True


def install_canonical_link_settings(config: dict) -> bool:
    """Install the one-page link settings model before any settings UI exists."""
    from app.config import save_config

    changed = migrate_canonical_links(config)
    _install_function_bindings()
    _install_links_page_patch()
    _install_developer_page_patch()
    _install_duty_settings_patch()
    _install_templates_patch()
    _install_live_monitor_patch()

    # Re-run after all compatibility bindings are active so every legacy
    # consumer receives the canonical value without deleting user settings.
    ensure_canonical_links(config)
    if changed:
        save_config(config)
    return True
