from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox


class NoWheelComboBox(QComboBox):
    """QComboBox that does not change values while the user scrolls a settings page."""

    def wheelEvent(self, event):
        event.ignore()


class NoWheelSpinBox(QSpinBox):
    """QSpinBox that lets parent scroll areas handle mouse wheel scrolling."""

    def wheelEvent(self, event):
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that lets parent scroll areas handle mouse wheel scrolling."""

    def wheelEvent(self, event):
        event.ignore()
