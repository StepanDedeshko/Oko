import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTableWidget

from app.jabka_live_zabbix_polish import (
    JABKA_GLOBAL_CONTRAST_QSS,
    JABKA_LIVE_TABLE_QSS,
    JabkaProblemRowDelegate,
    apply_jabka_global_contrast,
    apply_jabka_live_table_polish,
)


_APP = QApplication.instance() or QApplication([])


class _DummyLiveWidget:
    def __init__(self, theme="jabka"):
        self.config = {"settings": {"theme": theme}}
        self.table = QTableWidget(2, 9)
        self.table.setObjectName("LiveZabbixProblemsTable")


def test_jabka_problem_table_gets_card_delegate_and_contrast_styles():
    widget = _DummyLiveWidget()

    assert apply_jabka_live_table_polish(widget) is True
    assert isinstance(widget.table.itemDelegate(), JabkaProblemRowDelegate)
    assert widget.table.showGrid() is False
    assert widget.table.alternatingRowColors() is False
    assert widget.table.verticalHeader().defaultSectionSize() == 44
    assert widget.table.horizontalHeader().minimumHeight() == 38
    assert "selection-background-color: transparent" in widget.table.styleSheet()
    assert "border-radius: 18px" in widget.table.styleSheet()
    assert "QToolTip" not in widget.table.styleSheet()
    assert widget.table.property("jabka_problem_table_polished") is True

    # Applying twice must not stack delegates or styles.
    delegate = widget.table.itemDelegate()
    assert apply_jabka_live_table_polish(widget) is False
    assert widget.table.itemDelegate() is delegate


def test_other_themes_keep_the_original_table():
    widget = _DummyLiveWidget(theme="mass_effect")

    assert apply_jabka_live_table_polish(widget) is False
    assert not isinstance(widget.table.itemDelegate(), JabkaProblemRowDelegate)
    assert widget.table.property("jabka_problem_table_polished") is None


def test_jabka_global_tooltip_and_selection_contrast_is_appended_once():
    config = {"settings": {"theme": "jabka"}}
    old_style = _APP.styleSheet()
    old_property = _APP.property("jabka_global_contrast_applied")
    try:
        _APP.setProperty("jabka_global_contrast_applied", False)
        _APP.setStyleSheet("QWidget { color: #ffffff; }")

        assert apply_jabka_global_contrast(_APP, config) is True
        style = _APP.styleSheet()
        assert "QToolTip" in style
        assert "background-color: #102818" in style
        assert "selection-background-color: #B7F27A" in style
        assert apply_jabka_global_contrast(_APP, config) is False
    finally:
        _APP.setStyleSheet(old_style)
        _APP.setProperty("jabka_global_contrast_applied", old_property)


def test_main_installs_table_polish_before_main_window_and_contrast_after_theme():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert "install_jabka_live_zabbix_polish()" in source
    assert "apply_jabka_global_contrast(app, config)" in source
    assert source.index("install_jabka_live_zabbix_polish()") < source.index("window = MainWindow")
    assert source.index("apply_theme(app") < source.index("apply_jabka_global_contrast(app, config)")


def test_exported_qss_keeps_readable_selection_and_rounded_table_shell():
    assert "QToolTip" in JABKA_GLOBAL_CONTRAST_QSS
    assert "selection-color: #07140D" in JABKA_GLOBAL_CONTRAST_QSS
    assert "QTableWidget#LiveZabbixProblemsTable" in JABKA_LIVE_TABLE_QSS
    assert "border-radius: 18px" in JABKA_LIVE_TABLE_QSS
    assert "gridline-color: transparent" in JABKA_LIVE_TABLE_QSS
