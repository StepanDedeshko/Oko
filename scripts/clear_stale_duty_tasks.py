#!/usr/bin/env python3
"""Clear stale duty task bindings from config.json without touching credentials."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
CONFIG_CANDIDATES = [Path.cwd() / "config.json", ROOT / "config.json", Path.home() / "Monitor" / "config.json"]
FIELDS = [
    "current_ticket_number", "current_ticket_id", "current_ticket_url",
    "duty_zabbix_task_number", "duty_zabbix_task_id", "duty_zabbix_task_url",
    "duty_zabbix_task_system", "duty_zabbix_task_status", "duty_zabbix_task_linked_at", "duty_zabbix_task_session_id",
    "duty_service_checks_task_number", "duty_service_checks_task_id", "duty_service_checks_task_url",
    "duty_service_checks_task_system", "duty_service_checks_task_status", "duty_service_checks_task_linked_at", "duty_service_checks_task_session_id",
    "last_service_check_note", "last_zabbix_check_note", "last_service_check_time", "last_zabbix_check_time",
]

def find_config() -> Path:
    for path in CONFIG_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("config.json не найден")

def main() -> int:
    path = find_config()
    data = json.loads(path.read_text(encoding="utf-8"))
    duty = data.setdefault("duty_mode", {})
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"config.backup_before_clear_stale_tasks_{timestamp}.json")
    shutil.copy2(path, backup)
    old = {}
    cleared = []
    for key in FIELDS:
        old[key] = duty.get(key, "")
        if duty.get(key, "") != "":
            cleared.append(key)
        duty[key] = ""
    duty["enabled"] = False
    duty["duty_legacy_tasks_migrated"] = True
    duty["duty_legacy_tasks_detected_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    duty["duty_legacy_tasks_backup"] = old
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Backup: {backup}")
    print("Очищенные поля:")
    for key in cleared:
        print(f"- {key}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
