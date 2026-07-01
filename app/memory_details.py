import os
from collections import defaultdict

import psutil


PROCESS_ERRORS = (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess)


def format_bytes(value):
    value = float(value or 0)
    units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "Б" else f"{value:.0f} {unit}"
        value /= 1024


def collect_memory_summary():
    vm = psutil.virtual_memory()
    return {"total": vm.total, "used": vm.used, "available": vm.available, "percent": vm.percent}


def collect_top_memory_processes(limit=5, current_pid=None):
    current_pid = os.getpid() if current_pid is None else current_pid
    grouped = defaultdict(lambda: {"name": "", "rss": 0, "count": 0, "is_current_app": False})
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            info = proc.info or {}
            name = str(info.get("name") or "process")
            rss = int(proc.memory_info().rss or 0)
            pid = int(info.get("pid") or proc.pid)
        except PROCESS_ERRORS:
            continue
        bucket = grouped[name]
        bucket["name"] = name
        bucket["rss"] += rss
        bucket["count"] += 1
        if pid == current_pid:
            bucket["is_current_app"] = True
            bucket["name"] = f"oko / {name}"
    rows = sorted(grouped.values(), key=lambda item: item["rss"], reverse=True)
    return rows[:limit]
