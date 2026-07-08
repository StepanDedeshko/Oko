from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


JABKA_THEME_NAME = "jabka"
JABKA_APP_NAME = "Jabbix"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

JABKA_THEME = {
    "label": "Жабка",
    "bg_main": "#07140D",
    "bg_panel": "#0B1F13",
    "bg_panel2": "#102818",
    "bg_card": "#12331F",
    "bg_card2": "#1B4A2B",
    "bg_field": "#08160D",
    "text": "#EAF8D8",
    "text_soft": "#A9C89C",
    "text_title": "#F1FFE0",
    "accent": "#8FE388",
    "accent2": "#B7F27A",
    "danger": "#FFB84D",
    "danger_bg": "#2F1D08",
    "success": "#7DFF9A",
    "success_bg": "#0E2B16",
    "scroll": "#2D7D3A",
    "selected": "#214F2B",
    "hud_text": "#D6EFC3",
    "border_dark": "#66B95B",
    "glass": "rgba(10, 34, 20, 0.86)",
    "glass2": "rgba(17, 50, 29, 0.78)",
    "overlay": "rgba(7, 20, 13, 0.94)",
    "shadow": "#031008",
}

TEXT_OVERRIDES = {
    "Око": JABKA_APP_NAME,
    "ДЕЖУРКА": JABKA_APP_NAME.upper(),
    "Главная страница": "Мое болото",
    "Открыть главную страницу": "Открыть мое болото",
    "Главная страница-меню: выбери нужный раздел настроек или перейди в режим дежурства.": "Мое болото: выбери нужный раздел настроек или перейди в режим жабича.",
    "Перейти в режим дежурства": "Дежурный жаб",
    "Режим дежурства": "Режим жабича",
    "Включить дежурство": "Активировать режим жабича",
    "Остановить дежурство": "Усыпить жабича",
    "Проверить выбранное": "Проверить выбранных мух",
    "Показать уведомление сейчас": "Квакнуть уведомлением",
    "Что проверяем в дежурстве": "Что проверяем в болоте",
    "Заметка дежурного": "Записка жаба",
    "Сохранить": "Сохранить квак",
    "Скопировать заметку": "Скопировать квак",
    "Очистить": "Очистить кочку",
    "Задачи дежурства": "Жабьи задачи",
    "Обновить данные": "Освежить болото",
    "Обновить всё": "Освежить всё болото",
    "Запустить проверку": "Выпустить жаба",
    "Остановить проверку": "Вернуть жаба на кочку",
    "Профиль": "Профиль",
    "Настройки": "Настройки",
    "Администрирование": "Жабий админ",
    "Режим разработчика": "Режим картофельной жабки",
    "Обновление": "Улучшения болота",
    "Выход": "Покинуть болото",
    "Продукт": "Мухи",
    "Продукт: ": "Мухи: ",
    "Раздел": "Виды",
    "Раздел: ": "Виды: ",
    "Проверить обновления": "Проверить улучшения болота",
    "Скачать и установить": "Притащить улучшения в болото",
    "Обновление найдено": "Найдено улучшение болота",
    "Обновлений нет": "Болото уже свежее",
    "Закрыть": "Закрыть кочку",
    "Применить": "Применить квак",
    "Сохранить тему": "Сохранить жабку",
    "Все темы приложения теперь находятся здесь, на Главной странице.": "Все темы приложения теперь находятся здесь, в моем болоте.",
    "Для полного применения темы приложение предложит перезапуск.": "Для полного применения жабки приложение предложит перезапуск.",
    "Загрузка панели мониторинга": "Болото просыпается",
    "Ожидаю загрузку страницы проблем и счётчика...": "Ожидаю мух, графики и счётчики...",
}

PARTIAL_TEXT_OVERRIDES = {
    "Закрыть Око": "Покинуть болото",
    "Закрыть Око?": "Покинуть болото?",
    "Загрузка Zabbix и счётчика проблем": "Загрузка Zabbix, мух и счётчика проблем",
    "Папка: assets/loading": "Болотная папка: assets/loading",
}

JABKA_QSS_EXTRA = """
QWidget#HomeShell, QWidget#DutyModeShell {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #07140D, stop:0.55 #0B1F13, stop:1 #163A22);
}
QWidget#HomeMenuCard, QWidget#MenuCard {
    background: rgba(10, 34, 20, 210);
    border: 1px solid rgba(143, 227, 136, 150);
    border-radius: 22px;
}
QLabel#HomeTitle, QLabel#AppTitle {
    color: #F1FFE0;
    letter-spacing: 1px;
}
QLabel#ThemeLogo {
    background: rgba(17, 50, 29, 180);
    border: 1px solid rgba(183, 242, 122, 160);
    border-radius: 12px;
    padding: 3px;
}
QPushButton#PrimaryAction {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #2D7D3A, stop:1 #8FE388);
    color: #07140D;
    border: 1px solid #B7F27A;
}
QPushButton#SecondaryAction {
    background: rgba(18, 51, 31, 220);
    color: #EAF8D8;
    border: 1px solid rgba(102, 185, 91, 150);
}
QPushButton#PrimaryAction:hover, QPushButton#SecondaryAction:hover {
    border: 1px solid #B7F27A;
    background: rgba(33, 79, 43, 230);
    color: #F1FFE0;
}
QLabel#JabkaMascot {
    background: rgba(10, 34, 20, 150);
    border: 1px solid rgba(143, 227, 136, 120);
    border-radius: 20px;
    padding: 8px;
}
QDialog#JabkaRestartDialog {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #07140D, stop:0.55 #0B1F13, stop:1 #163A22);
    border: 1px solid #66B95B;
    border-radius: 18px;
}
QDialog#JabkaRestartDialog QLabel {
    color: #EAF8D8;
}
QDialog#JabkaRestartDialog QPushButton {
    background: rgba(18, 51, 31, 230);
    color: #F1FFE0;
    border: 1px solid #66B95B;
    border-radius: 12px;
    padding: 9px 18px;
    font-weight: bold;
}
QDialog#JabkaRestartDialog QPushButton:hover {
    background: #214F2B;
    border: 1px solid #B7F27A;
}
"""


def install_jabka_theme() -> None:
    """Register the frog theme in the existing centralized theme registry."""
    from app import theme

    theme.THEMES[JABKA_THEME_NAME] = dict(JABKA_THEME)

    if not getattr(theme, "_jabka_stylesheet_patched", False):
        original_build_stylesheet = theme.build_stylesheet

        def build_stylesheet_with_jabka(theme_name: str) -> str:
            stylesheet = original_build_stylesheet(theme_name)
            if is_jabka_theme(theme_name):
                stylesheet += JABKA_QSS_EXTRA
            return stylesheet

        theme.build_stylesheet = build_stylesheet_with_jabka
        theme._jabka_stylesheet_patched = True


def is_jabka_theme(theme_name: Any) -> bool:
    return str(theme_name or "") == JABKA_THEME_NAME


def config_theme_name(config: dict | None) -> str:
    if not isinstance(config, dict):
        return ""
    settings = config.get("settings", {})
    return str(settings.get("theme") or "")


def is_jabka_config(config: dict | None) -> bool:
    return is_jabka_theme(config_theme_name(config))


def jabka_display_name(theme_name: Any = JABKA_THEME_NAME, default: str = "Око") -> str:
    return JABKA_APP_NAME if is_jabka_theme(theme_name) else default


def themed_text(theme_name: Any, text: Any) -> str:
    value = str(text or "")
    if not is_jabka_theme(theme_name):
        return value
    if value in TEXT_OVERRIDES:
        return TEXT_OVERRIDES[value]
    return value


def theme_asset_path(*parts: str) -> Path:
    return PROJECT_ROOT / "assets" / "themes" / "jabka" / Path(*parts)


def jabka_icon_path() -> Path:
    return PROJECT_ROOT / "assets" / "theme_logos" / "jabka.png"


def resolve_jabka_app_icon() -> Path | None:
    path = jabka_icon_path()
    if path.exists():
        return path
    fallback = theme_asset_path("icons", "jabbix_frog_icon.png")
    if fallback.exists():
        return fallback
    return None


def jabka_sound_path(name: str) -> Path:
    return theme_asset_path("sounds", name)


def patch_module_app_names() -> None:
    """Keep technical APP_NAME intact on disk, but show Jabbix while the theme is active."""
    try:
        import app.splash as splash
        splash.APP_NAME = JABKA_APP_NAME
    except Exception:
        pass
    try:
        import app.main_window as main_window
        main_window.APP_NAME = JABKA_APP_NAME
    except Exception:
        pass
    try:
        import app.home_config as home_config
        home_config.APP_NAME = JABKA_APP_NAME
    except Exception:
        pass


def apply_jabka_runtime(config: dict | None, app: QApplication | None = None) -> Path | None:
    install_jabka_theme()
    if app is None:
        app = QApplication.instance()

    if not is_jabka_config(config):
        if app is not None:
            app.setProperty("oko_jabka_theme", False)
        return None

    patch_module_app_names()
    patch_splash()
    patch_loading_screen()
    patch_restart_dialog()

    icon_path = resolve_jabka_app_icon()
    if app is not None:
        app.setProperty("oko_jabka_theme", True)
        app.setApplicationName(JABKA_APP_NAME)
        if icon_path is not None:
            app.setWindowIcon(QIcon(str(icon_path)))
        install_text_event_filter(app)
    return icon_path


def apply_jabka_widget_tree(widget: QWidget | None, config: dict | None = None) -> None:
    if widget is None or not is_jabka_config(config):
        return
    apply_text_overrides(widget)
    add_home_mascot(widget)


def _replace_text(value: str) -> str:
    if value in TEXT_OVERRIDES:
        return TEXT_OVERRIDES[value]
    replaced = value
    for source, target in PARTIAL_TEXT_OVERRIDES.items():
        replaced = replaced.replace(source, target)
    return replaced


def _set_widget_text(widget: QWidget) -> None:
    for attr in ("text",):
        if hasattr(widget, attr) and callable(getattr(widget, attr)) and hasattr(widget, "setText"):
            current = widget.text()
            updated = _replace_text(current)
            if updated != current:
                widget.setText(updated)
    if isinstance(widget, QGroupBox):
        current = widget.title()
        updated = _replace_text(current)
        if updated != current:
            widget.setTitle(updated)
    if hasattr(widget, "toolTip") and hasattr(widget, "setToolTip"):
        current = widget.toolTip()
        updated = _replace_text(current)
        if updated != current:
            widget.setToolTip(updated)


def apply_text_overrides(root: QWidget) -> None:
    if root.property("jabka_text_overrides_done"):
        return
    for widget in [root, *root.findChildren(QWidget)]:
        try:
            if isinstance(widget, (QLabel, QPushButton, QToolButton, QCheckBox, QGroupBox)):
                _set_widget_text(widget)
        except Exception:
            continue
    root.setProperty("jabka_text_overrides_done", True)


class _JabkaTextEventFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() in {QEvent.Show, QEvent.Polish, QEvent.EnabledChange}:
            try:
                if isinstance(obj, QWidget):
                    apply_text_overrides(obj)
            except Exception:
                pass
        return False


def install_text_event_filter(app: QApplication) -> None:
    if app.property("jabka_text_filter_installed"):
        return
    event_filter = _JabkaTextEventFilter(app)
    app.installEventFilter(event_filter)
    app.setProperty("jabka_text_filter_installed", True)
    app.setProperty("jabka_text_filter_ref", event_filter)


def add_home_mascot(window: QWidget) -> None:
    """Add a lightweight frog mascot to the home menu if the current UI has space for it."""
    mascot_path = theme_asset_path("frogs", "frog_main.png")
    if not mascot_path.exists():
        return
    home_widgets = [w for w in window.findChildren(QWidget) if w.objectName() == "HomeShell"]
    for home in home_widgets:
        if home.property("jabka_mascot_added"):
            continue
        layout = home.layout()
        if layout is None:
            continue
        mascot = QLabel()
        mascot.setObjectName("JabkaMascot")
        mascot.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(str(mascot_path))
        if pixmap.isNull():
            continue
        mascot.setPixmap(pixmap.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        try:
            layout.insertWidget(max(0, layout.count() - 1), mascot, alignment=Qt.AlignCenter)
            home.setProperty("jabka_mascot_added", True)
        except Exception:
            pass


def patch_splash() -> None:
    try:
        import app.splash as splash
    except Exception:
        return
    if getattr(splash.ThemeSplash, "_jabka_patched", False):
        return

    original_subtitle_text = splash.ThemeSplash.subtitle_text
    original_palette = splash.ThemeSplash.palette

    def subtitle_text(self):
        if is_jabka_theme(getattr(self, "theme", "")):
            return "болото просыпается..."
        return original_subtitle_text(self)

    def palette(self):
        if is_jabka_theme(getattr(self, "theme", "")):
            return {
                "bg1": QColor("#07140D"),
                "bg2": QColor("#163A22"),
                "accent": QColor("#8FE388"),
                "accent2": QColor("#B7F27A"),
                "text": "#F1FFE0",
                "muted": "#A9C89C",
                "border": QColor("#66B95B"),
                "progress_bg": "#08160D",
            }
        return original_palette(self)

    splash.ThemeSplash.subtitle_text = subtitle_text
    splash.ThemeSplash.palette = palette
    splash.ThemeSplash._jabka_patched = True


def patch_loading_screen() -> None:
    try:
        import app.loading_screen as loading_screen
    except Exception:
        return
    cls = loading_screen.LoadingScreen
    if getattr(cls, "_jabka_patched", False):
        return

    original_init = cls.__init__

    def __init__(self, config, parent=None):
        use_jabka = is_jabka_config(config)
        original_init(self, config, parent)
        if not use_jabka:
            return
        self.setWindowTitle("Jabbix загружается")
        self.setStyleSheet("""
            QWidget { background-color: #07140D; color: #EAF8D8; }
            QLabel#Title { color: #F1FFE0; font-size: 34px; font-weight: bold; padding: 10px; letter-spacing: 5px; }
            QLabel#Subtitle { color: #B7F27A; font-size: 16px; padding: 6px; }
            QLabel#Hint { color: #A9C89C; font-size: 13px; padding: 6px; }
            QLabel { background: transparent; }
        """)
        self.title.setText(JABKA_APP_NAME.upper())
        self.subtitle.setText("Болото просыпается")
        self.hint.setText("Ожидаю мух, графики и счётчики...")

    cls.__init__ = __init__
    cls._jabka_patched = True


def patch_restart_dialog() -> None:
    try:
        import app.home_config as home_config
    except Exception:
        return
    if getattr(home_config, "_jabka_restart_patched", False):
        return

    original_request = home_config.request_application_restart

    def request_application_restart(parent=None, reason=None):
        config = getattr(parent, "config", None)
        app = QApplication.instance()
        app_jabka = bool(app.property("oko_jabka_theme")) if app is not None else False
        if is_jabka_config(config) or app_jabka:
            return show_jabka_restart_dialog(parent, reason, home_config.restart_application)
        return original_request(parent=parent, reason=reason)

    home_config.request_application_restart = request_application_restart
    home_config.ask_restart_required = request_application_restart
    home_config._jabka_restart_patched = True


def show_jabka_restart_dialog(parent=None, reason=None, restart_callback=None) -> bool:
    dialog = QDialog(parent)
    dialog.setObjectName("JabkaRestartDialog")
    dialog.setWindowTitle("Jabbix просит перезапуск")
    dialog.setModal(True)
    dialog.setMinimumWidth(460)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(22, 20, 22, 18)
    layout.setSpacing(14)

    title = QLabel("🐸 Jabbix хочет обновить болото")
    title.setObjectName("PageTitle")
    title.setAlignment(Qt.AlignCenter)
    layout.addWidget(title)

    message = "Изменения требуют перезапуска приложения."
    if reason:
        message += f"\n\nПричина: {reason}"
    message += "\n\nКва-ква и перезапустить сейчас?"
    text = QLabel(message)
    text.setWordWrap(True)
    text.setAlignment(Qt.AlignCenter)
    layout.addWidget(text)

    row = QHBoxLayout()
    row.addStretch(1)
    cancel = QPushButton("Отмена!!!")
    accept = QPushButton("Ква-Ква")
    accept.setObjectName("PrimaryAction")
    row.addWidget(cancel)
    row.addWidget(accept)
    layout.addLayout(row)

    result = {"restart": False}

    def do_cancel():
        dialog.reject()

    def do_accept():
        result["restart"] = True
        dialog.accept()

    cancel.clicked.connect(do_cancel)
    accept.clicked.connect(do_accept)
    dialog.exec()

    if result["restart"]:
        if restart_callback:
            restart_callback()
        return True
    return False
