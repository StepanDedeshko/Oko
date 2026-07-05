from datetime import datetime

import pytest

duty_mode = pytest.importorskip("app.duty_mode", exc_type=ImportError)


class DummyLineEdit:
    def __init__(self):
        self.value = ""

    def setText(self, value):
        self.value = value

    def text(self):
        return self.value


class DummyLabel:
    def __init__(self):
        self.value = ""

    def setText(self, value):
        self.value = value


class DummyLogger:
    def __init__(self):
        self.messages = []

    def info(self, message, *args):
        self.messages.append((message, args))


def make_note_dialog(config, task_type):
    dialog = duty_mode.OtrsNoteDialog.__new__(duty_mode.OtrsNoteDialog)
    dialog.config = config
    dialog.task_type = task_type
    dialog.url_input = DummyLineEdit()
    dialog.info_label = DummyLabel()
    return dialog


def test_otrs_note_dialog_keeps_service_and_zabbix_ticket_scope_separate(monkeypatch):
    monkeypatch.setattr(duty_mode, "save_config", lambda config: None)
    config = {
        "duty_mode": {
            "current_ticket_id": "B",
            "current_ticket_url": "https://otrs.example/?Action=AgentTicketZoom;TicketID=B",
            "current_ticket_number": "200",
            "duty_zabbix_task_id": "B",
            "duty_zabbix_task_url": "https://otrs.example/?Action=AgentTicketZoom;TicketID=B",
            "duty_zabbix_task_number": "200",
            "duty_service_checks_task_id": "A",
            "duty_service_checks_task_url": "https://otrs.example/?Action=AgentTicketZoom;TicketID=A",
            "duty_service_checks_task_number": "100",
        }
    }

    service_dialog = make_note_dialog(config, "service_checks")
    assert service_dialog.get_ticket_id() == "A"
    assert service_dialog.get_task_number() == "100"

    assert service_dialog.save_ticket_id_from_url("https://otrs.example/?Action=AgentTicketNote;TicketID=A2")
    service_dialog.after_detect_ticket_title({"title": "Заявка#101", "ticketNumber": "101"})

    settings = config["duty_mode"]
    assert settings["duty_service_checks_task_id"] == "A2"
    assert settings["duty_service_checks_task_number"] == "101"
    assert settings["duty_zabbix_task_id"] == "B"
    assert settings["duty_zabbix_task_number"] == "200"
    assert settings["current_ticket_id"] == "B"
    assert settings["current_ticket_number"] == "200"

    zabbix_dialog = make_note_dialog(config, "zabbix")
    assert zabbix_dialog.get_ticket_id() == "B"
    assert zabbix_dialog.get_task_number() == "200"


def test_open_graph_check_note_uses_zabbix_ticket_not_service_ticket(monkeypatch):
    captured = {}

    class FakeDialog:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.url_input = DummyLineEdit()
            self.url_input.setText(kwargs.get("initial_note_url", ""))

        def get_ticket_id(self):
            return "B"

        def exec(self):
            captured["exec_called"] = True

    config = {
        "duty_mode": {
            "duty_service_checks_task_id": "A",
            "duty_service_checks_task_url": "https://otrs.example/?Action=AgentTicketZoom;TicketID=A",
            "duty_zabbix_task_id": "B",
            "duty_zabbix_task_url": "https://otrs.example/?Action=AgentTicketZoom;TicketID=B",
        }
    }
    widget = duty_mode.DutyModeWidget.__new__(duty_mode.DutyModeWidget)
    widget.config = config
    widget.logger = DummyLogger()
    widget.graph_check_overlay = None
    widget.selected_zabbix_problems_for_note = []
    widget.build_graph_check_note_text = lambda: "note text"

    monkeypatch.setattr(duty_mode, "OtrsNoteDialog", FakeDialog)
    duty_mode.DutyModeWidget.open_graph_check_note(widget)

    assert captured["task_type"] == "zabbix"
    assert captured["initial_note_url"].endswith("TicketID=B")
    assert "TicketID=A" not in captured["initial_note_url"]
    assert captured["exec_called"] is True


def test_hourly_notification_shown_once_when_timer_runs_in_first_five_minutes(monkeypatch):
    class FakeDateTime(datetime):
        current = datetime(2026, 7, 5, 10, 1, 30, tzinfo=duty_mode.MSK)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    widget = duty_mode.DutyModeWidget.__new__(duty_mode.DutyModeWidget)
    widget.msk_time_label = DummyLabel()
    widget.config = {"duty_mode": {"enabled": True, "hourly_notification": True}}
    widget.last_hour_key = None
    widget.logger = DummyLogger()
    notifications = []
    widget.show_notification = notifications.append

    monkeypatch.setattr(duty_mode, "datetime", FakeDateTime)

    for minute in (1, 2, 3):
        FakeDateTime.current = datetime(2026, 7, 5, 10, minute, 30, tzinfo=duty_mode.MSK)
        duty_mode.DutyModeWidget.tick(widget)

    assert notifications == ["Нужно произвести проверку графиков."]
    assert widget.last_hour_key == "2026-07-05 10"
