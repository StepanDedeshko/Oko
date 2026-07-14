import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from app.canonical_link_store import install_canonical_link_settings
from app.live_zabbix_link_label_polish import (
    NEW_LABEL,
    OLD_LABEL,
    install_live_zabbix_link_label_polish,
)


def _app():
    return QApplication.instance() or QApplication([])


def test_links_page_uses_live_zabbix_monitor_name():
    _app()
    config = {
        "duty_links": {
            "redmine_create_url": "",
            "otrs_create_url": "",
            "mm_otrs_create_url": "",
            "live_zabbix_url": "https://zabbix.example/problems.php",
        },
        "live_zabbix_monitor": {},
        "duty_mode": {},
        "settings": {},
    }

    install_canonical_link_settings(config)
    install_live_zabbix_link_label_polish()

    from app.home_config import LinksSettingsWidget

    widget = LinksSettingsWidget(config)
    labels = [label.text() for label in widget.findChildren(QLabel)]

    assert any(NEW_LABEL in text for text in labels)
    assert all(OLD_LABEL not in text for text in labels)
    assert widget.zabbix_problems_url_input.placeholderText() == NEW_LABEL

    widget.deleteLater()


def test_developer_hint_uses_live_zabbix_monitor_name():
    _app()
    config = {
        "duty_links": {
            "redmine_create_url": "",
            "otrs_create_url": "",
            "mm_otrs_create_url": "",
            "live_zabbix_url": "https://zabbix.example/problems.php",
        },
        "live_zabbix_monitor": {},
        "duty_mode": {},
        "settings": {},
    }

    install_canonical_link_settings(config)
    install_live_zabbix_link_label_polish()

    from app.home_config import LiveZabbixDeveloperSettingsWidget

    widget = LiveZabbixDeveloperSettingsWidget(config)
    labels = [label.text() for label in widget.findChildren(QLabel)]

    assert any(NEW_LABEL in text for text in labels)
    assert all(OLD_LABEL not in text for text in labels)

    widget.deleteLater()
