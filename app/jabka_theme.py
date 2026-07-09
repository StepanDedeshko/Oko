from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
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
    background: qradialgradient(cx:0.84, cy:0.12, radius:1.15,
        fx:0.84, fy:0.12,
        stop:0 rgba(52, 108, 52, 0.42),
        stop:0.28 #102818,
        stop:0.74 #0B1F13,
        stop:1 #07140D);
}
QWidget#HomeShell::disabled, QWidget#DutyModeShell::disabled {
    background: #07140D;
}
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #07140D, stop:0.55 #0B1F13, stop:1 #102818);
}
QWidget#HomeMenuCard, QWidget#MenuCard {
    background: rgba(10, 34, 20, 220);
    border: 1px solid rgba(143, 227, 136, 170);
    border-radius: 24px;
}
QFrame, QGroupBox {
    border: 1px solid rgba(102, 185, 91, 135);
    border-radius: 18px;
    background: rgba(10, 34, 20, 205);
}
QLabel#HomeTitle, QLabel#AppTitle {
    color: #F1FFE0;
    letter-spacing: 1px;
}
QLabel#HomeTitle {
    font-size: 31px;
    padding-bottom: 8px;
}
QLabel#PageTitle {
    color: #F1FFE0;
    font-weight: 900;
}
QLabel#ThemeLogo {
    background: rgba(17, 50, 29, 190);
    border: 1px solid rgba(183, 242, 122, 180);
    border-radius: 12px;
    padding: 3px;
}
QToolBar, QWidget#BottomHud, QStatusBar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(7, 20, 13, 235),
        stop:0.45 rgba(17, 50, 29, 215),
        stop:1 rgba(7, 20, 13, 235));
    border: 1px solid rgba(102, 185, 91, 130);
}
QPushButton, QToolButton {
    border-radius: 14px;
    border: 1px solid rgba(102, 185, 91, 150);
    background: rgba(18, 51, 31, 225);
    color: #EAF8D8;
}
QPushButton#PrimaryAction {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #2D7D3A, stop:0.55 #8FE388, stop:1 #B7F27A);
    color: #07140D;
    border: 1px solid #D7B85A;
}
QPushButton#SecondaryAction {
    background: rgba(18, 51, 31, 230);
    color: #EAF8D8;
    border: 1px solid rgba(102, 185, 91, 165);
}
QPushButton:hover, QToolButton:hover,
QPushButton#PrimaryAction:hover, QPushButton#SecondaryAction:hover {
    border: 1px solid #B7F27A;
    background: rgba(33, 79, 43, 240);
    color: #F1FFE0;
}
QLineEdit, QTextEdit, QTextBrowser, QPlainTextEdit, QComboBox, QSpinBox {
    background: rgba(8, 22, 13, 235);
    border: 1px solid rgba(102, 185, 91, 145);
    border-radius: 13px;
    color: #F1FFE0;
}
QLineEdit:focus, QTextEdit:focus, QTextBrowser:focus, QPlainTextEdit:focus,
QComboBox:focus, QSpinBox:focus {
    border: 1px solid #B7F27A;
    background: rgba(10, 34, 20, 245);
}
QTableWidget, QTreeWidget, QListWidget {
    background: rgba(8, 22, 13, 245);
    alternate-background-color: rgba(18, 51, 31, 235);
    border: 1px solid rgba(102, 185, 91, 145);
    border-radius: 14px;
    gridline-color: rgba(102, 185, 91, 115);
}
QHeaderView::section {
    background: rgba(18, 51, 31, 245);
    color: #D6EFC3;
    border: 1px solid rgba(102, 185, 91, 120);
}
QTabWidget::pane {
    background: rgba(10, 34, 20, 210);
    border: 1px solid rgba(102, 185, 91, 135);
    border-radius: 16px;
}
QTabBar::tab {
    background: rgba(18, 51, 31, 225);
    border: 1px solid rgba(102, 185, 91, 120);
    border-radius: 12px;
    padding: 9px 14px;
}
QTabBar::tab:selected {
    background: rgba(45, 125, 58, 220);
    border: 1px solid #B7F27A;
    color: #F1FFE0;
}
QLabel#JabkaMascot {
    background: rgba(10, 34, 20, 165);
    border: 1px solid rgba(143, 227, 136, 130);
    border-radius: 22px;
    padding: 10px;
}
QDialog#JabkaRestartDialog {
    background: qradialgradient(cx:0.82, cy:0.15, radius:1.1,
        fx:0.82, fy:0.15,
        stop:0 rgba(52, 108, 52, 0.58),
        stop:0.35 #102818,
        stop:1 #07140D);
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


def _is_webengine_object(obj: object) -> bool:
    class_name = obj.__class__.__name__.lower()
    return "webengine" in class_name or "webview" in class_name


def _iter_safe_ui_widgets(root: QWidget) -> Iterable[QWidget]:
    """Walk normal Qt widgets but never descend into QWebEngine internals.

    QtWebEngine owns native/renderer objects. Touching those from a global event
    filter or recursive findChildren pass can cause a hard segfault, so the frog
    theme only rewrites text on safe application widgets.
    """
    stack = [root]
    while stack:
        widget = stack.pop()
        if _is_webengine_object(widget):
            continue
        yield widget
        for child in widget.children():
            if isinstance(child, QWidget) and not _is_webengine_object(child):
                stack.append(child)


def _set_widget_text(widget: QWidget) -> None:
    if hasattr(widget, "text") and callable(getattr(widget, "text")) and hasattr(widget, "setText"):
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
    for widget in _iter_safe_ui_widgets(root):
        try:
            if isinstance(widget, (QLabel, QPushButton, QToolButton, QCheckBox, QGroupBox)):
                _set_widget_text(widget)
        except Exception:
            continue
    root.setProperty("jabka_text_overrides_done", True)


def install_text_event_filter(app: QApplication) -> None:
    """Kept for compatibility; intentionally disabled.

    The first draft used a global QWidget event filter for live text overrides.
    That is unsafe with QtWebEngine graph pages and can crash the process, so all
    Jabbix text rewrites are now explicit and WebEngine-safe.
    """
    if app is not None:
        app.setProperty("jabka_text_filter_installed", False)


def add_home_mascot(window: QWidget) -> None:
    """Add a lightweight frog mascot to the home menu if the current UI has space for it."""
    home_widgets = [w for w in _iter_safe_ui_widgets(window) if w.objectName() == "HomeShell"]
    for home in home_widgets:
        if home.property("jabka_mascot_added"):
            continue
        layout = home.layout()
        if layout is None:
            continue
        pixmap = QPixmap()
        mascot_path = theme_asset_path("frogs", "frog_main.png")
        if mascot_path.exists():
            pixmap = QPixmap(str(mascot_path))
        if pixmap.isNull():
            try:
                from app.jabka_embedded_assets import jabka_pixmap
                pixmap = jabka_pixmap(220)
            except Exception:
                pixmap = QPixmap()
        if pixmap.isNull():
            continue
        mascot = QLabel()
        mascot.setObjectName("JabkaMascot")
        mascot.setAlignment(Qt.AlignCenter)
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
