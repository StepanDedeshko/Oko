import math
import random

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from app.music_config import normalize_bar_count, normalize_fps, normalize_mode


class EqualizerWidget(QWidget):
    def __init__(self, bar_count=24, fps=24, mode="auto", parent=None):
        super().__init__(parent)
        self.setObjectName("MusicEqualizerWidget")
        self._bar_count = normalize_bar_count(bar_count)
        self._fps = normalize_fps(fps)
        self._mode = normalize_mode(mode)
        self._levels = [0.12] * self._bar_count
        self._targets = list(self._levels)
        self._phase = 0.0
        self._active = True
        self._rng = random.Random(42)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.setMinimumHeight(28)
        self.setMaximumHeight(46)

    @property
    def bar_count(self):
        return self._bar_count

    @property
    def mode(self):
        return self._mode

    def set_bar_count(self, count: int):
        self._bar_count = normalize_bar_count(count)
        self._levels = (self._levels + [0.12] * self._bar_count)[: self._bar_count]
        self._targets = (self._targets + [0.12] * self._bar_count)[: self._bar_count]
        self.update()

    def set_fps(self, fps: int):
        self._fps = normalize_fps(fps)
        if self.timer.isActive():
            self.timer.start(round(1000 / self._fps))

    def set_levels(self, levels):
        safe = []
        for value in levels or []:
            try:
                safe.append(max(0.0, min(1.0, float(value))))
            except (TypeError, ValueError):
                safe.append(0.0)
        if not safe:
            return
        if len(safe) == self._bar_count:
            self._levels = safe
        else:
            step = max(1, len(safe) / self._bar_count)
            self._levels = [safe[min(len(safe) - 1, int(i * step))] for i in range(self._bar_count)]
        self.update()

    def set_active(self, active: bool):
        self._active = bool(active)
        if self._active and self.isVisible():
            self.start()
        else:
            self.stop()
        self.update()

    def set_mode(self, mode: str):
        self._mode = normalize_mode(mode)

    def start(self):
        if not self.timer.isActive():
            self.timer.start(round(1000 / self._fps))

    def stop(self):
        self.timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        if self._active:
            self.start()

    def hideEvent(self, event):
        self.stop()
        super().hideEvent(event)

    def _tick(self):
        if self._mode in {"decorative", "auto"}:
            self._phase += 0.16
            for i in range(self._bar_count):
                if self._rng.random() < 0.08:
                    wave = (math.sin(self._phase + i * 0.55) + 1) / 2
                    self._targets[i] = 0.10 + 0.72 * wave * self._rng.uniform(0.55, 1.0)
                self._levels[i] += (self._targets[i] - self._levels[i]) * 0.18
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(2, 3, -2, -3)
        if rect.width() <= 0 or rect.height() <= 0:
            return
        palette = self.palette()
        bg = palette.window().color()
        dark = bg.lightness() < 128
        accent = QColor(88, 170, 255) if dark else QColor(42, 126, 214)
        idle = QColor(accent)
        idle.setAlpha(70 if dark else 110)
        gap = 2
        bar_w = max(2, (rect.width() - gap * (self._bar_count - 1)) / self._bar_count)
        for i, level in enumerate(self._levels[: self._bar_count]):
            level = max(0.04, min(1.0, level))
            h = max(3, rect.height() * level)
            x = rect.left() + i * (bar_w + gap)
            y = rect.bottom() - h
            color = QColor(accent if self._active else idle)
            color.setAlpha(95 + int(120 * level) if self._active else 70)
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            path = QPainterPath()
            path.addRoundedRect(x, y, bar_w, h, 2, 2)
            painter.drawPath(path)
