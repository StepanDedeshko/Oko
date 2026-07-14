from __future__ import annotations


def add_live_zabbix_refresh_button(widget, button_type):
    """Append a manual refresh action to the visible Live Zabbix toolbar."""
    existing = getattr(widget, "live_refresh_button", None)
    if existing is not None:
        return existing

    root_layout = widget.layout()
    if root_layout is None or root_layout.count() < 1:
        return None

    controls_item = root_layout.itemAt(0)
    controls_layout = controls_item.layout() if controls_item is not None else None
    if controls_layout is None:
        return None

    button = button_type("Обновить", widget)
    button.setObjectName("LiveZabbixRefreshButton")
    button.setToolTip("Сразу обновить Live Zabbix Monitor")
    button.setMinimumWidth(120)
    button.clicked.connect(widget.poll_now)
    controls_layout.addWidget(button)
    widget.live_refresh_button = button
    return button


def install_live_zabbix_refresh_button() -> bool:
    """Install the manual refresh button before Live Zabbix widgets are built."""
    import app.live_zabbix_widget as live_widget

    cls = live_widget.LiveZabbixMonitorWidget
    if getattr(cls, "_manual_refresh_button_installed", False):
        return False

    original_build_ui = cls._build_ui

    def _build_ui(self):
        original_build_ui(self)
        add_live_zabbix_refresh_button(self, live_widget.QPushButton)

    cls._build_ui = _build_ui
    cls._manual_refresh_button_installed = True
    return True
