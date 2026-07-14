from pathlib import Path

from app.live_zabbix import DOM_PARSER_SCRIPT_PLACEHOLDER
from app.live_zabbix_two_step_auth_fix import patch_dom_parser_script


def test_warning_page_parser_accepts_real_two_step_login_markup():
    patched = patch_dom_parser_script(DOM_PARSER_SCRIPT_PLACEHOLDER)

    assert "output.msg-bad, .msg-bad" in patched
    assert "button#login, input#login, a#login" in patched
    assert "button.getAttribute('onclick')" in patched
    assert "click_login_button: true" in patched
    assert "loginButton.getAttribute('data-login-url') &&" not in patched
    assert "output.msg-bad.msg-global" not in patched


def test_warning_page_parser_patch_is_idempotent():
    patched = patch_dom_parser_script(DOM_PARSER_SCRIPT_PLACEHOLDER)
    assert patch_dom_parser_script(patched) == patched


def test_autologin_clicks_intermediate_button_then_fills_form():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "live_zabbix_two_step_auth_fix.py"
    ).read_text(encoding="utf-8")

    assert "button.click()" in source
    assert "_fill_zabbix_login_form(creds, 1)" in source
    assert "Zabbix: открываю форму входа…" in source


def test_main_installs_two_step_fix_before_main_window_is_created():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert "from app.live_zabbix_two_step_auth_fix import install_live_zabbix_two_step_auth_fix" in source
    assert "install_live_zabbix_two_step_auth_fix()" in source
    assert source.index("install_live_zabbix_two_step_auth_fix()") < source.index("window = MainWindow")
