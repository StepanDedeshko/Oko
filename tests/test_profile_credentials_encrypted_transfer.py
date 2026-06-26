import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.credentials import (
    export_profile_credentials_encrypted_file,
    import_profile_credentials_encrypted_file,
    load_saved_credentials,
    save_credentials,
)


class EncryptedProfileCredentialsTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.credentials_path = Path(self.temp_dir.name) / "credentials.json"
        self.export_path = Path(self.temp_dir.name) / "profile.okoenc"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_encrypted_profile_roundtrip_without_plaintext(self):
        source_credentials = {
            "otrs": {"login": "otrs-user", "password": "otrs-secret"},
            "zbx_product_1": {"login": "zabbix-user", "password": "zabbix-secret"},
            "service_check::service_1": {"login": "service-user", "password": "service-secret"},
            "service_group::group_1": {"login": "group-user", "password": "group-secret"},
        }

        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            save_credentials(source_credentials)
            export_profile_credentials_encrypted_file(self.export_path, "strong-password")

            exported_text = self.export_path.read_text(encoding="utf-8")
            self.assertIn('"type": "oko_profile_credentials_encrypted"', exported_text)
            self.assertNotIn("otrs-user", exported_text)
            self.assertNotIn("otrs-secret", exported_text)
            self.assertNotIn("zabbix-user", exported_text)
            self.assertNotIn("zabbix-secret", exported_text)
            self.assertNotIn("service-user", exported_text)
            self.assertNotIn("service-secret", exported_text)

            save_credentials({})
            imported_count = import_profile_credentials_encrypted_file(self.export_path, "strong-password")
            restored = load_saved_credentials()

        self.assertEqual(imported_count, 4)
        self.assertEqual(restored, source_credentials)

    def test_encrypted_profile_rejects_wrong_password(self):
        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            save_credentials({"otrs": {"login": "user", "password": "secret"}})
            export_profile_credentials_encrypted_file(self.export_path, "right-password")

            save_credentials({})
            with self.assertRaises(ValueError):
                import_profile_credentials_encrypted_file(self.export_path, "wrong-password")

            self.assertEqual(load_saved_credentials(), {})

    def test_encrypted_profile_rejects_plain_json_profile(self):
        self.export_path.write_text(
            json.dumps({"type": "oko_profile_credentials", "version": 1, "credentials": {}}),
            encoding="utf-8",
        )

        with patch("app.credentials.CREDENTIALS_FILE", self.credentials_path):
            with self.assertRaises(ValueError):
                import_profile_credentials_encrypted_file(self.export_path, "password")


if __name__ == "__main__":
    unittest.main()
