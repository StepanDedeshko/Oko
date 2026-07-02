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


class DutyOtrsFlowTest(unittest.TestCase):
    def test_otrs_number_formats_parse(self):
        from app.duty_otrs_flow import parse_otrs_ticket_number

        self.assertEqual(parse_otrs_ticket_number("Заявка#100070477"), "100070477")
        self.assertEqual(parse_otrs_ticket_number("Добавить заметку к Заявка#100070477"), "100070477")
        self.assertEqual(parse_otrs_ticket_number("Заявка №100070477"), "100070477")
        self.assertEqual(parse_otrs_ticket_number("100070477 - Подробно - Заявки - Service Desk"), "100070477")

    def test_v031_style_otrs_flow_binding_returns_id_number_url(self):
        from app.duty_otrs_flow import OtrsTaskBinding

        binding = OtrsTaskBinding(TASK_ZABBIX, "70400", "100070477", "https://otrs/index.pl?Action=AgentTicketZoom;TicketID=70400")
        self.assertEqual(binding.as_dict()["task_type"], TASK_ZABBIX)
        self.assertEqual(binding.as_dict()["ticket_id"], "70400")
        self.assertEqual(binding.as_dict()["ticket_number"], "100070477")
        self.assertEqual(binding.as_dict()["ticket_url"], "https://otrs/index.pl?Action=AgentTicketZoom;TicketID=70400")

    def test_zabbix_otrs_binding_visible_only_when_number_exists(self):
        from app.duty_otrs_flow import visible_task_status

        settings = {"current_ticket_id": "70400", "duty_zabbix_task_id": "70400"}
        self.assertFalse(has_current_task(settings, TASK_ZABBIX))
        self.assertEqual(visible_task_status(settings, TASK_ZABBIX), "не привязана")
        self.assertEqual(visible_task_status(settings, TASK_ZABBIX, reading_number=True), "ищу номер заявки...")
        settings["current_ticket_number"] = "100070477"
        self.assertTrue(has_current_task(settings, TASK_ZABBIX))
        self.assertEqual(visible_task_status(settings, TASK_ZABBIX), "№100070477")

    def test_service_otrs_binding_visible_only_when_number_exists(self):
        from app.duty_otrs_flow import visible_task_status

        settings = {"duty_service_checks_task_id": "70400"}
        self.assertFalse(has_current_task(settings, TASK_SERVICES))
        self.assertEqual(visible_task_status(settings, TASK_SERVICES), "не привязана")
        settings["duty_service_checks_task_number"] = "100070477"
        self.assertTrue(has_current_task(settings, TASK_SERVICES))
        self.assertEqual(visible_task_status(settings, TASK_SERVICES), "№100070477")

    def test_ticket_id_saved_but_not_shown_as_visible_binding(self):
        from app.duty_otrs_flow import OtrsTaskBinding, save_otrs_task_binding, visible_task_status

        settings = {}
        save_otrs_task_binding(settings, OtrsTaskBinding(TASK_ZABBIX, "70400", "", "https://otrs/?TicketID=70400"))
        self.assertEqual(settings["current_ticket_id"], "70400")
        self.assertEqual(visible_task_status(settings, TASK_ZABBIX), "не привязана")
        self.assertNotIn("TicketID=70400", visible_task_status(settings, TASK_ZABBIX))

    def test_note_dialog_opens_note_by_ticket_id(self):
        from app.duty_otrs_flow import make_note_url_by_ticket_id

        config = {"duty_mode": {"otrs": {"note_url_base": "https://otrs/index.pl?Action=AgentTicketNote;TicketID="}}}
        self.assertEqual(make_note_url_by_ticket_id(config, "70400"), "https://otrs/index.pl?Action=AgentTicketNote;TicketID=70400")

    def test_duty_tasks_dialog_uses_duty_otrs_flow_for_creation(self):
        from pathlib import Path

        source = Path(__file__).resolve().parents[1].joinpath("app", "duty_mode.py").read_text(encoding="utf-8")
        self.assertIn("from app.duty_otrs_flow import open_otrs_task_flow", source)
        self.assertIn("open_otrs_task_flow(self.config, parent=self, task_type=task_type)", source)


if __name__ == "__main__":
    unittest.main()
