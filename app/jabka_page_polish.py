from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from app.jabka_theme import apply_text_overrides, is_jabka_config, theme_asset_path


PAGE_HINTS = {
    "HomeShell": "🐸 Центральная кочка Jabbix",
    "DutyModeShell": "👑 Дежурный жаб следит за болотом",
}

PAGE_BACKGROUNDS = {
    "HomeShell": "swamp_main.svg",
    "DutyModeShell": "swamp_duty.svg",
}

PAGE_FROGS = {
    "HomeShell": "frog_main.svg",
    "DutyModeShell": "frog_duty.svg",
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


def _asset_url(path: Path) -> str:
    return path.resolve().as_posix()


def _apply_shell_background(shell: QWidget, background_file: str) -> None:
    if shell.property("jabka_background_applied"):
        return
    object_name = shell.objectName()
    if not object_name:
        return
    path = theme_asset_path("backgrounds", background_file)
    if not path.exists():
        return

    child_resets = "\n".join(
        f"QWidget#{object_name} {selector} {{ border-image: none; }}"
        for selector in _PLAIN_WIDGET_SELECTORS
    )
    shell.setStyleSheet(
        shell.styleSheet()
        + f"""
        QWidget#{object_name} {{
            border-image: url(\"{_asset_url(path)}\") 0 0 0 0 stretch stretch;
            background-color: #06140B;
        }}
        {child_resets}
        QLabel#JabkaPageBadge, QLabel#JabkaMascot, QLabel#JabkaSideFrog {{
            border-image: none;
        }}
        """
    )
    shell.setProperty("jabka_background_applied", True)


def _pixmap_for_frog(frog_file: str, size: int) -> QPixmap:
    path = theme_asset_path("frogs", frog_file)
    pixmap = QPixmap(str(path)) if path.exists() else QPixmap()
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
        pixmap = _pixmap_for_frog("frog_main.svg", 360)
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
