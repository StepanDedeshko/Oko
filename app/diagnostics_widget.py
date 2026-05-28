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
from app.logger import ensure_logs_dir


class DiagnosticsWidget(QWidget):
    LOG_TAIL_LINES = 100

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

        log_title = QLabel("Последние строки лога")
        root.addWidget(log_title)

        self.log_tail_text = QPlainTextEdit()
        self.log_tail_text.setReadOnly(True)
        root.addWidget(self.log_tail_text, stretch=1)

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

        log_row = QHBoxLayout()
        refresh_log_btn = QPushButton("Обновить лог")
        refresh_log_btn.clicked.connect(self.refresh_log_tail)
        copy_log_btn = QPushButton("Скопировать последние строки лога")
        copy_log_btn.clicked.connect(self.copy_log_tail_to_clipboard)
        open_backups_btn = QPushButton("Открыть папку резервных копий")
        open_backups_btn.clicked.connect(self.open_backups_folder)
        log_row.addWidget(refresh_log_btn)
        log_row.addWidget(copy_log_btn)
        log_row.addWidget(open_backups_btn)
        log_row.addStretch()
        root.addLayout(log_row)

        self.refresh()

    def get_app_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent

    def get_backups_dir(self) -> Path:
        return self.get_app_dir() / "_backups"

    def get_log_file_path(self) -> Path:
        return ensure_logs_dir() / "oko.log"

    def read_log_tail_text(self) -> str:
        log_file = self.get_log_file_path()
        if not log_file.exists():
            return f"Лог-файл не найден: {log_file}"

        try:
            with log_file.open("r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError as exc:
            return f"Не удалось прочитать лог-файл: {exc}"

        tail_lines = lines[-self.LOG_TAIL_LINES :]
        if not tail_lines:
            return f"Лог-файл пуст: {log_file}"

        return "".join(tail_lines).rstrip("\n")

    def count_backups_dirs(self, backups_dir: Path) -> int:
        if not backups_dir.exists() or not backups_dir.is_dir():
            return 0
        try:
            return sum(1 for item in backups_dir.iterdir() if item.is_dir())
        except OSError:
            return 0

    def build_text(self):
        app_dir = self.get_app_dir()
        config_path = app_dir / "config.json"
        config_example_path = app_dir / "config.example.json"
        logs_dir = ensure_logs_dir()
        log_file = self.get_log_file_path()
        backups_dir = self.get_backups_dir()
        settings = self.config.get("settings", {}) if isinstance(self.config, dict) else {}

        log_size = f"{log_file.stat().st_size} байт" if log_file.exists() else "—"

        lines = [
            f"Приложение: {APP_NAME}",
            f"Версия: {APP_VERSION}",
            f"Папка приложения: {app_dir}",
            f"Путь config.json: {config_path}",
            f"config.json существует: {'Да' if config_path.exists() else 'Нет'}",
            f"config.example.json существует: {'Да' if config_example_path.exists() else 'Нет'}",
            f"Папка логов: {logs_dir}",
            f"Путь лога: {log_file}",
            f"Размер лога: {log_size}",
            f"Путь папки резервных копий: {backups_dir}",
            f"Папка резервных копий существует: {'Да' if backups_dir.exists() else 'Нет'}",
            f"Количество backup-папок: {self.count_backups_dirs(backups_dir)}",
            f"Текущая тема: {settings.get('theme', 'mass_effect')}",
            f"Автопроверка обновлений: {'Да' if bool(settings.get('check_updates_on_startup', True)) else 'Нет'}",
            f"Python: {platform.python_version()}",
            f"Платформа ОС: {platform.platform()}",
        ]
        return "\n".join(lines)

    def refresh(self):
        self.text.setPlainText(self.build_text())
        self.refresh_log_tail()

    def refresh_log_tail(self):
        self.log_tail_text.setPlainText(self.read_log_tail_text())

    def copy_to_clipboard(self):
        QApplication.clipboard().setText(self.text.toPlainText())
        QMessageBox.information(self, "Диагностика", "Диагностика скопирована в буфер обмена.")

    def copy_log_tail_to_clipboard(self):
        QApplication.clipboard().setText(self.log_tail_text.toPlainText())
        QMessageBox.information(self, "Диагностика", "Последние строки лога скопированы в буфер обмена.")

    def open_logs_folder(self):
        logs_dir = ensure_logs_dir()
        url = QUrl.fromLocalFile(str(logs_dir))
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(self, "Диагностика", "Не удалось открыть папку логов.")

    def open_backups_folder(self):
        backups_dir = self.get_backups_dir()
        backups_dir.mkdir(parents=True, exist_ok=True)
        url = QUrl.fromLocalFile(str(backups_dir))
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(self, "Диагностика", "Не удалось открыть папку резервных копий.")
