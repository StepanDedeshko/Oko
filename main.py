#!/usr/bin/env python3
import sys
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.config import ensure_config_exists, load_config
from app.config_migrator import patch_config_file
from app.jabka_duty_note_fix import install_jabka_duty_note_fix
from app.jabka_embedded_assets import apply_jabka_icon_to_widget, install_jabka_embedded_assets
from app.jabka_notification_sounds import install_jabbix_notification_sounds
from app.jabka_page_polish import apply_jabka_page_polish
from app.jabka_theme import (
    apply_jabka_runtime,
    apply_jabka_widget_tree,
    install_jabka_theme,
)
from app.login_dialog import LoginDialog
from app.main_window import MainWindow
from app.splash import ThemeSplash
from app.loading_screen import LoadingScreen
from app.screen_utils import screen_under_cursor, screen_for_widget, center_widget_on_screen, geometry_dict
from app.theme import apply_theme
from app.app_info import APP_NAME, APP_VERSION
from app.logger import get_logger


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
    logger = get_logger()
    app_root = Path(__file__).resolve().parent
    config_path = app_root / "config.json"
    logger.info("Запуск приложения")
    logger.info("APP_VERSION=%s", APP_VERSION)
    logger.info("Путь приложения: %s", app_root)
    logger.info("Путь config.json: %s", config_path)

    # Регистрируем дополнительные темы до построения любых UI-экранов.
    # Это не меняет пользовательские данные и не трогает рабочую логику.
    install_jabka_theme()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("oko")

    default_icon_path = Path(__file__).resolve().parent / "assets" / "dezhurka_icon.png"
    icon_path = default_icon_path

    ensure_config_exists()
    patch_config_file()
    config = load_config()

    jabka_icon_path = apply_jabka_runtime(config, app)
    install_jabbix_notification_sounds(config)
    if jabka_icon_path is not None:
        icon_path = jabka_icon_path

    jabka_icon = install_jabka_embedded_assets(config, app)
    if jabka_icon is None and icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    apply_theme(app, config.get("settings", {}).get("theme", "mass_effect"))

    startup_screen = screen_under_cursor()

    splash = ThemeSplash(config=config, preferred_screen=startup_screen)
    if jabka_icon is not None:
        apply_jabka_icon_to_widget(splash, jabka_icon)
    elif icon_path.exists():
        splash.setWindowIcon(QIcon(str(icon_path)))
    splash.show()
    app.processEvents()
    splash.wait_minimum(1400)
    splash.close()
    app.processEvents()

    login_dialog = LoginDialog(config, preferred_screen=startup_screen)
    if jabka_icon is not None:
        apply_jabka_icon_to_widget(login_dialog, jabka_icon)
    elif icon_path.exists():
        login_dialog.setWindowIcon(QIcon(str(icon_path)))

    if login_dialog.exec() != LoginDialog.Accepted:
        sys.exit(0)

    login_screen = screen_for_widget(login_dialog)
    config['_startup_screen_geometry'] = geometry_dict(login_screen)

    window = MainWindow(config=config, credentials=login_dialog.credentials)

    if jabka_icon is not None:
        apply_jabka_icon_to_widget(window, jabka_icon)
    elif icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    apply_jabka_widget_tree(window, config)
    apply_jabka_page_polish(window, config)
    install_jabka_duty_note_fix(window, config)

    center_widget_on_screen(window, login_screen)
    window.show()

    def startup_update_check():
        try:
            home = getattr(window, "home_page_widget", None)
            if home is None:
                return
            settings = config.get("settings", {})
            if settings.get("check_updates_on_startup", True):
                home.check_for_updates(interactive=False, auto_start_install=True)
        except Exception:
            logger.exception("Не удалось проверить обновления при запуске")

    QTimer.singleShot(1500, startup_update_check)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
