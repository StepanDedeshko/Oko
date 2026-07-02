import unittest
from copy import deepcopy

from app.config import ensure_duty_mode_defaults


class DutyModeV033MigrationGuardTests(unittest.TestCase):
    def apply_defaults(self, duty_mode, extra=None):
        config = {"duty_mode": deepcopy(duty_mode)}
        if extra:
            config.update(deepcopy(extra))
        ensure_duty_mode_defaults(config)
        return config

    def test_broken_ticket_id_only_zabbix_binding_is_cleared(self):
        config = self.apply_defaults({
            "current_ticket_number": "",
            "current_ticket_id": "70400",
            "current_ticket_url": "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketZoom;TicketID=70400",
            "duty_zabbix_task_number": "",
            "duty_zabbix_task_id": "70400",
            "duty_zabbix_task_url": "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketZoom;TicketID=70400",
        })

        duty = config["duty_mode"]
        self.assertEqual(duty["current_ticket_id"], "")
        self.assertEqual(duty["current_ticket_url"], "")
        self.assertEqual(duty["duty_zabbix_task_id"], "")
        self.assertEqual(duty["duty_zabbix_task_url"], "")

    def test_valid_zabbix_binding_with_number_is_preserved(self):
        config = self.apply_defaults({
            "current_ticket_number": "123456",
            "current_ticket_id": "70400",
            "current_ticket_url": "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketZoom;TicketID=70400",
            "duty_zabbix_task_number": "123456",
            "duty_zabbix_task_id": "70400",
            "duty_zabbix_task_url": "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketZoom;TicketID=70400",
        })

        duty = config["duty_mode"]
        self.assertEqual(duty["current_ticket_id"], "70400")
        self.assertEqual(duty["current_ticket_url"], "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketZoom;TicketID=70400")
        self.assertEqual(duty["duty_zabbix_task_id"], "70400")
        self.assertEqual(duty["duty_zabbix_task_url"], "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketZoom;TicketID=70400")

    def test_broken_service_checks_ticket_id_only_binding_is_cleared(self):
        config = self.apply_defaults({
            "duty_service_checks_task_number": "",
            "duty_service_checks_task_id": "70401",
            "duty_service_checks_task_url": "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketZoom;TicketID=70401",
        })

        duty = config["duty_mode"]
        self.assertEqual(duty["duty_service_checks_task_id"], "")
        self.assertEqual(duty["duty_service_checks_task_url"], "")

    def test_valid_service_checks_binding_with_number_is_preserved(self):
        config = self.apply_defaults({
            "duty_service_checks_task_number": "123457",
            "duty_service_checks_task_id": "70401",
            "duty_service_checks_task_url": "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketZoom;TicketID=70401",
        })

        duty = config["duty_mode"]
        self.assertEqual(duty["duty_service_checks_task_id"], "70401")
        self.assertEqual(duty["duty_service_checks_task_url"], "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketZoom;TicketID=70401")

    def test_unrelated_user_data_is_preserved(self):
        config = self.apply_defaults(
            {
                "current_ticket_number": "",
                "current_ticket_id": "70400",
                "current_ticket_url": "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketZoom;TicketID=70400",
                "duty_zabbix_task_number": "",
                "duty_zabbix_task_id": "70400",
                "duty_zabbix_task_url": "https://itsm.stdpr.ru/itsm/index.pl?Action=AgentTicketZoom;TicketID=70400",
                "otrs_login": "operator",
                "otrs_password": "secret",
            },
            {
                "settings": {"theme": "mass_effect"},
                "profiles": {"active": "main"},
                "users": [{"name": "Stepan"}],
                "credentials": {"token": "keep"},
                "products": [{"name": "FacePay", "pages": []}],
                "zabbix_instances": [{"name": "Zabbix", "url": "https://zabbix"}],
            },
        )

        self.assertEqual(config["duty_mode"]["otrs_login"], "operator")
        self.assertEqual(config["duty_mode"]["otrs_password"], "secret")
        self.assertEqual(config["settings"]["theme"], "mass_effect")
        self.assertEqual(config["profiles"]["active"], "main")
        self.assertEqual(config["users"][0]["name"], "Stepan")
        self.assertEqual(config["credentials"]["token"], "keep")
        self.assertEqual(config["products"][0]["name"], "FacePay")
        self.assertEqual(config["zabbix_instances"][0]["url"], "https://zabbix")


if __name__ == "__main__":
    unittest.main()
