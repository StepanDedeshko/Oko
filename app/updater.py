import os
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from app.config_migrator import patch_config_file


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _find_project_root_in_zip(extract_dir: Path) -> Path:
    if (extract_dir / "main.py").exists() and (extract_dir / "app").exists():
        return extract_dir

    for folder in extract_dir.iterdir():
        if folder.is_dir() and (folder / "main.py").exists() and (folder / "app").exists():
            return folder

    raise RuntimeError("В ZIP не найден проект Дежурка: нет main.py и папки app.")


def _default_update_zip():
    candidates = [
        PROJECT_ROOT / "updates" / "update.zip",
        PROJECT_ROOT / "update.zip",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def _apply_zip(zip_path: Path):
    backup_dir = PROJECT_ROOT / "_backup_before_update"
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    current_config = PROJECT_ROOT / "config.json"
    config_backup = backup_dir / f"config_{timestamp}.json"

    if current_config.exists():
        shutil.copy2(current_config, config_backup)

    # Сохраняем пользовательские видео/музыку загрузки, чтобы обновление не затерло assets/loading.
    loading_media_backup = backup_dir / f"loading_media_{timestamp}"
    loading_media_dir = PROJECT_ROOT / "assets" / "loading"
    if loading_media_dir.exists():
        shutil.copytree(loading_media_dir, loading_media_backup, dirs_exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_path)

        new_root = _find_project_root_in_zip(tmp_path)

        skip_names = {
            ".venv",
            "__pycache__",
            "_backup_before_update",
        }

        for item in new_root.iterdir():
            if item.name in skip_names:
                continue

            # Рабочие ссылки пользователя не затираем.
            if item.name == "config.json":
                continue

            src = item
            dst = PROJECT_ROOT / item.name

            if dst.exists():
                if dst.is_dir():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()

            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        if config_backup.exists():
            shutil.copy2(config_backup, current_config)

        # Возвращаем пользовательские видео/музыку загрузки.
        if loading_media_backup.exists():
            target_loading_dir = PROJECT_ROOT / "assets" / "loading"
            target_loading_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(loading_media_backup, target_loading_dir, dirs_exist_ok=True)

        # Добавляем в сохранённый config.json новые настройки из текущей версии,
        # не затирая ссылки пользователя.
        patch_config_file(current_config)

    for script_name in [
        "ЗАПУСТИТЬ_ДЕЖУРКУ.sh",
        "СОЗДАТЬ_ЯРЛЫК.sh",
        "УСТАНОВИТЬ_ДЕЖУРКУ.sh",
        "ОБНОВИТЬ_ДЕЖУРКУ.sh",
        "run.sh",
        "run_dezhurka.sh",
        "install_gui.sh",
    ]:
        script = PROJECT_ROOT / script_name
        if script.exists():
            try:
                os.chmod(script, 0o755)
            except Exception:
                pass

    # Пересоздаем ярлык тихо.
    shortcut_script = PROJECT_ROOT / "СОЗДАТЬ_ЯРЛЫК.sh"
    if shortcut_script.exists():
        try:
            subprocess.run(
                ["bash", str(shortcut_script), "--no-pause"],
                cwd=str(PROJECT_ROOT),
                timeout=20,
                check=False
            )
        except Exception:
            pass


def apply_update_from_zip(parent_widget=None):
    """
    Простое обновление для пользователя:

    Вариант 1:
    положить ZIP обновления в:
      updates/update.zip
    и нажать кнопку "Обновить приложение".

    Вариант 2:
    если update.zip не найден, приложение попросит выбрать ZIP вручную.
    """
    zip_path = _default_update_zip()

    if zip_path is None:
        selected, _ = QFileDialog.getOpenFileName(
            parent_widget,
            "Выбери ZIP-архив обновления Дежурки",
            str(PROJECT_ROOT),
            "ZIP archives (*.zip)"
        )

        if not selected:
            return

        zip_path = Path(selected)
        message = f"Применить обновление из выбранного файла?\n\n{zip_path}"
    else:
        message = (
            "Найден файл обновления:\n\n"
            f"{zip_path}\n\n"
            "Применить обновление сейчас?"
        )

    answer = QMessageBox.question(
        parent_widget,
        "Обновление приложения",
        message + "\n\nТекущий config.json будет сохранён."
    )

    if answer != QMessageBox.Yes:
        return

    try:
        _apply_zip(zip_path)

        QMessageBox.information(
            parent_widget,
            "Обновление готово",
            "Обновление применено.\n\n"
            "Твой config.json сохранён.\n"
            "Ярлык пересоздан.\n\n"
            "Теперь закрой и снова открой Дежурку."
        )

    except Exception as error:
        QMessageBox.critical(
            parent_widget,
            "Ошибка обновления",
            f"Не удалось применить обновление:\n\n{error}"
        )
