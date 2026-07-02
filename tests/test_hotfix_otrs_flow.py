import unittest
from pathlib import Path

from app.duty_tasks import (
    TASK_SERVICES,
    TASK_ZABBIX,
    current_task_binding,
    extract_otrs_ticket_number_from_text,
    has_current_task,
    reset_duty_task_bindings_for_new_session,
    save_task_binding,
)


class HotfixOtrsFlowTests(unittest.TestCase):
    def test_start_duty_clears_current_ticket_fields(self):
        settings = {
            "current_ticket_number": "100070490",
            "current_ticket_id": "70413",
            "current_ticket_url": "https://itsm/itsm/index.pl?Action=AgentTicketZoom;TicketID=70413",
            "duty_session_id": "old",
        }
        reset_duty_task_bindings_for_new_session(settings)
        self.assertEqual(settings["current_ticket_number"], "")
        self.assertEqual(settings["current_ticket_id"], "")
        self.assertEqual(settings["current_ticket_url"], "")
        self.assertTrue(settings["duty_session_id"])
        self.assertNotEqual(settings["duty_session_id"], "old")

    def test_start_duty_clears_duty_task_fields(self):
        settings = {
            "duty_zabbix_task_number": "100070490",
            "duty_zabbix_task_id": "70413",
            "duty_zabbix_task_url": "https://itsm/?TicketID=70413",
            "duty_service_checks_task_number": "100070491",
            "duty_service_checks_task_id": "70414",
            "duty_service_checks_task_url": "https://itsm/?TicketID=70414",
        }
        reset_duty_task_bindings_for_new_session(settings)
        for prefix in ("duty_zabbix_task", "duty_service_checks_task"):
            self.assertEqual(settings[f"{prefix}_number"], "")
            self.assertEqual(settings[f"{prefix}_id"], "")
            self.assertEqual(settings[f"{prefix}_url"], "")

    def test_ticket_id_only_binding_is_current_task(self):
        settings = {}
        save_task_binding(settings, TASK_ZABBIX, {"system": "otrs", "id": "70413", "url": "https://itsm/?TicketID=70413", "number": ""})
        self.assertTrue(has_current_task(settings, TASK_ZABBIX))
        self.assertEqual(current_task_binding(settings, TASK_ZABBIX)["id"], "70413")
        self.assertEqual(current_task_binding(settings, TASK_ZABBIX)["number"], "")

    def test_empty_task_number_does_not_disable_note_when_ticket_id_exists(self):
        settings = {"current_ticket_id": "70413", "current_ticket_number": ""}
        self.assertTrue(has_current_task(settings, TASK_ZABBIX))
        self.assertEqual(current_task_binding(settings, TASK_ZABBIX)["id"], "70413")

    def test_current_ticket_id_fallback_still_works_for_zabbix_note(self):
        settings = {"current_ticket_id": "70413"}
        self.assertEqual(current_task_binding(settings, TASK_ZABBIX)["id"], "70413")

    def test_duty_zabbix_task_id_works_for_zabbix_note(self):
        settings = {"duty_zabbix_task_id": "70413"}
        self.assertEqual(current_task_binding(settings, TASK_ZABBIX)["id"], "70413")

    def test_service_checks_task_id_works_for_service_note(self):
        settings = {"duty_service_checks_task_id": "70414"}
        self.assertTrue(has_current_task(settings, TASK_SERVICES))
        self.assertEqual(current_task_binding(settings, TASK_SERVICES)["id"], "70414")

    def test_h1_ticket_number_saved_without_clearing_ticket_id_contract(self):
        settings = {"current_ticket_id": "70413", "duty_zabbix_task_id": "70413"}
        number = extract_otrs_ticket_number_from_text("Заявка#100070490")
        settings["current_ticket_number"] = number
        settings["duty_zabbix_task_number"] = number
        self.assertEqual(settings["current_ticket_number"], "100070490")
        self.assertEqual(settings["current_ticket_id"], "70413")
        self.assertEqual(settings["duty_zabbix_task_id"], "70413")

    def test_title_ticket_number_pattern(self):
        self.assertEqual(
            extract_otrs_ticket_number_from_text("", "", "100070490 - Подробно - Заявки - Service Desk", ""),
            "100070490",
        )

    def test_redmine_helpers_untouched(self):
        source = Path("app/live_zabbix_widget.py").read_text(encoding="utf-8")
        for needle in ("def _build_redmine_open_url", "class RedmineCreateDialog", "class RedmineAuthorizationDialog"):
            self.assertIn(needle, source)


if __name__ == "__main__":
    unittest.main()
