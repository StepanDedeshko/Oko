#!/usr/bin/env python3
import sys
from PySide6.QtCore import QEventLoop, QTimer
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.config import load_config
from app.config_migrator import patch_config_file
from app.login_dialog import LoginDialog
from app.main_window import MainWindow
from app.splash import ThemeSplash
from app.loading_screen import LoadingScreen
from app.screen_utils import screen_under_cursor, screen_for_widget, center_widget_on_screen, geometry_dict
from app.theme import apply_theme
from app.app_info import APP_NAME

def show_start_loading(config):
    loading_config = config.get("loading_screen", {})
    if not loading_config.get("enabled", True):
        return

    if not loading_config.get("show_after_login", True):
        return

    duration_ms = int(loading_config.get("duration_ms", 7000))
    duration_ms = max(1000, duration_ms)

    screen = LoadingScreen(config)
    screen.show()
    screen.start_media()

    loop = QEventLoop()

    def finish():
        screen.stop_media()
        screen.close()
        loop.quit()

    QTimer.singleShot(duration_ms, finish)
    loop.exec()



def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("oko")

    icon_path = Path(__file__).resolve().parent / "assets" / "dezhurka_icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    patch_config_file()
    config = load_config()
    apply_theme(app, config.get("settings", {}).get("theme", "mass_effect"))

    startup_screen = screen_under_cursor()

    splash = ThemeSplash(config=config, preferred_screen=startup_screen)
    splash.show()
    app.processEvents()
    splash.wait_minimum(1400)

    login_dialog = LoginDialog(config, preferred_screen=startup_screen)
    if icon_path.exists():
        login_dialog.setWindowIcon(QIcon(str(icon_path)))

    if login_dialog.exec() != LoginDialog.Accepted:
        sys.exit(0)

    login_screen = screen_for_widget(login_dialog)
    config['_startup_screen_geometry'] = geometry_dict(login_screen)

    window = MainWindow(config=config, credentials=login_dialog.credentials)

    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))

    center_widget_on_screen(window, login_screen)
    window.show()
    splash.close()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
