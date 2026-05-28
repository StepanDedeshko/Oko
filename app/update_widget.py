from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.app_info import APP_VERSION
from app.config import save_config
from app.updater import (
    download_and_install_update,
    fetch_latest_release_info,
    normalize_version_to_tuple,
)


class UpdateWorker(QObject):
    status = Signal(str)
    finished = Signal(str, str)
    failed = Signal(str)

    def __init__(self, update_url):
        super().__init__()
        self.update_url = update_url

    def run(self):
        self.status.emit("Скачивание обновления...")
        try:
            self.status.emit("Запуск UPDATE_OKO.sh...")
            stdout_text, stderr_text = download_and_install_update(self.update_url)
            self.finished.emit(stdout_text, stderr_text)
        except Exception as error:
            self.failed.emit(str(error))


class ReleaseCheckWorker(QObject):
    status = Signal(str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, current_version):
        super().__init__()
        self.current_version = current_version

    def run(self):
        try:
            self.status.emit("Проверка обновлений...")
            release = fetch_latest_release_info()
            latest_tag = release.get("tag_name", "")
            latest_tuple = normalize_version_to_tuple(latest_tag)
            current_tuple = normalize_version_to_tuple(self.current_version)
            release["is_newer"] = latest_tuple > current_tuple
            release["current_version"] = self.current_version
            self.finished.emit(release)
        except Exception as error:
            self.failed.emit(str(error))


class UpdateWidget(QWidget):
    def __init__(self, config, request_restart_callback, parent=None):
        super().__init__(parent)
        self.config = config
        self.request_restart_callback = request_restart_callback
        root = QVBoxLayout(self)

        title = QLabel("Обновление")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        version = QLabel(f"Текущая версия: {APP_VERSION}")
        version.setWordWrap(True)
        root.addWidget(version)

        self.url_input = QLineEdit(
            self.config.setdefault("settings", {}).get("update_archive_url", "")
        )
        self.url_input.setPlaceholderText(
            "https://github.com/<owner>/<repo>/releases/download/<tag>/update.zip"
        )
        help_label = QLabel("Рекомендуется использовать прямую ссылку на asset из GitHub Releases.")
        help_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("URL архива обновления:", self.url_input)
        root.addLayout(form)
        root.addWidget(help_label)

        self.install_button = QPushButton("Скачать и установить")
        self.install_button.clicked.connect(self.download_and_install)
        root.addWidget(self.install_button)

        self.status_log = QPlainTextEdit()
        self.status_log.setReadOnly(True)
        self.status_log.setPlaceholderText("Здесь будет отображаться статус обновления...")
        root.addWidget(self.status_log, stretch=1)

        self.check_on_startup_checkbox = QCheckBox("Проверять обновления при запуске")
        enabled = self.config.setdefault("settings", {}).get("check_updates_on_startup", True)
        self.check_on_startup_checkbox.setChecked(bool(enabled))
        self.check_on_startup_checkbox.toggled.connect(self.save_check_updates_on_startup)
        root.addWidget(self.check_on_startup_checkbox)

        self.check_updates_now_button = QPushButton("Проверить обновления сейчас")
        self.check_updates_now_button.clicked.connect(
            lambda: self.check_for_updates(interactive=True, auto_start_install=False)
        )
        root.addWidget(self.check_updates_now_button)
        root.addStretch()

        self.update_thread = None
        self.update_worker = None
        self.release_thread = None
        self.release_worker = None

    def append_status(self, text):
        self.status_log.appendPlainText(text)

    def save_check_updates_on_startup(self, enabled):
        self.config.setdefault("settings", {})["check_updates_on_startup"] = bool(enabled)
        save_config(self.config)

    def check_for_updates(self, interactive=False, auto_start_install=False):
        if self.release_thread is not None:
            return
        self.release_thread = QThread(self)
        self.release_worker = ReleaseCheckWorker(APP_VERSION)
        self.release_worker.moveToThread(self.release_thread)
        self.release_thread.started.connect(self.release_worker.run)
        self.release_worker.status.connect(self.append_status)
        self.release_worker.finished.connect(
            lambda payload: self.on_release_check_finished(payload, interactive, auto_start_install)
        )
        self.release_worker.failed.connect(lambda error: self.on_release_check_failed(error, interactive))
        self.release_worker.finished.connect(self.release_thread.quit)
        self.release_worker.failed.connect(self.release_thread.quit)
        self.release_thread.finished.connect(self.release_thread.deleteLater)
        self.release_thread.start()

    def on_release_check_finished(self, payload, interactive, auto_start_install):
        self.release_thread = None
        self.release_worker = None
        latest_tag = payload.get("tag_name", "")
        is_newer = payload.get("is_newer", False)
        asset_url = payload.get("update_asset_url", "")
        current_version = payload.get("current_version", APP_VERSION)

        if not latest_tag:
            if interactive:
                self.append_status("Ошибка обновления")
                QMessageBox.information(self, "Обновление", "Не удалось определить версию последнего релиза.")
            return
        if not is_newer:
            if interactive:
                self.append_status("Обновление не требуется")
                QMessageBox.information(self, "Обновление", "У вас уже установлена актуальная версия.")
            return
        if not asset_url:
            self.append_status("Ошибка обновления")
            QMessageBox.information(
                self,
                "Доступно обновление",
                "Новая версия найдена, но архив update.zip не прикреплён к релизу."
            )
            return

        answer = QMessageBox.question(
            self,
            "Доступно обновление",
            f"Доступна новая версия Око: {latest_tag}.\n"
            f"Текущая версия: {current_version}.\n\n"
            "Обновить сейчас?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if answer != QMessageBox.Yes:
            return
        self.url_input.setText(asset_url)
        self.open_update_tab()
        if auto_start_install:
            self.download_and_install()

    def on_release_check_failed(self, error_text, interactive):
        self.release_thread = None
        self.release_worker = None
        print(f"Не удалось проверить обновления: {error_text}")
        if interactive:
            self.append_status("Ошибка обновления")
            self.append_status(error_text)

    def open_update_tab(self):
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, QTabWidget):
                index = parent.indexOf(self)
                if index >= 0:
                    parent.setCurrentIndex(index)
                return
            parent = parent.parent()

    def download_and_install(self):
        update_url = self.url_input.text().strip()
        if not update_url:
            QMessageBox.warning(self, "Обновление", "Укажи URL архива обновления.")
            return
        self.config.setdefault("settings", {})["update_archive_url"] = update_url
        save_config(self.config)
        answer = QMessageBox.question(
            self,
            "Подтверждение обновления",
            "Перед обновлением будет создан backup.\n"
            "config.json сохранится.\n\n"
            "Начать обновление?"
        )
        if answer != QMessageBox.Yes:
            return

        self.status_log.clear()
        self.append_status("Скачивание обновления...")
        self.install_button.setEnabled(False)
        self.update_thread = QThread(self)
        self.update_worker = UpdateWorker(update_url)
        self.update_worker.moveToThread(self.update_thread)
        self.update_thread.started.connect(self.update_worker.run)
        self.update_worker.status.connect(self.append_status)
        self.update_worker.finished.connect(self.on_update_finished)
        self.update_worker.failed.connect(self.on_update_failed)
        self.update_worker.finished.connect(self.update_thread.quit)
        self.update_worker.failed.connect(self.update_thread.quit)
        self.update_thread.finished.connect(self.update_thread.deleteLater)
        self.update_thread.start()

    def on_update_finished(self, stdout_text, stderr_text):
        self.append_status("Обновление завершено")
        if stdout_text:
            self.append_status("\n=== STDOUT ===")
            self.append_status(stdout_text)
        if stderr_text:
            self.append_status("\n=== STDERR ===")
            self.append_status(stderr_text)
        self.install_button.setEnabled(True)
        self.update_thread = None
        self.update_worker = None
        restarted = self.request_restart_callback(
            self,
            "Обновление установлено. Рекомендуется перезапустить приложение."
        )
        if not restarted:
            QMessageBox.information(self, "Обновление", "Перезапусти приложение позже вручную.")

    def on_update_failed(self, error_text):
        self.append_status("Ошибка обновления")
        self.append_status("\n=== ОШИБКА ===")
        self.append_status(error_text)
        self.install_button.setEnabled(True)
        self.update_thread = None
        self.update_worker = None
        QMessageBox.critical(self, "Ошибка обновления", error_text)
