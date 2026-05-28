from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


THEMES = {
    "light_standard": {
        "label": "Светлая стандартная",
        "bg_main": "#f3f4f6",
        "bg_panel": "#ffffff",
        "bg_panel2": "#eef2f7",
        "bg_card": "#ffffff",
        "bg_card2": "#f9fafb",
        "bg_field": "#ffffff",
        "text": "#111827",
        "text_soft": "#4b5563",
        "text_title": "#111827",
        "accent": "#3b82f6",
        "accent2": "#2563eb",
        "danger": "#dc2626",
        "danger_bg": "#fef2f2",
        "scroll": "#d1d5db",
        "selected": "#dbeafe",
        "hud_text": "#374151",
        "border_dark": "#d1d5db",
    },
    "simple_dark": {
        "label": "Simple Dark",
        "bg_main": "#121212",
        "bg_panel": "#1b1b1b",
        "bg_panel2": "#222222",
        "bg_card": "#1e1e1e",
        "bg_card2": "#2a2a2a",
        "bg_field": "#181818",
        "text": "#e6e6e6",
        "text_soft": "#b8b8b8",
        "text_title": "#ffffff",
        "accent": "#5c8fd6",
        "accent2": "#7fb0f0",
        "danger": "#e57373",
        "danger_bg": "#2a1717",
        "scroll": "#4a4a4a",
        "selected": "#303a46",
        "hud_text": "#d0d0d0",
        "border_dark": "#333333",
    },
    "mass_effect": {
        "label": "Mass Effect HUD",
        "bg_main": "#020914",
        "bg_panel": "#031126",
        "bg_panel2": "#061a36",
        "bg_card": "#06152d",
        "bg_card2": "#102b54",
        "bg_field": "#031329",
        "text": "#d7e8ff",
        "text_soft": "#8fc7ff",
        "text_title": "#ffffff",
        "accent": "#2a7ed6",
        "accent2": "#58aaff",
        "danger": "#ff6570",
        "danger_bg": "#190b18",
        "scroll": "#14599e",
        "selected": "#123e75",
        "hud_text": "#9fd0ff",
        "border_dark": "#0d3d78",
    },
    "cerberus_red": {
        "label": "Cerberus Red",
        "bg_main": "#120607",
        "bg_panel": "#1c0b0d",
        "bg_panel2": "#2a1115",
        "bg_card": "#241012",
        "bg_card2": "#39171c",
        "bg_field": "#1a0a0c",
        "text": "#ffe6e6",
        "text_soft": "#ffb0b6",
        "text_title": "#ffffff",
        "accent": "#d04657",
        "accent2": "#ff7485",
        "danger": "#ff9e47",
        "danger_bg": "#2a1607",
        "scroll": "#a63e4c",
        "selected": "#5a1d28",
        "hud_text": "#ffc8cd",
        "border_dark": "#6f2230",
    },
    "matrix_green": {
        "label": "Matrix Green",
        "bg_main": "#030805",
        "bg_panel": "#07120b",
        "bg_panel2": "#0d1d14",
        "bg_card": "#0a160f",
        "bg_card2": "#12311f",
        "bg_field": "#08130d",
        "text": "#dfffe8",
        "text_soft": "#8ff5b0",
        "text_title": "#ffffff",
        "accent": "#2fbf71",
        "accent2": "#7dffb0",
        "danger": "#d7ff67",
        "danger_bg": "#1e2808",
        "scroll": "#2a8f57",
        "selected": "#163923",
        "hud_text": "#b7ffd0",
        "border_dark": "#1f6f42",
    },
    "omega_purple": {
        "label": "Omega Purple",
        "bg_main": "#090512",
        "bg_panel": "#130a25",
        "bg_panel2": "#231241",
        "bg_card": "#160d2d",
        "bg_card2": "#29184f",
        "bg_field": "#120922",
        "text": "#f0e6ff",
        "text_soft": "#caa8ff",
        "text_title": "#ffffff",
        "accent": "#8b56e2",
        "accent2": "#bb8cff",
        "danger": "#ff7cd2",
        "danger_bg": "#2a0b21",
        "scroll": "#7a46c8",
        "selected": "#372061",
        "hud_text": "#e0cfff",
        "border_dark": "#5e2ea7",
    },
    "amber_ops": {
        "label": "Amber Ops",
        "bg_main": "#110b03",
        "bg_panel": "#201406",
        "bg_panel2": "#362109",
        "bg_card": "#261807",
        "bg_card2": "#4a2e0d",
        "bg_field": "#1a1004",
        "text": "#fff1db",
        "text_soft": "#ffcf88",
        "text_title": "#ffffff",
        "accent": "#d68b22",
        "accent2": "#ffb347",
        "danger": "#ff6e40",
        "danger_bg": "#2b1307",
        "scroll": "#b36c16",
        "selected": "#5c3810",
        "hud_text": "#ffd9a6",
        "border_dark": "#8f5512",
    },
}


def get_available_themes():
    return [(name, info["label"]) for name, info in THEMES.items()]


def _theme(theme_name: str) -> dict:
    return THEMES.get(theme_name, THEMES["mass_effect"])


def build_palette(theme_name: str) -> QPalette:
    p = _theme(theme_name)

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(p["bg_main"]))
    palette.setColor(QPalette.WindowText, QColor(p["text"]))
    palette.setColor(QPalette.Base, QColor(p["bg_field"]))
    palette.setColor(QPalette.AlternateBase, QColor(p["bg_card"]))
    palette.setColor(QPalette.ToolTipBase, QColor(p["bg_card"]))
    palette.setColor(QPalette.ToolTipText, QColor(p["text"]))
    palette.setColor(QPalette.Text, QColor(p["text"]))
    palette.setColor(QPalette.Button, QColor(p["bg_card"]))
    palette.setColor(QPalette.ButtonText, QColor(p["text_title"]))
    palette.setColor(QPalette.BrightText, QColor(p["danger"]))
    palette.setColor(QPalette.Highlight, QColor(p["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor(p["text_title"]))
    return palette


def build_stylesheet(theme_name: str) -> str:
    p = _theme(theme_name)

    return f"""
    * {{
        font-family: "DejaVu Sans", "Segoe UI", "Ubuntu", sans-serif;
        color: {p['text']};
        selection-background-color: {p['accent']};
        selection-color: {p['text_title']};
    }}

    QMainWindow, QWidget {{
        background-color: {p['bg_main']};
    }}

    QMainWindow {{
        border: 1px solid {p['border_dark']};
    }}

    QLabel {{
        color: {p['text']};
        background: transparent;
    }}

    QLabel#AppTitle {{
        color: {p['text_title']};
        font-size: 22px;
        font-weight: bold;
        padding-right: 18px;
    }}

    QLabel#PageTitle {{
        color: {p['text_title']};
        font-size: 18px;
        font-weight: bold;
        padding: 4px;
    }}

    QWidget#BottomHud {{
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 {p['bg_panel']},
            stop:0.5 {p['bg_panel2']},
            stop:1 {p['bg_panel']}
        );
        border-top: 1px solid {p['scroll']};
        border-left: 1px solid {p['border_dark']};
        border-right: 1px solid {p['border_dark']};
        border-bottom: 1px solid {p['border_dark']};
    }}

    QWidget#BottomHud QLabel {{
        color: {p['hud_text']};
        font-weight: bold;
        padding: 3px 10px;
        border-left: 1px solid {p['scroll']};
    }}

    QToolBar {{
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 {p['bg_panel']},
            stop:0.45 {p['bg_panel2']},
            stop:1 {p['bg_panel']}
        );
        border: 1px solid {p['scroll']};
        border-bottom: 2px solid {p['accent']};
        spacing: 10px;
        padding: 10px;
    }}

    QToolBar QLabel {{
        color: {p['text_soft']};
        font-weight: bold;
        letter-spacing: 0.5px;
    }}

    QLabel#ProblemCounterLabel {{
        color: {p['danger']};
        font-weight: bold;
        font-size: 15px;
        padding: 6px 14px;
        border: 1px solid {p['danger']};
        border-radius: 7px;
        background-color: {p['danger_bg']};
    }}

    QStatusBar {{
        background-color: {p['bg_panel']};
        border-top: 1px solid {p['scroll']};
        color: {p['text_soft']};
        padding: 4px;
    }}

    QComboBox {{
        background-color: {p['bg_field']};
        color: {p['text_title']};
        border: 1px solid {p['accent']};
        border-radius: 6px;
        padding: 7px 28px 7px 10px;
        min-height: 24px;
        font-size: 14px;
    }}

    QComboBox:hover {{
        border: 1px solid {p['accent2']};
        background-color: {p['bg_card2']};
    }}

    QComboBox:focus {{
        border: 1px solid {p['danger']};
    }}

    QComboBox::drop-down {{
        border: 0px;
        width: 28px;
        background-color: transparent;
    }}

    QComboBox::down-arrow {{
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 7px solid {p['accent2']};
        width: 0px;
        height: 0px;
        margin-right: 8px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {p['bg_card']};
        color: {p['text']};
        border: 1px solid {p['accent']};
        selection-background-color: {p['selected']};
        selection-color: {p['text_title']};
        outline: 0;
        padding: 4px;
    }}

    QPushButton, QToolButton {{
        background-color: {p['bg_card']};
        color: {p['text_title']};
        border: 1px solid {p['accent']};
        border-radius: 7px;
        padding: 8px 16px;
        font-weight: bold;
        min-height: 24px;
    }}

    QPushButton:hover, QToolButton:hover {{
        background-color: {p['bg_card2']};
        border: 1px solid {p['accent2']};
    }}

    QPushButton:pressed, QToolButton:pressed {{
        background-color: {p['selected']};
        border: 1px solid {p['danger']};
    }}

    QPushButton:disabled, QToolButton:disabled {{
        color: {p['text_soft']};
        border: 1px solid {p['border_dark']};
        background-color: {p['bg_field']};
    }}

    QToolBar QPushButton[text="Обновить"] {{
        border: 1px solid {p['danger']};
        background-color: {p['danger_bg']};
        color: {p['text_title']};
    }}

    QMenu {{
        background-color: {p['bg_card']};
        border: 1px solid {p['accent']};
        padding: 6px;
    }}

    QMenu::item {{
        padding: 8px 28px 8px 18px;
        color: {p['text']};
        background-color: transparent;
    }}

    QMenu::item:selected {{
        background-color: {p['selected']};
        color: {p['text_title']};
        border-left: 3px solid {p['danger']};
    }}

    QMenu::separator {{
        height: 1px;
        background: {p['scroll']};
        margin: 6px 4px;
    }}

    QFrame, QGroupBox, QWidget#GraphCard {{
        background-color: {p['bg_panel']};
        border: 1px solid {p['scroll']};
        border-radius: 10px;
    }}

    QGroupBox {{
        color: {p['text_soft']};
        font-weight: bold;
        margin-top: 16px;
        padding: 10px;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: {p['text_soft']};
        background-color: {p['bg_main']};
    }}

    QLineEdit, QTextEdit, QPlainTextEdit {{
        background-color: {p['bg_field']};
        color: {p['text_title']};
        border: 1px solid {p['accent']};
        border-radius: 6px;
        padding: 7px;
    }}

    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border: 1px solid {p['danger']};
        background-color: {p['bg_panel']};
    }}

    QCheckBox {{
        color: {p['text']};
        spacing: 8px;
    }}

    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {p['accent']};
        border-radius: 3px;
        background-color: {p['bg_field']};
    }}

    QCheckBox::indicator:checked {{
        background-color: {p['accent']};
        border: 1px solid {p['accent2']};
    }}

    QScrollArea {{
        border: 0px;
        background-color: {p['bg_main']};
    }}

    QScrollBar:vertical {{
        background: {p['bg_main']};
        width: 12px;
        margin: 0;
    }}

    QScrollBar::handle:vertical {{
        background: {p['scroll']};
        border-radius: 5px;
        min-height: 28px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {p['accent2']};
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QTableWidget {{
        background-color: {p['bg_panel']};
        alternate-background-color: {p['bg_card']};
        gridline-color: {p['scroll']};
        border: 1px solid {p['scroll']};
        color: {p['text']};
    }}

    QHeaderView::section {{
        background-color: {p['bg_card']};
        color: {p['text_soft']};
        border: 1px solid {p['scroll']};
        padding: 6px;
        font-weight: bold;
    }}

    QTabWidget::pane {{
        border: 1px solid {p['scroll']};
        background: {p['bg_main']};
    }}

    QTabBar::tab {{
        background: {p['bg_card']};
        color: {p['text']};
        border: 1px solid {p['scroll']};
        padding: 8px 12px;
        margin-right: 2px;
        border-top-left-radius: 5px;
        border-top-right-radius: 5px;
    }}

    QTabBar::tab:selected {{
        background: {p['selected']};
        border-bottom-color: {p['selected']};
        color: {p['text_title']};
    }}

    QMessageBox, QFileDialog {{
        background-color: {p['bg_main']};
    }}
    """


def apply_theme(app, theme_name: str = "mass_effect"):
    if app is None:
        app = QApplication.instance()

    theme_name = theme_name if theme_name in THEMES else "mass_effect"

    try:
        app.setStyle("Fusion")
    except Exception:
        pass

    app.setPalette(build_palette(theme_name))
    app.setStyleSheet(build_stylesheet(theme_name))

    # Принудительно переполируем уже созданные виджеты,
    # чтобы тема применялась к кнопкам, полям и меню сразу.
    for widget in app.allWidgets():
        try:
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        except Exception:
            pass
