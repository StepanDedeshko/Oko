from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QCursor, QGuiApplication


def screen_under_cursor():
    app = QGuiApplication.instance()
    if not app:
        return None

    pos = QCursor.pos()
    screen = app.screenAt(pos)

    if screen:
        return screen

    return app.primaryScreen()


def screen_for_widget(widget):
    try:
        handle = widget.windowHandle()
        if handle and handle.screen():
            return handle.screen()
    except Exception:
        pass

    try:
        center = widget.frameGeometry().center()
        screen = QGuiApplication.screenAt(center)
        if screen:
            return screen
    except Exception:
        pass

    return screen_under_cursor()


def screen_for_rect(rect):
    app = QGuiApplication.instance()
    if app is None or rect is None:
        return screen_under_cursor()
    center = rect.center()
    screen = app.screenAt(center)
    if screen:
        return screen
    for candidate in app.screens():
        if candidate.availableGeometry().intersects(rect):
            return candidate
    return app.primaryScreen() or screen_under_cursor()


def available_geometry_for_widget(widget=None, preferred_screen=None):
    screen = preferred_screen or (screen_for_widget(widget) if widget is not None else None) or screen_under_cursor()
    return screen.availableGeometry() if screen is not None else QRect(0, 0, 1024, 768)


def safe_window_size(available, desired_width=1500, desired_height=900, margin=40, min_width=640, min_height=480):
    max_width = max(1, available.width() - margin)
    max_height = max(1, available.height() - margin)
    width = min(max_width, max(1, int(desired_width)))
    height = min(max_height, max(1, int(desired_height)))
    safe_min_width = min(min_width, max_width)
    safe_min_height = min(min_height, max_height)
    width = max(width, safe_min_width)
    height = max(height, safe_min_height)
    return QSize(width, height), QSize(safe_min_width, safe_min_height)


def rect_fits_available(rect, available, margin=0):
    safe = available.adjusted(margin, margin, -margin, -margin)
    return safe.contains(rect.topLeft()) and safe.contains(rect.bottomRight())


def clamp_rect_to_available(rect, available, margin=0):
    max_width = max(1, available.width() - margin * 2)
    max_height = max(1, available.height() - margin * 2)
    width = min(rect.width(), max_width)
    height = min(rect.height(), max_height)
    min_x = available.x() + margin
    min_y = available.y() + margin
    max_x = available.x() + available.width() - margin - width
    max_y = available.y() + available.height() - margin - height
    x = min(max(rect.x(), min_x), max_x)
    y = min(max(rect.y(), min_y), max_y)
    return QRect(x, y, width, height)


def center_widget_on_screen(widget, screen=None, margin=0):
    screen = screen or screen_under_cursor()

    if not screen:
        return

    geometry = screen.availableGeometry()
    width = min(max(1, widget.width()), max(1, geometry.width() - margin * 2))
    height = min(max(1, widget.height()), max(1, geometry.height() - margin * 2))
    x = geometry.x() + (geometry.width() - width) // 2
    y = geometry.y() + (geometry.height() - height) // 2
    widget.setGeometry(clamp_rect_to_available(QRect(x, y, width, height), geometry, margin))


def geometry_dict(screen):
    if not screen:
        return None

    g = screen.availableGeometry()
    full = screen.geometry()
    return {
        "x": g.x(),
        "y": g.y(),
        "width": g.width(),
        "height": g.height(),
        "screen_x": full.x(),
        "screen_y": full.y(),
        "screen_width": full.width(),
        "screen_height": full.height(),
        "device_pixel_ratio": screen.devicePixelRatio(),
    }
