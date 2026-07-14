from pathlib import Path

from app.live_zabbix_poll_url_guard import install_live_zabbix_poll_url_guard
from app.live_zabbix_widget import LiveZabbixMonitorWidget


class _FakeUrl:
    def __init__(self, value):
        self.value = value

    def toString(self):
        return self.value


class _FakeView:
    def __init__(self, current_url=""):
        self.current_url = current_url
        self.loaded = []
        self.reload_called = False

    def url(self):
        return _FakeUrl(self.current_url)

    def load(self, url):
        self.loaded.append(bytes(url.toEncoded()).decode("ascii"))

    def reload(self):
        self.reload_called = True


class _FakeStatus:
    def __init__(self):
        self.text = ""

    def setText(self, value):
        self.text = str(value)


class _DummyMonitor:
    def __init__(self, configured_url, current_url=""):
        self._configured_url = configured_url
        self.view = _FakeView(current_url)
        self.poll_status_label = _FakeStatus()

    def problems_url(self):
        return self._configured_url


def test_poll_reloads_current_working_zabbix_page():
    install_live_zabbix_poll_url_guard()
    configured = (
        "http://10.250.10.10/zabbix.php?action=problem.view"
        "&filter_name=%D0%A4%D0%B8%D0%BB%D1%8C%D1%82%D1%80%20%D0%B4%D0%BB%D1%8F%20%D0%9E%D0%BA%D0%BE"
    )
    monitor = _DummyMonitor(configured, current_url="http://10.250.10.10/zabbix.php?action=problem.view")

    LiveZabbixMonitorWidget.poll_now(monitor)

    assert monitor.view.reload_called is True
    assert monitor.view.loaded == []
    assert monitor.poll_status_label.text == "Опрос страницы…"


def test_poll_loads_configured_url_only_when_webview_is_blank():
    install_live_zabbix_poll_url_guard()
    configured = "http://10.250.10.10/zabbix.php?action=problem.view"
    monitor = _DummyMonitor(configured, current_url="")

    LiveZabbixMonitorWidget.poll_now(monitor)

    assert monitor.view.reload_called is False
    assert monitor.view.loaded == [configured]


def test_empty_configured_url_is_not_loaded_or_reloaded():
    install_live_zabbix_poll_url_guard()
    monitor = _DummyMonitor("", current_url="http://10.250.10.10/zabbix.php")

    LiveZabbixMonitorWidget.poll_now(monitor)

    assert monitor.view.loaded == []
    assert monitor.view.reload_called is False
    assert monitor.poll_status_label.text == "Ошибка: URL Live Zabbix Monitor не задан"


def test_main_installs_poll_url_guard_before_widgets_are_created():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "from app.live_zabbix_poll_url_guard import install_live_zabbix_poll_url_guard" in source
    assert "install_live_zabbix_poll_url_guard()" in source
    assert source.index("install_live_zabbix_poll_url_guard()") < source.index("window = MainWindow")
