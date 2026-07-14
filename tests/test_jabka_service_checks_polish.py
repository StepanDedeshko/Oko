import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QSplitter

from app.jabka_service_checks_polish import install_jabka_service_checks_polish
from app.service_checks_widget import ServiceChecksSettingsWidget


_APP = QApplication.instance() or QApplication([])


def _config(theme="jabka"):
    return {
        "settings": {"theme": theme},
        "service_checks": {
            "credential_groups": [
                {"id": "shared_group", "name": "Общая группа", "service_ids": ["service_1"]},
                {"id": "second_group", "name": "Вторая группа", "service_ids": ["service_2"]},
            ],
            "items": [
                {"id": "service_1", "name": "Сервис 1", "enabled": True},
                {"id": "service_2", "name": "Сервис 2", "enabled": True},
            ],
        },
    }


def test_jabka_service_checks_has_groups_left_and_products_right():
    install_jabka_service_checks_polish()
    widget = ServiceChecksSettingsWidget(_config())

    assert widget.property("jabka_service_checks_polished") is True
    columns = widget.service_checks_columns
    assert isinstance(columns, QSplitter)
    assert columns.orientation() == Qt.Orientation.Horizontal
    assert columns.indexOf(widget.service_credential_groups_card) == 0
    assert columns.indexOf(widget.service_checks_editor_splitter) == 1

    root = widget.layout()
    assert root.indexOf(columns) >= 0
    assert root.indexOf(widget.service_credential_groups_card) == -1
    assert root.indexOf(widget.service_checks_editor_splitter) == -1
    assert root.indexOf(widget.service_credential_groups_legacy_card) == -1
    assert widget.service_credential_groups_legacy_card.isHidden()

    groups = widget.service_credential_groups_card
    assert groups.title() == "Группы общих доступов"
    assert groups.isAncestorOf(widget.credential_groups_list)
    assert groups.isAncestorOf(widget.credential_group_name_input)
    assert groups.isAncestorOf(widget.credential_group_services_list)
    assert widget.credential_groups_list.count() == 2

    product_editor = widget.service_checks_editor_splitter
    assert product_editor.indexOf(widget.list_widget) == 0
    assert product_editor.indexOf(widget.form_scroll) == 1
    assert widget.list_widget.maximumWidth() == 330

    hidden_titles = [
        child
        for child in widget.children()
        if isinstance(child, QLabel)
        and child.text() == "Проверка сервисов"
        and child.property("service_checks_duplicate_title_hidden")
    ]
    assert len(hidden_titles) == 1
    assert hidden_titles[0].isHidden()

    button_texts = {button.text() for button in groups.findChildren(QPushButton)}
    assert button_texts == {"Добавить группу", "Удалить группу"}


def test_group_list_selects_existing_group_for_editing():
    install_jabka_service_checks_polish()
    widget = ServiceChecksSettingsWidget(_config())

    widget.credential_groups_list.setCurrentRow(1)

    assert widget.credential_group_select.currentData() == "second_group"
    assert widget.credential_group_name_input.text() == "Вторая группа"
    checked_ids = {
        widget.credential_group_services_list.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(widget.credential_group_services_list.count())
        if widget.credential_group_services_list.item(row).checkState() == Qt.CheckState.Checked
    }
    assert checked_ids == {"service_2"}


def test_double_click_toggles_membership_and_keeps_checked_state_obvious():
    install_jabka_service_checks_polish()
    config = _config()
    widget = ServiceChecksSettingsWidget(config)
    members = widget.credential_group_services_list

    second = members.item(1)
    assert second.data(Qt.ItemDataRole.UserRole) == "service_2"
    assert second.checkState() == Qt.CheckState.Unchecked
    assert second.icon().isNull()

    members.setCurrentItem(second)
    members.itemDoubleClicked.emit(second)

    assert second.checkState() == Qt.CheckState.Checked
    assert not second.icon().isNull()
    assert "service_2" in config["service_checks"]["credential_groups"][0]["service_ids"]
    assert "Двойной щелчок исключит" in second.toolTip()

    members.itemDoubleClicked.emit(second)

    assert second.checkState() == Qt.CheckState.Unchecked
    assert second.icon().isNull()
    assert "service_2" not in config["service_checks"]["credential_groups"][0]["service_ids"]
    assert "Двойной щелчок добавит" in second.toolTip()

    qss = widget.styleSheet()
    assert "ServiceCredentialGroupMembers::item:selected" in qss
    assert "ServiceCredentialGroupMembers::indicator:checked" in qss


def test_group_name_typing_keeps_cursor_position_and_updates_every_view_in_place():
    install_jabka_service_checks_polish()
    config = _config()
    widget = ServiceChecksSettingsWidget(config)
    editor = widget.credential_group_name_input

    editor.setText("Общая группа")
    editor.setCursorPosition(3)
    editor.insert("X")

    assert editor.cursorPosition() == 4
    assert editor.text() == "ОбщXая группа"
    assert config["service_checks"]["credential_groups"][0]["name"] == "ОбщXая группа"
    assert widget.credential_group_select.currentText() == "ОбщXая группа"
    assert widget.credential_groups_list.currentItem().text() == "ОбщXая группа"

    matching_names = [
        widget.credential_group_input.itemText(index)
        for index in range(widget.credential_group_input.count())
        if widget.credential_group_input.itemData(index) == "shared_group"
    ]
    assert matching_names == ["ОбщXая группа"]


def test_other_theme_keeps_original_service_checks_layout():
    install_jabka_service_checks_polish()
    widget = ServiceChecksSettingsWidget(_config(theme="mass_effect"))

    assert widget.property("jabka_service_checks_polished") is None
    assert not hasattr(widget, "service_checks_columns")
    assert not hasattr(widget, "service_credential_groups_card")
    assert any(
        isinstance(child, QLabel) and child.text() == "Проверка сервисов" and not child.isHidden()
        for child in widget.children()
    )


def test_main_installs_service_checks_polish_before_main_window():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert "install_jabka_service_checks_polish()" in source
    assert source.index("install_jabka_service_checks_polish()") < source.index("window = MainWindow")
