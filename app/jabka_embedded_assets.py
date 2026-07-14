from __future__ import annotations

import base64
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from app.jabka_theme import JABKA_THEME_NAME, is_jabka_config, is_jabka_theme


# Tiny built-in fallback icon for the first Jabbix theme PR.
# The full selected art assets can be replaced later without changing runtime logic.
_JABKA_ICON_PNG_BASE64 = (
    "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"
)


def jabka_pixmap(size: int | None = None) -> QPixmap:
    pixmap = QPixmap()
    pixmap.loadFromData(base64.b64decode(_JABKA_ICON_PNG_BASE64), "PNG")
    if size and not pixmap.isNull():
        return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return pixmap


def jabka_icon() -> QIcon:
    return QIcon(jabka_pixmap())


def _patch_logo_loader() -> None:
    def load_theme_logo(theme_name: Any, size: int = 28):
        if is_jabka_theme(theme_name):
            return jabka_pixmap(size)
        return _patch_logo_loader.original(theme_name, size=size)

    import app.theme_logo as theme_logo
    if not hasattr(_patch_logo_loader, "original"):
        _patch_logo_loader.original = theme_logo.load_theme_logo
    theme_logo.load_theme_logo = load_theme_logo

    # These modules import the function directly, so patch their references too.
    for module_name in ("app.splash", "app.main_window"):
        try:
            module = __import__(module_name, fromlist=["dummy"])
            module.load_theme_logo = load_theme_logo
        except Exception:
            pass


def install_jabka_embedded_assets(config: dict | None, app: QApplication | None = None) -> QIcon | None:
    if not is_jabka_config(config):
        return None
    _patch_logo_loader()
    icon = jabka_icon()
    if app is None:
        app = QApplication.instance()
    if app is not None:
        app.setWindowIcon(icon)
    return icon


def apply_jabka_icon_to_widget(widget: QWidget | None, icon: QIcon | None) -> None:
    if widget is not None and icon is not None:
        widget.setWindowIcon(icon)
