import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QAbstractItemView, QTableWidget
from shiboken6 import isValid

from app.jabka_live_zabbix_performance import install_jabka_live_zabbix_performance_fix
import app.jabka_live_zabbix_polish as polish


_APP = QApplication.instance() or QApplication([])


class _DummyLiveWidget:
    def __init__(self):
        self.config = {"settings": {"theme": "jabka"}}
        self.table = QTableWidget(20, 9)
        self.table.setObjectName("LiveZabbixProblemsTable")


def test_performance_fix_keeps_design_and_uses_row_scroll_mode():
    install_jabka_live_zabbix_performance_fix()
    widget = _DummyLiveWidget()

    assert polish.apply_jabka_live_table_polish(widget) is True
    assert isinstance(widget.table.itemDelegate(), polish.JabkaProblemRowDelegate)
    assert widget.table.verticalScrollMode() == QAbstractItemView.ScrollMode.ScrollPerItem
    assert widget.table.showGrid() is False
    assert widget.table.property("jabka_problem_table_polished") is True


def test_performance_fix_is_idempotent():
    assert install_jabka_live_zabbix_performance_fix() is False
    assert polish.JabkaProblemRowDelegate._performance_fix_installed is True


def test_event_filter_ignores_table_after_qt_deletes_it():
    widget = _DummyLiveWidget()
    assert polish.apply_jabka_live_table_polish(widget) is True

    table = widget.table
    delegate = table.itemDelegate()
    table.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    _APP.processEvents()

    assert isValid(table) is False
    assert delegate.eventFilter(object(), QEvent(QEvent.Type.Leave)) is False


def test_optimized_source_does_not_repaint_the_whole_viewport_on_hover():
    source = (Path(__file__).resolve().parents[1] / "app" / "jabka_live_zabbix_performance.py").read_text(encoding="utf-8")

    assert "viewport.update(rect)" in source
    assert "viewport().update()" not in source
    assert "if first or last:" in source
    assert "painter.fillRect(rect, background)" in source
    assert "ScrollPerItem" in source
    assert "isValid(table)" in source
    assert "super(self.__class__, self).eventFilter" not in source


def test_main_installs_performance_fix_before_main_window():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert "install_jabka_live_zabbix_performance_fix()" in source
    assert source.index("install_jabka_live_zabbix_polish()") < source.index("install_jabka_live_zabbix_performance_fix()")
    assert source.index("install_jabka_live_zabbix_performance_fix()") < source.index("window = MainWindow")
