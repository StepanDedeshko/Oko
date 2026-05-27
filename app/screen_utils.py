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


def center_widget_on_screen(widget, screen=None):
    screen = screen or screen_under_cursor()

    if not screen:
        return

    geometry = screen.availableGeometry()
    x = geometry.x() + (geometry.width() - widget.width()) // 2
    y = geometry.y() + (geometry.height() - widget.height()) // 2
    widget.move(x, y)


def geometry_dict(screen):
    if not screen:
        return None

    g = screen.availableGeometry()
    return {
        "x": g.x(),
        "y": g.y(),
        "width": g.width(),
        "height": g.height(),
    }
