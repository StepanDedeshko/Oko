from PySide6.QtCore import Qt, QTimer, QEventLoop
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QLinearGradient
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QApplication

from app.app_info import APP_NAME, APP_VERSION
from app.theme_logo import load_theme_logo


class ThemeSplash(QWidget):
    def __init__(self, config=None, parent=None, preferred_screen=None):
        super().__init__(parent)

        self.config = config or {}
        self.preferred_screen = preferred_screen
        self.theme = self.config.get("settings", {}).get("theme", "mass_effect")
        self.progress_value = 0

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(560, 340)

        root = QVBoxLayout(self)
        root.setContentsMargins(38, 34, 38, 30)
        root.setSpacing(10)

        self.logo = QLabel()
        self.logo.setAlignment(Qt.AlignCenter)
        logo_pixmap = load_theme_logo(self.theme, size=96)
        if not logo_pixmap.isNull():
            self.logo.setPixmap(logo_pixmap)
        else:
            self.logo.setText("◈")
            self.logo.setStyleSheet(self.logo_style())

        self.title = QLabel(APP_NAME)
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet(self.title_style())

        self.version = QLabel(APP_VERSION)
        self.version.setAlignment(Qt.AlignCenter)
        self.version.setStyleSheet(self.version_style())

        self.subtitle = QLabel(self.subtitle_text())
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setStyleSheet(self.subtitle_style())

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.setStyleSheet(self.progress_style())

        root.addStretch(1)
        root.addWidget(self.logo)
        root.addWidget(self.title)
        root.addWidget(self.version)
        root.addWidget(self.subtitle)
        root.addStretch(1)
        root.addWidget(self.progress)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick_progress)
        self.timer.start(25)

        self.center_on_screen()

    def center_on_screen(self):
        try:
            screen = self.preferred_screen or QApplication.primaryScreen()
            geometry = screen.availableGeometry()
            self.move(
                geometry.x() + (geometry.width() - self.width()) // 2,
                geometry.y() + (geometry.height() - self.height()) // 2,
            )
        except Exception:
            pass

    def tick_progress(self):
        self.progress_value = min(100, self.progress_value + 2)
        self.progress.setValue(self.progress_value)

    def wait_minimum(self, ms=1400):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def subtitle_text(self):
        if self.theme == "mass_effect":
            return "SYSTEM MONITORING INTERFACE"
        if self.theme == "matrix_green":
            return "monitoring node online"
        if self.theme == "cerberus_red":
            return "оперативный контур дежурства"
        if self.theme == "omega_purple":
            return "аналитический режим"
        if self.theme == "amber_ops":
            return "дежурный контур"
        return "загрузка приложения"

    def palette(self):
        if self.theme == "light_standard":
            return {"bg1": QColor("#f3f4f6"), "bg2": QColor("#ffffff"), "accent": QColor("#3b82f6"), "accent2": QColor("#2563eb"), "text": "#111827", "muted": "#4b5563", "border": QColor("#d1d5db")}
        if self.theme == "mass_effect":
            return {"bg1": QColor(8, 12, 18), "bg2": QColor(24, 36, 52), "accent": QColor(235, 59, 71), "accent2": QColor(70, 190, 255), "text": "#f2f6ff", "muted": "#9fb7cc", "border": QColor(235, 59, 71)}
        if self.theme == "cerberus_red":
            return {"bg1": QColor(18, 6, 7), "bg2": QColor(42, 17, 21), "accent": QColor(208, 70, 87), "accent2": QColor(255, 116, 133), "text": "#ffe6e6", "muted": "#ffb0b6", "border": QColor(208, 70, 87)}
        if self.theme == "matrix_green":
            return {"bg1": QColor(3, 8, 5), "bg2": QColor(13, 29, 20), "accent": QColor(47, 191, 113), "accent2": QColor(125, 255, 176), "text": "#dfffe8", "muted": "#8ff5b0", "border": QColor(47, 191, 113)}
        if self.theme == "omega_purple":
            return {"bg1": QColor(9, 5, 18), "bg2": QColor(35, 18, 65), "accent": QColor(139, 86, 226), "accent2": QColor(187, 140, 255), "text": "#f0e6ff", "muted": "#caa8ff", "border": QColor(139, 86, 226)}
        if self.theme == "amber_ops":
            return {"bg1": QColor(17, 11, 3), "bg2": QColor(54, 33, 9), "accent": QColor(214, 139, 34), "accent2": QColor(255, 179, 71), "text": "#fff1db", "muted": "#ffcf88", "border": QColor(214, 139, 34)}
        return {"bg1": QColor(18, 18, 18), "bg2": QColor(34, 34, 34), "accent": QColor(92, 143, 214), "accent2": QColor(127, 176, 240), "text": "#ffffff", "muted": "#b8b8b8", "border": QColor(92, 143, 214)}

    def logo_style(self):
        p = self.palette()
        return f"color: {p['text']}; font-size: 56px; font-weight: 900;"

    def title_style(self):
        p = self.palette()
        return f"color: {p['text']}; font-size: 34px; font-weight: 900; letter-spacing: 7px;"

    def version_style(self):
        p = self.palette()
        return f"color: {p['accent2'].name()}; font-size: 12px; font-weight: 700; letter-spacing: 2px;"

    def subtitle_style(self):
        p = self.palette()
        return f"color: {p['muted']}; font-size: 12px; font-weight: 500; letter-spacing: 2px;"

    def progress_style(self):
        p = self.palette()
        progress_bg = "rgba(255, 255, 255, 180)" if self.theme == "light_standard" else "rgba(0, 0, 0, 70)"
        return f"""
            QProgressBar {{
                background-color: {progress_bg};
                border: 1px solid {p['border'].name()};
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {p['accent'].name()};
                border-radius: 4px;
            }}
        """

    def paintEvent(self, event):
        p = self.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(6, 6, -6, -6)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, p["bg1"])
        gradient.setColorAt(1, p["bg2"])

        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(p["border"], 2))
        painter.drawRoundedRect(rect, 22, 22)

        painter.setPen(QPen(p["accent"], 2))
        painter.drawLine(42, 62, 190, 62)
        painter.drawLine(370, 258, 516, 258)
        painter.setPen(QPen(p["accent2"], 1))
        painter.drawLine(42, 260, 135, 260)
        painter.drawLine(425, 60, 516, 60)
