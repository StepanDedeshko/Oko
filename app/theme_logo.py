from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap


def theme_logo_path(theme_name):
    base = Path(__file__).resolve().parent.parent / "assets" / "theme_logos"
    path = base / f"{theme_name}.png"

    if path.exists():
        return path

    fallback = base / "mass_effect.png"
    if fallback.exists():
        return fallback

    return None


def load_theme_logo(theme_name, size=28):
    path = theme_logo_path(theme_name)

    if not path:
        return QPixmap()

    pixmap = QPixmap(str(path))

    if pixmap.isNull():
        return QPixmap()

    return pixmap.scaled(
        size,
        size,
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation
    )
