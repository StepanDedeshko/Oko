import io
import logging
import unittest
from datetime import datetime

from app.session_warmup import (
    SYSTEM_OTRS,
    SYSTEM_ZABBIX,
    SessionWarmupManager,
    WarmupResult,
    WarmupStatus,
    collect_warmup_urls,
    default_warmup_settings,
    detect_auth_status,
    ensure_session_warmup_defaults,
)


class SessionWarmupPureTests(unittest.TestCase):
    def test_detect_zabbix_login_form(self):
        html = '<form action="zabbix.php?action=user.login"><input name="name"><input name="password"><button>Sign in</button></form>'
        status, reason = detect_auth_status(SYSTEM_ZABBIX, "https://zabbix/zabbix.php?action=user.login", html)
        self.assertEqual(status, WarmupStatus.AUTH_REQUIRED)
        self.assertEqual(reason, "login_form_detected")

    def test_detect_otrs_login_form(self):
        html = '<form action="index.pl?Action=Login"><input name="User"><input name="Password"><button>Login</button></form>'
        status, _ = detect_auth_status(SYSTEM_OTRS, "https://otrs/index.pl?Action=Login", html)
        self.assertEqual(status, WarmupStatus.AUTH_REQUIRED)

    def test_detect_ok_page_without_login_form(self):
        z_status, _ = detect_auth_status(SYSTEM_ZABBIX, "https://zabbix/zabbix.php?action=problem.view", "<main>Problems Monitoring</main>")
        o_status, _ = detect_auth_status(SYSTEM_OTRS, "https://otrs/index.pl?Action=AgentTicketZoom;TicketID=42", "<main>Agent Ticket</main>")
        self.assertEqual(z_status, WarmupStatus.OK)
        self.assertEqual(o_status, WarmupStatus.OK)

    def test_collect_urls_from_duty_links(self):
        config = {"duty_links": {"live_zabbix_url": "https://zabbix/problems", "otrs_create_url": "https://otrs/create", "mm_otrs_create_url": "https://otrs/mm"}}
        targets = collect_warmup_urls(config)
        self.assertEqual([(t.system, t.url) for t in targets], [(SYSTEM_ZABBIX, "https://zabbix/problems"), (SYSTEM_OTRS, "https://otrs/mm"), (SYSTEM_OTRS, "https://otrs/create")])

    def test_empty_urls_do_not_crash(self):
        self.assertEqual(collect_warmup_urls({}), [])

    def test_default_settings(self):
        settings = ensure_session_warmup_defaults({})
        self.assertEqual(settings["warmup_on_startup"], True)
        self.assertEqual(settings["check_before_tasks"], True)
        self.assertGreaterEqual(settings["timeout_seconds"], 20)
        self.assertEqual(default_warmup_settings()["last_results"], {})

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

    def test_auth_required_status_value(self):
        status, _ = detect_auth_status(SYSTEM_ZABBIX, "https://zabbix/", '<input name="password"><button>Войти</button>')
        self.assertEqual(status.value, "auth_required")


if __name__ == "__main__":
    unittest.main()
