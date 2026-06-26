import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.credentials import (
    export_profile_credentials_file,
    import_profile_credentials_file,
    load_saved_credentials,
    save_credentials,
)


class ProfileCredentialsTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.credentials_path = Path(self.temp_dir.name) / "credentials.json"
        self.export_path = Path(self.temp_dir.name) / "profile.oko-profile.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_profile_export_import_roundtrip_without_plaintext_passwords(self):
        source_credentials = {
            "otrs": {"login": "otrs-user", "password": "otrs-secret"},
            "zbx_product_1": {"login": "zabbix-user", "password": "zabbix-secret"},
            "service_check::service_1": {"login": "service-user", "password": "service-secret"},
            "service_group::group_1": {"login": "group-user", "password": "group-secret"},
        }

        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            save_credentials(source_credentials)
            export_profile_credentials_file(self.export_path)

            exported_text = self.export_path.read_text(encoding="utf-8")
            self.assertNotIn("otrs-secret", exported_text)
            self.assertNotIn("zabbix-secret", exported_text)
            self.assertNotIn("service-secret", exported_text)
            self.assertNotIn("group-secret", exported_text)

            save_credentials({})
            imported_count = import_profile_credentials_file(self.export_path)
            restored = load_saved_credentials()

        self.assertEqual(imported_count, 4)
        self.assertEqual(restored, source_credentials)

    def test_profile_import_merges_with_existing_credentials(self):
        imported_credentials = {
            "service_group::group_1": {"login": "group-user", "password": "group-secret"},
        }

        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            save_credentials(imported_credentials)
            export_profile_credentials_file(self.export_path)

            save_credentials({
                "existing": {"login": "old-user", "password": "old-secret"},
            })

            import_profile_credentials_file(self.export_path)
            restored = load_saved_credentials()

        self.assertEqual(restored["existing"], {"login": "old-user", "password": "old-secret"})
        self.assertEqual(restored["service_group::group_1"], {"login": "group-user", "password": "group-secret"})

    def test_rejects_common_settings_export_as_profile(self):
        self.export_path.write_text(
            json.dumps({"type": "oko_settings_export", "version": 1}),
            encoding="utf-8",
        )

        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            with self.assertRaises(ValueError):
                import_profile_credentials_file(self.export_path)


if __name__ == "__main__":
    unittest.main()
