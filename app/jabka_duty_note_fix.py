from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget

from app.jabka_theme import is_jabka_config


NOTE_ACTION_TEXTS = {
    "Сохранить",
    "Сохранить квак",
    "Скопировать заметку",
    "Скопировать квак",
    "Очистить",
    "Очистить кочку",
}

_NOTE_BUTTON_QSS = """
QPushButton {
    min-height: 24px;
    max-height: 28px;
    padding: 2px 10px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 900;
    background: rgba(18, 51, 31, 228);
    color: #F1FFE0;
    border: 1px solid rgba(143, 227, 136, 170);
}
QPushButton:hover {
    background: rgba(33, 79, 43, 240);
    border: 1px solid #B7F27A;
}
QPushButton:pressed {
    background: rgba(8, 22, 13, 245);
    border: 1px solid #D7B85A;
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


def _clean_text(text: str) -> str:
    return " ".join(str(text or "").replace("&", "").split())


def _polish_note_button(button: QPushButton) -> None:
    button.setMinimumHeight(24)
    button.setMaximumHeight(28)
    button.setMinimumWidth(116)
    button.setMaximumWidth(158)
    button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    button.setProperty("jabka_duty_note_action", True)
    if not button.property("jabka_duty_note_qss_applied"):
        button.setStyleSheet(button.styleSheet() + _NOTE_BUTTON_QSS)
        button.setProperty("jabka_duty_note_qss_applied", True)


def _polish_action_row(buttons: list[QPushButton]) -> None:
    for button in buttons:
        parent = button.parentWidget()
        if parent is None:
            continue
        layout = parent.layout()
        if layout is None:
            continue
        try:
            layout.setSpacing(7)
            layout.setContentsMargins(0, 8, 0, 8)
        except Exception:
            pass


def polish_jabka_duty_note_buttons(window: QWidget | None, config: dict | None) -> None:
    if window is None or not is_jabka_config(config):
        return

    for shell in _safe_widgets(window):
        if shell.objectName() != "DutyModeShell":
            continue
        buttons = [
            widget
            for widget in _safe_widgets(shell)
            if isinstance(widget, QPushButton) and _clean_text(widget.text()) in NOTE_ACTION_TEXTS
        ]
        if not buttons:
            continue
        for button in buttons:
            _polish_note_button(button)
        _polish_action_row(buttons)


class _JabkaDutyNotePolishFilter(QObject):
    def __init__(self, window: QWidget, config: dict):
        super().__init__(window)
        self.window = window
        self.config = config
        self._scheduled = False

    def eventFilter(self, obj, event):
        if event.type() in {QEvent.Show, QEvent.Resize, QEvent.ChildAdded, QEvent.LayoutRequest}:
            self.schedule()
        return False

    def schedule(self) -> None:
        if self._scheduled:
            return
        self._scheduled = True
        QTimer.singleShot(80, self._run)

    def _run(self) -> None:
        self._scheduled = False
        polish_jabka_duty_note_buttons(self.window, self.config)


def install_jabka_duty_note_fix(window: QWidget | None, config: dict | None) -> None:
    if window is None or not is_jabka_config(config):
        return
    if window.property("jabka_duty_note_fix_installed"):
        polish_jabka_duty_note_buttons(window, config)
        return

    watcher = _JabkaDutyNotePolishFilter(window, config)
    window.installEventFilter(watcher)
    window.setProperty("jabka_duty_note_fix_installed", True)
    setattr(window, "_jabka_duty_note_fix_filter", watcher)

    polish_jabka_duty_note_buttons(window, config)
    QTimer.singleShot(350, lambda: polish_jabka_duty_note_buttons(window, config))
    QTimer.singleShot(1200, lambda: polish_jabka_duty_note_buttons(window, config))
    QTimer.singleShot(2500, lambda: polish_jabka_duty_note_buttons(window, config))
