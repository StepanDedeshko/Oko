import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.credentials import (
    OTRS_CREDENTIALS_KEY,
    build_otrs_login_injection_js,
    load_otrs_credentials,
    save_credentials,
)


class OtrsProfileLoginTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.credentials_path = Path(self.temp_dir.name) / "credentials.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_otrs_credentials_prefers_profile_store_over_empty_legacy_duty_values(self):
        config = {"duty_mode": {"otrs_login": None, "otrs_password": None}}
        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            save_credentials({OTRS_CREDENTIALS_KEY: {"login": "profile-user", "password": "profile-secret"}})
            loaded = load_otrs_credentials(config)

        self.assertEqual(loaded, {"login": "profile-user", "password": "profile-secret"})

    def test_otrs_login_injection_js_fills_without_submit_when_auto_submit_false(self):
        js = build_otrs_login_injection_js("profile-user", "profile-secret", auto_submit=False)

        self.assertIn("#User", js)
        self.assertIn("#Password", js)
        self.assertIn("profile-user", js)
        self.assertIn("profile-secret", js)
        self.assertIn("if (false && button)", js)
        self.assertIn("return 'filled'", js)

    def test_otrs_login_injection_js_clicks_submit_when_auto_submit_true(self):
        js = build_otrs_login_injection_js("profile-user", "profile-secret", auto_submit=True)

        self.assertIn("if (true && button)", js)
        self.assertIn("button.click()", js)
        self.assertIn("return 'filled-and-submitted'", js)

    def test_empty_otrs_credentials_do_not_generate_submit_js(self):
        self.assertEqual(build_otrs_login_injection_js("", "profile-secret", auto_submit=True), "")
        self.assertEqual(build_otrs_login_injection_js("profile-user", "", auto_submit=True), "")

    def test_profile_exposes_and_saves_otrs_auto_submit_setting(self):
        source = Path("app/home_config.py").read_text(encoding="utf-8")

        self.assertIn("self.otrs_auto_submit_checkbox = QCheckBox", source)
        self.assertIn("duty[\"otrs_auto_submit_login\"] = self.otrs_auto_submit_checkbox.isChecked()", source)
        self.assertIn("duty[\"otrs_login_enabled\"] = self.enabled.isChecked()", source)
        self.assertIn("credentials[OTRS_CREDENTIALS_KEY]", source)

    def test_duty_mode_logs_and_uses_profile_otrs_injection_helper(self):
        source = Path("app/duty_mode.py").read_text(encoding="utf-8")

        self.assertIn("OTRS login injection skipped: login_enabled=false", source)
        self.assertIn("OTRS login page detected: has_saved_credentials=%s auto_submit=%s", source)
        self.assertIn("OTRS login fields filled: credential_source=profile", source)
        self.assertIn("OTRS autologin submitted: credential_source=profile", source)
        self.assertIn("OTRS login fields not found: has_saved_credentials=true", source)
        self.assertIn("inject_otrs_login_if_needed_for_view(self.view, self.config, self.logger)", source)


if __name__ == "__main__":
    unittest.main()
