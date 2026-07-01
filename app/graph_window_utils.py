from PySide6.QtCore import QRect, Qt


def calculate_graph_window_geometry(available_geometry, preferred_width=1200, preferred_height=800):
    width = min(preferred_width, int(available_geometry.width() * 0.9))
    height = min(preferred_height, int(available_geometry.height() * 0.9))
    width = max(1, width)
    height = max(1, height)
    x = available_geometry.x() + max(0, (available_geometry.width() - width) // 2)
    y = available_geometry.y() + max(0, (available_geometry.height() - height) // 2)
    return QRect(x, y, width, height)


def current_available_geometry(parent=None):
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import QApplication

    screen = None
    if parent is not None:
        try:
            screen = parent.screen()
        except Exception:
            screen = None
    if screen is None:
        try:
            screen = QApplication.screenAt(QCursor.pos())
        except Exception:
            screen = None
    if screen is None:
        screen = QApplication.primaryScreen()
    return screen.availableGeometry() if screen is not None else QRect(0, 0, 1200, 800)


def apply_resizable_graph_window(dialog, logger=None, minimum_width=900, minimum_height=600):
    dialog.setWindowFlags(
        Qt.Window
        | Qt.WindowMinimizeButtonHint
        | Qt.WindowMaximizeButtonHint
        | Qt.WindowCloseButtonHint
    )
    if hasattr(dialog, "setSizeGripEnabled"):
        dialog.setSizeGripEnabled(True)
    geometry = calculate_graph_window_geometry(current_available_geometry(dialog.parentWidget()))
    dialog.setMinimumSize(min(minimum_width, geometry.width()), min(minimum_height, geometry.height()))
    dialog.resize(geometry.size())
    dialog.move(geometry.topLeft())
    if logger is not None:
        logger.info("Graph check window opened: size=%sx%s screen=%s", geometry.width(), geometry.height(), geometry)
    return geometry


def set_expanding_webview(view):
    from PySide6.QtWidgets import QSizePolicy

    view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)


def install_maximize_shortcut(dialog, logger=None, button=None):
    def update_button_text():
        if button is not None:
            button.setText("Восстановить" if dialog.isMaximized() else "Развернуть")

    def toggle():
        if dialog.isMaximized():
            dialog.showNormal()
            if logger is not None:
                logger.info("Graph check window restored")
        else:
            dialog.showMaximized()
            if logger is not None:
                logger.info("Graph check window maximized")
        update_button_text()

    from PySide6.QtGui import QKeySequence, QShortcut

    shortcut = QShortcut(QKeySequence("F11"), dialog)
    shortcut.activated.connect(toggle)
    if button is not None:
        button.clicked.connect(toggle)
        update_button_text()
    dialog._graph_window_maximize_shortcut = shortcut
    return toggle
