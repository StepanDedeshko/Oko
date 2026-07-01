from pathlib import Path

SOURCE = Path("app/update_widget.py").read_text(encoding="utf-8")


def test_prompt_yes_uses_startup_callback_and_prompt_starter():
    assert "startup_update_callback(payload)" in SOURCE
    assert "self.start_update_from_prompt(payload)" in SOURCE
    assert "auto_start_install" in SOURCE


def test_prompt_no_logs_decline_and_returns_before_start():
    declined_block = SOURCE.split("if answer != QMessageBox.Yes:", 1)[1].split("self.logger.info(\"Startup update prompt accepted\")", 1)[0]
    assert "Startup update prompt declined" in declined_block
    assert "User declined startup update prompt" in declined_block
    assert "return" in declined_block


def test_update_already_running_is_guarded():
    method = SOURCE.split("def start_update_from_prompt", 1)[1].split("def _start_download_and_install", 1)[0]
    assert "if self.update_thread is not None" in method
    assert "Обновление уже выполняется" in method
    assert "UpdateWorker" not in method


def test_missing_update_url_is_handled():
    method = SOURCE.split("def start_update_from_prompt", 1)[1].split("def _start_download_and_install", 1)[0]
    assert "Startup update accepted but update URL is missing" in method
    assert "ссылка на обновление не найдена" in method
