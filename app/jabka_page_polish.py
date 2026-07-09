from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from app.jabka_theme import apply_text_overrides, is_jabka_config, theme_asset_path


PAGE_HINTS = {
    "DutyModeShell": "👑 Дежурный жаб следит за болотом",
}

PAGE_FROGS = {
    "HomeShell": "frog_main.jpg",
    "DutyModeShell": "frog_duty.jpg",
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


def _resolve_asset(folder: str, filename: str, fallbacks: tuple[str, ...]) -> str | None:
    for candidate in (filename, *fallbacks):
        path = theme_asset_path(folder, candidate)
        if path.exists():
            return str(path)
    return None


class _JabkaBackdrop(QWidget):
    """Code-drawn swamp backdrop, not a pasted concept-art screenshot."""

    def __init__(self, parent: QWidget, variant: str = "home"):
        super().__init__(parent)
        self.variant = variant
        self.setObjectName("JabkaPaintedBackdrop")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAutoFillBackground(False)

    def paintEvent(self, event):  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        rect = self.rect()
        w = max(1, rect.width())
        h = max(1, rect.height())

        bg = QLinearGradient(0, 0, w, h)
        bg.setColorAt(0.0, QColor("#020905"))
        bg.setColorAt(0.30, QColor("#061b0e"))
        bg.setColorAt(0.62, QColor("#092913"))
        bg.setColorAt(1.0, QColor("#020704"))
        painter.fillRect(rect, bg)

        glow_center = QPointF(w * 0.68, h * 0.18)
        glow = QRadialGradient(glow_center, max(w, h) * 0.62)
        glow.setColorAt(0.0, QColor(143, 227, 136, 86))
        glow.setColorAt(0.24, QColor(45, 125, 58, 48))
        glow.setColorAt(0.75, QColor(4, 16, 8, 0))
        painter.fillRect(rect, glow)

        # Dark castle-like silhouette on the far right, as in the reference mockup.
        self._draw_distant_silhouette(painter, w, h)

        water_y = h * 0.48
        water = QLinearGradient(0, water_y, 0, h)
        water.setColorAt(0.0, QColor(4, 20, 10, 65))
        water.setColorAt(0.5, QColor(4, 25, 13, 150))
        water.setColorAt(1.0, QColor(1, 7, 4, 225))
        painter.fillRect(QRectF(0, water_y, w, h - water_y), water)

        self._draw_mist(painter, w, h)
        self._draw_reeds(painter, w, h)
        self._draw_lilies(painter, w, h)
        self._draw_fireflies(painter, w, h)
        self._draw_ripples(painter, w, h)

        vignette = QRadialGradient(QPointF(w * 0.52, h * 0.46), max(w, h) * 0.80)
        vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
        vignette.setColorAt(0.72, QColor(0, 0, 0, 75))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 165))
        painter.fillRect(rect, vignette)
        painter.fillRect(rect, QColor(2, 10, 5, 42))

    def _draw_distant_silhouette(self, painter: QPainter, w: int, h: int) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(2, 7, 4, 118))
        base_x = w * 0.77
        base_y = h * 0.36
        path = QPainterPath(QPointF(base_x, base_y + h * 0.18))
        path.lineTo(base_x + w * 0.03, base_y + h * 0.03)
        path.lineTo(base_x + w * 0.05, base_y + h * 0.14)
        path.lineTo(base_x + w * 0.08, base_y)
        path.lineTo(base_x + w * 0.10, base_y + h * 0.15)
        path.lineTo(base_x + w * 0.14, base_y + h * 0.05)
        path.lineTo(base_x + w * 0.17, base_y + h * 0.19)
        path.lineTo(base_x + w * 0.19, base_y + h * 0.19)
        path.lineTo(base_x + w * 0.19, base_y + h * 0.24)
        path.lineTo(base_x, base_y + h * 0.24)
        path.closeSubpath()
        painter.drawPath(path)

    def _draw_mist(self, painter: QPainter, w: int, h: int) -> None:
        painter.setPen(Qt.NoPen)
        for x, y, rw, rh, alpha in (
            (0.18, 0.34, 0.34, 0.05, 30),
            (0.50, 0.39, 0.46, 0.06, 24),
            (0.72, 0.31, 0.36, 0.05, 22),
            (0.32, 0.62, 0.52, 0.05, 18),
        ):
            painter.setBrush(QColor(183, 242, 122, alpha))
            painter.drawEllipse(QRectF(w * x - w * rw / 2, h * y, w * rw, h * rh))

    def _draw_reeds(self, painter: QPainter, w: int, h: int) -> None:
        reed_color = QColor(44, 91, 45, 165)
        reed_tip = QColor(118, 98, 42, 160)
        painter.setPen(QPen(reed_color, max(2, w // 560), Qt.SolidLine, Qt.RoundCap))
        for side in (0.035, 0.07, 0.105, 0.885, 0.925, 0.965):
            base_x = w * side
            for idx in range(5):
                offset = (idx - 2) * w * 0.012
                top_x = base_x + offset * 1.8
                top_y = h * (0.22 + 0.07 * ((idx + int(side * 100)) % 3))
                path = QPainterPath(QPointF(base_x + offset, h * 0.83))
                path.cubicTo(base_x + offset * 0.4, h * 0.63, top_x, h * 0.48, top_x, top_y)
                painter.drawPath(path)
                painter.setBrush(reed_tip)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QRectF(top_x - 5, top_y - 18, 10, 34))
                painter.setPen(QPen(reed_color, max(2, w // 560), Qt.SolidLine, Qt.RoundCap))

    def _draw_lilies(self, painter: QPainter, w: int, h: int) -> None:
        lilies = (
            (0.09, 0.80, 0.14),
            (0.27, 0.72, 0.08),
            (0.61, 0.76, 0.10),
            (0.78, 0.66, 0.11),
            (0.88, 0.78, 0.16),
        )
        painter.setPen(QPen(QColor(143, 227, 136, 70), 1))
        for x, y, size in lilies:
            cx = w * x
            cy = h * y
            rx = w * size * 0.26
            ry = h * size * 0.10
            painter.setBrush(QColor(26, 83, 40, 174))
            painter.drawEllipse(QRectF(cx - rx, cy - ry, rx * 2, ry * 2))
            painter.setPen(QPen(QColor(183, 242, 122, 70), 2))
            painter.drawLine(QPointF(cx, cy), QPointF(cx + rx * 0.72, cy - ry * 0.42))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(234, 248, 216, 205))
            for petal in range(8):
                px = cx + (petal - 3.5) * rx * 0.08
                painter.drawEllipse(QRectF(px - rx * 0.055, cy - ry * 1.35, rx * 0.11, ry * 0.9))
            painter.setBrush(QColor(215, 184, 90, 220))
            painter.drawEllipse(QRectF(cx - rx * 0.05, cy - ry * 1.02, rx * 0.10, ry * 0.18))
            painter.setPen(QPen(QColor(143, 227, 136, 70), 1))

    def _draw_fireflies(self, painter: QPainter, w: int, h: int) -> None:
        painter.setPen(Qt.NoPen)
        points = (
            (0.08, 0.40), (0.16, 0.32), (0.24, 0.58), (0.36, 0.45),
            (0.47, 0.35), (0.58, 0.62), (0.67, 0.28), (0.78, 0.48),
            (0.88, 0.36), (0.93, 0.66), (0.18, 0.66), (0.73, 0.73),
        )
        for idx, (x, y) in enumerate(points):
            cx = w * x
            cy = h * y
            radius = 3 + (idx % 3)
            glow = QRadialGradient(QPointF(cx, cy), radius * 7)
            glow.setColorAt(0.0, QColor(215, 184, 90, 230))
            glow.setColorAt(0.35, QColor(183, 242, 122, 110))
            glow.setColorAt(1.0, QColor(183, 242, 122, 0))
            painter.setBrush(glow)
            painter.drawEllipse(QRectF(cx - radius * 7, cy - radius * 7, radius * 14, radius * 14))

    def _draw_ripples(self, painter: QPainter, w: int, h: int) -> None:
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(143, 227, 136, 52), 1))
        for x, y, rw in ((0.18, 0.83, 0.12), (0.44, 0.74, 0.10), (0.73, 0.82, 0.16), (0.86, 0.68, 0.12)):
            cx = w * x
            cy = h * y
            for step in range(3):
                painter.drawEllipse(QRectF(cx - w * rw * (step + 1) / 5, cy - h * 0.012 * (step + 1), w * rw * (step + 1) * 2 / 5, h * 0.024 * (step + 1)))


class _JabkaBackdropResizer(QObject):
    def __init__(self, shell: QWidget, backdrop: _JabkaBackdrop):
        super().__init__(shell)
        self.shell = shell
        self.backdrop = backdrop

    def eventFilter(self, obj, event):
        if obj is self.shell and event.type() in {QEvent.Resize, QEvent.Show, QEvent.LayoutRequest}:
            self.update_background()
        return False

    def update_background(self) -> None:
        size = self.shell.size()
        if size.width() <= 1 or size.height() <= 1:
            return
        self.backdrop.setGeometry(0, 0, size.width(), size.height())
        self.backdrop.lower()
        self.backdrop.show()
        self.backdrop.update()


def _apply_shell_background(shell: QWidget) -> None:
    if shell.property("jabka_background_applied"):
        resizer = getattr(shell, "_jabka_backdrop_resizer", None)
        if resizer is not None:
            resizer.update_background()
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
            QWidget#JabkaPaintedBackdrop, QLabel#JabkaPageBadge, QLabel#JabkaMascot, QLabel#JabkaSideFrog, QLabel#JabkaMenuCrown {{
                border-image: none;
            }}
            """
        )

    backdrop = _JabkaBackdrop(shell, "duty" if object_name == "DutyModeShell" else "home")
    resizer = _JabkaBackdropResizer(shell, backdrop)
    shell.installEventFilter(resizer)
    setattr(shell, "_jabka_backdrop", backdrop)
    setattr(shell, "_jabka_backdrop_resizer", resizer)
    shell.setProperty("jabka_background_applied", True)
    resizer.update_background()


def _pixmap_for_frog(frog_file: str, size: int) -> QPixmap:
    path = _resolve_asset(
        "frogs",
        frog_file,
        (frog_file.replace(".jpg", ".png"), frog_file.replace(".jpg", ".svg")),
    )
    pixmap = QPixmap(path) if path is not None else QPixmap()
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
        "background: rgba(4, 16, 8, 95);"
        "border: 1px solid rgba(183, 242, 122, 120);"
        "border-radius: 24px;"
        "padding: 8px;"
        "}"
    )


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


def _polish_home_buttons(menu: QWidget) -> None:
    for button in menu.findChildren(QPushButton):
        if button.property("jabka_home_button_done"):
            continue
        text = button.text().strip()
        clean_text = text.split("  ›", 1)[0].strip()
        icon = BUTTON_ICONS.get(clean_text, "🐸")
        button.setText(f"{icon}   {clean_text}                                      ›")
        button.setMinimumHeight(54)
        button.setStyleSheet(
            "QPushButton {"
            "text-align: left;"
            "padding-left: 22px;"
            "padding-right: 18px;"
            "border-radius: 12px;"
            "background: rgba(13, 42, 24, 210);"
            "border: 1px solid rgba(183, 242, 122, 135);"
            "color: #EAF8D8;"
            "font-weight: 800;"
            "}"
            "QPushButton:hover {"
            "background: rgba(45, 125, 58, 225);"
            "border: 1px solid #B7F27A;"
            "color: #F1FFE0;"
            "}"
            "QPushButton#PrimaryAction {"
            "background: rgba(45, 125, 58, 230);"
            "border: 1px solid #D7B85A;"
            "color: #F1FFE0;"
            "}"
        )
        button.setProperty("jabka_home_button_done", True)


class _JabkaHomeLayoutResizer(QObject):
    def __init__(self, shell: QWidget, menu: QWidget, frog: QLabel, title: QLabel | None, subtitle: QLabel | None, footer: QLabel | None, crown: QLabel):
        super().__init__(shell)
        self.shell = shell
        self.menu = menu
        self.frog = frog
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
        top = max(14, int(h * 0.03))
        left = max(28, int(w * 0.022))

        if self.title is not None:
            self.title.setGeometry(left, top, min(420, int(w * 0.38)), 58)
            self.title.raise_()
        if self.subtitle is not None:
            self.subtitle.setGeometry(left + 6, top + 58, min(900, int(w * 0.72)), 32)
            self.subtitle.raise_()

        menu_w = min(max(310, int(w * 0.24)), 430)
        menu_h = min(max(360, self.menu.sizeHint().height() + 60), int(h * 0.62))
        menu_x = int(w * 0.49 - menu_w / 2)
        menu_y = max(top + 115, int(h * 0.19))
        self.menu.setGeometry(menu_x, menu_y, menu_w, menu_h)
        self.menu.raise_()

        self.crown.setGeometry(menu_x + int(menu_w * 0.30), max(top + 98, menu_y - 40), int(menu_w * 0.40), 46)
        self.crown.raise_()

        frog_size = min(max(270, int(h * 0.36)), 420)
        frog_x = max(left + 35, int(w * 0.12))
        frog_y = max(top + 165, int(h * 0.36))
        self.frog.setGeometry(frog_x, frog_y, frog_size, frog_size)
        self.frog.raise_()

        if self.footer is not None:
            self.footer.setGeometry(left, h - 76, w - left * 2, 50)
            self.footer.raise_()


def _apply_home_scene(shell: QWidget) -> None:
    if shell.property("jabka_home_scene_done"):
        resizer = getattr(shell, "_jabka_home_layout_resizer", None)
        if resizer is not None:
            resizer.update_layout()
        return

    menu, title, subtitle, footer = _find_home_widgets(shell)
    if menu is None:
        return

    layout = shell.layout()
    if layout is not None:
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

    menu.setParent(shell)
    menu.setMaximumWidth(16777215)
    menu.setSizePolicy(menu.sizePolicy().horizontalPolicy(), menu.sizePolicy().verticalPolicy())
    menu.setStyleSheet(
        "QWidget#HomeMenuCard {"
        "background: rgba(4, 16, 8, 205);"
        "border: 1px solid rgba(215, 184, 90, 155);"
        "border-radius: 22px;"
        "}"
    )
    _polish_home_buttons(menu)

    if title is not None:
        title.setParent(shell)
        title.setText("Jabbix")
        title.setStyleSheet("QLabel#HomeTitle { color: #EAF8D8; font-size: 42px; font-weight: 900; padding: 0; }")
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

    frog = QLabel(shell)
    frog.setObjectName("JabkaMascot")
    frog.setAlignment(Qt.AlignCenter)
    pixmap = _pixmap_for_frog("frog_main.jpg", 420)
    if not pixmap.isNull():
        frog.setPixmap(pixmap)
    _style_art_label(frog)

    crown = QLabel("♕")
    crown.setParent(shell)
    crown.setObjectName("JabkaMenuCrown")
    crown.setAlignment(Qt.AlignCenter)
    crown.setStyleSheet(
        "QLabel#JabkaMenuCrown {"
        "background: rgba(4, 16, 8, 190);"
        "border: 1px solid rgba(215, 184, 90, 165);"
        "border-radius: 18px;"
        "color: #D7B85A;"
        "font-size: 28px;"
        "font-weight: 900;"
        "}"
    )

    resizer = _JabkaHomeLayoutResizer(shell, menu, frog, title, subtitle, footer, crown)
    shell.installEventFilter(resizer)
    setattr(shell, "_jabka_home_layout_resizer", resizer)
    shell.setProperty("jabka_home_scene_done", True)
    resizer.update_layout()


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
                if object_name in {"HomeShell", "DutyModeShell"}:
                    _apply_shell_background(widget)
                if object_name == "HomeShell":
                    _apply_home_scene(widget)
                elif object_name in PAGE_HINTS:
                    _decorate_named_shell(widget, PAGE_HINTS[object_name])
                if object_name == "DutyModeShell":
                    _add_side_frog(widget, PAGE_FROGS[object_name], 300)
                if object_name in {"HomeMenuCard", "MenuCard"}:
                    widget.setProperty("jabka_card", True)
                if object_name in {"PrimaryAction", "SecondaryAction"}:
                    widget.setCursor(Qt.PointingHandCursor)
        except Exception:
            pass

    polish_once()
    QTimer.singleShot(350, polish_once)
    QTimer.singleShot(1200, polish_once)
