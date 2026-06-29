import json
import unittest
from pathlib import Path
import tempfile

from app.permissions import (
    ALL_SECTION_PERMISSIONS,
    SAFE_AGENT_SECTION_PERMISSIONS,
    SECTION_ADMIN,
    SECTION_DEVELOPER,
    SECTION_DUTY_SETTINGS,
    SECTION_PROFILE,
    build_user_settings_export,
    can_open_section,
    ensure_duty_links,
    get_duty_link,
    import_user_settings_payload,
    normalize_user_permissions,
    service_checks_for_user,
    service_check_items_for_group,
    set_duty_link,
    visible_service_groups_for_user,
)
from app.app_users import create_user, update_user
from app.config import import_settings_file, load_settings_export


class PermissionsAndUserExportTests(unittest.TestCase):
    def test_admin_has_all_sections_and_agent_is_safe_by_default(self):
        admin = normalize_user_permissions({"role": "admin"})
        agent = normalize_user_permissions({"role": "agent"})

        self.assertEqual(set(admin["section_permissions"]), set(ALL_SECTION_PERMISSIONS))
        self.assertEqual(set(agent["section_permissions"]), set(SAFE_AGENT_SECTION_PERMISSIONS))
        self.assertTrue(can_open_section(admin, "Администрирование"))
        self.assertFalse(can_open_section(agent, "Администрирование"))
        self.assertFalse(can_open_section(agent, "Режим разработчика"))

    def test_custom_only_gets_explicit_permissions_and_navigation_blocks(self):
        user = normalize_user_permissions({"role": "custom", "section_permissions": [SECTION_PROFILE, SECTION_DUTY_SETTINGS]})
        self.assertTrue(can_open_section(user, "Профиль"))
        self.assertTrue(can_open_section(user, "Настройки дежурки"))
        self.assertFalse(can_open_section(user, "Режим разработчика"))
        self.assertFalse(can_open_section(user, "Администрирование"))

    def test_legacy_duty_urls_are_read_and_new_keys_are_saved(self):
        config = {
            "live_zabbix_monitor": {"problems_url": "https://zabbix/problems", "mm_otrs_create_url": "https://old-mm"},
            "duty_mode": {"otrs": {"create_url": "https://otrs/create"}, "redmine_create_url": "https://redmine/new"},
        }
        self.assertEqual(get_duty_link(config, "live_zabbix_url"), "https://zabbix/problems")
        self.assertEqual(get_duty_link(config, "otrs_create_url"), "https://otrs/create")
        ensure_duty_links(config)
        set_duty_link(config, "live_zabbix_url", "https://new-zabbix")
        self.assertEqual(config["duty_links"]["live_zabbix_url"], "https://new-zabbix")

    def test_user_export_contains_rights_and_no_secrets(self):
        config = {
            "settings": {"theme": "mass_effect"},
            "duty_links": {"live_zabbix_url": "https://zabbix", "otrs_create_url": "https://otrs"},
            "service_checks": {
                "credential_groups": [{"id": "g1", "name": "G1"}, {"id": "g2", "name": "G2"}],
                "items": [
                    {"id": "s1", "credential_group_id": "g1", "url": "https://svc", "login_selector": "#u", "password_selector": "#p", "password": "secret"},
                    {"id": "s2", "credential_group_id": "g2", "url": "https://other"},
                ],
            },
            "products": [{"name": "P", "token": "secret-token"}],
        }
        user = {"login": "agent", "role": "agent", "section_permissions": [SECTION_PROFILE], "service_group_ids": ["g1"]}
        payload = build_user_settings_export(config, user)
        text = json.dumps(payload, ensure_ascii=False).lower()
        self.assertEqual(payload["user"]["section_permissions"], [SECTION_PROFILE])
        self.assertEqual(payload["settings"]["service_checks"]["credential_groups"][0]["id"], "g1")
        self.assertNotIn("secret-token", text)
        self.assertNotIn("password\": \"secret", text)
        self.assertIn("login_selector", text)

    def test_import_applies_rights_and_keeps_credentials_out_of_config(self):
        current = {"settings": {"theme": "old"}, "local": "keep"}
        payload = {
            "format": "oko_user_settings_export",
            "format_version": 1,
            "user": {"login": "agent", "role": "custom", "section_permissions": [SECTION_PROFILE], "service_group_ids": ["g1"]},
            "settings": {"settings": {"theme": "new"}, "duty_links": {"live_zabbix_url": "https://z"}},
        }
        imported = import_user_settings_payload(current, payload, keep_passwords=True)
        self.assertEqual(imported["settings"]["theme"], "new")
        self.assertEqual(imported["_current_user"]["section_permissions"], [SECTION_PROFILE])
        self.assertEqual(imported["_current_user"]["service_group_ids"], ["g1"])
        self.assertNotIn("credentials", imported)

    def test_user_settings_export_can_be_loaded_and_imported_from_file(self):
        payload = {
            "format": "oko_user_settings_export",
            "format_version": 1,
            "user": {"login": "agent", "role": "custom", "section_permissions": [SECTION_PROFILE], "service_group_ids": ["g1"]},
            "settings": {
                "duty_links": {"live_zabbix_url": "https://z", "redmine_create_url": "https://r", "otrs_create_url": "https://o", "mm_otrs_create_url": "https://m"},
                "service_checks": {"credential_groups": [{"id": "g1"}], "items": []},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            export_path = Path(tmp) / "user.json"
            config_path = Path(tmp) / "config.json"
            export_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            config_path.write_text(json.dumps({"local_credentials_marker": True}, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(load_settings_export(export_path)["format"], "oko_user_settings_export")
            import_settings_file(export_path, config_path=config_path)
            imported = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(imported["_current_user"]["service_group_ids"], ["g1"])
        self.assertEqual(imported["duty_links"]["mm_otrs_create_url"], "https://m")
        self.assertTrue(imported["local_credentials_marker"])

    def test_service_checks_for_user_limits_to_groups_but_keeps_technical_for_export(self):
        config = {"service_checks": {"credential_groups": [{"id": "g1"}, {"id": "g2"}], "items": [{"id": "s1", "credential_group_id": "g1", "timeout_seconds": 5}, {"id": "s2", "credential_group_id": "g2"}]}}
        checks = service_checks_for_user(config, {"role": "agent", "service_group_ids": ["g1"]})
        self.assertEqual([g["id"] for g in checks["credential_groups"]], ["g1"])
        self.assertEqual([i["id"] for i in checks["items"]], ["s1"])
        self.assertEqual(checks["items"][0]["timeout_seconds"], 5)

        empty_agent_checks = service_checks_for_user(config, {"role": "agent", "service_group_ids": []})
        self.assertEqual(empty_agent_checks["credential_groups"], [])
        self.assertEqual(empty_agent_checks["items"], [])

    def test_visible_service_groups_respect_roles_and_empty_agent_groups(self):
        config = {"service_checks": {"credential_groups": [{"id": "g1"}, {"id": "g2"}], "items": []}}
        self.assertEqual([g["id"] for g in visible_service_groups_for_user(config, {"role": "agent", "service_group_ids": ["g1"]})], ["g1"])
        self.assertEqual(visible_service_groups_for_user(config, {"role": "agent", "service_group_ids": []}), [])
        self.assertEqual([g["id"] for g in visible_service_groups_for_user(config, {"role": "admin", "service_group_ids": []})], ["g1", "g2"])

    def test_agent_group_ui_helpers_do_not_expose_technical_editor_fields(self):
        config = {
            "service_checks": {
                "credential_groups": [{"id": "g1", "name": "Group 1", "service_ids": ["s1"]}],
                "items": [{"id": "s1", "credential_group_id": "g1", "url": "https://svc", "login_selector": "#login", "timeout_seconds": 10}],
            }
        }
        user = {"role": "agent", "service_group_ids": ["g1"]}
        groups = visible_service_groups_for_user(config, user)
        items = service_check_items_for_group(config, groups[0]["id"])
        self.assertEqual(groups[0]["name"], "Group 1")
        self.assertEqual(items[0]["id"], "s1")
        self.assertFalse(can_open_section(user, "Технические настройки проверок"))

    def test_duty_links_all_new_keys_saved(self):
        config = {}
        for key in ("live_zabbix_url", "redmine_create_url", "otrs_create_url", "mm_otrs_create_url"):
            set_duty_link(config, key, f"https://example/{key}")
        self.assertEqual(config["duty_links"], {key: f"https://example/{key}" for key in ("live_zabbix_url", "redmine_create_url", "otrs_create_url", "mm_otrs_create_url")})

    def test_update_user_cannot_remove_last_admin_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "users.json"
            create_user("owner", "pass1", role="owner", path=path)
            with self.assertRaises(ValueError):
                update_user("owner", role="agent", path=path)
            with self.assertRaises(ValueError):
                update_user("owner", active=False, path=path)


if __name__ == "__main__":
    unittest.main()
