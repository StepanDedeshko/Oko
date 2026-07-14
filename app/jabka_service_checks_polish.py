from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QVBoxLayout,
    QWidget,
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
QWidget#ServiceGroupsColumn {
    background: transparent;
}
QLabel#ServiceGroupsSectionLabel {
    color: #B7F27A;
    font-weight: 700;
    padding: 1px 2px;
}
QListWidget#ServiceCredentialGroupsList,
QListWidget#ServiceCredentialGroupMembers {
    background: rgba(6, 23, 13, 235);
    border: 1px solid rgba(102, 185, 91, 130);
    border-radius: 12px;
    padding: 6px;
    outline: 0;
}
QListWidget#ServiceCredentialGroupsList::item,
QListWidget#ServiceCredentialGroupMembers::item {
    min-height: 28px;
    padding: 3px 7px;
    border-radius: 7px;
}
QListWidget#ServiceCredentialGroupsList::item:hover,
QListWidget#ServiceCredentialGroupMembers::item:hover {
    background: rgba(33, 79, 43, 210);
}
QListWidget#ServiceCredentialGroupsList::item:selected {
    background: #B7F27A;
    color: #07140D;
}
QListWidget#ServiceCredentialGroupMembers::item:selected {
    background: rgba(45, 92, 51, 235);
    color: #F2FFE5;
    border: 1px solid rgba(183, 242, 122, 175);
}
QListWidget#ServiceCredentialGroupMembers::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #6DAF62;
    border-radius: 4px;
    background: #06170D;
}
QListWidget#ServiceCredentialGroupMembers::indicator:checked,
QListWidget#ServiceCredentialGroupMembers::indicator:checked:selected {
    background: #B7F27A;
    border: 2px solid #F2FFE5;
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
QSplitter#ServiceChecksColumns::handle,
QSplitter#ServiceChecksEditor::handle {
    background: rgba(102, 185, 91, 90);
    width: 7px;
    margin: 8px 2px;
    border-radius: 3px;
}
QSplitter#ServiceChecksColumns::handle:hover,
QSplitter#ServiceChecksEditor::handle:hover {
    background: rgba(183, 242, 122, 150);
}
"""

_MAX_WIDGET_WIDTH = 16777215


def _hide_duplicate_inner_title(widget) -> None:
    """Hide the editor heading because the settings shell already shows it."""
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


def _find_editor_splitter(widget):
    products = getattr(widget, "list_widget", None)
    for candidate in widget.findChildren(QSplitter):
        if products is not None and candidate.indexOf(products) >= 0:
            return candidate
    return None


def _current_group_id(widget) -> str:
    combo = getattr(widget, "credential_group_select", None)
    return str(combo.currentData() or "") if combo is not None else ""


def _sync_group_list_selection(widget, selected_id: str | None = None) -> None:
    group_list = getattr(widget, "credential_groups_list", None)
    if not isinstance(group_list, QListWidget):
        return

    selected_id = str(selected_id if selected_id is not None else _current_group_id(widget))
    target_row = -1
    for row in range(group_list.count()):
        item = group_list.item(row)
        if str(item.data(Qt.ItemDataRole.UserRole) or "") == selected_id:
            target_row = row
            break

    group_list.blockSignals(True)
    group_list.setCurrentRow(target_row)
    group_list.blockSignals(False)


def _sync_group_list(widget, selected_id: str | None = None) -> None:
    group_list = getattr(widget, "credential_groups_list", None)
    if not isinstance(group_list, QListWidget):
        return

    selected_id = str(selected_id if selected_id is not None else _current_group_id(widget))
    group_list.blockSignals(True)
    group_list.clear()
    target_row = -1

    for row, group in enumerate(widget.credential_groups()):
        group_id = str(group.get("id", "") or "")
        item = QListWidgetItem(str(group.get("name") or group_id or "Без названия"))
        item.setData(Qt.ItemDataRole.UserRole, group_id)
        group_list.addItem(item)
        if group_id == selected_id:
            target_row = row

    if target_row < 0 and group_list.count():
        target_row = 0
    group_list.setCurrentRow(target_row)
    group_list.blockSignals(False)


def _select_group_from_list(widget, row: int) -> None:
    group_list = getattr(widget, "credential_groups_list", None)
    combo = getattr(widget, "credential_group_select", None)
    if not isinstance(group_list, QListWidget) or combo is None or row < 0:
        return

    item = group_list.item(row)
    if item is None:
        return
    group_id = str(item.data(Qt.ItemDataRole.UserRole) or "")

    for index in range(combo.count()):
        if str(combo.itemData(index) or "") == group_id:
            if combo.currentIndex() != index:
                combo.setCurrentIndex(index)
            else:
                widget.select_credential_group()
            return


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("ServiceGroupsSectionLabel")
    return label


def _update_member_item_visual(widget, item: QListWidgetItem | None) -> None:
    """Keep an unmistakable check icon visible even while the row is selected."""
    if item is None:
        return
    members = getattr(widget, "credential_group_services_list", None)
    if not isinstance(members, QListWidget):
        return

    checked = item.checkState() == Qt.CheckState.Checked
    previous = members.blockSignals(True)
    try:
        if checked:
            item.setIcon(widget.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
            item.setToolTip("Сервис входит в выбранную группу. Двойной щелчок исключит его.")
        else:
            item.setIcon(QIcon())
            item.setToolTip("Сервис не входит в выбранную группу. Двойной щелчок добавит его.")
    finally:
        members.blockSignals(previous)


def _refresh_member_visuals(widget) -> None:
    members = getattr(widget, "credential_group_services_list", None)
    if not isinstance(members, QListWidget):
        return
    for row in range(members.count()):
        _update_member_item_visual(widget, members.item(row))


def _toggle_member_on_double_click(widget, item: QListWidgetItem | None) -> None:
    if item is None:
        return
    new_state = (
        Qt.CheckState.Unchecked
        if item.checkState() == Qt.CheckState.Checked
        else Qt.CheckState.Checked
    )
    item.setCheckState(new_state)
    _update_member_item_visual(widget, item)


def _build_group_manager(widget, legacy_box) -> QGroupBox:
    """Build the complete group editor as the permanent left page column."""
    manager = QGroupBox("Группы общих доступов")
    manager.setObjectName("ServiceCredentialGroupsCard")
    manager.setMinimumWidth(380)
    manager.setMaximumWidth(680)
    manager.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

    layout = QVBoxLayout(manager)
    layout.setContentsMargins(16, 18, 16, 14)
    layout.setSpacing(8)

    layout.addWidget(_section_label("Созданные группы"))
    group_list = QListWidget(manager)
    group_list.setObjectName("ServiceCredentialGroupsList")
    group_list.setMinimumHeight(150)
    group_list.setAlternatingRowColors(False)
    group_list.currentRowChanged.connect(lambda row: _select_group_from_list(widget, row))
    layout.addWidget(group_list, stretch=2)

    buttons = QHBoxLayout()
    add_button = QPushButton("Добавить группу")
    add_button.setObjectName("PrimaryAction")
    add_button.clicked.connect(widget.add_credential_group)
    delete_button = QPushButton("Удалить группу")
    delete_button.clicked.connect(widget.delete_credential_group)
    buttons.addWidget(add_button)
    buttons.addWidget(delete_button)
    layout.addLayout(buttons)

    layout.addWidget(_section_label("Название выбранной группы"))
    name_input = widget.credential_group_name_input
    name_input.setParent(manager)
    name_input.setMinimumWidth(0)
    name_input.setMaximumWidth(_MAX_WIDGET_WIDTH)
    name_input.setPlaceholderText("Например: Сервисы 2–5")
    name_input.setClearButtonEnabled(True)
    layout.addWidget(name_input)

    layout.addWidget(_section_label("Сервисы в группе"))
    members = widget.credential_group_services_list
    members.setParent(manager)
    members.setObjectName("ServiceCredentialGroupMembers")
    members.setMinimumWidth(0)
    members.setMaximumWidth(_MAX_WIDGET_WIDTH)
    members.setMinimumHeight(190)
    members.setMaximumHeight(_MAX_WIDGET_WIDTH)
    members.setAlternatingRowColors(False)
    members.setToolTip("Щёлкните по флажку или дважды щёлкните по сервису, чтобы изменить состав группы")
    members.itemDoubleClicked.connect(lambda item: _toggle_member_on_double_click(widget, item))
    members.itemChanged.connect(lambda item: _update_member_item_visual(widget, item))
    layout.addWidget(members, stretch=3)

    hint = QLabel(
        "Группа объединяет сервисы с общими учётными данными. "
        "Пользователи вводят свои логины и пароли в разделе «Профиль». "
        "Сервис можно добавить или убрать флажком либо двойным щелчком."
    )
    hint.setWordWrap(True)
    layout.addWidget(hint)

    widget.credential_groups_list = group_list
    widget.service_credential_groups_card = manager
    widget.service_credential_groups_legacy_card = legacy_box
    _refresh_member_visuals(widget)
    return manager


def _prepare_product_editor(widget, root) -> QSplitter | None:
    """Prepare the existing product list and product form as the right column."""
    products = getattr(widget, "list_widget", None)
    if isinstance(products, QListWidget):
        products.setObjectName("ServiceProductsList")
        products.setMinimumWidth(220)
        products.setMaximumWidth(330)

    splitter = _find_editor_splitter(widget)
    if splitter is None:
        return None

    splitter.setObjectName("ServiceChecksEditor")
    splitter.setHandleWidth(7)
    splitter.setChildrenCollapsible(False)
    splitter.setMinimumWidth(640)
    splitter.setMaximumWidth(_MAX_WIDGET_WIDTH)
    splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)
    splitter.setSizes([270, 1050])

    form_scroll = getattr(widget, "form_scroll", None)
    if form_scroll is not None:
        form_scroll.setMinimumWidth(420)
        form_scroll.setMaximumWidth(_MAX_WIDGET_WIDTH)
        form_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        form_container = form_scroll.widget()
        if form_container is not None:
            form_container.setMinimumWidth(620)
            form_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    root.removeWidget(splitter)
    widget.service_checks_editor_splitter = splitter
    return splitter


def apply_jabka_service_checks_polish(widget) -> bool:
    if widget is None or not is_jabka_config(getattr(widget, "config", None)):
        return False
    if widget.property("jabka_service_checks_polished"):
        return False
    if not getattr(widget, "is_technical_editor", False):
        return False

    root = widget.layout()
    if root is None:
        return False

    widget.setObjectName("JabkaServiceChecksPage")
    _hide_duplicate_inner_title(widget)

    legacy_box = _find_groups_box(widget)
    if legacy_box is not None:
        root.removeWidget(legacy_box)
        legacy_box.hide()

    product_editor = _prepare_product_editor(widget, root)
    if product_editor is None:
        return False

    groups = _build_group_manager(widget, legacy_box)

    columns = QSplitter(Qt.Orientation.Horizontal, widget)
    columns.setObjectName("ServiceChecksColumns")
    columns.setHandleWidth(9)
    columns.setChildrenCollapsible(False)
    columns.addWidget(groups)
    columns.addWidget(product_editor)
    columns.setStretchFactor(0, 0)
    columns.setStretchFactor(1, 1)
    columns.setSizes([500, 1200])

    root.addWidget(columns, stretch=1)
    root.setContentsMargins(12, 8, 12, 12)
    root.setSpacing(10)
    root.setStretchFactor(columns, 1)

    widget.service_checks_columns = columns
    widget.setStyleSheet(widget.styleSheet() + "\n" + JABKA_SERVICE_CHECKS_QSS)
    widget.setProperty("jabka_service_checks_polished", True)
    _sync_group_list(widget)
    return True


def _stable_update_credential_group_from_form(self, *_args):
    """Update a group without rebuilding controls or resetting text selection."""
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

    group_list = getattr(self, "credential_groups_list", None)
    if isinstance(group_list, QListWidget):
        for row in range(group_list.count()):
            item = group_list.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole) or "") == group_id:
                item.setText(group_name)
                break


def install_jabka_service_checks_polish() -> bool:
    import app.service_checks_widget as service_checks_widget

    cls = service_checks_widget.ServiceChecksSettingsWidget
    if getattr(cls, "_jabka_service_checks_patch_installed", False):
        return False

    original_init = cls.__init__
    original_refresh_groups = cls.refresh_credential_groups
    original_select_group = cls.select_credential_group
    original_refresh_members = cls.refresh_credential_group_services_list

    def refresh_credential_groups(self, *args, **kwargs):
        result = original_refresh_groups(self, *args, **kwargs)
        _sync_group_list(self)
        return result

    def select_credential_group(self, *args, **kwargs):
        result = original_select_group(self)
        _sync_group_list_selection(self)
        return result

    def refresh_credential_group_services_list(self, *args, **kwargs):
        result = original_refresh_members(self, *args, **kwargs)
        _refresh_member_visuals(self)
        return result

    def __init__(self, config, parent=None):
        original_init(self, config, parent)
        apply_jabka_service_checks_polish(self)

    cls.refresh_credential_groups = refresh_credential_groups
    cls.select_credential_group = select_credential_group
    cls.refresh_credential_group_services_list = refresh_credential_group_services_list
    cls.__init__ = __init__
    # Cursor stability is functional and safe for every theme.
    cls.update_credential_group_from_form = _stable_update_credential_group_from_form
    cls._jabka_service_checks_patch_installed = True
    return True
