import io
import logging
import unittest
from datetime import datetime

from app.session_warmup import (
    MODE_SILENT,
    SYSTEM_OTRS,
    SYSTEM_ZABBIX,
    SessionWarmupManager,
    WarmupResult,
    WarmupStatus,
    build_autologin_script,
    collect_warmup_urls,
    default_warmup_settings,
    detect_auth_status,
    ensure_session_warmup_defaults,
    zabbix_login_url_from_html,
)


class FakeSignal:
    def emit(self, *args):
        pass


class FakeTimer:
    def stop(self):
        pass


class FakeManager(SessionWarmupManager):
    dialog_calls = 0

    class Dialog:
        def __init__(self, *args, **kwargs):
            FakeManager.dialog_calls += 1
        def exec(self):
            return False

    open_dialog_class = Dialog


class SessionWarmupPureTests(unittest.TestCase):
    def test_detect_zabbix_not_logged_in_intermediate_page(self):
        html = '''<output class="msg-bad msg-global">Вы не выполнили вход. Для просмотра этой страницы вы должны войти в систему.</output>
        <button type="button" id="login" name="login" data-login-url="index.php?request=zabbix.php%3Faction%3Ddashboard.view">Вход в систему</button>'''
        status, reason = detect_auth_status(SYSTEM_ZABBIX, "https://zabbix.local/zabbix.php?action=dashboard.view", html)
        self.assertEqual(status, WarmupStatus.AUTH_REQUIRED)
        self.assertEqual(reason, "zabbix_not_logged_in_message")

    def test_zabbix_data_login_url_is_resolved(self):
        html = '<button id="login" data-login-url="index.php?request=zabbix.php%3Faction%3Ddashboard.view">Вход в систему</button>'
        self.assertEqual(
            zabbix_login_url_from_html("https://zabbix.local/zabbix.php?action=dashboard.view", html),
            "https://zabbix.local/index.php?request=zabbix.php%3Faction%3Ddashboard.view",
        )

    def test_detect_zabbix_login_form(self):
        html = '<form action="zabbix.php?action=user.login"><input name="name"><input name="password"><button>Sign in</button></form>'
        status, reason = detect_auth_status(SYSTEM_ZABBIX, "https://zabbix/zabbix.php?action=user.login", html)
        self.assertEqual(status, WarmupStatus.AUTH_REQUIRED)
        self.assertEqual(reason, "login_form_detected")

    def test_detect_otrs_login_form(self):
        html = '<form action="index.pl?Action=Login"><input name="User"><input type="password" name="Password"><button>Login</button></form>'
        status, _ = detect_auth_status(SYSTEM_OTRS, "https://otrs/index.pl?Action=Login", html)
        self.assertEqual(status, WarmupStatus.AUTH_REQUIRED)

    def test_detect_ok_page_without_login_form(self):
        z_status, _ = detect_auth_status(SYSTEM_ZABBIX, "https://zabbix/zabbix.php?action=problem.view", "<main>Problems Monitoring</main>")
        o_status, _ = detect_auth_status(SYSTEM_OTRS, "https://otrs/index.pl?Action=AgentTicketZoom;TicketID=42", "<main>Agent Ticket</main>")
        self.assertEqual(z_status, WarmupStatus.OK)
        self.assertEqual(o_status, WarmupStatus.OK)

    def test_collect_urls_from_duty_links_deduplicates_to_one_per_system(self):
        config = {"duty_links": {"live_zabbix_url": "https://zabbix/problems", "otrs_create_url": "https://otrs/create", "mm_otrs_create_url": "https://otrs/mm"}}
        targets = collect_warmup_urls(config)
        self.assertEqual([(t.system, t.url) for t in targets], [(SYSTEM_ZABBIX, "https://zabbix/problems"), (SYSTEM_OTRS, "https://otrs/mm")])

    def test_collect_urls_uses_graph_only_as_fallback(self):
        config = {"products": [{"pages": [{"type": "graphs", "graphs": [{"url": "https://zabbix/graph"}, {"url": "https://zabbix/other"}]}]}]}
        targets = collect_warmup_urls(config)
        self.assertEqual(len([t for t in targets if t.system == SYSTEM_ZABBIX]), 1)
        self.assertEqual(targets[0].url, "https://zabbix/graph")

    def test_empty_urls_do_not_crash(self):
        self.assertEqual(collect_warmup_urls({}), [])

    def test_default_settings(self):
        settings = ensure_session_warmup_defaults({})
        self.assertTrue(settings["warmup_on_startup"])
        self.assertTrue(settings["silent_autologin"])
        self.assertTrue(settings["check_before_tasks"])
        self.assertFalse(settings["auto_show_auth_windows"])
        self.assertGreaterEqual(settings["timeout_seconds"], 20)
        self.assertEqual(default_warmup_settings()["last_results"], {})

    def test_session_warmup_settings_do_not_contain_credentials(self):
        serialized = str(default_warmup_settings()).lower()
        self.assertNotIn("password", serialized)
        self.assertNotIn("cookie", serialized)
        self.assertNotIn("token", serialized)

    def test_secrets_not_logged_by_detection(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("app.session_warmup")
        logger.addHandler(handler)
        try:
            detect_auth_status(SYSTEM_OTRS, "https://otrs/index.pl?Action=Login", '<input name="Password" value="super-secret">')
        finally:
            logger.removeHandler(handler)
        self.assertNotIn("super-secret", stream.getvalue())

    def test_fresh_ok_throttles_extra_warmup(self):
        manager = SessionWarmupManager({"session_warmup": {"fresh_ok_seconds": 300, "timeout_seconds": 5}})
        manager.results[SYSTEM_ZABBIX] = WarmupResult(SYSTEM_ZABBIX, WarmupStatus.OK, checked_at=datetime.now())
        self.assertTrue(manager.is_fresh_ok(SYSTEM_ZABBIX))

    def test_silent_auth_required_does_not_open_manual_window(self):
        FakeManager.dialog_calls = 0
        manager = FakeManager.__new__(FakeManager)
        manager._current = type("Target", (), {"system": SYSTEM_ZABBIX, "url": "https://zabbix", "profile_id": ""})()
        manager._mode = MODE_SILENT
        manager.settings = {"silent_autologin": False, "last_results": {}}
        manager.results = {}
        manager.logger = logging.getLogger("test")
        manager.result_ready = FakeSignal()
        manager._timer = FakeTimer()
        manager._view = None
        manager._cleanup_view = lambda: None
        manager._next = lambda: None
        manager._record = lambda result: manager.results.setdefault(result.system, result)
        manager._on_html('<input name="password"><button>Войти</button>')
        self.assertEqual(FakeManager.dialog_calls, 0)
        self.assertEqual(manager.results[SYSTEM_ZABBIX].status, WarmupStatus.AUTH_REQUIRED)

    def test_autologin_script_is_single_safe_action(self):
        script = build_autologin_script({"login": "user", "password": "secret"})
        self.assertIn("document.querySelector", script)
        self.assertIn("button.click", script)

    def test_auth_required_status_value(self):
        status, _ = detect_auth_status(SYSTEM_ZABBIX, "https://zabbix/", '<input name="password"><button>Войти</button>')
        self.assertEqual(status.value, "auth_required")


if __name__ == "__main__":
    unittest.main()
