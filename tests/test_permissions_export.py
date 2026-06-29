import json
import unittest

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
    set_duty_link,
)


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

    def test_service_checks_for_user_limits_to_groups_but_keeps_technical_for_export(self):
        config = {"service_checks": {"credential_groups": [{"id": "g1"}, {"id": "g2"}], "items": [{"id": "s1", "credential_group_id": "g1", "timeout_seconds": 5}, {"id": "s2", "credential_group_id": "g2"}]}}
        checks = service_checks_for_user(config, {"role": "agent", "service_group_ids": ["g1"]})
        self.assertEqual([g["id"] for g in checks["credential_groups"]], ["g1"])
        self.assertEqual([i["id"] for i in checks["items"]], ["s1"])
        self.assertEqual(checks["items"][0]["timeout_seconds"], 5)


if __name__ == "__main__":
    unittest.main()
