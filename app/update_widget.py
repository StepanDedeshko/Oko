from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
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
from app.config import apply_prepared_config_file, save_config
from app.logger import get_logger
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
    def __init__(self, config, request_restart_callback, parent=None, show_title=True, startup_update_callback=None):
        super().__init__(parent)
        self.config = config
        self.request_restart_callback = request_restart_callback
        self.startup_update_callback = startup_update_callback
        self.logger = get_logger()
        self.release_check_interactive = False
        self.release_check_auto_start_install = False
        root = QVBoxLayout(self)

        if show_title:
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
        self.check_updates_now_button.clicked.connect(self.check_updates_now)
        root.addWidget(self.check_updates_now_button)

        apply_hint = QLabel(
            "Если администратор передал подготовленный конфиг Око, примените его здесь. "
            "Роль и права текущего пользователя при этом не повышаются."
        )
        apply_hint.setWordWrap(True)
        root.addWidget(apply_hint)
        self.apply_config_button = QPushButton("Применить конфиг")
        self.apply_config_button.clicked.connect(self.apply_prepared_config)
        root.addWidget(self.apply_config_button)
        root.addStretch()

        self.update_thread = None
        self.update_worker = None
        self.release_thread = None
        self.release_worker = None
        self.cached_update_info = None

    def apply_prepared_config(self):
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Применить конфиг Око",
            "",
            "JSON (*.json);;Все файлы (*)",
        )
        if not selected_path:
            return
        answer = QMessageBox.question(
            self,
            "Применить конфиг",
            "Будут применены рабочие настройки из выбранного файла. "
            "Роль, права и доступ к настройкам останутся назначенными локально.\n\n"
            "Продолжить?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            applied_config, summary = apply_prepared_config_file(selected_path, self.config)
            self.config.clear()
            self.config.update(applied_config)
        except Exception as exc:
            self.logger.exception("Не удалось применить конфиг Око")
            QMessageBox.warning(self, "Применить конфиг", f"Не удалось применить конфиг:\n{exc}")
            return
        role_title = {"agent": "Агент", "admin": "Администратор", "owner": "Владелец"}.get(str(summary.get("role") or "agent"), str(summary.get("role") or "agent"))
        groups = ", ".join(summary.get("service_group_ids") or []) or "не заданы"
        message = (
            "Конфиг успешно применён.\n\n"
            f"Роль: {role_title}\n"
            f"Доступные группы сервисов: {groups}\n"
            f"Перенесено сервисов: {summary.get('services_count', 0)}\n"
            f"Перенесено ссылок: {summary.get('links_count', 0)}\n"
            f"Перенесено шаблонов: {summary.get('templates_count', 0)}\n"
            "Ограничения сохранены.\n\n"
            "Для полного применения настроек перезапустите приложение."
        )
        self.append_status("Конфиг Око применён")
        QMessageBox.information(self, "Применить конфиг", message)

    def append_status(self, text):
        self.status_log.appendPlainText(text)

    def check_updates_now(self):
        self.check_for_updates(interactive=True, auto_start_install=False)

    def save_check_updates_on_startup(self, enabled):
        self.config.setdefault("settings", {})["check_updates_on_startup"] = bool(enabled)
        save_config(self.config)

    def check_for_updates(self, interactive=False, auto_start_install=False):
        if self.release_thread is not None:
            return
        self.logger.info("Начало проверки обновлений")
        self.release_check_interactive = interactive
        self.release_check_auto_start_install = auto_start_install
        self.release_thread = QThread(self)
        self.release_worker = ReleaseCheckWorker(APP_VERSION)
        self.release_worker.moveToThread(self.release_thread)
        self.release_thread.started.connect(self.release_worker.run)
        self.release_worker.status.connect(self.append_status)
        self.release_worker.finished.connect(self.on_release_check_finished)
        self.release_worker.failed.connect(self.on_release_check_failed)
        self.release_worker.finished.connect(self.release_thread.quit)
        self.release_worker.failed.connect(self.release_thread.quit)
        self.release_worker.finished.connect(self.release_worker.deleteLater)
        self.release_worker.failed.connect(self.release_worker.deleteLater)
        self.release_thread.finished.connect(self.release_thread.deleteLater)
        self.release_thread.finished.connect(self.clear_release_thread_refs)
        self.release_thread.start()

    def on_release_check_finished(self, payload):
        interactive = self.release_check_interactive
        auto_start_install = self.release_check_auto_start_install
        latest_tag = payload.get("tag_name", "")
        is_newer = payload.get("is_newer", False)
        asset_url = payload.get("update_asset_url", "")
        current_version = payload.get("current_version", APP_VERSION)

        self.logger.info("Найдена версия релиза: %s", latest_tag or "unknown")
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
        self.cached_update_info = payload
        self.logger.info("Startup update check found new version: current=%s latest=%s", current_version, latest_tag)
        if not asset_url:
            self.append_status("Ошибка обновления")
            QMessageBox.information(
                self,
                "Доступно обновление",
                "Новая версия найдена, но архив update.zip не прикреплён к релизу."
            )
            return

        self.logger.info("Startup update prompt shown")
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
            self.logger.info("Startup update prompt declined")
            self.logger.info("User declined startup update prompt")
            return
        self.logger.info("Startup update prompt accepted")
        self.url_input.setText(asset_url)
        if auto_start_install:
            if self.startup_update_callback is not None:
                self.startup_update_callback(payload)
            else:
                self.open_update_tab()
                self.start_update_from_prompt(payload)
            return
        self.open_update_tab()

    def on_release_check_failed(self, error_text):
        interactive = self.release_check_interactive
        self.logger.warning("Не удалось проверить обновления: %s", error_text)
        if interactive:
            self.append_status("Ошибка обновления")
            self.append_status(error_text)

    def clear_release_thread_refs(self):
        self.release_thread = None
        self.release_worker = None

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
        answer = QMessageBox.question(
            self,
            "Подтверждение обновления",
            "Перед обновлением будет создан backup.\n"
            "config.json сохранится.\n\n"
            "Начать обновление?"
        )
        if answer != QMessageBox.Yes:
            return
        self._start_download_and_install(update_url)

    def start_update_from_prompt(self, update_info=None):
        self.logger.info("Starting update from startup prompt")
        if self.update_thread is not None:
            self.logger.info("Update already running, focusing update page")
            self.open_update_tab()
            self.append_status("Обновление уже выполняется")
            return False
        if update_info:
            self.cached_update_info = update_info
        update_info = update_info or self.cached_update_info or {}
        update_url = str(update_info.get("update_asset_url") or update_info.get("update_url") or self.url_input.text() or "").strip()
        if not update_url:
            self.logger.error("Startup update accepted but update URL is missing")
            self.append_status("Не удалось запустить обновление: ссылка на обновление не найдена.")
            return False
        self.url_input.setText(update_url)
        self.append_status("Подготовка обновления...")
        try:
            return self._start_download_and_install(update_url)
        except Exception:
            self.logger.exception("Failed to start update from startup prompt")
            self.append_status("Failed to start update from startup prompt")
            return False

    def _start_download_and_install(self, update_url):
        if self.update_thread is not None:
            self.logger.info("Update already running, focusing update page")
            self.open_update_tab()
            self.append_status("Обновление уже выполняется")
            return False
        self.config.setdefault("settings", {})["update_archive_url"] = update_url
        save_config(self.config)
        self.logger.info("Начало установки обновления из URL: %s", update_url)
        self.status_log.clear()
        self.append_status("Подготовка обновления...")
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
        self.update_worker.finished.connect(self.update_worker.deleteLater)
        self.update_worker.failed.connect(self.update_worker.deleteLater)
        self.update_thread.finished.connect(self.update_thread.deleteLater)
        self.update_thread.finished.connect(self.clear_update_thread_refs)
        self.update_thread.start()
        return True

    def on_update_finished(self, stdout_text, stderr_text):
        self.logger.info("Обновление успешно завершено")
        self.append_status("Обновление завершено")
        if stdout_text:
            self.append_status("\n=== STDOUT ===")
            self.append_status(stdout_text)
        if stderr_text:
            self.append_status("\n=== STDERR ===")
            self.append_status(stderr_text)
        self.install_button.setEnabled(True)
        restarted = self.request_restart_callback(
            self,
            "Обновление установлено. Рекомендуется перезапустить приложение."
        )
        if not restarted:
            QMessageBox.information(self, "Обновление", "Перезапусти приложение позже вручную.")

    def on_update_failed(self, error_text):
        self.logger.error("Ошибка обновления: %s", error_text)
        self.append_status("Ошибка обновления")
        self.append_status("\n=== ОШИБКА ===")
        self.append_status(error_text)
        self.install_button.setEnabled(True)
        QMessageBox.critical(self, "Ошибка обновления", error_text)

    def clear_update_thread_refs(self):
        self.update_thread = None
        self.update_worker = None

    def cleanup(self):
        """Stop background update/check threads before application shutdown."""
        for thread_attr in ("release_thread", "update_thread"):
            thread = getattr(self, thread_attr, None)
            if thread is None:
                continue
            try:
                thread.quit()
                thread.wait(3000)
            except Exception:
                pass
            setattr(self, thread_attr, None)
        self.release_worker = None
        self.cached_update_info = None
        self.update_worker = None
