from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer, Qt, QUrl
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractScrollArea, QLabel, QPushButton, QSizePolicy, QWidget

try:
    from PySide6.QtWidgets import QFrame
except Exception:  # pragma: no cover - defensive for unusual Qt builds
    QFrame = None

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QSoundEffect
except Exception:  # pragma: no cover - sound is optional
    QAudioOutput = None
    QMediaPlayer = None
    QSoundEffect = None

from app.jabka_theme import apply_text_overrides, is_jabka_config, theme_asset_path


# The main wallpaper already contains the swamp, frog and decorative menu frame.
# Runtime must place ONLY real Qt buttons over that baked-in frame.
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

FROG_SOUND_FILES = (
    "frog_croak.wav",
    "frog_croak.mp3",
    "frog_croak.ogg",
    "croak.wav",
    "croak.mp3",
    "croak.ogg",
    "kwak.wav",
    "kwak.mp3",
    "kwak.ogg",
)

_READABLE_PANEL_QSS = """
QWidget#HomeShell QWidget#HomeMenuCard,
QWidget#HomeShell QFrame#HomeMenuCard {
    background: transparent;
    background-color: transparent;
    border: 0px solid transparent;
    border-radius: 0;
    margin: 0;
    padding: 0;
}
QWidget#DutyModeShell QFrame,
QWidget#DutyModeShell QGroupBox {
    background: rgba(4, 16, 8, 118);
    border: 1px solid rgba(183, 242, 122, 120);
    border-radius: 16px;
}
QWidget#DutyModeShell QPushButton,
QWidget#DutyModeShell QToolButton {
    background: rgba(8, 28, 15, 176);
    border: 1px solid rgba(183, 242, 122, 135);
    border-radius: 12px;
    color: #EAF8D8;
}
QWidget#DutyModeShell QPushButton:hover,
QWidget#DutyModeShell QToolButton:hover {
    background: rgba(45, 125, 58, 210);
    border: 1px solid #B7F27A;
}
QWidget#DutyModeShell QLineEdit,
QWidget#DutyModeShell QTextEdit,
QWidget#DutyModeShell QPlainTextEdit,
QWidget#DutyModeShell QComboBox {
    background: rgba(4, 16, 8, 120);
    border: 1px solid rgba(183, 242, 122, 110);
    border-radius: 10px;
}
QWidget#DutyModeShell QTableWidget,
QWidget#DutyModeShell QTreeWidget,
QWidget#DutyModeShell QListWidget {
    background: rgba(3, 12, 6, 178);
    alternate-background-color: rgba(12, 37, 20, 158);
    border: 1px solid rgba(183, 242, 122, 110);
    border-radius: 13px;
}
QLabel#JabkaBackgroundLayer,
QLabel#JabkaCellBackgroundLayer {
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


def _resolve_sound_asset() -> Path | None:
    for folder in ("sounds", "audio", "sfx", "backgrounds"):
        for filename in FROG_SOUND_FILES:
            path = _resolve_asset(folder, filename)
            if path is not None:
                return path
    return None


def _cover_pixmap(source: QPixmap, target_size, overlay_alpha: int) -> QPixmap:
    scaled = source.scaled(target_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    result = scaled.copy(
        max(0, (scaled.width() - target_size.width()) // 2),
        max(0, (scaled.height() - target_size.height()) // 2),
        target_size.width(),
        target_size.height(),
    )
    if overlay_alpha > 0:
        painter = QPainter(result)
        painter.fillRect(result.rect(), QColor(2, 10, 5, overlay_alpha))
        painter.end()
    return result


class _JabkaBackgroundResizer(QObject):
    def __init__(self, target: QWidget, label: QLabel, pixmap: QPixmap, overlay_alpha: int = 0):
        super().__init__(target)
        self.target = target
        self.label = label
        self.pixmap = pixmap
        self.overlay_alpha = overlay_alpha
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
            self.label.setPixmap(_cover_pixmap(self.pixmap, size, self.overlay_alpha))
            self._last_size = size
        self.label.lower()
        self.label.show()


def _install_background_layer(target: QWidget, path: Path, property_name: str, overlay_alpha: int, object_name: str) -> None:
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
    label.setObjectName(object_name)
    label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    label.setScaledContents(False)
    label.setAlignment(Qt.AlignCenter)

    resizer = _JabkaBackgroundResizer(target, label, pixmap, overlay_alpha=overlay_alpha)
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
    _install_background_layer(shell, path, "jabka_page_background", overlay_alpha=0, object_name="JabkaBackgroundLayer")


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
    if widget.objectName() in {"JabkaBackgroundLayer", "JabkaCellBackgroundLayer"}:
        return False
    if _is_webengine_widget(widget) or _has_cell_background_ancestor(widget, shell):
        return False
    if isinstance(widget, (QPushButton, QLabel, QAbstractScrollArea)):
        return False
    if widget.__class__.__name__ not in {"QFrame", "QGroupBox"}:
        return False
    size = widget.size()
    return size.width() * size.height() >= MIN_CELL_BACKGROUND_AREA


def _make_cell_translucent(widget: QWidget) -> None:
    if widget.property("jabka_cell_translucent"):
        return
    object_name = widget.objectName() or f"jabka_cell_{id(widget)}"
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
    _install_background_layer(widget, path, "jabka_cell_background", overlay_alpha=105, object_name="JabkaCellBackgroundLayer")


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
        _apply_cell_background(widget, _choose_cell_background(widget, applied))
        if widget.property("jabka_cell_background_applied"):
            applied += 1

    if applied > 0:
        shell.setProperty("jabka_cell_background_pass_done", True)


def _find_home_widgets(shell: QWidget):
    menu = None
    title = None
    subtitle = None
    footer = None
    for widget in _safe_widgets(shell):
        object_name = widget.objectName()
        if object_name == "HomeMenuCard" and menu is None:
            menu = widget
        elif object_name == "HomeTitle" and isinstance(widget, QLabel):
            title = widget
        elif object_name == "AppFooter" and isinstance(widget, QLabel):
            footer = widget
        elif isinstance(widget, QLabel) and "выбери нужный раздел" in widget.text().lower():
            subtitle = widget
    return menu, title, subtitle, footer


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
        "QWidget#HomeMenuCard, QFrame#HomeMenuCard {"
        "background: transparent; background-color: transparent;"
        "border: 0px solid transparent; border-radius: 0; padding: 0; margin: 0;"
        "}"
    )


def _extract_home_buttons(shell: QWidget, menu: QWidget) -> list[QPushButton]:
    buttons = getattr(shell, "_jabka_absolute_home_buttons", None)
    if isinstance(buttons, list) and buttons and all(isinstance(button, QPushButton) for button in buttons):
        return buttons

    buttons = menu.findChildren(QPushButton)
    buttons.sort(key=lambda button: (button.geometry().y(), button.geometry().x()))
    for button in buttons:
        button.setParent(shell)
        button.show()
        button.raise_()

    _make_menu_container_transparent(menu)
    menu.hide()
    setattr(shell, "_jabka_absolute_home_buttons", buttons)
    return buttons


def _polish_home_buttons(buttons: list[QPushButton]) -> None:
    for button in buttons:
        clean_text = _clean_button_text(button.text())
        icon = BUTTON_ICONS.get(clean_text, "🐸")
        button.setText(f"{icon}   {clean_text}")
        button.setMinimumHeight(60)
        button.setMaximumHeight(68)
        button.setMinimumWidth(500)
        button.setMaximumWidth(620)
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(
            "QPushButton {"
            "text-align: left;"
            "padding-left: 38px; padding-right: 22px;"
            "border-radius: 17px;"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 rgba(9, 39, 17, 212), stop:0.55 rgba(6, 25, 12, 185), stop:1 rgba(3, 13, 7, 164));"
            "border: 1px solid rgba(151, 232, 128, 175);"
            "color: #F0F9DC; font-size: 19px; font-weight: 900;"
            "}"
            "QPushButton:hover {"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 rgba(55, 143, 67, 230), stop:0.55 rgba(24, 79, 36, 214), stop:1 rgba(7, 31, 15, 188));"
            "border: 1px solid #D7B85A; color: #F7FFE8;"
            "}"
            "QPushButton#PrimaryAction {"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 rgba(69, 155, 76, 238), stop:0.58 rgba(47, 126, 59, 226), stop:1 rgba(16, 58, 26, 206));"
            "border: 1px solid #D7B85A; color: #FBFFE8;"
            "}"
        )
        button.show()
        button.raise_()


def _frog_dialog_text(subtitle: QLabel | None) -> str:
    fallback = "Выбери нужный раздел настроек или перейди в режим жабича."
    try:
        source = subtitle.text().strip() if subtitle is not None else fallback
    except Exception:
        source = fallback
    source = source.replace("Мое болото:", "").strip()
    if not source:
        source = fallback
    return f"🐸 Ква!\n{source}"


def _prepare_frog_sound(shell: QWidget) -> None:
    if shell.property("jabka_frog_sound_prepared"):
        return
    shell.setProperty("jabka_frog_sound_prepared", True)

    path = _resolve_sound_asset()
    if path is None:
        return

    suffix = path.suffix.lower()
    if QSoundEffect is not None and suffix in {".wav", ".ogg"}:
        try:
            sound = QSoundEffect(shell)
            sound.setSource(QUrl.fromLocalFile(str(path.resolve())))
            sound.setVolume(0.65)
            setattr(shell, "_jabka_frog_sound_effect", sound)
            return
        except Exception:
            pass

    if QMediaPlayer is not None and QAudioOutput is not None:
        try:
            player = QMediaPlayer(shell)
            audio = QAudioOutput(shell)
            audio.setVolume(0.65)
            player.setAudioOutput(audio)
            player.setSource(QUrl.fromLocalFile(str(path.resolve())))
            setattr(shell, "_jabka_frog_sound_player", player)
            setattr(shell, "_jabka_frog_sound_audio", audio)
        except Exception:
            pass


def _play_frog_sound(shell: QWidget) -> None:
    sound = getattr(shell, "_jabka_frog_sound_effect", None)
    if sound is not None:
        try:
            if sound.isPlaying():
                sound.stop()
            sound.play()
            return
        except Exception:
            pass

    player = getattr(shell, "_jabka_frog_sound_player", None)
    if player is not None:
        try:
            player.setPosition(0)
            player.play()
        except Exception:
            pass


def _hide_frog_dialog(shell: QWidget) -> None:
    bubble = getattr(shell, "_jabka_frog_dialog", None)
    tail = getattr(shell, "_jabka_frog_dialog_tail", None)
    if isinstance(bubble, QLabel):
        bubble.hide()
    if isinstance(tail, QLabel):
        tail.hide()


def _show_frog_dialog(shell: QWidget) -> None:
    bubble = getattr(shell, "_jabka_frog_dialog", None)
    tail = getattr(shell, "_jabka_frog_dialog_tail", None)
    if not isinstance(bubble, QLabel):
        return

    bubble.show()
    bubble.raise_()
    if isinstance(tail, QLabel):
        tail.show()
        tail.raise_()

    _play_frog_sound(shell)

    timer = getattr(shell, "_jabka_frog_dialog_hide_timer", None)
    if not isinstance(timer, QTimer):
        timer = QTimer(shell)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: _hide_frog_dialog(shell))
        setattr(shell, "_jabka_frog_dialog_hide_timer", timer)
    timer.start(7000)


def _ensure_frog_interaction(shell: QWidget, subtitle: QLabel | None) -> None:
    bubble = getattr(shell, "_jabka_frog_dialog", None)
    hotspot = getattr(shell, "_jabka_frog_hotspot", None)
    if isinstance(bubble, QLabel) and isinstance(hotspot, QPushButton):
        _prepare_frog_sound(shell)
        return

    bubble = QLabel(shell)
    bubble.setObjectName("JabkaFrogDialog")
    bubble.setWordWrap(True)
    bubble.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    bubble.setText(_frog_dialog_text(subtitle))
    bubble.setStyleSheet(
        "QLabel#JabkaFrogDialog {"
        "background: rgba(4, 17, 8, 222);"
        "border: 1px solid rgba(215, 184, 90, 210);"
        "border-radius: 22px;"
        "padding: 14px 20px;"
        "color: #F3FFE4;"
        "font-size: 17px;"
        "font-weight: 900;"
        "}"
    )
    bubble.hide()

    tail = QLabel(shell)
    tail.setObjectName("JabkaFrogDialogTail")
    tail.setText("▾")
    tail.setAlignment(Qt.AlignCenter)
    tail.setStyleSheet(
        "QLabel#JabkaFrogDialogTail {"
        "background: transparent; border: none; color: #D7B85A;"
        "font-size: 44px; font-weight: 900;"
        "}"
    )
    tail.hide()

    hotspot = QPushButton(shell)
    hotspot.setObjectName("JabkaFrogHotspot")
    hotspot.setText("")
    hotspot.setCursor(Qt.PointingHandCursor)
    hotspot.setToolTip("Кликни жабку")
    hotspot.setFlat(True)
    hotspot.setStyleSheet(
        "QPushButton#JabkaFrogHotspot {"
        "background: transparent; border: 0px solid transparent;"
        "}"
        "QPushButton#JabkaFrogHotspot:hover {"
        "background: rgba(183, 242, 122, 18); border: 1px solid rgba(215, 184, 90, 55);"
        "border-radius: 22px;"
        "}"
    )
    hotspot.clicked.connect(lambda: _show_frog_dialog(shell))
    hotspot.show()

    setattr(shell, "_jabka_frog_dialog", bubble)
    setattr(shell, "_jabka_frog_dialog_tail", tail)
    setattr(shell, "_jabka_frog_hotspot", hotspot)
    _prepare_frog_sound(shell)


class _JabkaHomeLayoutResizer(QObject):
    def __init__(self, shell: QWidget, menu: QWidget, buttons: list[QPushButton], title: QLabel | None, subtitle: QLabel | None, footer: QLabel | None):
        super().__init__(shell)
        self.shell = shell
        self.menu = menu
        self.buttons = buttons
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
            self.subtitle.hide()

        frog_x = int(w * 0.162)
        frog_y = int(h * 0.300)
        frog_w = min(max(300, int(w * 0.215)), 455)
        frog_h = min(max(275, int(h * 0.330)), 385)
        hotspot = getattr(self.shell, "_jabka_frog_hotspot", None)
        if isinstance(hotspot, QPushButton):
            hotspot.setGeometry(frog_x, frog_y, frog_w, frog_h)
            hotspot.show()
            hotspot.raise_()

        dialog_w = min(max(430, int(w * 0.285)), 590)
        dialog_h = min(max(104, int(h * 0.108)), 130)
        dialog_x = int(w * 0.315)
        dialog_y = int(h * 0.215)
        bubble = getattr(self.shell, "_jabka_frog_dialog", None)
        tail = getattr(self.shell, "_jabka_frog_dialog_tail", None)
        if isinstance(bubble, QLabel):
            bubble.setGeometry(dialog_x, dialog_y, dialog_w, dialog_h)
            if bubble.isVisible():
                bubble.raise_()
        if isinstance(tail, QLabel):
            tail.setGeometry(dialog_x + int(dialog_w * 0.16), dialog_y + dialog_h - 13, 54, 48)
            if tail.isVisible():
                tail.raise_()

        # Buttons are placed directly on the baked right-side menu frame.
        # These coordinates are intentionally absolute relative to HomeShell,
        # because the source HomeMenuCard layout keeps fighting setGeometry().
        button_w = min(max(520, int(w * 0.285)), 610)
        button_h = min(max(58, int(h * 0.058)), 68)
        button_x = int(w * 0.492)
        button_y = int(h * 0.255)
        gap = max(13, int(h * 0.017))

        self.menu.hide()
        for index, button in enumerate(self.buttons):
            button.setGeometry(button_x, button_y + index * (button_h + gap), button_w, button_h)
            button.show()
            button.raise_()

        if self.footer is not None:
            self.footer.setGeometry(left, h - 76, w - left * 2, 46)
            self.footer.raise_()


def _apply_home_scene(shell: QWidget) -> None:
    _hide_layout_mascots(shell)
    menu, title, subtitle, footer = _find_home_widgets(shell)
    if menu is None:
        return

    buttons = _extract_home_buttons(shell, menu)
    if not buttons:
        return

    _ensure_frog_interaction(shell, subtitle)

    if shell.property("jabka_home_scene_done"):
        _make_menu_container_transparent(menu)
        _polish_home_buttons(buttons)
        if subtitle is not None:
            subtitle.hide()
        resizer = getattr(shell, "_jabka_home_layout_resizer", None)
        if resizer is not None:
            resizer.update_layout()
        return

    layout = shell.layout()
    if layout is not None:
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

    _make_menu_container_transparent(menu)
    _polish_home_buttons(buttons)

    if title is not None:
        title.setParent(shell)
        title.setText("Jabbix")
        title.setStyleSheet(
            "QLabel#HomeTitle {"
            "background: transparent; border: none; color: #EAF8D8;"
            "font-size: 42px; font-weight: 900; padding-left: 14px;"
            "}"
        )
    if subtitle is not None:
        subtitle.setParent(shell)
        subtitle.hide()
    if footer is not None:
        footer.setParent(shell)
        footer.setStyleSheet(
            "QLabel#AppFooter { background: rgba(4, 16, 8, 130); border: 1px solid rgba(183, 242, 122, 95);"
            "border-radius: 10px; padding: 5px; color: #A9C89C; font-size: 11px; }"
        )

    resizer = _JabkaHomeLayoutResizer(shell, menu, buttons, title, subtitle, footer)
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
