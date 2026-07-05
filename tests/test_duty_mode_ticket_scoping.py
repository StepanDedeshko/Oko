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
        self.debug_messages = []

    def info(self, message, *args):
        self.messages.append((message, args))

    def debug(self, message, *args):
        self.debug_messages.append((message, args))


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


class FakeDateTime(datetime):
    current = datetime(2026, 7, 5, 20, 15, 0, tzinfo=duty_mode.MSK)

    @classmethod
    def now(cls, tz=None):
        return cls.current


def make_hourly_widget(enabled=True, hourly_notification=True, last_hour_key=None):
    widget = duty_mode.DutyModeWidget.__new__(duty_mode.DutyModeWidget)
    widget.msk_time_label = DummyLabel()
    widget.config = {
        "duty_mode": {
            "enabled": enabled,
            "hourly_notification": hourly_notification,
        }
    }
    widget.last_hour_key = last_hour_key
    widget.logger = DummyLogger()
    notifications = []
    widget.show_notification = notifications.append
    return widget, notifications


def run_tick_at(widget, year=2026, month=7, day=5, hour=20, minute=15, second=0):
    FakeDateTime.current = datetime(year, month, day, hour, minute, second, tzinfo=duty_mode.MSK)
    duty_mode.DutyModeWidget.tick(widget)


def make_toggle_widget(enabled=False):
    widget = duty_mode.DutyModeWidget.__new__(duty_mode.DutyModeWidget)
    widget.config = {
        "duty_mode": {
            "enabled": enabled,
            "hourly_notification": True,
            "check_zabbix_enabled": True,
        }
    }
    widget.last_hour_key = None
    widget._selected_duty_checks = lambda: ["zabbix"]
    widget._ask_duty_check_selection = lambda: True
    widget.update_enable_button = lambda: None
    widget.ask_duty_task_flow_called = False

    def ask_duty_task_flow():
        widget.ask_duty_task_flow_called = True

    widget.ask_duty_task_flow = ask_duty_task_flow
    return widget


def test_enabling_duty_at_2003_marks_current_hour_without_immediate_notification(monkeypatch):
    monkeypatch.setattr(duty_mode, "datetime", FakeDateTime)
    monkeypatch.setattr(duty_mode, "save_config", lambda config: None)
    FakeDateTime.current = datetime(2026, 7, 5, 20, 3, 0, tzinfo=duty_mode.MSK)
    widget = make_toggle_widget(enabled=False)

    duty_mode.DutyModeWidget.toggle_enabled(widget)
    notifications = []
    widget.msk_time_label = DummyLabel()
    widget.logger = DummyLogger()
    widget.show_notification = notifications.append
    run_tick_at(widget, hour=20, minute=3)

    assert widget.config["duty_mode"]["enabled"] is True
    assert widget.ask_duty_task_flow_called is True
    assert widget.last_hour_key == "2026-07-05 20"
    assert notifications == []


def test_enabling_duty_at_2015_marks_current_hour_without_immediate_notification(monkeypatch):
    monkeypatch.setattr(duty_mode, "datetime", FakeDateTime)
    monkeypatch.setattr(duty_mode, "save_config", lambda config: None)
    FakeDateTime.current = datetime(2026, 7, 5, 20, 15, 0, tzinfo=duty_mode.MSK)
    widget = make_toggle_widget(enabled=False)

    duty_mode.DutyModeWidget.toggle_enabled(widget)
    notifications = []
    widget.msk_time_label = DummyLabel()
    widget.logger = DummyLogger()
    widget.show_notification = notifications.append
    run_tick_at(widget, hour=20, minute=15)

    assert widget.last_hour_key == "2026-07-05 20"
    assert notifications == []


def test_first_hourly_notification_after_enabling_is_next_calendar_hour(monkeypatch):
    monkeypatch.setattr(duty_mode, "datetime", FakeDateTime)
    monkeypatch.setattr(duty_mode, "save_config", lambda config: None)
    FakeDateTime.current = datetime(2026, 7, 5, 20, 3, 0, tzinfo=duty_mode.MSK)
    widget = make_toggle_widget(enabled=False)

    duty_mode.DutyModeWidget.toggle_enabled(widget)
    notifications = []
    widget.msk_time_label = DummyLabel()
    widget.logger = DummyLogger()
    widget.show_notification = notifications.append

    run_tick_at(widget, hour=21, minute=0)
    for minute in (1, 2, 3):
        run_tick_at(widget, hour=21, minute=minute)

    assert notifications == ["Нужно произвести проверку графиков."]
    assert widget.last_hour_key == "2026-07-05 21"


def test_hourly_notification_not_shown_in_middle_of_hour(monkeypatch):
    monkeypatch.setattr(duty_mode, "datetime", FakeDateTime)
    widget, notifications = make_hourly_widget()

    run_tick_at(widget, hour=20, minute=15)

    assert notifications == []
    assert widget.last_hour_key is None


def test_hourly_notification_not_shown_before_next_hour(monkeypatch):
    monkeypatch.setattr(duty_mode, "datetime", FakeDateTime)
    widget, notifications = make_hourly_widget()

    run_tick_at(widget, hour=20, minute=59)

    assert notifications == []
    assert widget.last_hour_key is None


def test_hourly_notification_shown_at_calendar_hour_start(monkeypatch):
    monkeypatch.setattr(duty_mode, "datetime", FakeDateTime)
    widget, notifications = make_hourly_widget()

    run_tick_at(widget, hour=21, minute=0)

    assert notifications == ["Нужно произвести проверку графиков."]
    assert widget.last_hour_key == "2026-07-05 21"


def test_hourly_notification_not_repeated_in_same_hour(monkeypatch):
    monkeypatch.setattr(duty_mode, "datetime", FakeDateTime)
    widget, notifications = make_hourly_widget()

    run_tick_at(widget, hour=21, minute=0)
    for minute in (1, 2, 3):
        run_tick_at(widget, hour=21, minute=minute)

    assert notifications == ["Нужно произвести проверку графиков."]
    assert widget.last_hour_key == "2026-07-05 21"


def test_hourly_notification_catch_up_window_shown_once(monkeypatch):
    monkeypatch.setattr(duty_mode, "datetime", FakeDateTime)
    widget, notifications = make_hourly_widget(last_hour_key="2026-07-05 20")

    run_tick_at(widget, hour=21, minute=3)
    run_tick_at(widget, hour=21, minute=4)

    assert notifications == ["Нужно произвести проверку графиков."]
    assert widget.last_hour_key == "2026-07-05 21"


def test_hourly_notification_shown_again_next_hour(monkeypatch):
    monkeypatch.setattr(duty_mode, "datetime", FakeDateTime)
    widget, notifications = make_hourly_widget()

    run_tick_at(widget, hour=21, minute=3)
    run_tick_at(widget, hour=22, minute=0)

    assert notifications == [
        "Нужно произвести проверку графиков.",
        "Нужно произвести проверку графиков.",
    ]
    assert widget.last_hour_key == "2026-07-05 22"


def test_hourly_notification_not_shown_when_duty_disabled(monkeypatch):
    monkeypatch.setattr(duty_mode, "datetime", FakeDateTime)
    widget, notifications = make_hourly_widget(enabled=False)

    run_tick_at(widget, hour=21, minute=0)

    assert notifications == []
    assert widget.last_hour_key is None


def test_hourly_notification_not_shown_when_hourly_disabled(monkeypatch):
    monkeypatch.setattr(duty_mode, "datetime", FakeDateTime)
    widget, notifications = make_hourly_widget(hourly_notification=False)

    run_tick_at(widget, hour=21, minute=0)

    assert notifications == []
    assert widget.last_hour_key is None
