from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractScrollArea, QLabel, QPushButton, QVBoxLayout, QWidget

try:
    from PySide6.QtWidgets import QFrame
except Exception:  # pragma: no cover - defensive for unusual Qt builds
    QFrame = None

from app.jabka_theme import apply_text_overrides, is_jabka_config, theme_asset_path


PAGE_BACKGROUNDS = {
    "HomeShell": "00_main_menu_wallpaper.png",
}

CELL_BACKGROUND_FILES = (
    "01_cell_top_left_wide_background.png",
    "02_cell_top_right_small_background.png",
    "03_cell_middle_strip_background.png",
    "04_cell_bottom_left_background.png",
    "05_cell_bottom_right_background.png",
)

MENU_FRAME_FILE = "menu_frame.png"
MENU_FRAME_ASPECT = 2 / 3

MAX_CELL_BACKGROUNDS_PER_PAGE = 6
MIN_CELL_BACKGROUND_AREA = 52_000

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
    background: rgba(4, 16, 8, 118);
    border: 1px solid rgba(183, 242, 122, 120);
    border-radius: 16px;
}
QWidget#HomeShell QWidget#HomeMenuCard,
QWidget#HomeShell QFrame#HomeMenuCard,
QWidget#HomeShell QWidget#JabkaMenuOverlay,
QWidget#HomeShell QFrame#JabkaMenuOverlay {
    background: transparent;
    background-color: transparent;
    border: 0px solid transparent;
    border-radius: 0;
    margin: 0;
    padding: 0;
}
QWidget#HomeShell QPushButton,
QWidget#DutyModeShell QPushButton,
QWidget#HomeShell QToolButton,
QWidget#DutyModeShell QToolButton {
    background: rgba(8, 28, 15, 176);
    border: 1px solid rgba(183, 242, 122, 135);
    border-radius: 12px;
    color: #EAF8D8;
}
QWidget#HomeShell QPushButton:hover,
QWidget#DutyModeShell QPushButton:hover,
QWidget#HomeShell QToolButton:hover,
QWidget#DutyModeShell QToolButton:hover {
    background: rgba(45, 125, 58, 210);
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
    background: rgba(4, 16, 8, 120);
    border: 1px solid rgba(183, 242, 122, 110);
    border-radius: 10px;
}
QWidget#HomeShell QTableWidget,
QWidget#HomeShell QTreeWidget,
QWidget#HomeShell QListWidget,
QWidget#DutyModeShell QTableWidget,
QWidget#DutyModeShell QTreeWidget,
QWidget#DutyModeShell QListWidget {
    background: rgba(3, 12, 6, 178);
    alternate-background-color: rgba(12, 37, 20, 158);
    border: 1px solid rgba(183, 242, 122, 110);
    border-radius: 13px;
}
QLabel#JabkaBackgroundLayer,
QLabel#JabkaCellBackgroundLayer,
QLabel#JabkaMenuFrameLayer,
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


def _scaled_background_pixmap(source: QPixmap, target_size, overlay_alpha: int, scale_mode: str = "cover") -> QPixmap:
    if scale_mode == "menu_frame":
        crop_x = max(1, int(source.width() * 0.035))
        crop_y = max(1, int(source.height() * 0.028))
        source = source.copy(
            crop_x,
            crop_y,
            max(1, source.width() - crop_x * 2),
            max(1, source.height() - crop_y * 2),
        )
        result = source.scaled(target_size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    elif scale_mode == "stretch":
        result = source.scaled(target_size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    elif scale_mode == "contain":
        result = QPixmap(target_size)
        result.fill(Qt.transparent)
        scaled = source.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = max(0, (target_size.width() - scaled.width()) // 2)
        y = max(0, (target_size.height() - scaled.height()) // 2)
        painter = QPainter(result)
        painter.drawPixmap(x, y, scaled)
        painter.end()
    else:
        scaled = source.scaled(target_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = max(0, (scaled.width() - target_size.width()) // 2)
        y = max(0, (scaled.height() - target_size.height()) // 2)
        result = scaled.copy(x, y, target_size.width(), target_size.height())

    if overlay_alpha > 0:
        painter = QPainter(result)
        painter.fillRect(result.rect(), QColor(2, 10, 5, overlay_alpha))
        painter.end()
    return result


class _JabkaBackgroundResizer(QObject):
    def __init__(self, target: QWidget, label: QLabel, pixmap: QPixmap, overlay_alpha: int = 0, scale_mode: str = "cover"):
        super().__init__(target)
        self.target = target
        self.label = label
        self.pixmap = pixmap
        self.overlay_alpha = overlay_alpha
        self.scale_mode = scale_mode
        self._last_size = None

    def eventFilter(self, obj, event):
        if obj is self.target and event.type() in {QEvent.Resize, QEvent.Show}:
            self.update_background()
        return False

    def update_background(self) -> None:
        size = self.target.size()
        if size.width() <= 1 or size.height() <= 1 or self.pixmap.isNull():
            return
        self.label.setGeometry(0, 0, size.width(), size.height())
        if self._last_size != size:
            self.label.setPixmap(_scaled_background_pixmap(self.pixmap, size, self.overlay_alpha, self.scale_mode))
            self._last_size = size
        self.label.lower()
        self.label.show()


def _install_background_layer(
    target: QWidget,
    path: Path,
    property_name: str,
    overlay_alpha: int,
    object_name: str | None = None,
    scale_mode: str = "cover",
) -> None:
    resizer_attr = f"_{property_name}_resizer"
    applied_property = f"{property_name}_applied"
    if target.property(applied_property):
        resizer = getattr(target, resizer_attr, None)
        if resizer is not None:
            resizer.update_background()
        return

    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return

    label = QLabel(target)
    if object_name:
        label.setObjectName(object_name)
    elif "cell" in property_name:
        label.setObjectName("JabkaCellBackgroundLayer")
    else:
        label.setObjectName("JabkaBackgroundLayer")
    label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    label.setScaledContents(False)
    label.setAlignment(Qt.AlignCenter)

    resizer = _JabkaBackgroundResizer(target, label, pixmap, overlay_alpha=overlay_alpha, scale_mode=scale_mode)
    target.installEventFilter(resizer)
    setattr(target, f"_{property_name}_label", label)
    setattr(target, resizer_attr, resizer)
    target.setProperty(applied_property, True)
    resizer.update_background()


def _apply_shell_background(shell: QWidget, filename: str) -> None:
    path = _resolve_asset("backgrounds", filename, (filename.replace(".png", ".svg"),))
    if path is None:
        return
    if not shell.property("jabka_readable_qss_applied"):
        shell.setStyleSheet(shell.styleSheet() + _READABLE_PANEL_QSS)
        shell.setProperty("jabka_readable_qss_applied", True)
    _install_background_layer(shell, path, "jabka_page_background", overlay_alpha=34, scale_mode="cover")


def _widget_text_blob(widget: QWidget) -> str:
    parts = [widget.objectName(), widget.accessibleName()]
    if hasattr(widget, "title"):
        try:
            parts.append(widget.title())
        except Exception:
            pass
    if hasattr(widget, "text"):
        try:
            parts.append(widget.text())
        except Exception:
            pass
    return " ".join(str(part or "") for part in parts).lower()


def _choose_cell_background(widget: QWidget, index: int) -> str:
    text = _widget_text_blob(widget)
    if "замет" in text or "квак" in text or "note" in text:
        return "03_cell_middle_strip_background.png"
    if "сервис" in text or "service" in text:
        return "04_cell_bottom_left_background.png"
    if "zabbix" in text or "граф" in text or "trigger" in text:
        return "05_cell_bottom_right_background.png"
    if "состоя" in text or "status" in text or "послед" in text:
        return "01_cell_top_left_wide_background.png"
    return CELL_BACKGROUND_FILES[index % len(CELL_BACKGROUND_FILES)]


def _has_cell_background_ancestor(widget: QWidget, shell: QWidget) -> bool:
    parent = widget.parentWidget()
    while parent is not None and parent is not shell:
        if parent.property("jabka_cell_background_applied"):
            return True
        parent = parent.parentWidget()
    return False


def _is_cell_candidate(widget: QWidget, shell: QWidget) -> bool:
    if widget is shell:
        return False
    if widget.objectName() in {"JabkaBackgroundLayer", "JabkaCellBackgroundLayer", "JabkaMenuFrameLayer", "JabkaMenuOverlay", "JabkaMenuCrown"}:
        return False
    if _is_webengine_widget(widget) or _has_cell_background_ancestor(widget, shell):
        return False
    if isinstance(widget, (QPushButton, QLabel, QAbstractScrollArea)):
        return False
    class_name = widget.__class__.__name__
    if class_name not in {"QFrame", "QGroupBox"}:
        return False
    size = widget.size()
    return size.width() * size.height() >= MIN_CELL_BACKGROUND_AREA


def _make_cell_translucent(widget: QWidget) -> None:
    if widget.property("jabka_cell_translucent"):
        return
    object_name = widget.objectName()
    if not object_name:
        object_name = f"jabka_cell_{id(widget)}"
        widget.setObjectName(object_name)
    widget.setStyleSheet(
        widget.styleSheet()
        + f"""
        QWidget#{object_name} {{
            background: rgba(4, 16, 8, 112);
            border: 1px solid rgba(183, 242, 122, 110);
            border-radius: 14px;
        }}
        QWidget#{object_name} QLabel,
        QWidget#{object_name} QPushButton,
        QWidget#{object_name} QToolButton,
        QWidget#{object_name} QCheckBox {{
            background: transparent;
        }}
        """
    )
    widget.setProperty("jabka_cell_translucent", True)


def _apply_cell_background(widget: QWidget, filename: str) -> None:
    path = _resolve_asset("backgrounds", filename)
    if path is None:
        return
    _make_cell_translucent(widget)
    _install_background_layer(widget, path, "jabka_cell_background", overlay_alpha=105, scale_mode="cover")


def _apply_menu_frame_background(menu: QWidget) -> None:
    path = _resolve_asset("menu", MENU_FRAME_FILE)
    if path is None:
        return
    _install_background_layer(
        menu,
        path,
        "jabka_menu_frame_background",
        overlay_alpha=0,
        object_name="JabkaMenuFrameLayer",
        scale_mode="menu_frame",
    )


def _update_existing_cell_backgrounds(shell: QWidget) -> None:
    for widget in _safe_widgets(shell):
        if widget.property("jabka_cell_background_applied"):
            resizer = getattr(widget, "_jabka_cell_background_resizer", None)
            if resizer is not None:
                resizer.update_background()


def _apply_shell_cell_backgrounds(shell: QWidget) -> None:
    if shell.property("jabka_cell_background_pass_done"):
        _update_existing_cell_backgrounds(shell)
        return

    candidates = [widget for widget in _safe_widgets(shell) if _is_cell_candidate(widget, shell)]
    candidates.sort(key=lambda widget: widget.width() * widget.height(), reverse=True)

    applied = 0
    for widget in candidates:
        if applied >= MAX_CELL_BACKGROUNDS_PER_PAGE:
            break
        if _has_cell_background_ancestor(widget, shell):
            continue
        filename = _choose_cell_background(widget, applied)
        _apply_cell_background(widget, filename)
        if widget.property("jabka_cell_background_applied"):
            applied += 1

    if applied > 0:
        shell.setProperty("jabka_cell_background_pass_done", True)


def _find_home_widgets(shell: QWidget):
    menu = getattr(shell, "_jabka_home_menu_overlay", None)
    source_menu = getattr(shell, "_jabka_original_home_menu", None)
    title = None
    subtitle = None
    footer = None
    if not isinstance(menu, QWidget):
        menu = None
    if not isinstance(source_menu, QWidget):
        source_menu = None
    for widget in _safe_widgets(shell):
        object_name = widget.objectName()
        if object_name == "HomeMenuCard" and source_menu is None:
            source_menu = widget
        elif object_name == "JabkaMenuOverlay" and menu is None:
            menu = widget
        elif object_name == "HomeTitle" and isinstance(widget, QLabel):
            title = widget
        elif object_name == "AppFooter" and isinstance(widget, QLabel):
            footer = widget
        elif isinstance(widget, QLabel) and "выбери нужный раздел" in widget.text().lower():
            subtitle = widget
    return menu, source_menu, title, subtitle, footer


def _hide_layout_mascots(shell: QWidget) -> None:
    for mascot in [w for w in _safe_widgets(shell) if w.objectName() == "JabkaMascot"]:
        mascot.hide()
        mascot.setParent(None)


def _clean_button_text(text: str) -> str:
    value = text.strip()
    for marker in ("  ›", " ›", "›", ">"):
        value = value.replace(marker, "")
    value = " ".join(value.split())
    for icon in BUTTON_ICONS.values():
        if value.startswith(icon):
            value = value[len(icon):].strip()
    return value


def _polish_home_buttons(menu: QWidget) -> None:
    for button in menu.findChildren(QPushButton):
        clean_text = _clean_button_text(button.text())
        icon = BUTTON_ICONS.get(clean_text, "🐸")
        button.setText(f"{icon}   {clean_text}")
        button.setMinimumHeight(64)
        button.setMaximumHeight(72)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(
            "QPushButton {"
            "text-align: left;"
            "padding-left: 36px;"
            "padding-right: 22px;"
            "border-radius: 16px;"
            "background: rgba(7, 27, 14, 174);"
            "border: 1px solid rgba(143, 227, 136, 155);"
            "color: #D6EFC3;"
            "font-size: 18px;"
            "font-weight: 900;"
            "}"
            "QPushButton:hover {"
            "background: rgba(45, 125, 58, 218);"
            "border: 1px solid #B7F27A;"
            "color: #F1FFE0;"
            "}"
            "QPushButton#PrimaryAction {"
            "background: rgba(45, 125, 58, 226);"
            "border: 1px solid #D7B85A;"
            "color: #F1FFE0;"
            "}"
        )


class _JabkaHomeLayoutResizer(QObject):
    def __init__(self, shell: QWidget, menu: QWidget, title: QLabel | None, subtitle: QLabel | None, footer: QLabel | None):
        super().__init__(shell)
        self.shell = shell
        self.menu = menu
        self.title = title
        self.subtitle = subtitle
        self.footer = footer

    def eventFilter(self, obj, event):
        if obj is self.shell and event.type() in {QEvent.Resize, QEvent.Show}:
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

        menu_w = min(max(540, int(w * 0.315)), 710)
        menu_h = int(menu_w / MENU_FRAME_ASPECT)
        max_menu_h = int(h * 0.83)
        if menu_h > max_menu_h:
            menu_h = max_menu_h
            menu_w = int(menu_h * MENU_FRAME_ASPECT)
        menu_x = int(w * 0.50 - menu_w / 2)
        menu_y = max(top + 104, int(h * 0.095))
        self.menu.setGeometry(menu_x, menu_y, menu_w, menu_h)
        self.menu.raise_()

        menu_layout = self.menu.layout()
        if menu_layout is not None:
            menu_layout.setContentsMargins(
                int(menu_w * 0.115),
                int(menu_h * 0.185),
                int(menu_w * 0.115),
                int(menu_h * 0.135),
            )
            menu_layout.setSpacing(max(12, int(menu_h * 0.014)))

        frame_resizer = getattr(self.menu, "_jabka_menu_frame_background_resizer", None)
        if frame_resizer is not None:
            frame_resizer.update_background()

        if self.footer is not None:
            self.footer.setGeometry(left, h - 76, w - left * 2, 46)
            self.footer.raise_()


def _make_menu_container_transparent(menu: QWidget) -> None:
    menu.setAttribute(Qt.WA_TranslucentBackground, True)
    menu.setAutoFillBackground(False)
    if QFrame is not None and isinstance(menu, QFrame):
        try:
            menu.setFrameShape(QFrame.NoFrame)
            menu.setFrameShadow(QFrame.Plain)
            menu.setLineWidth(0)
            menu.setMidLineWidth(0)
            menu.setFrameStyle(0)
        except Exception:
            pass
    menu.setStyleSheet(
        "QWidget#HomeMenuCard, QFrame#HomeMenuCard, QWidget#JabkaMenuOverlay, QFrame#JabkaMenuOverlay {"
        "background: transparent;"
        "background-color: transparent;"
        "border: 0px solid transparent;"
        "border-radius: 0;"
        "padding: 0;"
        "margin: 0;"
        "}"
    )


def _create_menu_overlay(shell: QWidget, source_menu: QWidget) -> QWidget:
    overlay = getattr(shell, "_jabka_home_menu_overlay", None)
    if isinstance(overlay, QWidget):
        return overlay

    buttons = source_menu.findChildren(QPushButton)
    buttons.sort(key=lambda button: (button.geometry().y(), button.geometry().x()))

    overlay = QWidget(shell)
    overlay.setObjectName("JabkaMenuOverlay")
    _make_menu_container_transparent(overlay)
    overlay_layout = QVBoxLayout(overlay)
    overlay_layout.setContentsMargins(0, 0, 0, 0)
    overlay_layout.setSpacing(12)

    for button in buttons:
        button.setParent(overlay)
        overlay_layout.addWidget(button)

    _make_menu_container_transparent(source_menu)
    source_menu.hide()
    try:
        source_menu.setParent(None)
    except Exception:
        pass

    setattr(shell, "_jabka_original_home_menu", source_menu)
    setattr(shell, "_jabka_home_menu_overlay", overlay)
    return overlay


def _apply_home_scene(shell: QWidget) -> None:
    _hide_layout_mascots(shell)
    menu, source_menu, title, subtitle, footer = _find_home_widgets(shell)
    if menu is None and source_menu is not None:
        menu = _create_menu_overlay(shell, source_menu)
    if menu is None:
        return

    if shell.property("jabka_home_scene_done"):
        _make_menu_container_transparent(menu)
        _polish_home_buttons(menu)
        _apply_menu_frame_background(menu)
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
    _make_menu_container_transparent(menu)
    _apply_menu_frame_background(menu)
    _polish_home_buttons(menu)

    if title is not None:
        title.setParent(shell)
        title.setText("Jabbix")
        title.setStyleSheet(
            "QLabel#HomeTitle {"
            "background: transparent;"
            "border: none;"
            "color: #EAF8D8;"
            "font-size: 42px;"
            "font-weight: 900;"
            "padding-left: 14px;"
            "}"
        )
    if subtitle is not None:
        subtitle.setParent(shell)
        subtitle.setStyleSheet(
            "QLabel { background: rgba(4, 16, 8, 120); border: 1px solid rgba(183, 242, 122, 95);"
            "border-radius: 8px; padding: 4px 10px; color: #D6EFC3; }"
        )
    if footer is not None:
        footer.setParent(shell)
        footer.setStyleSheet(
            "QLabel#AppFooter { background: rgba(4, 16, 8, 130); border: 1px solid rgba(183, 242, 122, 95);"
            "border-radius: 10px; padding: 5px; color: #A9C89C; font-size: 11px; }"
        )

    resizer = _JabkaHomeLayoutResizer(shell, menu, title, subtitle, footer)
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
                elif object_name == "DutyModeShell":
                    _apply_shell_cell_backgrounds(widget)
                if object_name in {"PrimaryAction", "SecondaryAction"}:
                    widget.setCursor(Qt.PointingHandCursor)
        except Exception:
            pass

    polish_once()
    QTimer.singleShot(350, polish_once)
    QTimer.singleShot(1200, polish_once)
