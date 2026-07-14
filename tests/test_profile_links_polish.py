import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import app.home_config as home_config
from app.profile_links_polish import install_profile_links_polish


class ProfileLinksPolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        install_profile_links_polish()

    def test_patch_hides_profile_login_url_widgets(self):
        source = Path("app/profile_links_polish.py").read_text(encoding="utf-8")
        self.assertIn('field.hide()', source)
        self.assertIn('label.hide()', source)
        self.assertIn('live.get("redmine_login_url")', source)
        self.assertIn('field.setText(current_url)', source)

    def test_main_installs_patch_before_window(self):
        source = Path("main.py").read_text(encoding="utf-8")
        self.assertIn("install_profile_links_polish()", source)
        self.assertLess(
            source.index("install_profile_links_polish()"),
            source.index("window = MainWindow"),
        )


if __name__ == "__main__":
    unittest.main()
