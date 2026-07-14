import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QGroupBox, QSplitter

from app.jabka_profile_polish import install_jabka_profile_polish
from app.home_config import ProfileWidget


_APP = QApplication.instance() or QApplication([])


def _config(theme="jabka"):
    return {
        "settings": {"theme": theme},
        "duty_mode": {
            "otrs_login_enabled": True,
            "otrs_auto_submit_login": False,
        },
        "duty_links": {"live_zabbix_url": "http://zabbix.local/zabbix.php?action=problem.view"},
        "live_zabbix_monitor": {
            "url": "http://zabbix.local/zabbix.php?action=problem.view",
            "redmine_login_url": "http://redmine.local/login",
        },
        "zabbix_instances": [
            {"id": "zbx_product_1", "name": "Zabbix FacePay", "enabled": True},
            {"id": "zbx_product_2", "name": "Zabbix продукт 2", "enabled": True},
        ],
        "service_checks": {
            "credential_groups": [
                {"id": "service_group_1", "name": "Основные сервисы", "service_ids": ["service_1"]},
                {"id": "service_group_2", "name": "Дополнительные сервисы", "service_ids": ["service_2"]},
            ],
            "items": [
                {"id": "service_1", "name": "Сервис 1", "enabled": True},
                {"id": "service_2", "name": "Сервис 2", "enabled": True},
            ],
        },
    }


def test_jabka_profile_has_integrations_left_and_service_groups_right():
    install_jabka_profile_polish()
    widget = ProfileWidget(_config())

    assert widget.property("jabka_profile_polished") is True
    assert isinstance(widget.profile_columns, QSplitter)
    assert widget.profile_columns.orientation() == Qt.Orientation.Horizontal
    assert widget.profile_columns.indexOf(widget.profile_integrations_card) == 0
    assert widget.profile_columns.indexOf(widget.profile_service_groups_card) == 1

    assert widget.profile_integrations_card.title() == "Интеграции"
    assert widget.profile_service_groups_card.title() == "Группы сервисов"
    assert widget.profile_service_groups_list.count() == 2
    assert widget.profile_service_group_stack.count() == 2
    assert widget.profile_service_groups_list.item(0).text() == "Основные сервисы"
    assert widget.profile_service_groups_list.item(1).text() == "Дополнительные сервисы"

    integration_titles = {
        box.title()
        for box in widget.profile_integrations_card.findChildren(QGroupBox)
    }
    assert {"OTRS", "Zabbix", "Redmine"}.issubset(integration_titles)
    assert widget.redmine_login_url_input.isHidden()


def test_service_group_selection_switches_existing_credential_fields():
    install_jabka_profile_polish()
    widget = ProfileWidget(_config())

    first_fields = widget.service_group_inputs["service_group_1"]
    second_fields = widget.service_group_inputs["service_group_2"]

    assert widget.profile_service_group_stack.currentIndex() == 0
    first_page = widget.profile_service_group_stack.widget(0)
    second_page = widget.profile_service_group_stack.widget(1)
    assert first_page.isAncestorOf(first_fields["login"])
    assert first_page.isAncestorOf(first_fields["password"])
    assert second_page.isAncestorOf(second_fields["login"])
    assert second_page.isAncestorOf(second_fields["password"])

    widget.profile_service_groups_list.setCurrentRow(1)
    assert widget.profile_service_group_stack.currentIndex() == 1

    second_fields["login"].setText("group-two-user")
    second_fields["password"].setText("group-two-password")
    assert widget.service_group_inputs["service_group_2"]["login"].text() == "group-two-user"
    assert widget.service_group_inputs["service_group_2"]["password"].text() == "group-two-password"


def test_profile_actions_remain_available_after_relayout():
    install_jabka_profile_polish()
    widget = ProfileWidget(_config())

    assert widget.profile_save_button.text() == "Сохранить все доступы"
    assert widget.profile_clear_zabbix_button.text() == "Удалить сохранённые Zabbix-пароли"
    assert not widget.profile_save_button.isHidden()
    assert not widget.profile_clear_zabbix_button.isHidden()
    assert widget.logout_button.text() == "Выйти из аккаунта Око"


def test_other_theme_keeps_original_profile_layout():
    install_jabka_profile_polish()
    widget = ProfileWidget(_config(theme="mass_effect"))

    assert widget.property("jabka_profile_polished") is None
    assert not hasattr(widget, "profile_columns")
    assert not hasattr(widget, "profile_service_group_stack")


def test_main_installs_profile_link_guard_before_jabka_profile_polish():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert "install_profile_links_polish()" in source
    assert "install_jabka_profile_polish()" in source
    assert source.index("install_profile_links_polish()") < source.index("install_jabka_profile_polish()")
    assert source.index("install_jabka_profile_polish()") < source.index("window = MainWindow")
