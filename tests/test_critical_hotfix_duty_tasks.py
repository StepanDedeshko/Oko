from app.duty_tasks import (
    TASK_SERVICES,
    TASK_ZABBIX,
    bind_duty_task,
    can_send_duty_note,
    current_task_binding,
    get_active_duty_task,
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
    ok, reason = can_send_duty_note(settings, TASK_ZABBIX)
    assert not ok
    assert "Задача текущего дежурства не привязана" in reason


def test_binding_is_separate_and_session_scoped():
    settings = {"enabled": True, "duty_session_id": "s"}
    bind_duty_task(settings, TASK_ZABBIX, {"number": "1", "id": "10", "url": "u1"})
    bind_duty_task(settings, TASK_SERVICES, {"number": "2", "id": "20", "url": "u2"})
    assert settings["duty_zabbix_task_id"] == "10"
    assert settings["duty_service_checks_task_id"] == "20"
    assert settings.get("current_ticket_id", "") == ""
    assert get_active_duty_task(settings, TASK_ZABBIX)["active"] is True
    settings["duty_service_checks_task_session_id"] = "old"
    assert get_active_duty_task(settings, TASK_SERVICES)["active"] is False


def test_migration_marks_disabled_linked_tasks_stale():
    config = {"duty_mode": {"enabled": False, "duty_zabbix_task_status": "linked", "duty_zabbix_task_id": "70413"}}
    migrated = migrate_config(config)
    duty = migrated["duty_mode"]
    assert duty["duty_legacy_tasks_migrated"] is True
    assert duty["duty_zabbix_task_id"] == ""
    assert duty["duty_legacy_tasks_backup"]["duty_zabbix_task_id"] == "70413"
