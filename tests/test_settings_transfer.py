import json
import tempfile
import unittest
from pathlib import Path

from app.config import (
    SETTINGS_EXPORT_FORMAT,
    export_settings_file,
    import_settings_file,
    load_settings_export,
)


class SettingsTransferTest(unittest.TestCase):
    def test_export_creates_oko_settings_json_without_secret_fields(self):
        config = {
            "settings": {"theme": "mass_effect", "email": "user@example.local"},
            "products": [
                {
                    "name": "Продукт",
                    "password": "pass",
                    "token": "token",
                    "cookie": "cookie",
                    "session": "session",
                    "auth": "auth",
                    "credential": "credential",
                    "secret": "secret",
                    "login": "login",
                    "username": "username",
                    "sections": [{"title": "Раздел"}],
                }
            ],
            "templates": {"otrs_graph_check": {"text": "OK"}},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = Path(tmpdir) / "oko_settings_export.json"
            export_settings_file(config, export_path)
            data = json.loads(export_path.read_text(encoding="utf-8"))

        self.assertEqual(data["format"], SETTINGS_EXPORT_FORMAT)
        serialized = json.dumps(data, ensure_ascii=False).lower()
        for key in (
            "password",
            "token",
            "cookie",
            "session",
            "auth",
            "credential",
            "secret",
            "login",
            "username",
            "email",
        ):
            self.assertNotIn(key, serialized)
        self.assertEqual(data["settings"]["settings"]["theme"], "mass_effect")
        self.assertEqual(data["settings"]["products"][0]["name"], "Продукт")

    def test_import_valid_file_writes_config_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            config_path = tmpdir / "config.json"
            config_path.write_text(json.dumps({"settings": {"theme": "old"}}), encoding="utf-8")
            source_path = tmpdir / "export.json"
            source_path.write_text(
                json.dumps(
                    {
                        "app": "Око",
                        "format": SETTINGS_EXPORT_FORMAT,
                        "format_version": 1,
                        "exported_at": "2026-06-05 12:00:00",
                        "settings": {
                            "settings": {"theme": "new"},
                            "products": [{"name": "A", "token": "must-drop"}],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            backup_path = import_settings_file(source_path, config_path=config_path)
            imported = json.loads(config_path.read_text(encoding="utf-8"))

            self.assertIsNotNone(backup_path)
            self.assertTrue(backup_path.exists())
            self.assertEqual(imported["settings"]["theme"], "new")
            self.assertNotIn("token", json.dumps(imported).lower())

    def test_invalid_import_returns_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "bad.json"
            source_path.write_text('{"format":"other"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_settings_export(source_path)


if __name__ == "__main__":
    unittest.main()
