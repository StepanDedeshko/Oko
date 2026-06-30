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

    "white_1": {
        "label": "White-1",
        "bg_main": "#f5faff",
        "bg_panel": "#ffffff",
        "bg_panel2": "#edf7ff",
        "bg_card": "#ffffff",
        "bg_card2": "#e7f7ff",
        "bg_field": "#f8fcff",
        "text": "#132238",
        "text_soft": "#607083",
        "text_title": "#091827",
        "accent": "#17bce3",
        "accent2": "#0a84d8",
        "danger": "#e05b65",
        "danger_bg": "#fff1f3",
        "success": "#24b97a",
        "success_bg": "#e9fff5",
        "scroll": "#bed8e8",
        "selected": "#d9f4ff",
        "hud_text": "#28677f",
        "border_dark": "#b9d7e7",
        "glass": "rgba(255, 255, 255, 0.82)",
        "glass2": "rgba(233, 248, 255, 0.72)",
        "overlay": "rgba(247, 252, 255, 0.92)",
        "shadow": "#d5e8f2",
    },
    "dark_1": {
        "label": "Dark-1",
        "bg_main": "#070b13",
        "bg_panel": "#101722",
        "bg_panel2": "#162130",
        "bg_card": "#111a27",
        "bg_card2": "#1b2a3a",
        "bg_field": "#0c121c",
        "text": "#e8f0f6",
        "text_soft": "#9fb0c0",
        "text_title": "#ffffff",
        "accent": "#e14b56",
        "accent2": "#ff6b72",
        "danger": "#ff4f62",
        "danger_bg": "#351018",
        "success": "#44d39a",
        "success_bg": "#0e2b25",
        "scroll": "#344757",
        "selected": "#34202a",
        "hud_text": "#ffabb0",
        "border_dark": "#354458",
        "glass": "rgba(16, 23, 34, 0.82)",
        "glass2": "rgba(27, 42, 58, 0.68)",
        "overlay": "rgba(8, 13, 22, 0.92)",
        "shadow": "#04070c",
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
    """ + _build_nextgen_stylesheet(theme_name, p)



def _build_nextgen_stylesheet(theme_name: str, p: dict) -> str:
    if theme_name not in {"white_1", "dark_1"}:
        return ""

    primary_text = "#ffffff" if theme_name == "dark_1" else "#062033"
    subtle_button_text = p["text_title"]
    graph_page_bg = "#ffffff" if theme_name == "white_1" else "#0b0b0b"
    graph_card_bg = "#ffffff" if theme_name == "white_1" else "#101722"
    graph_area_bg = "#f5faff" if theme_name == "white_1" else "#070b13"
    return f"""
    QWidget {{
        background-color: {p['bg_main']};
    }}

    QMainWindow {{
        border: 1px solid {p['border_dark']};
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['bg_main']}, stop:0.55 {p['bg_panel']}, stop:1 {p['bg_panel2']});
    }}

    QToolBar, QWidget#BottomHud, QStatusBar {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {p['glass']}, stop:0.52 {p['glass2']}, stop:1 {p['glass']});
        border: 1px solid {p['border_dark']};
        border-radius: 14px;
        padding: 10px;
    }}

    QWidget#BottomHud QLabel {{
        border-left: 1px solid {p['border_dark']};
        color: {p['hud_text']};
    }}

    QLabel#HomeTitle {{
        color: {p['text_title']};
        font-size: 28px;
        font-weight: 800;
        padding: 10px 4px 4px 4px;
        letter-spacing: 1px;
    }}

    QLabel#PageTitle {{
        color: {p['text_title']};
        font-size: 18px;
        font-weight: 800;
        padding: 6px 2px;
    }}

    QLabel#ThemeLogo {{
        background: {p['glass2']};
        border: 1px solid {p['accent']};
        border-radius: 12px;
        padding: 3px;
    }}

    QFrame, QGroupBox {{
        background: {p['bg_panel']};
        border: 1px solid {p['border_dark']};
        border-radius: 18px;
    }}

    QWidget#DutyStatePanel, QDialog#DutyNotificationDialog {{
        background: {p['glass']};
        border: 1px solid {p['border_dark']};
        border-radius: 18px;
    }}

    QWidget#GraphCheckOverlayPanel {{
        background: {p['bg_panel']};
        border: 1px solid {p['border_dark']};
        border-radius: 18px;
    }}

    QWidget#GraphCard, QWidget#OverlayGraphCard, QFrame#GraphCard, QFrame#OverlayGraphCard {{
        background: transparent;
        border: 1px solid {p['border_dark']};
        border-radius: 16px;
    }}

    QLabel#GraphTitle {{
        color: {p['text_title']};
        background: transparent;
        border: 0px;
        font-size: 17px;
        font-weight: 800;
        padding: 6px 4px;
    }}

    QPushButton#GraphOpenButton {{
        background: {p['bg_field']};
        color: {p['text_title']};
        border: 1px solid {p['accent']};
        border-radius: 12px;
        padding: 7px 14px;
    }}

    QPushButton#GraphOpenButton:hover {{
        background: {p['selected']};
        border: 1px solid {p['accent2']};
    }}

    QFrame#GraphWebContainer, QWidget#GraphWebContainer {{
        background: transparent;
        border: 0px;
    }}

    QWebEngineView#GraphWebView {{
        background: transparent;
        border: 0px;
    }}

    QScrollArea#OverlayGraphArea {{
        background: transparent;
        border: 1px solid {p['border_dark']};
        border-radius: 14px;
    }}

    QWidget#OverlayGraphContent, QWidget#OverlayGraphViewport {{
        background: transparent;
    }}

    QWidget#DutyModeShell, QWidget#HomeShell {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['bg_main']}, stop:0.6 {p['bg_panel']}, stop:1 {p['bg_panel2']});
        border-radius: 20px;
    }}

    QGroupBox {{
        margin-top: 18px;
        padding: 14px;
        font-weight: 700;
    }}

    QGroupBox::title {{
        color: {p['hud_text']};
        background: {p['bg_main']};
        border: 1px solid {p['border_dark']};
        border-radius: 10px;
        padding: 3px 10px;
    }}

    QPushButton, QToolButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['glass']}, stop:1 {p['glass2']});
        color: {subtle_button_text};
        border: 1px solid {p['border_dark']};
        border-radius: 14px;
        padding: 9px 18px;
        font-weight: 750;
        min-height: 28px;
    }}

    QPushButton:hover, QToolButton:hover {{
        background: {p['selected']};
        border: 1px solid {p['accent']};
        color: {p['text_title']};
    }}

    QPushButton:pressed, QToolButton:pressed {{
        background: {p['accent']};
        border: 1px solid {p['accent2']};
        color: {primary_text};
    }}

    QPushButton:disabled, QToolButton:disabled {{
        color: {p['text_soft']};
        background: {p['bg_field']};
        border: 1px solid {p['scroll']};
    }}

    QPushButton#PrimaryAction {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['accent']}, stop:1 {p['accent2']});
        color: {primary_text};
        border: 1px solid {p['accent2']};
    }}

    QPushButton#DestructiveAction {{
        background: {p['danger_bg']};
        color: {p['danger']};
        border: 1px solid {p['danger']};
    }}

    QLineEdit, QTextEdit, QTextBrowser, QPlainTextEdit, QComboBox, QSpinBox {{
        background: {p['bg_field']};
        color: {p['text_title']};
        border: 1px solid {p['border_dark']};
        border-radius: 13px;
        padding: 8px 11px;
        selection-background-color: {p['accent']};
        selection-color: {primary_text};
    }}

    QLineEdit:focus, QTextEdit:focus, QTextBrowser:focus, QPlainTextEdit:focus,
    QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {p['accent']};
        background: {p['glass']};
    }}

    QListWidget, QTreeWidget, QTableWidget {{
        background: {p['bg_field']};
        alternate-background-color: {p['bg_panel']};
        border: 1px solid {p['border_dark']};
        border-radius: 14px;
        padding: 6px;
    }}

    QListWidget::item, QTreeWidget::item {{
        border-radius: 10px;
        padding: 7px;
    }}

    QListWidget::item:selected, QTreeWidget::item:selected {{
        background: {p['selected']};
        color: {p['text_title']};
    }}

    QScrollArea {{
        background: transparent;
        border: 0px;
    }}

    QScrollArea#GraphScrollArea {{
        background: {graph_area_bg};
        border: 0px;
    }}

    QScrollBar:vertical, QScrollBar:horizontal {{
        background: transparent;
        border: 0px;
        width: 10px;
        height: 10px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {p['scroll']};
        border-radius: 5px;
        min-height: 34px;
        min-width: 34px;
    }}

    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
        background: {p['accent']};
    }}

    QScrollBar::add-line, QScrollBar::sub-line {{
        width: 0px;
        height: 0px;
    }}

    QCheckBox, QRadioButton {{
        spacing: 9px;
        color: {p['text']};
        background: transparent;
    }}

    QCheckBox::indicator, QRadioButton::indicator {{
        width: 18px;
        height: 18px;
        border: 1px solid {p['accent']};
        background: {p['bg_field']};
        border-radius: 6px;
    }}

    QRadioButton::indicator {{ border-radius: 9px; }}

    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background: {p['accent']};
        border: 1px solid {p['accent2']};
    }}

    QTabWidget::pane {{
        border: 1px solid {p['border_dark']};
        border-radius: 14px;
        background: {p['glass']};
        padding: 6px;
    }}

    QTabBar::tab {{
        background: {p['glass2']};
        border: 1px solid {p['border_dark']};
        border-radius: 12px;
        padding: 9px 14px;
        margin: 2px;
    }}

    QTabBar::tab:selected {{
        background: {p['selected']};
        border: 1px solid {p['accent']};
        color: {p['text_title']};
    }}

    QProgressBar {{
        background: {p['bg_field']};
        border: 1px solid {p['border_dark']};
        border-radius: 10px;
        text-align: center;
    }}

    QProgressBar::chunk {{
        background: {p['accent']};
        border-radius: 9px;
    }}

    QToolTip, QMenu {{
        background-color: {p['bg_field']};
        color: {p['text_title']};
        border: 1px solid {p['border_dark']};
        padding: 6px;
    }}

    QMenu::item {{
        background: transparent;
        color: {p['text_title']};
        padding: 6px 20px;
    }}

    QMenu::item:selected {{
        background: {p['selected']};
        color: {p['text_title']};
    }}

    QDialog, QWidget[windowType="tool"] {{
        background-color: {p['bg_main']};
        color: {p['text_title']};
    }}

    QLabel#DutyTriggerStatus {{
        border-radius: 12px;
        padding: 9px 12px;
    }}

    QDialog#DutyNotificationDialog {{
        background: {p['overlay']};
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
    app.setProperty("oko_theme_name", theme_name)

    # Принудительно переполируем уже созданные виджеты,
    # чтобы тема применялась к кнопкам, полям и меню сразу.
    for widget in app.allWidgets():
        try:
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        except Exception:
            pass
