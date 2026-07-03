import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.credentials import OTRS_CREDENTIALS_KEY, load_otrs_credentials, save_credentials
from app.credentials import build_otrs_login_injection_js


class OtrsLoginTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.credentials_path = Path(self.temp_dir.name) / "credentials.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_otrs_credentials_prefers_profile_key_over_empty_legacy_duty_fields(self):
        config = {"duty_mode": {"otrs_login": "", "otrs_password": ""}}
        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            save_credentials({OTRS_CREDENTIALS_KEY: {"login": "profile-user", "password": "profile-secret"}})
            self.assertEqual(
                load_otrs_credentials(config),
                {"login": "profile-user", "password": "profile-secret"},
            )

    def test_otrs_login_js_fills_credentials_without_submit(self):
        js = build_otrs_login_injection_js("otrs-user", "otrs-secret", auto_submit=False)
        self.assertIn("document.querySelector('#User')", js)
        self.assertIn("document.querySelector('#Password')", js)
        self.assertIn("user.value = 'otrs-user'", js)
        self.assertIn("password.value = 'otrs-secret'", js)
        self.assertIn("if (false && button)", js)
        self.assertNotIn("if (true && button)", js)

    def test_otrs_login_js_submits_when_enabled(self):
        js = build_otrs_login_injection_js("otrs-user", "otrs-secret", auto_submit=True)
        self.assertIn("document.querySelector('#LoginButton')", js)
        self.assertIn("if (true && button)", js)
        self.assertIn("button.click()", js)
        self.assertIn("filled-and-submitted", js)

    def test_empty_credentials_produce_no_submit_js(self):
        self.assertEqual(build_otrs_login_injection_js("", "secret", auto_submit=True), "")
        self.assertEqual(build_otrs_login_injection_js("user", "", auto_submit=True), "")

    def test_profile_source_contains_and_saves_otrs_auto_submit_checkbox(self):
        source = Path("app/home_config.py").read_text(encoding="utf-8")
        self.assertIn("Автоматически нажимать кнопку входа ОТРС после подстановки", source)
        self.assertIn("self.otrs_auto_submit_login = QCheckBox", source)
        self.assertIn('duty["otrs_auto_submit_login"] = self.otrs_auto_submit_login.isChecked()', source)

    def test_duty_mode_uses_shared_otrs_injection_helper_and_expected_logs(self):
        source = Path("app/duty_mode.py").read_text(encoding="utf-8")
        self.assertIn("build_otrs_login_injection_js", source)
        self.assertIn("def build_otrs_login_injection_js", Path("app/credentials.py").read_text(encoding="utf-8"))
        self.assertEqual(source.count("def inject_shared_otrs_login_if_needed"), 1)
        self.assertGreaterEqual(source.count("inject_shared_otrs_login_if_needed(self.view, self.config, self.logger)"), 3)
        for message in (
            "OTRS login injection skipped: login_enabled=false",
            "OTRS login page detected: has_saved_credentials=%s auto_submit=%s",
            "OTRS login fields filled: credential_source=profile",
            "OTRS autologin submitted: credential_source=profile",
            "OTRS login fields not found: has_saved_credentials=true",
        ):
            self.assertIn(message, source)


if __name__ == "__main__":
    unittest.main()
