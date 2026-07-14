import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from app.jabka_service_checks_polish import install_jabka_service_checks_polish
from app.service_checks_widget import ServiceChecksSettingsWidget


_APP = QApplication.instance() or QApplication([])


def _config(theme="jabka"):
    return {
        "settings": {"theme": theme},
        "service_checks": {
            "credential_groups": [
                {"id": "shared_group", "name": "Общая группа", "service_ids": ["service_1"]},
            ],
            "items": [
                {"id": "service_1", "name": "Сервис 1", "enabled": True},
                {"id": "service_2", "name": "Сервис 2", "enabled": True},
            ],
        },
    }


def test_jabka_service_checks_page_is_compact_and_not_duplicated():
    install_jabka_service_checks_polish()
    widget = ServiceChecksSettingsWidget(_config())

    assert widget.property("jabka_service_checks_polished") is True
    assert widget.service_credential_groups_card.title() == "Группы общих доступов"
    assert widget.service_credential_groups_card.maximumWidth() == 1180
    assert widget.credential_group_services_list.maximumWidth() == 920
    assert widget.credential_group_services_list.maximumHeight() == 155
    assert widget.list_widget.maximumWidth() == 310
    assert widget.service_checks_editor_splitter.maximumWidth() == 1400

    hidden_titles = [
        child
        for child in widget.children()
        if isinstance(child, QLabel)
        and child.text() == "Проверка сервисов"
        and child.property("service_checks_duplicate_title_hidden")
    ]
    assert len(hidden_titles) == 1
    assert hidden_titles[0].isHidden()

    button_texts = {button.text() for button in widget.findChildren(QPushButton)}
    assert "Добавить группу" in button_texts
    assert "Удалить группу" in button_texts
    assert "Добавить доступ" not in button_texts


def test_group_name_typing_keeps_cursor_position_and_updates_combos_in_place():
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
    assert not hasattr(widget, "service_credential_groups_card")
    assert any(
        isinstance(child, QLabel) and child.text() == "Проверка сервисов" and not child.isHidden()
        for child in widget.children()
    )


def test_main_installs_service_checks_polish_before_main_window():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert "install_jabka_service_checks_polish()" in source
    assert source.index("install_jabka_service_checks_polish()") < source.index("window = MainWindow")
