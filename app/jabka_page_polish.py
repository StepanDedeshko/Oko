from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from app.jabka_theme import apply_text_overrides, is_jabka_config, theme_asset_path


PAGE_HINTS = {
    "HomeShell": "🐸 Центральная кочка Jabbix",
    "DutyModeShell": "👑 Дежурный жаб следит за болотом",
}

PAGE_BACKGROUNDS = {
    "HomeShell": "swamp_main.jpg",
    "DutyModeShell": "swamp_duty.jpg",
}

PAGE_FROGS = {
    "HomeShell": "frog_main.jpg",
    "DutyModeShell": "frog_duty.jpg",
}


_PLAIN_WIDGET_SELECTORS = (
    "QFrame", "QGroupBox", "QLabel", "QPushButton", "QToolButton", "QLineEdit",
    "QTextEdit", "QPlainTextEdit", "QComboBox", "QTableWidget", "QTreeWidget",
    "QListWidget", "QTabWidget", "QTabBar"
)


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


def _resolve_asset(folder: str, filename: str, fallbacks: tuple[str, ...]) -> Path | None:
    candidates = (filename, *fallbacks)
    for candidate in candidates:
        path = theme_asset_path(folder, candidate)
        if path.exists():
            return path
    return None


class _JabkaBackgroundResizer(QObject):
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
        if self.pixmap.isNull():
            return
        size = self.shell.size()
        if size.width() <= 1 or size.height() <= 1:
            return
        scaled = self.pixmap.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = max(0, (scaled.width() - size.width()) // 2)
        y = max(0, (scaled.height() - size.height()) // 2)
        cropped = scaled.copy(x, y, size.width(), size.height())
        self.label.setGeometry(0, 0, size.width(), size.height())
        self.label.setPixmap(cropped)
        self.label.lower()
        self.label.show()


def _apply_shell_background(shell: QWidget, background_file: str) -> None:
    path = _resolve_asset(
        "backgrounds",
        background_file,
        (background_file.replace(".jpg", ".png"), background_file.replace(".jpg", ".svg")),
    )
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

    object_name = shell.objectName()
    if object_name:
        child_resets = "\n".join(
            f"QWidget#{object_name} {selector} {{ border-image: none; }}"
            for selector in _PLAIN_WIDGET_SELECTORS
        )
        shell.setStyleSheet(
            shell.styleSheet()
            + f"""
            QWidget#{object_name} {{
                background-color: #06140B;
            }}
            {child_resets}
            QLabel#JabkaBackground, QLabel#JabkaPageBadge, QLabel#JabkaMascot, QLabel#JabkaSideFrog {{
                border-image: none;
            }}
            """
        )

    label = QLabel(shell)
    label.setObjectName("JabkaBackground")
    label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    label.setAlignment(Qt.AlignCenter)
    label.setStyleSheet("QLabel#JabkaBackground { background: transparent; border: none; }")
    resizer = _JabkaBackgroundResizer(shell, label, pixmap)
    shell.installEventFilter(resizer)
    setattr(shell, "_jabka_background_label", label)
    setattr(shell, "_jabka_background_resizer", resizer)
    shell.setProperty("jabka_background_applied", True)
    resizer.update_background()


def _pixmap_for_frog(frog_file: str, size: int) -> QPixmap:
    path = _resolve_asset(
        "frogs",
        frog_file,
        (frog_file.replace(".jpg", ".png"), frog_file.replace(".jpg", ".svg")),
    )
    pixmap = QPixmap(str(path)) if path is not None else QPixmap()
    if pixmap.isNull():
        try:
            from app.jabka_embedded_assets import jabka_pixmap
            return jabka_pixmap(size)
        except Exception:
            return QPixmap()
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def _style_art_label(label: QLabel) -> None:
    label.setStyleSheet(
        "QLabel {"
        "background: rgba(4, 16, 8, 105);"
        "border: 1px solid rgba(183, 242, 122, 145);"
        "border-radius: 26px;"
        "padding: 8px;"
        "}"
    )


def _decorate_named_shell(shell: QWidget, text: str) -> None:
    if shell.property("jabka_page_polished"):
        return
    layout = shell.layout()
    if layout is None:
        return

    badge = QLabel(text)
    badge.setObjectName("JabkaPageBadge")
    badge.setAlignment(Qt.AlignCenter)
    badge.setWordWrap(True)
    badge.setStyleSheet(
        "QLabel#JabkaPageBadge {"
        "background: rgba(10, 34, 20, 200);"
        "border: 1px solid rgba(183, 242, 122, 150);"
        "border-radius: 14px;"
        "padding: 8px 14px;"
        "color: #D6EFC3;"
        "font-weight: 700;"
        "}"
    )
    try:
        layout.insertWidget(0, badge)
        shell.setProperty("jabka_page_polished", True)
    except Exception:
        pass


def _upgrade_existing_home_mascots(window: QWidget) -> None:
    for mascot in [w for w in _safe_widgets(window) if w.objectName() == "JabkaMascot" and isinstance(w, QLabel)]:
        if mascot.property("jabka_real_art_applied"):
            continue
        pixmap = _pixmap_for_frog("frog_main.jpg", 360)
        if pixmap.isNull():
            continue
        mascot.setPixmap(pixmap)
        mascot.setMinimumSize(380, 360)
        mascot.setMaximumHeight(390)
        _style_art_label(mascot)
        mascot.setProperty("jabka_real_art_applied", True)


def _add_side_frog(shell: QWidget, frog_file: str, size: int = 310) -> None:
    if shell.property("jabka_side_frog_added"):
        return
    layout = shell.layout()
    if layout is None:
        return
    pixmap = _pixmap_for_frog(frog_file, size)
    if pixmap.isNull():
        return
    label = QLabel()
    label.setObjectName("JabkaSideFrog")
    label.setAlignment(Qt.AlignCenter)
    label.setPixmap(pixmap)
    label.setMinimumHeight(size + 28)
    label.setMaximumHeight(size + 48)
    _style_art_label(label)
    try:
        layout.insertWidget(min(layout.count(), 2), label, alignment=Qt.AlignCenter)
        shell.setProperty("jabka_side_frog_added", True)
    except Exception:
        pass


def apply_jabka_page_polish(window: QWidget | None, config: dict | None) -> None:
    """Apply extra frog styling to normal Qt pages.

    This intentionally avoids QWebEngine internals. It only decorates regular
    application widgets and schedules delayed safe passes for pages built after
    the main window is shown.
    """
    if window is None or not is_jabka_config(config):
        return

    def polish_once():
        try:
            apply_text_overrides(window)
            for widget in _safe_widgets(window):
                object_name = widget.objectName()
                if object_name in PAGE_BACKGROUNDS:
                    _apply_shell_background(widget, PAGE_BACKGROUNDS[object_name])
                if object_name in PAGE_HINTS:
                    _decorate_named_shell(widget, PAGE_HINTS[object_name])
                if object_name == "DutyModeShell":
                    _add_side_frog(widget, PAGE_FROGS[object_name], 300)
                if object_name in {"HomeMenuCard", "MenuCard"}:
                    widget.setProperty("jabka_card", True)
                if object_name in {"PrimaryAction", "SecondaryAction"}:
                    widget.setCursor(Qt.PointingHandCursor)
            _upgrade_existing_home_mascots(window)
        except Exception:
            pass

    polish_once()
    QTimer.singleShot(350, polish_once)
    QTimer.singleShot(1200, polish_once)
