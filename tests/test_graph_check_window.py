from pathlib import Path

DUTY_SOURCE = Path("app/duty_mode.py").read_text(encoding="utf-8")
UTIL_SOURCE = Path("app/graph_window_utils.py").read_text(encoding="utf-8")


def test_graph_check_dialog_applies_resizable_window_helper():
    dialog_source = DUTY_SOURCE.split("class GraphCheckOverlayDialog", 1)[1].split("class DutySettingsDialog", 1)[0]
    assert "apply_resizable_graph_window(self" in dialog_source
    assert "install_maximize_shortcut" in dialog_source
    assert "Qt.Key_F11" in dialog_source


def test_graph_window_helper_sets_maximize_flags_and_size_grip():
    assert "Qt.WindowMaximizeButtonHint" in UTIL_SOURCE
    assert "Qt.WindowMinimizeButtonHint" in UTIL_SOURCE
    assert "Qt.WindowCloseButtonHint" in UTIL_SOURCE
    assert "setSizeGripEnabled(True)" in UTIL_SOURCE
    assert "setMinimumSize" in UTIL_SOURCE
