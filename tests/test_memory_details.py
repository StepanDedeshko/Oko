from types import SimpleNamespace
from unittest import mock

import psutil

from app.memory_details import collect_memory_summary, collect_top_memory_processes


class Proc:
    def __init__(self, pid, name, rss, error=False):
        self.pid = pid
        self.info = {"pid": pid, "name": name}
        self._rss = rss
        self._error = error
    def memory_info(self):
        if self._error:
            raise psutil.AccessDenied(pid=self.pid)
        return SimpleNamespace(rss=self._rss)


def test_collect_memory_summary_returns_data():
    with mock.patch("app.memory_details.psutil.virtual_memory", return_value=SimpleNamespace(total=10, used=7, available=3, percent=70)):
        assert collect_memory_summary()["percent"] == 70


def test_top_processes_groups_sorts_and_ignores_access_denied():
    procs = [Proc(1, "chrome", 100), Proc(2, "chrome", 50), Proc(3, "bad", 999, True), Proc(4, "python3", 75)]
    with mock.patch("app.memory_details.psutil.process_iter", return_value=procs):
        rows = collect_top_memory_processes(limit=2, current_pid=4)
    assert rows[0]["name"] == "chrome"
    assert rows[0]["rss"] == 150
    assert rows[0]["count"] == 2
    assert rows[1]["is_current_app"] is True
