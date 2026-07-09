from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QLabel, QWidget

from app.jabka_theme import apply_text_overrides, is_jabka_config


PAGE_HINTS = {
    "HomeShell": "🐸 Центральная кочка Jabbix",
    "DutyModeShell": "👑 Дежурный жаб следит за болотом",
}


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
        "background: rgba(10, 34, 20, 185);"
        "border: 1px solid rgba(183, 242, 122, 130);"
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


def apply_jabka_page_polish(window: QWidget | None, config: dict | None) -> None:
    """Apply extra frog styling to normal Qt pages.

    This intentionally avoids QWebEngine internals. It only decorates regular
    application widgets and schedules one delayed pass for pages built after the
    main window is shown.
    """
    if window is None or not is_jabka_config(config):
        return

    def polish_once():
        try:
            apply_text_overrides(window)
            for widget in _safe_widgets(window):
                object_name = widget.objectName()
                if object_name in PAGE_HINTS:
                    _decorate_named_shell(widget, PAGE_HINTS[object_name])
                if object_name in {"HomeMenuCard", "MenuCard"}:
                    widget.setProperty("jabka_card", True)
                if object_name in {"PrimaryAction", "SecondaryAction"}:
                    widget.setCursor(Qt.PointingHandCursor)
        except Exception:
            pass

    polish_once()
    QTimer.singleShot(350, polish_once)
    QTimer.singleShot(1200, polish_once)
