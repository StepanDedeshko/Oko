#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path


APP_NAME = "Око"
APP_VERSION = "0.2 [pre-release]"
APP_DESCRIPTION = (
    "Око — панель дежурного мониторинга Zabbix/ОТРС.\n\n"
    "Приложение предназначено для просмотра графиков, работы с режимом "
    "дежурства, привязки задач ОТРС, быстрого доступа к рабочим разделам "
    "и ведения заметок дежурного."
)


def source_dir():
    return Path(__file__).resolve().parent


def default_install_dir():
    return Path.home() / "Applications" / "Oko"


def ignore_install_files(directory, names):
    ignored = {
        ".venv",
        "__pycache__",
        "_backups",
        ".git",
        ".idea",
        ".vscode",
    }

    result = []

    for name in names:
        if name in ignored:
            result.append(name)
        elif name.endswith(".pyc"):
            result.append(name)
        elif name.endswith(".pyo"):
            result.append(name)

    return result


class GuiInstaller:
    def __init__(self):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk

        self.root = tk.Tk()
        self.root.title(f"Установка {APP_NAME}")
        self.root.geometry("760x560")
        self.root.minsize(720, 520)

        self.install_path = tk.StringVar(value=str(default_install_dir()))
        self.installing = False

        self.build_ui()
        self.center_window()

    def center_window(self):
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = int((self.root.winfo_screenwidth() - width) / 2)
        y = int((self.root.winfo_screenheight() - height) / 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def build_ui(self):
        tk = self.tk
        ttk = self.ttk

        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")

        title = ttk.Label(
            header,
            text=APP_NAME,
            font=("Arial", 24, "bold")
        )
        title.pack(side="left")

        version = ttk.Label(
            header,
            text=APP_VERSION,
            font=("Arial", 11)
        )
        version.pack(side="left", padx=(12, 0), pady=(10, 0))

        about_button = ttk.Button(
            header,
            text="О приложении",
            command=self.show_about
        )
        about_button.pack(side="right")

        sep = ttk.Separator(outer)
        sep.pack(fill="x", pady=14)

        message = ttk.Label(
            outer,
            text=(
                "Установка будет произведена по указанному пути.\n"
                "Можно оставить путь по умолчанию или выбрать другую папку."
            ),
            wraplength=700
        )
        message.pack(anchor="w")

        path_frame = ttk.LabelFrame(outer, text="Папка установки", padding=10)
        path_frame.pack(fill="x", pady=(14, 10))

        path_entry = ttk.Entry(path_frame, textvariable=self.install_path)
        path_entry.pack(side="left", fill="x", expand=True)

        browse_button = ttk.Button(
            path_frame,
            text="Обзор...",
            command=self.browse_folder
        )
        browse_button.pack(side="left", padx=(8, 0))

        info = ttk.Label(
            outer,
            text=(
                "После установки будет создан ярлык «Око» в меню приложений. "
                "Пользовательские настройки при обновлениях сохраняются."
            ),
            wraplength=700
        )
        info.pack(anchor="w", pady=(0, 10))

        log_frame = ttk.LabelFrame(outer, text="Ход установки", padding=8)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            log_frame,
            height=12,
            wrap="word",
            state="disabled"
        )
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(14, 0))

        self.install_button = ttk.Button(
            buttons,
            text="Установить",
            command=self.start_install
        )
        self.install_button.pack(side="right")

        close_button = ttk.Button(
            buttons,
            text="Закрыть",
            command=self.root.destroy
        )
        close_button.pack(side="right", padx=(0, 8))

        self.run_after_install = tk.BooleanVar(value=True)
        run_check = ttk.Checkbutton(
            buttons,
            text="Запустить после установки",
            variable=self.run_after_install
        )
        run_check.pack(side="left")

        self.log(f"Готово к установке {APP_NAME} {APP_VERSION}.")
        self.log(f"Путь по умолчанию: {self.install_path.get()}")

    def show_about(self):
        from tkinter import messagebox

        messagebox.showinfo(
            f"О приложении {APP_NAME}",
            f"{APP_NAME}\n"
            f"Версия: {APP_VERSION}\n\n"
            f"{APP_DESCRIPTION}"
        )

    def browse_folder(self):
        from tkinter import filedialog

        selected = filedialog.askdirectory(
            title="Выберите папку установки",
            initialdir=str(Path.home())
        )

        if selected:
            target = Path(selected)

            # Если пользователь выбрал просто родительскую папку, ставим туда /Oko.
            if target.name.lower() not in ("oko", "око"):
                target = target / "Oko"

            self.install_path.set(str(target))

    def log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", str(text) + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.root.update_idletasks()

    def start_install(self):
        if self.installing:
            return

        self.installing = True
        self.install_button.configure(state="disabled")

        thread = threading.Thread(target=self.install, daemon=True)
        thread.start()

    def install(self):
        try:
            self._install()
        except Exception as error:
            self.log("")
            self.log(f"ОШИБКА: {error}")
            self.install_button.configure(state="normal")
            self.installing = False
            return

        self.installing = False
        self.install_button.configure(state="normal")

    def _install(self):
        src = source_dir()
        dst = Path(self.install_path.get()).expanduser().resolve()

        if not (src / "main.py").exists() or not (src / "app").exists():
            raise RuntimeError("Папка установщика не похожа на сборку Око: нет main.py/app.")

        self.log("")
        self.log(f"Источник: {src}")
        self.log(f"Папка установки: {dst}")

        dst.mkdir(parents=True, exist_ok=True)

        if src == dst:
            self.log("Приложение уже находится в выбранной папке. Копирование не требуется.")
        else:
            backup_dir = None

            if (dst / "main.py").exists() and (dst / "app").exists():
                backup_root = dst / "_backups"
                backup_root.mkdir(parents=True, exist_ok=True)
                import datetime
                backup_dir = backup_root / ("before_gui_install_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))

                self.log(f"Найдена старая установка. Делаю резервную копию: {backup_dir}")
                shutil.copytree(
                    dst,
                    backup_dir,
                    ignore=ignore_install_files,
                    dirs_exist_ok=True
                )

            saved_config = None

            if (dst / "config.json").exists():
                saved_config = (dst / "config.json").read_text(encoding="utf-8")
                self.log("Сохраняю существующий config.json пользователя.")

            self.log("Копирую файлы приложения...")
            shutil.copytree(
                src,
                dst,
                ignore=ignore_install_files,
                dirs_exist_ok=True
            )

            if saved_config is not None:
                (dst / "config.json").write_text(saved_config, encoding="utf-8")
                self.log("Возвращаю пользовательский config.json.")

        self.make_scripts_executable(dst)

        self.log("Создаю ярлык приложения...")
        self.run_command(["bash", str(dst / "CREATE_DESKTOP_SHORTCUT.sh"), "--no-pause"], cwd=dst, check=False)

        self.log("")
        self.log("Установка завершена.")
        self.log(f"Запуск: {dst / 'run_oko.sh'}")

        if self.run_after_install.get():
            self.log("Запускаю приложение...")
            subprocess.Popen(["bash", str(dst / "run_oko.sh")], cwd=str(dst))
            self.root.after(900, self.root.destroy)

    def make_scripts_executable(self, dst):
        for script in [
            "run_oko.sh",
            "start_terminal.sh",
            "run_terminal.sh",
            "INSTALL_OKO.sh",
            "INSTALL_OKO_GUI.sh",
            "UPDATE_OKO.sh",
            "ROLLBACK_OKO.sh",
            "CREATE_DESKTOP_SHORTCUT.sh",
            "СОЗДАТЬ_ЯРЛЫК.sh",
            "ЗАПУСТИТЬ_ОКО.sh",
        ]:
            path = dst / script
            if path.exists():
                try:
                    path.chmod(path.stat().st_mode | 0o755)
                except Exception:
                    pass

    def run_command(self, command, cwd=None, check=True):
        self.log("$ " + " ".join(str(item) for item in command))

        process = subprocess.Popen(
            command,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        for line in process.stdout:
            self.log(line.rstrip())

        code = process.wait()

        if check and code != 0:
            raise RuntimeError(f"Команда завершилась с ошибкой: {' '.join(command)}")

        return code

    def run(self):
        self.root.mainloop()


def run_gui():
    installer = GuiInstaller()
    installer.run()


def run_console_fallback():
    print(f"Установка {APP_NAME} {APP_VERSION}")
    print("")
    print("Графический установщик недоступен.")
    print("Запустите INSTALL_OKO.sh или установите python3-tk.")
    print("")
    input("Нажмите Enter для выхода...")


if __name__ == "__main__":
    try:
        run_gui()
    except Exception as error:
        print("Не удалось открыть графический установщик:", error)
        run_console_fallback()
