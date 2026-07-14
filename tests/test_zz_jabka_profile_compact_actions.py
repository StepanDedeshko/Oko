import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGroupBox

from app.jabka_profile_polish import install_jabka_profile_polish
from app.jabka_profile_compact_actions import install_jabka_profile_compact_actions
from app.home_config import ProfileWidget


_APP = QApplication.instance() or QApplication([])


def _config():
    return {
        "settings": {"theme": "jabka"},
        "duty_mode": {},
        "duty_links": {"live_zabbix_url": "http://zabbix.local/problems"},
        "live_zabbix_monitor": {"url": "http://zabbix.local/problems"},
        "zabbix_instances": [
            {"id": "zbx_product_1", "name": "Zabbix 1", "enabled": True},
        ],
        "service_checks": {
            "credential_groups": [
                {"id": "group_1", "name": "Группа 1", "service_ids": ["service_1"]},
            ],
            "items": [
                {"id": "service_1", "name": "Сервис 1", "enabled": True},
            ],
        },
    }


def test_service_groups_are_compact_and_logout_is_bottom_red_action():
    install_jabka_profile_polish()
    install_jabka_profile_compact_actions()
    widget = ProfileWidget(_config())

    assert widget.property("jabka_profile_compact_actions") is True
    assert widget.profile_columns.indexOf(widget.profile_service_groups_column) == 1
    assert widget.profile_service_groups_column.isAncestorOf(widget.profile_service_groups_card)
    assert widget.profile_service_groups_card.maximumHeight() == 330
    assert widget.profile_service_groups_list.maximumHeight() == 230
    assert widget.profile_service_group_stack.maximumHeight() == 230

    account_boxes = [
        box for box in widget.findChildren(QGroupBox)
        if box.title().strip() == "Аккаунт Око"
    ]
    assert len(account_boxes) == 1
    assert account_boxes[0].isHidden()

    assert widget.profile_logout_button is widget.logout_button
    assert widget.profile_logout_button.objectName() == "ProfileLogoutButton"
    assert widget.profile_logout_button.text() == "Выйти из аккаунта Око"
    assert not widget.profile_logout_button.isHidden()
    assert "#8D1D1D" in widget.styleSheet()


def test_main_installs_compact_profile_after_profile_layout():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert "install_jabka_profile_compact_actions()" in source
    assert source.index("install_jabka_profile_polish()") < source.index("install_jabka_profile_compact_actions()")
    assert source.index("install_jabka_profile_compact_actions()") < source.index("window = MainWindow")
