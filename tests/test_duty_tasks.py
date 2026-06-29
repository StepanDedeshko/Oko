import unittest

from app.duty_tasks import (
    TASK_SERVICES,
    TASK_ZABBIX,
    current_task_binding,
    duty_tasks_button_enabled,
    has_current_task,
    parse_ticket_url,
    planned_actions,
    save_task_binding,
    selected_task_types,
    smart_action_text,
)


class DutyTasksHelpersTest(unittest.TestCase):
    def test_button_enabled_depends_on_selected_checks(self):
        self.assertFalse(duty_tasks_button_enabled({"check_zabbix_enabled": False, "check_services_enabled": False}))
        self.assertTrue(duty_tasks_button_enabled({"check_zabbix_enabled": True, "check_services_enabled": False}))
        self.assertTrue(duty_tasks_button_enabled({"check_zabbix_enabled": False, "check_services_enabled": True}))

    def test_selected_rows_follow_selected_checks(self):
        self.assertEqual(selected_task_types({"check_zabbix_enabled": True, "check_services_enabled": False}), [TASK_ZABBIX])
        self.assertEqual(selected_task_types({"check_zabbix_enabled": False, "check_services_enabled": True}), [TASK_SERVICES])
        self.assertEqual(selected_task_types({"check_zabbix_enabled": True, "check_services_enabled": True}), [TASK_ZABBIX, TASK_SERVICES])

    def test_smart_button_text(self):
        tasks = [TASK_ZABBIX, TASK_SERVICES]
        self.assertEqual(smart_action_text({}, tasks), "Создать оба тикета")
        self.assertEqual(smart_action_text({TASK_ZABBIX: "u", TASK_SERVICES: "v"}, tasks), "Привязать оба тикета")
        self.assertEqual(smart_action_text({TASK_ZABBIX: "u", TASK_SERVICES: ""}, tasks), "Применить")
        self.assertEqual(smart_action_text({}, [TASK_ZABBIX]), "Создать тикет")
        self.assertEqual(smart_action_text({TASK_ZABBIX: "u"}, [TASK_ZABBIX]), "Привязать тикет")

    def test_empty_fields_plan_create(self):
        self.assertEqual(planned_actions({}, [TASK_ZABBIX, TASK_SERVICES]), {TASK_ZABBIX: "create", TASK_SERVICES: "create"})

    def test_filled_fields_plan_link(self):
        self.assertEqual(
            planned_actions({TASK_ZABBIX: "https://redmine.example/issues/70194", TASK_SERVICES: "https://otrs.example/?TicketID=42"}, [TASK_ZABBIX, TASK_SERVICES]),
            {TASK_ZABBIX: "link", TASK_SERVICES: "link"},
        )

    def test_mixed_fields_plan_apply(self):
        self.assertEqual(planned_actions({TASK_ZABBIX: "https://redmine.example/issues/70194"}, [TASK_ZABBIX, TASK_SERVICES]), {TASK_ZABBIX: "link", TASK_SERVICES: "create"})

    def test_parse_redmine_url(self):
        parsed = parse_ticket_url("https://redmine.example.org/issues/70194?tab=notes")
        self.assertEqual(parsed["system"], "redmine")
        self.assertEqual(parsed["id"], "70194")
        self.assertEqual(parsed["number"], "70194")

    def test_parse_otrs_url(self):
        parsed = parse_ticket_url("https://otrs.example.org/index.pl?Action=AgentTicketZoom;TicketID=100068754")
        self.assertEqual(parsed["system"], "otrs")
        self.assertEqual(parsed["id"], "100068754")

    def test_duplicate_create_guard_uses_existing_binding(self):
        settings = {}
        self.assertFalse(has_current_task(settings, TASK_ZABBIX))
        save_task_binding(settings, TASK_ZABBIX, parse_ticket_url("https://redmine.example.org/issues/70194"))
        self.assertTrue(has_current_task(settings, TASK_ZABBIX))
        self.assertEqual(current_task_binding(settings, TASK_ZABBIX)["id"], "70194")


if __name__ == "__main__":
    unittest.main()
