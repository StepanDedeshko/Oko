from app.duty_tasks import (
    TASK_SERVICES,
    TASK_ZABBIX,
    bind_duty_task,
    can_send_duty_note,
    current_task_binding,
    get_active_duty_task,
    is_valid_duty_task_binding,
    parse_ticket_url,
    save_task_binding,
    start_new_duty_session,
)
from app.config import migrate_config


def test_start_duty_creates_session_and_clears_old_bindings():
    settings = {"enabled": False, "current_ticket_number": "old", "duty_zabbix_task_id": "70413", "last_zabbix_check_note": "old"}
    start_new_duty_session(settings)
    assert settings["enabled"] is True
    assert settings["duty_session_id"]
    assert settings["current_ticket_number"] == ""
    assert settings["duty_zabbix_task_id"] == ""
    assert settings["last_zabbix_check_note"] == ""


def test_old_current_ticket_is_not_active_zabbix_task():
    settings = {"enabled": True, "duty_session_id": "s", "current_ticket_number": "100", "current_ticket_id": "70413"}
    assert current_task_binding(settings, TASK_ZABBIX)["number"] == ""
    assert get_active_duty_task(settings, TASK_ZABBIX) is None
    ok, reason = can_send_duty_note(settings, TASK_ZABBIX)
    assert not ok
    assert "Задача текущего дежурства не привязана" in reason


def test_binding_is_separate_and_session_scoped():
    settings = {"enabled": True, "duty_session_id": "s"}
    assert bind_duty_task(settings, TASK_ZABBIX, {"number": "1", "id": "10", "url": "u1"})["valid"] is True
    assert bind_duty_task(settings, TASK_SERVICES, {"number": "2", "id": "20", "url": "u2"})["valid"] is True
    assert settings["duty_zabbix_task_id"] == "10"
    assert settings["duty_service_checks_task_id"] == "20"
    assert settings.get("current_ticket_id", "") == ""
    assert get_active_duty_task(settings, TASK_ZABBIX)["active"] is True
    settings["duty_service_checks_task_session_id"] = "old"
    assert get_active_duty_task(settings, TASK_SERVICES) is None


def test_migration_marks_disabled_linked_tasks_stale():
    config = {"duty_mode": {"enabled": False, "duty_zabbix_task_status": "linked", "duty_zabbix_task_id": "70413"}}
    migrated = migrate_config(config)
    duty = migrated["duty_mode"]
    assert duty["duty_legacy_tasks_migrated"] is True
    assert duty["duty_zabbix_task_id"] == ""
    assert duty["duty_legacy_tasks_backup"]["duty_zabbix_task_id"] == "70413"


def test_ticket_id_url_without_task_number_creates_valid_linked_binding():
    settings = {"enabled": True, "duty_session_id": "s"}
    result = bind_duty_task(settings, TASK_ZABBIX, {"id": "70413", "url": "https://otrs/TicketID=70413"})
    assert result["valid"] is True
    assert settings["duty_zabbix_task_status"] == "linked"
    assert settings["duty_zabbix_task_session_id"] == "s"
    assert settings["duty_zabbix_task_number"] == ""
    assert get_active_duty_task(settings, TASK_ZABBIX)["active"] is True
    assert can_send_duty_note(settings, TASK_ZABBIX) == (True, "")


def test_save_task_binding_with_ticket_id_but_no_number_sets_linked():
    settings = {"enabled": True, "duty_session_id": "s"}
    result = save_task_binding(settings, TASK_ZABBIX, parse_ticket_url("https://otrs/index.pl?Action=AgentTicketZoom;TicketID=70413"))
    assert result["valid"] is True
    assert settings["duty_zabbix_task_status"] == "linked"
    assert settings["duty_zabbix_task_number"] == ""
    assert get_active_duty_task(settings, TASK_ZABBIX)["id"] == "70413"


def test_active_task_requires_enabled_linked_session_and_target():
    settings = {"enabled": True, "duty_session_id": "s"}
    bind_duty_task(settings, TASK_ZABBIX, {"number": "100069955", "id": "70413", "url": "u"})
    assert is_valid_duty_task_binding(settings, TASK_ZABBIX) is True
    assert can_send_duty_note(settings, TASK_ZABBIX) == (True, "")
    settings["enabled"] = False
    assert get_active_duty_task(settings, TASK_ZABBIX) is None
    ok, _ = can_send_duty_note(settings, TASK_ZABBIX)
    assert ok is False


def test_migration_keeps_ticket_id_without_number_when_session_is_current():
    config = {"duty_mode": {"enabled": True, "duty_session_id": "s", "duty_zabbix_task_status": "linked", "duty_zabbix_task_id": "70413", "duty_zabbix_task_session_id": "s"}}
    duty = migrate_config(config)["duty_mode"]
    assert duty["duty_zabbix_task_status"] == "linked"
    assert duty["duty_zabbix_task_id"] == "70413"
    assert get_active_duty_task(duty, TASK_ZABBIX)["active"] is True


def test_migration_clears_invalid_linked_with_wrong_session():
    config = {"duty_mode": {"enabled": True, "duty_session_id": "s", "duty_zabbix_task_number": "100", "duty_zabbix_task_status": "linked", "duty_zabbix_task_id": "70413", "duty_zabbix_task_session_id": "old"}}
    duty = migrate_config(config)["duty_mode"]
    assert duty["duty_zabbix_task_status"] == ""
    assert duty["duty_zabbix_task_number"] == ""


def test_manual_number_plus_ticket_id_url_creates_valid_linked_binding():
    settings = {"enabled": True, "duty_session_id": "s"}
    result = bind_duty_task(settings, TASK_ZABBIX, {"number": "100069955", "id": "70413", "url": "https://otrs/TicketID=70413"})
    assert result["valid"] is True
    assert settings["duty_zabbix_task_status"] == "linked"
    assert settings["duty_zabbix_task_session_id"] == "s"
    assert get_active_duty_task(settings, TASK_ZABBIX)["active"] is True


def test_disabled_duty_and_stale_without_session_are_not_active():
    settings = {"enabled": False, "duty_session_id": "s"}
    bind_duty_task(settings, TASK_ZABBIX, {"id": "70413", "url": "u"})
    assert get_active_duty_task(settings, TASK_ZABBIX) is None

    stale = {"enabled": True, "duty_session_id": "s", "duty_zabbix_task_status": "linked", "duty_zabbix_task_id": "70413", "duty_zabbix_task_url": "u", "duty_zabbix_task_session_id": ""}
    assert get_active_duty_task(stale, TASK_ZABBIX) is None


def test_ui_summary_source_shows_ticketid_when_number_empty():
    source = __import__("pathlib").Path("app/duty_mode.py").read_text(encoding="utf-8")
    assert "Привязана по TicketID=" in source
