from __future__ import annotations


OLD_LABEL = "URL Zabbix Problems"
NEW_LABEL = "URL Live Zabbix Monitor"


def _replace_label_text(widget, label_type) -> None:
    for label in widget.findChildren(label_type):
        text = str(label.text() or "")
        if OLD_LABEL in text:
            label.setText(text.replace(OLD_LABEL, NEW_LABEL))


def install_live_zabbix_link_label_polish() -> bool:
    """Use the user-facing Live Zabbix Monitor name everywhere in settings."""
    import app.home_config as home_config

    installed = False

    links_cls = home_config.LinksSettingsWidget
    if not getattr(links_cls, "_live_zabbix_link_label_polished", False):
        original_links_init = links_cls.__init__

        def links_init(self, config, parent=None):
            original_links_init(self, config, parent=parent)
            field = getattr(self, "zabbix_problems_url_input", None)
            if field is not None:
                field.setPlaceholderText(NEW_LABEL)
            _replace_label_text(self, home_config.QLabel)

        links_cls.__init__ = links_init
        links_cls._live_zabbix_link_label_polished = True
        installed = True

    developer_cls = home_config.LiveZabbixDeveloperSettingsWidget
    if not getattr(developer_cls, "_live_zabbix_link_label_polished", False):
        original_developer_init = developer_cls.__init__

        def developer_init(self, config, parent=None):
            original_developer_init(self, config, parent=parent)
            _replace_label_text(self, home_config.QLabel)

        developer_cls.__init__ = developer_init
        developer_cls._live_zabbix_link_label_polished = True
        installed = True

    return installed
