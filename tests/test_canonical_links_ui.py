import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGroupBox, QLineEdit, QMessageBox

from app.canonical_links import (
    CANONICAL_LINKS_SCHEMA_VERSION,
    get_canonical_link,
    install_canonical_link_settings,
    set_canonical_link,
)
from app.config import get_default_config


def _config_with_canonical_links():
    config = get_default_config()
    config["duty_links"] = {
        "_schema_version": CANONICAL_LINKS_SCHEMA_VERSION,
        "redmine_create_url": "https://redmine.example/issues/new",
        "otrs_create_url": "https://itsm.example/normal",
        "mm_otrs_create_url": "https://itsm.example/mm",
        "live_zabbix_url": "https://zabbix.example/problems",
    }
    return config


def test_shared_urls_are_editable_only_on_links_page(monkeypatch):
    app = QApplication.instance() or QApplication([])
    config = _config_with_canonical_links()

    monkeypatch.setattr("app.config.save_config", lambda _config: None)
    monkeypatch.setattr("app.home_config.save_config", lambda _config: None)
    monkeypatch.setattr("app.duty_settings.save_config", lambda _config: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Ok)

    install_canonical_link_settings(config)

    from app.home_config import (
        LinksSettingsWidget,
        LiveZabbixDeveloperSettingsWidget,
        TemplatesWidget,
    )
    from app.duty_settings import DutyModeSettingsWidget

    links = LinksSettingsWidget(config)
    assert not links.redmine_create_url_input.isHidden()
    assert not links.redmine_login_url_input.isHidden()
    assert not links.otrs_create_url_input.isHidden()
    assert not links.mm_otrs_create_url_input.isHidden()
    assert not links.zabbix_problems_url_input.isHidden()

    links.redmine_create_url_input.setText("https://redmine.example/new")
    links.otrs_create_url_input.setText("https://itsm.example/new-normal")
    links.mm_otrs_create_url_input.setText("https://itsm.example/new-mm")
    links.zabbix_problems_url_input.setText("https://zabbix.example/new-problems")
    links.save_links()

    assert get_canonical_link(config, "redmine_create_url") == "https://redmine.example/new"
    assert get_canonical_link(config, "otrs_create_url") == "https://itsm.example/new-normal"
    assert get_canonical_link(config, "mm_otrs_create_url") == "https://itsm.example/new-mm"
    assert get_canonical_link(config, "live_zabbix_url") == "https://zabbix.example/new-problems"

    developer = LiveZabbixDeveloperSettingsWidget(config)
    visible_developer_fields = [
        field for field in developer.findChildren(QLineEdit) if not field.isHidden()
    ]
    assert len(visible_developer_fields) == 1
    assert visible_developer_fields[0] is developer.profile_input

    duty = DutyModeSettingsWidget(config)
    assert duty.live_zabbix_url_input.isHidden()
    assert duty.redmine_create_url_input.isHidden()
    assert duty.otrs_create_url_link_input.isHidden()
    assert duty.mm_otrs_create_url_input.isHidden()
    assert "Рабочие ссылки дежурки" not in [
        box.title() for box in duty.findChildren(QGroupBox)
    ]
    assert not hasattr(duty, "otrs_create_url")

    templates = TemplatesWidget(config)
    assert templates.redmine_create_url_input.isHidden()

    # A duty page opened before a Links-page edit must not restore stale values.
    set_canonical_link(config, "otrs_create_url", "https://itsm.example/final")
    duty.save()
    assert get_canonical_link(config, "otrs_create_url") == "https://itsm.example/final"

    for widget in (templates, duty, developer, links):
        widget.deleteLater()
    app.processEvents()
