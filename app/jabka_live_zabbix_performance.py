from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QAbstractItemView, QStyle, QStyleOptionViewItem, QStyledItemDelegate
from shiboken6 import isValid


_BG_SELECTED = QColor("#2D6B3A")
_BG_HOVERED = QColor("#173D24")
_BG_ODD = QColor("#0E2918")
_BG_EVEN = QColor("#0A2013")
_TEXT_NORMAL = QColor("#EAF8D8")
_TEXT_SELECTED = QColor("#F7FFE8")
_EDGE_SELECTED = QColor("#B7F27A")
_EDGE_NORMAL = QColor(102, 185, 91, 54)
_EDGE_HOVERED = QColor(102, 185, 91, 105)
_ACCENT_NORMAL = QColor("#2D7D3A")


def _live_table(delegate):
    """Return the backing table only while its Qt/C++ object is still alive."""
    table = getattr(delegate, "table", None)
    if table is None:
        return None
    try:
        if not isValid(table):
            return None
        # Accessing viewport also validates the internal QAbstractScrollArea state.
        table.viewport()
    except RuntimeError:
        return None
    return table


def _visible_row_rect(delegate, row: int):
    table = _live_table(delegate)
    if table is None or row < 0 or row >= table.rowCount() or table.columnCount() <= 0:
        return None
    try:
        model = table.model()
        first = table.visualRect(model.index(row, 0))
        last = table.visualRect(model.index(row, table.columnCount() - 1))
    except RuntimeError:
        return None
    rect = first.united(last)
    if not rect.isValid() or rect.isEmpty():
        return None
    return rect.adjusted(-6, -6, 6, 6)


def _update_hover_row(delegate, row: int) -> None:
    table = _live_table(delegate)
    if table is None:
        return
    rect = _visible_row_rect(delegate, row)
    if rect is None:
        return
    try:
        viewport = table.viewport()
        if isValid(viewport):
            viewport.update(rect)
    except RuntimeError:
        return


def _optimized_event_filter(self, watched, event):
    table = _live_table(self)
    if table is None:
        # During QApplication shutdown Python wrappers can outlive their C++ table.
        # Returning False is enough: there is no live viewport left to handle.
        return False

    try:
        viewport = table.viewport()
    except RuntimeError:
        return False

    if watched is viewport:
        if event.type() == QEvent.Type.MouseMove:
            position = event.position().toPoint() if hasattr(event, "position") else event.pos()
            index = table.indexAt(position)
            row = index.row() if index.isValid() else -1
            if row != self.hovered_row:
                previous_row = self.hovered_row
                self.hovered_row = row
                _update_hover_row(self, previous_row)
                _update_hover_row(self, row)
        elif event.type() in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
            if self.hovered_row != -1:
                previous_row = self.hovered_row
                self.hovered_row = -1
                _update_hover_row(self, previous_row)

    # The filter only adds hover repainting and never consumes the original event.
    # Avoid calling the C++ base implementation while Qt is tearing objects down.
    return False


def _optimized_paint(self, painter: QPainter, option, index):
    table = _live_table(self)
    if table is None:
        try:
            return QStyledItemDelegate.paint(self, painter, option, index)
        except RuntimeError:
            return None

    opt = QStyleOptionViewItem(option)
    self.initStyleOption(opt, index)

    painter.save()

    row = index.row()
    column = index.column()
    last_column = max(0, table.columnCount() - 1)
    first = column == 0
    last = column == last_column
    rect = QRectF(opt.rect).adjusted(4.0 if first else 0.0, 4.0, -4.0 if last else 0.0, -4.0)

    if self._is_separator(index):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0.0, QColor("#163A22"))
        gradient.setColorAt(0.5, QColor("#214F2B"))
        gradient.setColorAt(1.0, QColor("#163A22"))
        painter.setPen(QPen(QColor("#66B95B"), 1.0))
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect.adjusted(2.0, 0.0, -2.0, 0.0), 10.0, 10.0)
        painter.setPen(_TEXT_NORMAL)
        painter.setFont(opt.font)
        painter.drawText(rect.toRect(), Qt.AlignmentFlag.AlignCenter, opt.text)
        painter.restore()
        return

    selected = bool(opt.state & QStyle.StateFlag.State_Selected)
    hovered = row == self.hovered_row
    if selected:
        background = _BG_SELECTED
    elif hovered:
        background = _BG_HOVERED
    elif row % 2:
        background = _BG_ODD
    else:
        background = _BG_EVEN

    painter.setPen(Qt.PenStyle.NoPen)
    if first or last:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(background)
        painter.drawPath(self._rounded_row_path(rect, first, last))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    else:
        painter.fillRect(rect, background)

    edge = _EDGE_SELECTED if selected else (_EDGE_HOVERED if hovered else _EDGE_NORMAL)
    painter.setPen(QPen(edge, 1.0))
    painter.drawLine(rect.topLeft(), rect.topRight())
    painter.drawLine(rect.bottomLeft(), rect.bottomRight())

    if first:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(_EDGE_SELECTED if selected else _ACCENT_NORMAL, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(rect.left() + 2.0, rect.top() + 9.0, rect.left() + 2.0, rect.bottom() - 9.0)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    severity_brush = index.data(Qt.ItemDataRole.BackgroundRole)
    severity_badge = column == 1 and severity_brush is not None
    if severity_badge:
        color = severity_brush.color() if hasattr(severity_brush, "color") else QColor(severity_brush)
        if color.isValid() and color.alpha() > 0:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            badge = rect.adjusted(8.0, 5.0, -8.0, -5.0)
            painter.setPen(QPen(color.lighter(118), 1.0))
            painter.setBrush(color)
            painter.drawRoundedRect(badge, 9.0, 9.0)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    foreground = index.data(Qt.ItemDataRole.ForegroundRole)
    if severity_badge:
        text_color = QColor("#07140D")
    elif selected:
        text_color = _TEXT_SELECTED
    elif foreground is not None and hasattr(foreground, "color") and foreground.color().isValid():
        text_color = foreground.color()
    else:
        text_color = _TEXT_NORMAL

    painter.setPen(text_color)
    painter.setFont(opt.font)
    text_rect = rect.toRect().adjusted(11 if first else 9, 0, -9, 0)
    text = opt.fontMetrics.elidedText(opt.text, Qt.TextElideMode.ElideRight, max(0, text_rect.width()))
    alignment = opt.displayAlignment or (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    painter.drawText(text_rect, alignment, text)

    painter.restore()


def install_jabka_live_zabbix_performance_fix() -> bool:
    """Reduce hover/selection repaint cost while preserving the rounded Jabbix design."""
    import app.jabka_live_zabbix_polish as polish

    delegate_cls = polish.JabkaProblemRowDelegate
    if getattr(delegate_cls, "_performance_fix_installed", False):
        return False

    delegate_cls.eventFilter = _optimized_event_filter
    delegate_cls.paint = _optimized_paint
    delegate_cls._performance_fix_installed = True

    original_apply = polish.apply_jabka_live_table_polish

    def apply_jabka_live_table_polish_fast(widget):
        applied = original_apply(widget)
        table = getattr(widget, "table", None)
        if applied and table is not None:
            table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
            table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        return applied

    polish.apply_jabka_live_table_polish = apply_jabka_live_table_polish_fast
    return True
