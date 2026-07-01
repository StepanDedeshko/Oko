import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import apply_prepared_config_file
from app.permissions import SECTION_PROFILE


class AgentSafeConfigImportTests(unittest.TestCase):
    def test_agent_apply_user_config_keeps_role_and_permissions_but_applies_work_settings(self):
        current = {
            "_current_user": {
                "login": "ivanov",
                "role": "agent",
                "section_permissions": [SECTION_PROFILE],
                "service_group_ids": [],
            },
            "settings": {"theme": "old"},
        }
        payload = {
            "format": "oko_user_settings_export",
            "format_version": 1,
            "user": {
                "login": "ivanov",
                "role": "owner",
                "is_owner": True,
                "is_admin": True,
                "developer_mode": True,
                "permissions": {"all_permissions": True},
                "section_permissions": ["section.admin", "section.links"],
                "service_group_ids": ["facepay", "zabbix"],
            },
            "settings": {
                "settings": {"theme": "mass_effect", "developer_password": "evil"},
                "duty_links": {
                    "live_zabbix_url": "https://zabbix/problems",
                    "redmine_create_url": "https://redmine/new",
                    "mm_otrs_create_url": "https://otrs-mm/new",
                },
                "service_checks": {
                    "credential_groups": [{"id": "facepay"}],
                    "items": [{"id": "svc", "credential_group_id": "facepay", "timeout_seconds": 7, "enabled": True}],
                },
                "templates": {"redmine_task": {"subject_template": "Subj"}},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prepared.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with patch("app.config.CONFIG_PATH", Path(tmp) / "config.json"):
                result, summary = apply_prepared_config_file(path, current)

        user = result["_current_user"]
        self.assertEqual(user["role"], "agent")
        self.assertFalse(user["is_owner"])
        self.assertFalse(user["is_admin"])
        self.assertFalse(user["developer_mode"])
        self.assertEqual(user["service_group_ids"], ["facepay", "zabbix"])
        self.assertEqual(result["settings"]["theme"], "mass_effect")
        self.assertNotIn("developer_password", result["settings"])
        self.assertEqual(result["duty_links"]["redmine_create_url"], "https://redmine/new")
        self.assertEqual(result["service_checks"]["items"][0]["timeout_seconds"], 7)
        self.assertEqual(summary["role"], "agent")
        self.assertEqual(summary["services_count"], 1)
        self.assertEqual(summary["links_count"], 3)

    def test_agent_apply_raw_config_ignores_top_level_access_fields(self):
        current = {"_current_user": {"login": "agent", "role": "agent", "service_group_ids": ["g1"]}}
        payload = {
            "role": "owner",
            "permissions": {"all_permissions": True},
            "is_owner": True,
            "developer_password": "evil",
            "settings": {"theme": "dark"},
            "duty_links": {"live_zabbix_url": "https://z"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "raw.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with patch("app.config.CONFIG_PATH", Path(tmp) / "config.json"):
                result, _summary = apply_prepared_config_file(path, current)

        self.assertEqual(result["_current_user"]["role"], "agent")
        self.assertNotIn("role", {k: v for k, v in result.items() if k != "_current_user"})
        self.assertNotIn("developer_password", result)
        self.assertEqual(result["settings"]["theme"], "dark")
        self.assertEqual(result["duty_links"]["live_zabbix_url"], "https://z")


if __name__ == "__main__":
    unittest.main()
