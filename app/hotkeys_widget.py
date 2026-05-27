from PySide6.QtWidgets import (
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class HotkeysWidget(QWidget):
    """
    Справка по горячим клавишам.
    Пока это информационный экран, без редактирования комбинаций.
    """

    def __init__(self):
        super().__init__()

        root = QVBoxLayout(self)

        title = QLabel("Горячие клавиши")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 6px;")
        root.addWidget(title)

        hint = QLabel(
            "Здесь отображаются основные горячие клавиши Дежурки. "
            "Если понадобится, позже можно сделать редактирование комбинаций."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Клавиша", "Действие"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        hotkeys = [
            ("F5", "Обновить текущий открытый раздел"),
            ("Ctrl + R", "Обновить текущий открытый раздел"),
            ("F11", "Включить / выключить полный экран"),
            ("Esc", "Выйти из полного экрана"),
            ("Alt + ↓", "Открыть выпадающий список, если фокус на поле выбора"),
            ("Tab", "Перейти к следующему элементу интерфейса"),
            ("Shift + Tab", "Перейти к предыдущему элементу интерфейса"),
        ]

        self.table.setRowCount(len(hotkeys))

        for row, (keys, action) in enumerate(hotkeys):
            self.table.setItem(row, 0, QTableWidgetItem(keys))
            self.table.setItem(row, 1, QTableWidgetItem(action))

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

        root.addWidget(self.table, stretch=1)
