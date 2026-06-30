import unittest
from pathlib import Path


class ThemeNextgenStylesTests(unittest.TestCase):
    def test_dark_white_tooltip_menu_dialog_styles_are_theme_aware(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "theme.py").read_text(encoding="utf-8")
        self.assertIn('if theme_name not in {"white_1", "dark_1"}', source)
        self.assertIn("QToolTip, QMenu", source)
        self.assertIn("QMenu::item:selected", source)
        self.assertIn('QDialog, QWidget[windowType="tool"]', source)
        self.assertIn("background-color: {p['bg_field']}", source)
        self.assertIn("color: {p['text_title']}", source)
        self.assertIn("border: 1px solid {p['border_dark']}", source)


if __name__ == "__main__":
    unittest.main()
