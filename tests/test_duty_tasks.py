import unittest

from app.duty_tasks import (
    TASK_SERVICES,
    TASK_ZABBIX,
    DUTY_NOTE_DISABLED_MESSAGE,
    DUTY_NOTE_UNBOUND_MESSAGE,
    current_task_binding,
    duty_note_guard,
    duty_tasks_button_enabled,
    has_current_task,
    parse_ticket_number_from_html,
    parse_ticket_url,
    planned_actions,
    save_task_binding,
    start_duty_session,
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

class DutySessionSafetyTest(unittest.TestCase):
    def test_start_duty_creates_duty_session_id(self):
        settings = {}
        session_id = start_duty_session(settings)
        self.assertTrue(session_id)
        self.assertEqual(settings["duty_session_id"], session_id)
        self.assertTrue(settings["enabled"])
        self.assertTrue(settings["duty_started_at"])
        self.assertEqual(settings["duty_finished_at"], "")

    def test_start_duty_clears_old_current_and_task_fields(self):
        settings = {
            "current_ticket_number": "old",
            "current_ticket_id": "old-id",
            "current_ticket_url": "old-url",
            "duty_zabbix_task_number": "old-z",
            "duty_zabbix_task_id": "old-z-id",
            "duty_zabbix_task_url": "old-z-url",
            "duty_zabbix_task_session_id": "old-session",
            "duty_service_checks_task_number": "old-s",
            "duty_service_checks_task_id": "old-s-id",
            "duty_service_checks_task_url": "old-s-url",
            "duty_service_checks_task_session_id": "old-session",
            "last_zabbix_check_note": "old note",
            "last_service_check_note": "old note",
        }
        start_duty_session(settings)
        for key in (
            "current_ticket_number", "current_ticket_id", "current_ticket_url",
            "duty_zabbix_task_number", "duty_zabbix_task_id", "duty_zabbix_task_url", "duty_zabbix_task_session_id",
            "duty_service_checks_task_number", "duty_service_checks_task_id", "duty_service_checks_task_url", "duty_service_checks_task_session_id",
            "last_zabbix_check_note", "last_service_check_note",
        ):
            self.assertEqual(settings[key], "")

    def test_disabled_duty_blocks_zabbix_note(self):
        ok, message = duty_note_guard({"enabled": False}, TASK_ZABBIX)
        self.assertFalse(ok)
        self.assertEqual(message, DUTY_NOTE_DISABLED_MESSAGE)

    def test_disabled_duty_blocks_service_checks_note(self):
        ok, message = duty_note_guard({"enabled": False}, TASK_SERVICES)
        self.assertFalse(ok)
        self.assertEqual(message, DUTY_NOTE_DISABLED_MESSAGE)

    def test_stale_zabbix_task_from_old_session_blocks_note(self):
        ok, message = duty_note_guard({"enabled": True, "duty_session_id": "new", "duty_zabbix_task_session_id": "old", "duty_zabbix_task_id": "70413"}, TASK_ZABBIX)
        self.assertFalse(ok)
        self.assertEqual(message, DUTY_NOTE_UNBOUND_MESSAGE)

    def test_stale_service_checks_task_from_old_session_blocks_note(self):
        ok, message = duty_note_guard({"enabled": True, "duty_session_id": "new", "duty_service_checks_task_session_id": "old", "duty_service_checks_task_id": "70413"}, TASK_SERVICES)
        self.assertFalse(ok)
        self.assertEqual(message, DUTY_NOTE_UNBOUND_MESSAGE)

    def test_zabbix_task_with_current_session_allows_note(self):
        ok, message = duty_note_guard({"enabled": True, "duty_session_id": "s", "duty_zabbix_task_session_id": "s", "duty_zabbix_task_id": "70413"}, TASK_ZABBIX)
        self.assertTrue(ok)
        self.assertEqual(message, "")

    def test_service_checks_task_with_current_session_allows_note(self):
        ok, message = duty_note_guard({"enabled": True, "duty_session_id": "s", "duty_service_checks_task_session_id": "s", "duty_service_checks_task_url": "https://otrs/?TicketID=70413"}, TASK_SERVICES)
        self.assertTrue(ok)
        self.assertEqual(message, "")

    def test_zabbix_binding_does_not_overwrite_service_checks_binding(self):
        settings = {"duty_session_id": "s", "duty_service_checks_task_id": "svc", "duty_service_checks_task_number": "100"}
        save_task_binding(settings, TASK_ZABBIX, {"id": "70413", "number": "100070490", "url": "u", "system": "otrs"})
        self.assertEqual(settings["duty_service_checks_task_id"], "svc")
        self.assertEqual(settings["duty_service_checks_task_number"], "100")
        self.assertEqual(settings["duty_zabbix_task_session_id"], "s")

    def test_service_checks_binding_does_not_overwrite_zabbix_binding(self):
        settings = {"duty_session_id": "s", "duty_zabbix_task_id": "zbx", "duty_zabbix_task_number": "200"}
        save_task_binding(settings, TASK_SERVICES, {"id": "70414", "number": "100070491", "url": "u", "system": "otrs"})
        self.assertEqual(settings["duty_zabbix_task_id"], "zbx")
        self.assertEqual(settings["duty_zabbix_task_number"], "200")
        self.assertEqual(settings["duty_service_checks_task_session_id"], "s")

    def test_ticket_id_is_not_used_as_visible_task_number_when_h1_exists(self):
        html = """<html><head><title>OTRS</title></head><body><h1>Заявка#100070490 — Проверка Zabbix</h1><a href='index.pl?Action=AgentTicketNote;TicketID=70413'>Note</a></body></html>"""
        self.assertEqual(parse_ticket_number_from_html(html), "100070490")

    def test_h1_zayavka_parses_as_number(self):
        self.assertEqual(parse_ticket_number_from_html("<h1>\n    Заявка#100070490 — Проверка Zabbix (Важных IT-сервисов)\n</h1>"), "100070490")
