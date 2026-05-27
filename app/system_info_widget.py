import platform
import subprocess
from pathlib import Path

import psutil
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class SystemInfoWidget(QWidget):
    """
    Минимальная информация о ноутбуке:
    ОС, CPU, память всего/занято, видеокарта.
    """

    def __init__(self):
        super().__init__()

        root = QVBoxLayout(self)

        title = QLabel("Информация о системе")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 6px;")
        root.addWidget(title)

        hint = QLabel(
            "Короткий конфиг ноутбука. Можно скопировать и отправить администратору."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(220)
        root.addWidget(self.text, stretch=1)

        self.refresh_button = QPushButton("Обновить")
        self.refresh_button.clicked.connect(self.refresh)

        self.copy_button = QPushButton("Копировать")
        self.copy_button.clicked.connect(self.copy_to_clipboard)

        root.addWidget(self.refresh_button)
        root.addWidget(self.copy_button)

        self.refresh()

    def run_command(self, command):
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def read_file(self, path):
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def format_bytes(self, value):
        try:
            value = float(value)
        except Exception:
            return "н/д"

        for unit in ["Б", "КБ", "МБ", "ГБ", "ТБ"]:
            if value < 1024:
                return f"{value:.1f} {unit}"
            value /= 1024

        return f"{value:.1f} ПБ"

    def get_linux_distribution(self):
        os_release = self.read_file("/etc/os-release")
        if not os_release:
            return platform.platform()

        data = {}
        for line in os_release.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                data[key] = value.strip().strip('"')

        return data.get("PRETTY_NAME") or platform.platform()

    def get_cpu_name(self):
        cpuinfo = self.read_file("/proc/cpuinfo")
        for line in cpuinfo.splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()

        lscpu = self.run_command(["lscpu"])
        for line in lscpu.splitlines():
            if line.startswith("Model name:"):
                return line.split(":", 1)[1].strip()

        return platform.processor() or "н/д"

    def get_gpu_info(self):
        output = self.run_command(["lspci"])
        if not output:
            return "н/д"

        gpus = []
        for line in output.splitlines():
            lower = line.lower()
            if (
                "vga compatible controller" in lower
                or "3d controller" in lower
                or "display controller" in lower
            ):
                parts = line.split(": ", 1)
                gpus.append(parts[1] if len(parts) > 1 else line)

        return "; ".join(gpus) if gpus else "н/д"

    def build_report(self):
        vm = psutil.virtual_memory()

        return f"""ОС: {self.get_linux_distribution()}
CPU: {self.get_cpu_name()}
Память всего/занято: {self.format_bytes(vm.total)} / {self.format_bytes(vm.used)} ({vm.percent:.0f}%)
Видеокарта: {self.get_gpu_info()}
"""

    def refresh(self):
        self.text.setPlainText(self.build_report())

    def copy_to_clipboard(self):
        value = self.text.toPlainText().strip()

        if not value:
            QMessageBox.warning(self, "Информация о системе", "Нет данных для копирования.")
            return

        QGuiApplication.clipboard().setText(value)
        QMessageBox.information(
            self,
            "Информация о системе",
            "Информация скопирована в буфер обмена."
        )
