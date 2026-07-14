from pathlib import Path

from app.live_zabbix_refresh_button import add_live_zabbix_refresh_button


class _Signal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback

    def emit(self):
        assert self.callback is not None
        self.callback()


class _Button:
    def __init__(self, text, parent):
        self.text = text
        self.parent = parent
        self.clicked = _Signal()
        self.object_name = ""
        self.tooltip = ""
        self.minimum_width = 0

    def setObjectName(self, value):
        self.object_name = value

    def setToolTip(self, value):
        self.tooltip = value

    def setMinimumWidth(self, value):
        self.minimum_width = value


class _ControlsLayout:
    def __init__(self):
        self.widgets = []

    def addWidget(self, widget):
        self.widgets.append(widget)


class _LayoutItem:
    def __init__(self, layout):
        self._layout = layout

    def layout(self):
        return self._layout


class _RootLayout:
    def __init__(self, controls):
        self._item = _LayoutItem(controls)

    def count(self):
        return 1

    def itemAt(self, index):
        return self._item if index == 0 else None


class _Widget:
    def __init__(self):
        self.controls = _ControlsLayout()
        self.root = _RootLayout(self.controls)
        self.poll_count = 0

    def layout(self):
        return self.root

    def poll_now(self):
        self.poll_count += 1


def test_refresh_button_is_appended_and_runs_manual_poll():
    widget = _Widget()

    button = add_live_zabbix_refresh_button(widget, _Button)

    assert button is widget.live_refresh_button
    assert widget.controls.widgets == [button]
    assert button.text == "Обновить"
    assert button.object_name == "LiveZabbixRefreshButton"
    assert button.tooltip == "Сразу обновить Live Zabbix Monitor"
    assert button.minimum_width == 120

    button.clicked.emit()
    assert widget.poll_count == 1


def test_refresh_button_installation_is_idempotent():
    widget = _Widget()

    first = add_live_zabbix_refresh_button(widget, _Button)
    second = add_live_zabbix_refresh_button(widget, _Button)

    assert second is first
    assert widget.controls.widgets == [first]


def test_main_installs_button_before_main_window_creation():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert "from app.live_zabbix_refresh_button import install_live_zabbix_refresh_button" in source
    assert "install_live_zabbix_refresh_button()" in source
    assert source.index("install_live_zabbix_refresh_button()") < source.index("window = MainWindow")
