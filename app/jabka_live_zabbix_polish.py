from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
)

from app.jabka_theme import is_jabka_config


JABKA_GLOBAL_CONTRAST_QSS = r"""
QToolTip {
    color: #F7FFE8;
    background-color: #102818;
    border: 1px solid #B7F27A;
    border-radius: 8px;
    padding: 7px 10px;
    opacity: 255;
}
QLineEdit, QTextEdit, QTextBrowser, QPlainTextEdit, QComboBox, QSpinBox,
QListWidget, QTreeWidget, QTableWidget, QTableView {
    selection-background-color: #B7F27A;
    selection-color: #07140D;
}
"""


JABKA_LIVE_TABLE_QSS = r"""
QTableWidget#LiveZabbixProblemsTable {
    background: #07140D;
    alternate-background-color: #07140D;
    color: #EAF8D8;
    border: 1px solid rgba(102, 185, 91, 165);
    border-radius: 18px;
    gridline-color: transparent;
    selection-background-color: transparent;
    selection-color: #F7FFE8;
    outline: 0;
    font-size: 12px;
    padding: 4px;
}
QTableWidget#LiveZabbixProblemsTable::item {
    border: 0;
    padding: 0;
    background: transparent;
}
QTableWidget#LiveZabbixProblemsTable::item:selected,
QTableWidget#LiveZabbixProblemsTable::item:hover {
    background: transparent;
    color: #F7FFE8;
}
QTableWidget#LiveZabbixProblemsTable QHeaderView::section {
    background: #12331F;
    color: #EAF8D8;
    border: 0;
    border-right: 1px solid rgba(102, 185, 91, 75);
    border-bottom: 1px solid rgba(183, 242, 122, 155);
    padding: 9px 10px;
    font-size: 12px;
    font-weight: 700;
}
QTableWidget#LiveZabbixProblemsTable QTableCornerButton::section {
    background: #12331F;
    border: 0;
    border-bottom: 1px solid rgba(183, 242, 122, 155);
}
QTableWidget#LiveZabbixProblemsTable QScrollBar:vertical {
    background: #08160D;
    width: 14px;
    margin: 4px 2px 4px 2px;
    border-radius: 7px;
}
QTableWidget#LiveZabbixProblemsTable QScrollBar::handle:vertical {
    background: #2D7D3A;
    min-height: 36px;
    border: 1px solid #66B95B;
    border-radius: 6px;
}
QTableWidget#LiveZabbixProblemsTable QScrollBar::handle:vertical:hover {
    background: #3D9650;
    border-color: #B7F27A;
}
QTableWidget#LiveZabbixProblemsTable QScrollBar::add-line:vertical,
QTableWidget#LiveZabbixProblemsTable QScrollBar::sub-line:vertical,
QTableWidget#LiveZabbixProblemsTable QScrollBar::add-page:vertical,
QTableWidget#LiveZabbixProblemsTable QScrollBar::sub-page:vertical {
    background: transparent;
    border: 0;
    height: 0;
}
"""


class JabkaProblemRowDelegate(QStyledItemDelegate):
    """Paint Live Zabbix rows as soft rounded cards without changing table data."""

    def __init__(self, table):
        super().__init__(table)
        self.table = table
        self.hovered_row = -1
        table.setMouseTracking(True)
        table.viewport().setMouseTracking(True)
        table.viewport().installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.table.viewport():
            if event.type() == QEvent.Type.MouseMove:
                position = event.position().toPoint() if hasattr(event, "position") else event.pos()
                index = self.table.indexAt(position)
                row = index.row() if index.isValid() else -1
                if row != self.hovered_row:
                    self.hovered_row = row
                    self.table.viewport().update()
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
                if self.hovered_row != -1:
                    self.hovered_row = -1
                    self.table.viewport().update()
        return super().eventFilter(watched, event)

    @staticmethod
    def _rounded_row_path(rect: QRectF, first: bool, last: bool, radius: float = 10.0) -> QPainterPath:
        if first and last:
            path = QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            return path

        path = QPainterPath()
        if first:
            path.moveTo(rect.right(), rect.top())
            path.lineTo(rect.left() + radius, rect.top())
            path.quadTo(rect.left(), rect.top(), rect.left(), rect.top() + radius)
            path.lineTo(rect.left(), rect.bottom() - radius)
            path.quadTo(rect.left(), rect.bottom(), rect.left() + radius, rect.bottom())
            path.lineTo(rect.right(), rect.bottom())
            path.closeSubpath()
            return path

        if last:
            path.moveTo(rect.left(), rect.top())
            path.lineTo(rect.right() - radius, rect.top())
            path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + radius)
            path.lineTo(rect.right(), rect.bottom() - radius)
            path.quadTo(rect.right(), rect.bottom(), rect.right() - radius, rect.bottom())
            path.lineTo(rect.left(), rect.bottom())
            path.closeSubpath()
            return path

        path.addRect(rect)
        return path

    def _is_separator(self, index) -> bool:
        try:
            return self.table.columnSpan(index.row(), 0) > 1
        except Exception:
            return False

    def paint(self, painter: QPainter, option, index):
        opt = option
        self.initStyleOption(opt, index)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        row = index.row()
        column = index.column()
        last_column = max(0, self.table.columnCount() - 1)
        first = column == 0
        last = column == last_column
        rect = QRectF(opt.rect).adjusted(4.0 if first else 0.0, 4.0, -4.0 if last else 0.0, -4.0)

        if self._is_separator(index):
            gradient = QLinearGradient(rect.topLeft(), rect.topRight())
            gradient.setColorAt(0.0, QColor("#163A22"))
            gradient.setColorAt(0.5, QColor("#214F2B"))
            gradient.setColorAt(1.0, QColor("#163A22"))
            painter.setPen(QPen(QColor("#66B95B"), 1.0))
            painter.setBrush(gradient)
            painter.drawRoundedRect(rect.adjusted(2.0, 0.0, -2.0, 0.0), 10.0, 10.0)
            painter.setPen(QColor("#EAF8D8"))
            painter.setFont(opt.font)
            painter.drawText(rect.toRect(), Qt.AlignmentFlag.AlignCenter, opt.text)
            painter.restore()
            return

        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        hovered = row == self.hovered_row
        if selected:
            background = QColor("#2D6B3A")
        elif hovered:
            background = QColor("#173D24")
        elif row % 2:
            background = QColor("#0E2918")
        else:
            background = QColor("#0A2013")

        path = self._rounded_row_path(rect, first, last)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawPath(path)

        # A thin top/bottom line keeps the card visually whole across all cells.
        edge = QColor("#B7F27A") if selected else QColor(102, 185, 91, 54 if not hovered else 105)
        painter.setPen(QPen(edge, 1.0))
        painter.drawLine(rect.topLeft(), rect.topRight())
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        if first:
            accent = QColor("#B7F27A") if selected else QColor("#2D7D3A")
            painter.setPen(QPen(accent, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(rect.left() + 2.0, rect.top() + 9.0, rect.left() + 2.0, rect.bottom() - 9.0)

        severity_brush = index.data(Qt.ItemDataRole.BackgroundRole)
        severity_badge = column == 1 and severity_brush is not None
        if severity_badge:
            color = severity_brush.color() if hasattr(severity_brush, "color") else QColor(severity_brush)
            if color.isValid() and color.alpha() > 0:
                badge = rect.adjusted(8.0, 5.0, -8.0, -5.0)
                painter.setPen(QPen(color.lighter(118), 1.0))
                painter.setBrush(color)
                painter.drawRoundedRect(badge, 9.0, 9.0)

        foreground = index.data(Qt.ItemDataRole.ForegroundRole)
        if severity_badge:
            text_color = QColor("#07140D")
        elif selected:
            text_color = QColor("#F7FFE8")
        elif foreground is not None and hasattr(foreground, "color") and foreground.color().isValid():
            text_color = foreground.color()
        else:
            text_color = QColor("#EAF8D8")

        painter.setPen(text_color)
        painter.setFont(opt.font)
        text_rect = rect.toRect().adjusted(11 if first else 9, 0, -9, 0)
        metrics = QFontMetrics(opt.font)
        text = metrics.elidedText(opt.text, Qt.TextElideMode.ElideRight, max(0, text_rect.width()))
        alignment = opt.displayAlignment or (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        painter.drawText(text_rect, alignment, text)

        painter.restore()


def apply_jabka_global_contrast(app: QApplication | None, config: dict | None) -> bool:
    """Fix tooltip and text-selection contrast for the Jabbix theme."""
    if app is None or not is_jabka_config(config):
        return False
    if app.property("jabka_global_contrast_applied"):
        return False
    app.setStyleSheet(app.styleSheet() + "\n" + JABKA_GLOBAL_CONTRAST_QSS)
    app.setProperty("jabka_global_contrast_applied", True)
    return True


def apply_jabka_live_table_polish(widget) -> bool:
    """Apply the visual table redesign only to a Jabbix Live Zabbix widget."""
    if widget is None or not is_jabka_config(getattr(widget, "config", None)):
        return False
    table = getattr(widget, "table", None)
    if table is None or table.property("jabka_problem_table_polished"):
        return False

    table.setShowGrid(False)
    table.setAlternatingRowColors(False)
    table.setWordWrap(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setStyleSheet(JABKA_LIVE_TABLE_QSS)

    vertical = table.verticalHeader()
    vertical.setDefaultSectionSize(44)
    vertical.setMinimumSectionSize(38)

    horizontal = table.horizontalHeader()
    horizontal.setMinimumHeight(38)
    horizontal.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    horizontal.setHighlightSections(False)
    horizontal.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    if table.columnCount() > 4:
        horizontal.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

    delegate = JabkaProblemRowDelegate(table)
    table.setItemDelegate(delegate)
    table._jabka_problem_row_delegate = delegate
    table.setProperty("jabka_problem_table_polished", True)
    return True


def install_jabka_live_zabbix_polish() -> bool:
    """Patch LiveZabbixMonitorWidget construction before the main window is built."""
    import app.live_zabbix_widget as live_widget

    cls = live_widget.LiveZabbixMonitorWidget
    if getattr(cls, "_jabka_problem_table_patch_installed", False):
        return False

    original_build_ui = cls._build_ui

    def _build_ui(self):
        original_build_ui(self)
        apply_jabka_live_table_polish(self)

    cls._build_ui = _build_ui
    cls._jabka_problem_table_patch_installed = True
    return True
