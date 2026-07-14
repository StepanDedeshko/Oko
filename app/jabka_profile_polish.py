from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.jabka_theme import is_jabka_config


JABKA_PROFILE_QSS = r"""
QWidget#JabkaProfilePage {
    background: transparent;
}
QGroupBox#ProfileIntegrationsCard,
QGroupBox#ProfileServiceGroupsCard {
    background: rgba(8, 31, 18, 225);
    border: 1px solid rgba(102, 185, 91, 175);
    border-radius: 18px;
    margin-top: 14px;
    padding: 14px 14px 12px 14px;
    font-weight: 700;
}
QGroupBox#ProfileIntegrationsCard::title,
QGroupBox#ProfileServiceGroupsCard::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 16px;
    padding: 0 8px;
    color: #EAF8D8;
}
QGroupBox#ProfileIntegrationSection,
QGroupBox#ProfileServiceGroupEditor {
    background: rgba(6, 23, 13, 220);
    border: 1px solid rgba(102, 185, 91, 115);
    border-radius: 13px;
    margin-top: 12px;
    padding: 10px 10px 8px 10px;
    font-weight: 700;
}
QGroupBox#ProfileIntegrationSection::title,
QGroupBox#ProfileServiceGroupEditor::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #B7F27A;
}
QScrollArea#ProfileIntegrationsScroll,
QScrollArea#ProfileServiceGroupEditorScroll {
    background: transparent;
    border: none;
}
QScrollArea#ProfileIntegrationsScroll > QWidget > QWidget,
QScrollArea#ProfileServiceGroupEditorScroll > QWidget > QWidget {
    background: transparent;
}
QListWidget#ProfileServiceGroupsList {
    background: rgba(6, 23, 13, 235);
    border: 1px solid rgba(102, 185, 91, 135);
    border-radius: 13px;
    padding: 6px;
    outline: 0;
}
QListWidget#ProfileServiceGroupsList::item {
    min-height: 32px;
    padding: 5px 8px;
    border-radius: 8px;
}
QListWidget#ProfileServiceGroupsList::item:hover {
    background: rgba(33, 79, 43, 210);
}
QListWidget#ProfileServiceGroupsList::item:selected {
    background: #B7F27A;
    color: #07140D;
}
QLabel#ProfileColumnHint {
    color: #CFE8C2;
    padding: 2px 3px 8px 3px;
}
QSplitter#ProfileColumns::handle {
    background: rgba(102, 185, 91, 90);
    width: 8px;
    margin: 10px 3px;
    border-radius: 4px;
}
QSplitter#ProfileColumns::handle:hover {
    background: rgba(183, 242, 122, 155);
}
"""


def _drain_layout(layout) -> None:
    """Detach old layout items without deleting credential widgets or data."""
    while layout.count():
        item = layout.takeAt(0)
        nested = item.layout()
        if nested is not None:
            _drain_layout(nested)


def _find_group_box(widget, title: str):
    for box in widget.findChildren(QGroupBox):
        if box.title().strip() == title:
            return box
    return None


def _find_button(widget, text: str):
    for button in widget.findChildren(QPushButton):
        if button.text().strip() == text:
            return button
    return None


def _show(widget) -> None:
    if widget is not None:
        widget.show()


def _add_credentials_form(layout: QVBoxLayout, login, password) -> None:
    form = QFormLayout()
    form.setContentsMargins(0, 2, 0, 0)
    form.setHorizontalSpacing(10)
    form.setVerticalSpacing(8)
    login.setMinimumHeight(38)
    password.setMinimumHeight(38)
    login.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    password.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    _show(login)
    _show(password)
    form.addRow("Логин:", login)
    form.addRow("Пароль:", password)
    layout.addLayout(form)


def _integration_section(title: str, parent=None):
    section = QGroupBox(title, parent)
    section.setObjectName("ProfileIntegrationSection")
    section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    layout = QVBoxLayout(section)
    layout.setContentsMargins(12, 14, 12, 10)
    layout.setSpacing(8)
    return section, layout


def _build_integrations(widget) -> QGroupBox:
    card = QGroupBox("Интеграции")
    card.setObjectName("ProfileIntegrationsCard")
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(14, 18, 14, 12)
    card_layout.setSpacing(8)

    hint = QLabel("Учётные данные OTRS, Zabbix и Redmine.")
    hint.setObjectName("ProfileColumnHint")
    hint.setWordWrap(True)
    card_layout.addWidget(hint)

    scroll = QScrollArea(card)
    scroll.setObjectName("ProfileIntegrationsScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    container = QWidget(scroll)
    content = QVBoxLayout(container)
    content.setContentsMargins(0, 0, 6, 0)
    content.setSpacing(10)

    otrs, otrs_layout = _integration_section("OTRS", container)
    widget.enabled.setParent(otrs)
    widget.otrs_auto_submit_login.setParent(otrs)
    _show(widget.enabled)
    _show(widget.otrs_auto_submit_login)
    otrs_layout.addWidget(widget.enabled)
    otrs_layout.addWidget(widget.otrs_auto_submit_login)
    widget.login.setParent(otrs)
    widget.password.setParent(otrs)
    _add_credentials_form(otrs_layout, widget.login, widget.password)
    content.addWidget(otrs)

    zabbix, zabbix_layout = _integration_section("Zabbix", container)
    if widget.zabbix_inputs:
        for zabbix_id, fields in widget.zabbix_inputs.items():
            instance = QGroupBox(str(fields.get("name") or zabbix_id), zabbix)
            instance.setObjectName("ProfileIntegrationSection")
            instance_layout = QVBoxLayout(instance)
            instance_layout.setContentsMargins(10, 13, 10, 8)
            instance_layout.setSpacing(6)
            fields["login"].setParent(instance)
            fields["password"].setParent(instance)
            _add_credentials_form(instance_layout, fields["login"], fields["password"])
            zabbix_layout.addWidget(instance)
    else:
        empty = QLabel("Включённые Zabbix-профили не найдены.")
        empty.setWordWrap(True)
        zabbix_layout.addWidget(empty)
    content.addWidget(zabbix)

    redmine, redmine_layout = _integration_section("Redmine", container)
    widget.redmine_save_credentials_checkbox.setParent(redmine)
    _show(widget.redmine_save_credentials_checkbox)
    redmine_layout.addWidget(widget.redmine_save_credentials_checkbox)
    widget.redmine_username_input.setParent(redmine)
    widget.redmine_password_input.setParent(redmine)
    _add_credentials_form(redmine_layout, widget.redmine_username_input, widget.redmine_password_input)
    # URL is edited centrally on Settings -> Links. Keep the compatibility field hidden.
    widget.redmine_login_url_input.hide()
    content.addWidget(redmine)

    content.addStretch(1)
    scroll.setWidget(container)
    card_layout.addWidget(scroll, stretch=1)

    widget.profile_integrations_card = card
    widget.profile_integrations_scroll = scroll
    return card


def _select_service_group(widget, row: int) -> None:
    stack = getattr(widget, "profile_service_group_stack", None)
    if stack is None:
        return
    if 0 <= row < stack.count():
        stack.setCurrentIndex(row)


def _build_service_groups(widget) -> QGroupBox:
    card = QGroupBox("Группы сервисов")
    card.setObjectName("ProfileServiceGroupsCard")
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(14, 18, 14, 12)
    card_layout.setSpacing(8)

    hint = QLabel("Выберите группу и укажите личный логин и пароль для её сервисов.")
    hint.setObjectName("ProfileColumnHint")
    hint.setWordWrap(True)
    card_layout.addWidget(hint)

    if not widget.service_group_inputs:
        empty = QLabel("Группы сервисов ещё не настроены администратором.")
        empty.setWordWrap(True)
        card_layout.addWidget(empty)
        card_layout.addStretch(1)
        widget.profile_service_groups_card = card
        widget.profile_service_groups_list = None
        widget.profile_service_group_stack = None
        return card

    inner = QSplitter(Qt.Orientation.Horizontal, card)
    inner.setObjectName("ProfileServiceGroupsInner")
    inner.setChildrenCollapsible(False)
    inner.setHandleWidth(7)

    group_list = QListWidget(inner)
    group_list.setObjectName("ProfileServiceGroupsList")
    group_list.setMinimumWidth(210)
    group_list.setMaximumWidth(330)

    stack = QStackedWidget(inner)
    stack.setObjectName("ProfileServiceGroupStack")

    for group_id, fields in widget.service_group_inputs.items():
        group_name = str(fields.get("name") or group_id)
        item = QListWidgetItem(group_name)
        item.setData(Qt.ItemDataRole.UserRole, group_id)
        group_list.addItem(item)

        page = QGroupBox(group_name, stack)
        page.setObjectName("ProfileServiceGroupEditor")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(14, 18, 14, 12)
        page_layout.setSpacing(10)

        description = QLabel("Эти данные используются всеми сервисами выбранной группы.")
        description.setWordWrap(True)
        page_layout.addWidget(description)

        fields["login"].setParent(page)
        fields["password"].setParent(page)
        _add_credentials_form(page_layout, fields["login"], fields["password"])
        page_layout.addStretch(1)
        stack.addWidget(page)

    group_list.currentRowChanged.connect(lambda row: _select_service_group(widget, row))
    inner.addWidget(group_list)
    inner.addWidget(stack)
    inner.setStretchFactor(0, 0)
    inner.setStretchFactor(1, 1)
    inner.setSizes([270, 560])
    card_layout.addWidget(inner, stretch=1)

    group_list.setCurrentRow(0)
    widget.profile_service_groups_card = card
    widget.profile_service_groups_list = group_list
    widget.profile_service_group_stack = stack
    return card


def apply_jabka_profile_polish(widget) -> bool:
    if widget is None or not is_jabka_config(getattr(widget, "config", None)):
        return False
    if widget.property("jabka_profile_polished"):
        return False

    root = widget.layout()
    if root is None:
        return False

    account = _find_group_box(widget, "Аккаунт Око")
    save_button = _find_button(widget, "Сохранить все доступы")
    clear_button = _find_button(widget, "Удалить сохранённые Zabbix-пароли")
    if account is None or save_button is None or clear_button is None:
        return False

    _drain_layout(root)

    # Hide obsolete section labels and row labels left from the old one-column form.
    for child in widget.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
        if child is account:
            continue
        child.hide()

    widget.setObjectName("JabkaProfilePage")
    root.setContentsMargins(12, 8, 12, 12)
    root.setSpacing(10)

    account.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    account.show()
    root.addWidget(account)

    integrations = _build_integrations(widget)
    service_groups = _build_service_groups(widget)

    columns = QSplitter(Qt.Orientation.Horizontal, widget)
    columns.setObjectName("ProfileColumns")
    columns.setChildrenCollapsible(False)
    columns.setHandleWidth(9)
    columns.addWidget(integrations)
    columns.addWidget(service_groups)
    columns.setStretchFactor(0, 1)
    columns.setStretchFactor(1, 1)
    columns.setSizes([900, 760])
    root.addWidget(columns, stretch=1)

    actions = QHBoxLayout()
    save_button.setObjectName("PrimaryAction")
    save_button.show()
    clear_button.show()
    actions.addWidget(save_button)
    actions.addWidget(clear_button)
    actions.addStretch(1)
    root.addLayout(actions)

    widget.profile_columns = columns
    widget.profile_save_button = save_button
    widget.profile_clear_zabbix_button = clear_button
    widget.setStyleSheet(widget.styleSheet() + "\n" + JABKA_PROFILE_QSS)
    widget.setProperty("jabka_profile_polished", True)
    return True


def install_jabka_profile_polish() -> bool:
    import app.home_config as home_config

    cls = home_config.ProfileWidget
    if getattr(cls, "_jabka_profile_patch_installed", False):
        return False

    original_init = cls.__init__

    def __init__(self, config, logout_callback=None, parent=None):
        original_init(self, config, logout_callback, parent)
        apply_jabka_profile_polish(self)

    cls.__init__ = __init__
    cls._jabka_profile_patch_installed = True
    return True
