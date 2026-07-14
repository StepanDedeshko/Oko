from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QSplitter,
)

from app.jabka_theme import is_jabka_config


JABKA_SERVICE_CHECKS_QSS = r"""
QWidget#JabkaServiceChecksPage {
    background: transparent;
}
QGroupBox#ServiceCredentialGroupsCard {
    background: rgba(8, 31, 18, 225);
    border: 1px solid rgba(102, 185, 91, 175);
    border-radius: 18px;
    margin-top: 14px;
    padding: 14px 14px 12px 14px;
    font-weight: 700;
}
QGroupBox#ServiceCredentialGroupsCard::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 16px;
    padding: 0 8px;
    color: #EAF8D8;
}
QGroupBox#ServiceCredentialGroupsCard QLineEdit,
QGroupBox#ServiceCredentialGroupsCard QComboBox {
    min-height: 34px;
}
QListWidget#ServiceCredentialGroupMembers {
    background: rgba(6, 23, 13, 235);
    border: 1px solid rgba(102, 185, 91, 130);
    border-radius: 12px;
    padding: 6px;
    outline: 0;
}
QListWidget#ServiceCredentialGroupMembers::item {
    min-height: 28px;
    padding: 3px 7px;
    border-radius: 7px;
}
QListWidget#ServiceCredentialGroupMembers::item:hover {
    background: rgba(33, 79, 43, 210);
}
QListWidget#ServiceCredentialGroupMembers::item:selected {
    background: #B7F27A;
    color: #07140D;
}
QListWidget#ServiceProductsList {
    background: rgba(6, 23, 13, 235);
    border: 1px solid rgba(102, 185, 91, 145);
    border-radius: 14px;
    padding: 6px;
    outline: 0;
}
QListWidget#ServiceProductsList::item {
    min-height: 30px;
    padding: 4px 8px;
    border-radius: 8px;
}
QListWidget#ServiceProductsList::item:selected {
    background: #B7F27A;
    color: #07140D;
}
QSplitter#ServiceChecksEditor::handle {
    background: rgba(102, 185, 91, 90);
    width: 6px;
    margin: 8px 2px;
    border-radius: 3px;
}
"""


def _rename_label(root, old_text: str, new_text: str) -> None:
    for label in root.findChildren(QLabel):
        if label.text().strip() == old_text:
            label.setText(new_text)


def _rename_button(root, old_text: str, new_text: str) -> None:
    for button in root.findChildren(QPushButton):
        if button.text().strip() == old_text:
            button.setText(new_text)


def _hide_duplicate_inner_title(widget) -> None:
    # The settings page already provides its own page heading. The editor used to
    # add the same heading once more, which produced two adjacent identical rows.
    for child in widget.children():
        if isinstance(child, QLabel) and child.text().strip() == "Проверка сервисов":
            child.hide()
            child.setProperty("service_checks_duplicate_title_hidden", True)
            break


def _find_groups_box(widget):
    for box in widget.findChildren(QGroupBox):
        if box.title().strip() in {"Общие доступы сервисов", "Группы общих доступов"}:
            return box
    return None


def apply_jabka_service_checks_polish(widget) -> bool:
    if widget is None or not is_jabka_config(getattr(widget, "config", None)):
        return False
    if widget.property("jabka_service_checks_polished"):
        return False
    if not getattr(widget, "is_technical_editor", False):
        return False

    widget.setObjectName("JabkaServiceChecksPage")
    _hide_duplicate_inner_title(widget)

    groups_box = _find_groups_box(widget)
    if groups_box is not None:
        groups_box.setTitle("Группы общих доступов")
        groups_box.setObjectName("ServiceCredentialGroupsCard")
        groups_box.setMinimumWidth(720)
        groups_box.setMaximumWidth(1180)
        groups_box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        widget.service_credential_groups_card = groups_box
        root = widget.layout()
        if root is not None:
            root.setAlignment(groups_box, Qt.AlignmentFlag.AlignLeft)

    _rename_label(widget, "Доступ:", "Группа:")
    _rename_label(widget, "Название доступа:", "Название группы:")
    _rename_label(widget, "Сервисы:", "Сервисы группы:")
    _rename_button(widget, "Добавить доступ", "Добавить группу")
    _rename_button(widget, "Удалить доступ", "Удалить группу")

    group_select = getattr(widget, "credential_group_select", None)
    if group_select is not None:
        group_select.setMinimumWidth(360)
        group_select.setMaximumWidth(620)
        group_select.setToolTip("Выберите группу сервисов с общими учётными данными")

    group_name = getattr(widget, "credential_group_name_input", None)
    if group_name is not None:
        group_name.setMaximumWidth(620)
        group_name.setPlaceholderText("Например: Сервисы 2–5")
        group_name.setClearButtonEnabled(True)

    members = getattr(widget, "credential_group_services_list", None)
    if isinstance(members, QListWidget):
        members.setObjectName("ServiceCredentialGroupMembers")
        members.setMinimumWidth(620)
        members.setMaximumWidth(920)
        members.setMinimumHeight(105)
        members.setMaximumHeight(155)
        members.setAlternatingRowColors(False)
        layout = groups_box.layout() if groups_box is not None else None
        if layout is not None:
            layout.setAlignment(members, Qt.AlignmentFlag.AlignLeft)

    products = getattr(widget, "list_widget", None)
    if isinstance(products, QListWidget):
        products.setObjectName("ServiceProductsList")
        products.setMinimumWidth(220)
        products.setMaximumWidth(310)

    splitter = None
    for candidate in widget.findChildren(QSplitter):
        splitter = candidate
        break
    if splitter is not None:
        splitter.setObjectName("ServiceChecksEditor")
        splitter.setHandleWidth(7)
        splitter.setChildrenCollapsible(False)
        splitter.setMaximumWidth(1400)
        splitter.setSizes([260, 1040])
        widget.service_checks_editor_splitter = splitter
        root = widget.layout()
        if root is not None:
            root.setAlignment(splitter, Qt.AlignmentFlag.AlignLeft)

    form_scroll = getattr(widget, "form_scroll", None)
    if form_scroll is not None:
        form_scroll.setMaximumWidth(1080)

    root = widget.layout()
    if root is not None:
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)

    widget.setStyleSheet(widget.styleSheet() + "\n" + JABKA_SERVICE_CHECKS_QSS)
    widget.setProperty("jabka_service_checks_polished", True)
    return True


def _stable_update_credential_group_from_form(self, *_args):
    """Update a group without rebuilding comboboxes and resetting the text cursor."""
    if getattr(self, "_loading", False):
        return
    group = self.current_credential_group()
    if not group:
        return

    name_input = self.credential_group_name_input
    group_name = name_input.text().strip() or "Новый общий доступ"
    group["name"] = group_name
    group_id = str(group.get("id", "") or "")

    selected_service_ids = []
    services_list = self.credential_group_services_list
    for index in range(services_list.count()):
        item = services_list.item(index)
        service_id = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            selected_service_ids.append(service_id)
    group["service_ids"] = selected_service_ids

    for service in self.settings.get("items", []):
        service_id = service.get("id", "")
        if service_id in selected_service_ids:
            service["credential_group_id"] = group_id
        elif service.get("credential_group_id") == group_id:
            service["credential_group_id"] = ""

    # Change the visible labels in place. Clearing/repopulating these combos used
    # to call select_credential_group(), which called setText() on every keystroke
    # and destroyed the user's cursor position or selection.
    select = getattr(self, "credential_group_select", None)
    if select is not None:
        current = select.currentIndex()
        if current >= 0 and str(select.itemData(current) or "") == group_id:
            select.setItemText(current, group_name)

    service_group_combo = getattr(self, "credential_group_input", None)
    if service_group_combo is not None:
        for index in range(service_group_combo.count()):
            if str(service_group_combo.itemData(index) or "") == group_id:
                service_group_combo.setItemText(index, group_name)
                break


def install_jabka_service_checks_polish() -> bool:
    import app.service_checks_widget as service_checks_widget

    cls = service_checks_widget.ServiceChecksSettingsWidget
    if getattr(cls, "_jabka_service_checks_patch_installed", False):
        return False

    original_init = cls.__init__

    def __init__(self, config, parent=None):
        original_init(self, config, parent)
        apply_jabka_service_checks_polish(self)

    cls.__init__ = __init__
    # The cursor-stability fix is functional and safe for every theme.
    cls.update_credential_group_from_form = _stable_update_credential_group_from_form
    cls._jabka_service_checks_patch_installed = True
    return True
