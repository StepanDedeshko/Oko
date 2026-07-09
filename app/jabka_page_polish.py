from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from app.jabka_theme import apply_text_overrides, is_jabka_config, theme_asset_path


PAGE_BACKGROUNDS = {
    "HomeShell": "swamp_main.jpg",
    "DutyModeShell": "swamp_duty.jpg",
}

BUTTON_ICONS = {
    "Дежурный жаб": "🐸",
    "Профиль": "🐸",
    "Настройки": "⚙",
    "Жабий админ": "👑",
    "Режим картофельной жабки": "🥔",
    "Улучшения болота": "⬆",
    "Покинуть болото": "↪",
}

_READABLE_PANEL_QSS = """
QWidget#HomeShell QFrame,
QWidget#HomeShell QGroupBox,
QWidget#DutyModeShell QFrame,
QWidget#DutyModeShell QGroupBox {
    background: rgba(4, 16, 8, 145);
    border: 1px solid rgba(183, 242, 122, 115);
    border-radius: 16px;
}
QWidget#HomeShell QPushButton,
QWidget#DutyModeShell QPushButton,
QWidget#HomeShell QToolButton,
QWidget#DutyModeShell QToolButton {
    background: rgba(8, 28, 15, 172);
    border: 1px solid rgba(183, 242, 122, 130);
    border-radius: 12px;
    color: #EAF8D8;
}
QWidget#HomeShell QPushButton:hover,
QWidget#DutyModeShell QPushButton:hover,
QWidget#HomeShell QToolButton:hover,
QWidget#DutyModeShell QToolButton:hover {
    background: rgba(45, 125, 58, 205);
    border: 1px solid #B7F27A;
}
QWidget#HomeShell QLineEdit,
QWidget#HomeShell QTextEdit,
QWidget#HomeShell QPlainTextEdit,
QWidget#HomeShell QComboBox,
QWidget#DutyModeShell QLineEdit,
QWidget#DutyModeShell QTextEdit,
QWidget#DutyModeShell QPlainTextEdit,
QWidget#DutyModeShell QComboBox {
    background: rgba(4, 16, 8, 165);
    border: 1px solid rgba(183, 242, 122, 105);
    border-radius: 10px;
}
QWidget#HomeShell QTableWidget,
QWidget#HomeShell QTreeWidget,
QWidget#HomeShell QListWidget,
QWidget#DutyModeShell QTableWidget,
QWidget#DutyModeShell QTreeWidget,
QWidget#DutyModeShell QListWidget {
    background: rgba(3, 12, 6, 188);
    alternate-background-color: rgba(12, 37, 20, 172);
    border: 1px solid rgba(183, 242, 122, 105);
    border-radius: 13px;
}
QLabel#JabkaBackgroundLayer,
QLabel#JabkaMenuCrown {
    background: transparent;
    border: none;
}
"""


def _is_webengine_widget(widget: QWidget) -> bool:
    class_name = widget.__class__.__name__.lower()
    return "webengine" in class_name or "webview" in class_name


def _safe_widgets(root: QWidget):
    stack = [root]
    while stack:
        widget = stack.pop()
        if _is_webengine_widget(widget):
            continue
        yield widget
        for child in widget.children():
            if isinstance(child, QWidget) and not _is_webengine_widget(child):
                stack.append(child)


def _resolve_asset(folder: str, filename: str, fallbacks: tuple[str, ...] = ()) -> Path | None:
    for candidate in (filename, *fallbacks):
        path = theme_asset_path(folder, candidate)
        if path.exists():
            return path
    return None


class _JabkaBackgroundResizer(QObject):
    """Keeps the chosen art image as a non-layout background layer.

    The layer is a child of the page shell, not a layout item. It never pushes
    buttons, tables or QtWebEngine views out of the working area.
    """

    def __init__(self, shell: QWidget, label: QLabel, pixmap: QPixmap):
        super().__init__(shell)
        self.shell = shell
        self.label = label
        self.pixmap = pixmap

    def eventFilter(self, obj, event):
        if obj is self.shell and event.type() in {QEvent.Resize, QEvent.Show, QEvent.LayoutRequest}:
            self.update_background()
        return False

    def update_background(self) -> None:
        size = self.shell.size()
        if size.width() <= 1 or size.height() <= 1 or self.pixmap.isNull():
            return
        scaled = self.pixmap.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = max(0, (scaled.width() - size.width()) // 2)
        y = max(0, (scaled.height() - size.height()) // 2)
        cropped = scaled.copy(x, y, size.width(), size.height())
        self.label.setGeometry(0, 0, size.width(), size.height())
        self.label.setPixmap(cropped)
        self.label.lower()
        self.label.show()


def _apply_shell_background(shell: QWidget, filename: str) -> None:
    path = _resolve_asset("backgrounds", filename, (filename.replace(".jpg", ".png"), filename.replace(".jpg", ".svg")))
    if path is None:
        return

    if shell.property("jabka_background_applied"):
        resizer = getattr(shell, "_jabka_background_resizer", None)
        if resizer is not None:
            resizer.update_background()
        return

    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return

    shell.setStyleSheet(shell.styleSheet() + _READABLE_PANEL_QSS)
    label = QLabel(shell)
    label.setObjectName("JabkaBackgroundLayer")
    label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    label.setScaledContents(False)
    label.setAlignment(Qt.AlignCenter)

    resizer = _JabkaBackgroundResizer(shell, label, pixmap)
    shell.installEventFilter(resizer)
    setattr(shell, "_jabka_background_label", label)
    setattr(shell, "_jabka_background_resizer", resizer)
    shell.setProperty("jabka_background_applied", True)
    resizer.update_background()


def _find_home_widgets(shell: QWidget):
    menu = None
    title = None
    subtitle = None
    footer = None
    for widget in _safe_widgets(shell):
        if widget.objectName() == "HomeMenuCard":
            menu = widget
        elif widget.objectName() == "HomeTitle" and isinstance(widget, QLabel):
            title = widget
        elif widget.objectName() == "AppFooter" and isinstance(widget, QLabel):
            footer = widget
        elif isinstance(widget, QLabel) and "выбери нужный раздел" in widget.text().lower():
            subtitle = widget
    return menu, title, subtitle, footer


def _hide_layout_mascots(shell: QWidget) -> None:
    for mascot in [w for w in _safe_widgets(shell) if w.objectName() == "JabkaMascot"]:
        mascot.hide()
        mascot.setParent(None)


def _polish_home_buttons(menu: QWidget) -> None:
    for button in menu.findChildren(QPushButton):
        text = button.text().strip()
        clean_text = text.split("  ›", 1)[0].strip()
        for icon in BUTTON_ICONS.values():
            if clean_text.startswith(icon):
                clean_text = clean_text[len(icon):].strip()
        icon = BUTTON_ICONS.get(clean_text, "🐸")
        button.setText(f"{icon}   {clean_text}                                      ›")
        button.setMinimumHeight(50)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(
            "QPushButton {"
            "text-align: left;"
            "padding-left: 22px;"
            "padding-right: 16px;"
            "border-radius: 12px;"
            "background: rgba(6, 24, 12, 172);"
            "border: 1px solid rgba(183, 242, 122, 125);"
            "color: #EAF8D8;"
            "font-weight: 800;"
            "}"
            "QPushButton:hover {"
            "background: rgba(45, 125, 58, 205);"
            "border: 1px solid #B7F27A;"
            "color: #F1FFE0;"
            "}"
            "QPushButton#PrimaryAction {"
            "background: rgba(45, 125, 58, 218);"
            "border: 1px solid #D7B85A;"
            "color: #F1FFE0;"
            "}"
        )


class _JabkaHomeLayoutResizer(QObject):
    def __init__(self, shell: QWidget, menu: QWidget, title: QLabel | None, subtitle: QLabel | None, footer: QLabel | None, crown: QLabel):
        super().__init__(shell)
        self.shell = shell
        self.menu = menu
        self.title = title
        self.subtitle = subtitle
        self.footer = footer
        self.crown = crown

    def eventFilter(self, obj, event):
        if obj is self.shell and event.type() in {QEvent.Resize, QEvent.Show, QEvent.LayoutRequest}:
            self.update_layout()
        return False

    def update_layout(self) -> None:
        w = max(1, self.shell.width())
        h = max(1, self.shell.height())
        left = max(32, int(w * 0.025))
        top = max(20, int(h * 0.035))

        if self.title is not None:
            self.title.setGeometry(left, top, min(430, int(w * 0.38)), 64)
            self.title.raise_()
        if self.subtitle is not None:
            self.subtitle.setGeometry(left + 8, top + 70, min(760, int(w * 0.55)), 34)
            self.subtitle.raise_()

        menu_w = min(max(360, int(w * 0.25)), 470)
        menu_h = min(max(390, self.menu.sizeHint().height() + 72), int(h * 0.64))
        menu_x = int(w * 0.50 - menu_w / 2)
        menu_y = max(top + 155, int(h * 0.22))
        self.menu.setGeometry(menu_x, menu_y, menu_w, menu_h)
        self.menu.raise_()

        self.crown.setGeometry(menu_x + int(menu_w * 0.31), max(top + 130, menu_y - 48), int(menu_w * 0.38), 48)
        self.crown.raise_()

        if self.footer is not None:
            self.footer.setGeometry(left, h - 76, w - left * 2, 46)
            self.footer.raise_()


def _apply_home_scene(shell: QWidget) -> None:
    _hide_layout_mascots(shell)
    menu, title, subtitle, footer = _find_home_widgets(shell)
    if menu is None:
        return

    if shell.property("jabka_home_scene_done"):
        resizer = getattr(shell, "_jabka_home_layout_resizer", None)
        if resizer is not None:
            resizer.update_layout()
        return

    layout = shell.layout()
    if layout is not None:
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

    menu.setParent(shell)
    menu.setMaximumWidth(16777215)
    menu.setStyleSheet(
        "QWidget#HomeMenuCard {"
        "background: rgba(4, 16, 8, 162);"
        "border: 1px solid rgba(215, 184, 90, 150);"
        "border-radius: 22px;"
        "}"
    )
    _polish_home_buttons(menu)

    if title is not None:
        title.setParent(shell)
        title.setText("Jabbix")
        title.setStyleSheet(
            "QLabel#HomeTitle {"
            "background: rgba(4, 16, 8, 145);"
            "border: 1px solid rgba(183, 242, 122, 95);"
            "border-radius: 14px;"
            "color: #EAF8D8;"
            "font-size: 42px;"
            "font-weight: 900;"
            "padding-left: 14px;"
            "}"
        )
    if subtitle is not None:
        subtitle.setParent(shell)
        subtitle.setStyleSheet(
            "QLabel { background: rgba(4, 16, 8, 135); border: 1px solid rgba(183, 242, 122, 90);"
            "border-radius: 8px; padding: 4px 10px; color: #D6EFC3; }"
        )
    if footer is not None:
        footer.setParent(shell)
        footer.setStyleSheet(
            "QLabel#AppFooter { background: rgba(4, 16, 8, 150); border: 1px solid rgba(183, 242, 122, 90);"
            "border-radius: 10px; padding: 5px; color: #A9C89C; font-size: 11px; }"
        )

    crown = QLabel("♕", shell)
    crown.setObjectName("JabkaMenuCrown")
    crown.setAlignment(Qt.AlignCenter)
    crown.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    crown.setStyleSheet(
        "QLabel#JabkaMenuCrown {"
        "background: rgba(4, 16, 8, 158);"
        "border: 1px solid rgba(215, 184, 90, 160);"
        "border-radius: 18px;"
        "color: #D7B85A;"
        "font-size: 28px;"
        "font-weight: 900;"
        "}"
    )

    resizer = _JabkaHomeLayoutResizer(shell, menu, title, subtitle, footer, crown)
    shell.installEventFilter(resizer)
    setattr(shell, "_jabka_home_layout_resizer", resizer)
    shell.setProperty("jabka_home_scene_done", True)
    resizer.update_layout()


def apply_jabka_page_polish(window: QWidget | None, config: dict | None) -> None:
    """Apply Jabbix visual polish without touching QtWebEngine internals."""
    if window is None or not is_jabka_config(config):
        return

    def polish_once():
        try:
            apply_text_overrides(window)
            for widget in _safe_widgets(window):
                object_name = widget.objectName()
                if object_name in PAGE_BACKGROUNDS:
                    _apply_shell_background(widget, PAGE_BACKGROUNDS[object_name])
                if object_name == "HomeShell":
                    _apply_home_scene(widget)
                if object_name in {"PrimaryAction", "SecondaryAction"}:
                    widget.setCursor(Qt.PointingHandCursor)
        except Exception:
            pass

    polish_once()
    QTimer.singleShot(350, polish_once)
    QTimer.singleShot(1200, polish_once)
