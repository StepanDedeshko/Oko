import platform
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
)

from app.app_info import APP_NAME, APP_VERSION
from app.logger import ensure_logs_dir, get_logs_dir


class DiagnosticsWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config

        root = QVBoxLayout(self)
        title = QLabel("Диагностика")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        root.addWidget(self.text, stretch=1)

        row = QHBoxLayout()
        refresh_btn = QPushButton("Обновить диагностику")
        refresh_btn.clicked.connect(self.refresh)
        copy_btn = QPushButton("Скопировать диагностику")
        copy_btn.clicked.connect(self.copy_to_clipboard)
        open_logs_btn = QPushButton("Открыть папку логов")
        open_logs_btn.clicked.connect(self.open_logs_folder)
        row.addWidget(refresh_btn)
        row.addWidget(copy_btn)
        row.addWidget(open_logs_btn)
        row.addStretch()
        root.addLayout(row)

        self.refresh()

    def build_text(self):
        app_dir = Path(__file__).resolve().parent.parent
        config_path = app_dir / "config.json"
        config_example_path = app_dir / "config.example.json"
        logs_dir = ensure_logs_dir()
        settings = self.config.get("settings", {}) if isinstance(self.config, dict) else {}

        lines = [
            f"Приложение: {APP_NAME}",
            f"Версия: {APP_VERSION}",
            f"Папка приложения: {app_dir}",
            f"Путь config.json: {config_path}",
            f"config.json существует: {'Да' if config_path.exists() else 'Нет'}",
            f"config.example.json существует: {'Да' if config_example_path.exists() else 'Нет'}",
            f"Папка логов: {logs_dir}",
            f"Текущая тема: {settings.get('theme', 'mass_effect')}",
            f"Автопроверка обновлений: {'Да' if bool(settings.get('check_updates_on_startup', True)) else 'Нет'}",
            f"Python: {platform.python_version()}",
            f"Платформа ОС: {platform.platform()}",
        ]
        return "\n".join(lines)

    def refresh(self):
        self.text.setPlainText(self.build_text())

    def copy_to_clipboard(self):
        QApplication.clipboard().setText(self.text.toPlainText())
        QMessageBox.information(self, "Диагностика", "Диагностика скопирована в буфер обмена.")

    def open_logs_folder(self):
        logs_dir = ensure_logs_dir()
        url = QUrl.fromLocalFile(str(logs_dir))
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(self, "Диагностика", "Не удалось открыть папку логов.")
