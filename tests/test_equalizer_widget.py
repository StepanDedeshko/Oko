import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from app.equalizer_widget import EqualizerWidget
    PYSIDE_ERROR = None
except ImportError as exc:
    QApplication = None
    EqualizerWidget = None
    PYSIDE_ERROR = exc


@unittest.skipIf(PYSIDE_ERROR is not None, f"PySide6 GUI dependencies unavailable: {PYSIDE_ERROR}")
class EqualizerWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_bar_count_clamped(self):
        widget = EqualizerWidget(bar_count=1)
        self.assertEqual(widget.bar_count, 4)
        widget.set_bar_count(500)
        self.assertEqual(widget.bar_count, 96)

    def test_levels_are_clamped_and_resized(self):
        widget = EqualizerWidget(bar_count=4)
        widget.set_levels([-1, 0.5, 2])
        self.assertEqual(len(widget._levels), 4)
        self.assertTrue(all(0 <= level <= 1 for level in widget._levels))

    def test_invalid_mode_is_safe_and_timer_methods_do_not_crash(self):
        widget = EqualizerWidget(mode="broken")
        self.assertEqual(widget.mode, "auto")
        widget.set_mode("bad")
        self.assertEqual(widget.mode, "auto")
        widget.start()
        widget.stop()


if __name__ == "__main__":
    unittest.main()
