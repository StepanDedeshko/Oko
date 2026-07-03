import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.credentials import (
    OTRS_CREDENTIALS_KEY,
    SERVICE_CREDENTIALS_PREFIX,
    SERVICE_GROUP_CREDENTIALS_PREFIX,
    ZABBIX_COMMON_CREDENTIALS_KEY,
    clear_zabbix_profile_credentials,
    load_saved_credentials,
    load_zabbix_profile_credentials,
    save_credentials,
    save_zabbix_profile_credentials,
    zabbix_credential_key_for_instance,
    zabbix_profile_credential_targets,
)


class ProfileZabbixCredentialsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.credentials_path = Path(self.temp_dir.name) / "credentials.json"
        self.instances = [
            {"id": "zbx_main", "name": "Main Zabbix", "enabled": True},
            {"id": "zbx_backup", "name": "Backup Zabbix", "enabled": True},
            {"id": "", "name": "Missing id", "enabled": True},
        ]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_zabbix_key_uses_stable_instance_id(self):
        self.assertEqual(zabbix_credential_key_for_instance({"id": " zbx_main ", "name": "Main"}), "zbx_main")
        self.assertEqual(zabbix_credential_key_for_instance({"name": "Missing id"}), "")

    def test_zabbix_credentials_are_saved_under_stable_key(self):
        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            save_zabbix_profile_credentials(
                self.instances,
                {"zbx_main": {"login": "z-user", "password": "z-secret"}},
            )
            restored = load_saved_credentials()

        self.assertEqual(restored["zbx_main"], {"login": "z-user", "password": "z-secret"})
        self.assertNotIn("", restored)

    def test_saved_zabbix_credentials_load_back_for_profile_fields(self):
        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            save_credentials({"zbx_main": {"login": "z-user", "password": "z-secret"}})
            loaded = load_zabbix_profile_credentials(self.instances)

        self.assertEqual(loaded["zbx_main"], {"login": "z-user", "password": "z-secret"})
        self.assertEqual(loaded["zbx_backup"], {"login": "", "password": ""})

    def test_reported_save_recreate_reload_scenario_keeps_zabbix_values(self):
        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            save_zabbix_profile_credentials(
                self.instances,
                {"zbx_main": {"login": "entered-login", "password": "entered-password"}},
            )
            reloaded_for_recreated_widget = load_zabbix_profile_credentials(self.instances)

        self.assertEqual(
            reloaded_for_recreated_widget["zbx_main"],
            {"login": "entered-login", "password": "entered-password"},
        )

    def test_multiple_zabbix_instances_keep_separate_credentials(self):
        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            save_zabbix_profile_credentials(
                self.instances,
                {
                    "zbx_main": {"login": "main-login", "password": "main-password"},
                    "zbx_backup": {"login": "backup-login", "password": "backup-password"},
                },
            )
            loaded = load_zabbix_profile_credentials(self.instances)

        self.assertEqual(loaded["zbx_main"], {"login": "main-login", "password": "main-password"})
        self.assertEqual(loaded["zbx_backup"], {"login": "backup-login", "password": "backup-password"})

    def test_saving_zabbix_preserves_redmine_otrs_and_service_credentials(self):
        original = {
            OTRS_CREDENTIALS_KEY: {"login": "otrs-user", "password": "otrs-secret"},
            "live_zabbix_monitor::redmine": {"login": "redmine-user", "password": "redmine-secret"},
            f"{SERVICE_CREDENTIALS_PREFIX}svc_1": {"login": "service-user", "password": "service-secret"},
            f"{SERVICE_GROUP_CREDENTIALS_PREFIX}group_1": {"login": "group-user", "password": "group-secret"},
        }
        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            save_credentials(original)
            save_zabbix_profile_credentials(
                self.instances,
                {"zbx_main": {"login": "z-user", "password": "z-secret"}},
            )
            restored = load_saved_credentials()

        for key, value in original.items():
            self.assertEqual(restored[key], value)
        self.assertEqual(restored["zbx_main"], {"login": "z-user", "password": "z-secret"})


    def test_no_zabbix_instances_uses_common_fallback_key(self):
        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            save_zabbix_profile_credentials(
                [],
                {ZABBIX_COMMON_CREDENTIALS_KEY: {"login": "common-user", "password": "common-secret"}},
            )
            restored = load_saved_credentials()

        self.assertEqual(
            restored[ZABBIX_COMMON_CREDENTIALS_KEY],
            {"login": "common-user", "password": "common-secret"},
        )
        self.assertEqual(
            zabbix_profile_credential_targets([]),
            [{"id": ZABBIX_COMMON_CREDENTIALS_KEY, "name": "Zabbix", "common": True}],
        )

    def test_no_zabbix_instances_reload_keeps_common_credentials(self):
        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            save_credentials({ZABBIX_COMMON_CREDENTIALS_KEY: {"login": "common-user", "password": "common-secret"}})
            reloaded_for_recreated_widget = load_zabbix_profile_credentials([])

        self.assertEqual(
            reloaded_for_recreated_widget[ZABBIX_COMMON_CREDENTIALS_KEY],
            {"login": "common-user", "password": "common-secret"},
        )

    def test_explicit_clear_zabbix_credentials_clears_only_zabbix(self):
        original = {
            OTRS_CREDENTIALS_KEY: {"login": "otrs-user", "password": "otrs-secret"},
            "live_zabbix_monitor::redmine": {"login": "redmine-user", "password": "redmine-secret"},
            ZABBIX_COMMON_CREDENTIALS_KEY: {"login": "common", "password": "common-secret"},
            "zbx_main": {"login": "main", "password": "main-secret"},
            "zbx_backup": {"login": "backup", "password": "backup-secret"},
            f"{SERVICE_CREDENTIALS_PREFIX}svc_1": {"login": "service-user", "password": "service-secret"},
            f"{SERVICE_GROUP_CREDENTIALS_PREFIX}group_1": {"login": "group-user", "password": "group-secret"},
        }
        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            save_credentials(original)
            clear_zabbix_profile_credentials(self.instances)
            restored = load_saved_credentials()

        self.assertNotIn(ZABBIX_COMMON_CREDENTIALS_KEY, restored)
        self.assertNotIn("zbx_main", restored)
        self.assertNotIn("zbx_backup", restored)
        for key in (OTRS_CREDENTIALS_KEY, "live_zabbix_monitor::redmine", f"{SERVICE_CREDENTIALS_PREFIX}svc_1", f"{SERVICE_GROUP_CREDENTIALS_PREFIX}group_1"):
            self.assertEqual(restored[key], original[key])


if __name__ == "__main__":
    unittest.main()
