from pathlib import Path


def test_install_send_button_observer_has_webview_guard():
    source = Path("app/duty_mode.py").read_text(encoding="utf-8")
    assert 'def _web_page_or_none(self, context="observer")' in source
    assert 'if view is None:' in source
    assert 'page = view.page()' in source
    assert 'Send button observer skipped: WebView is not available' in source
    assert 'page = self._web_page_or_none("install_send_button_observer")' in source
