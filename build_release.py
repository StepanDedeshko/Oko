from __future__ import annotations

import hashlib
import shutil
import stat
import zipfile
from pathlib import Path

from app.app_info import APP_VERSION


EXPECTED_VERSION = "0.3.7"
ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
PACKAGE_NAME = f"Oko-{APP_VERSION}"
STAGE = DIST / PACKAGE_NAME

EXCLUDED_TOP_LEVEL = {
    ".git",
    ".github",
    ".venv",
    ".pytest_cache",
    "tests",
    "dist",
    "_backups",
    "_backup_before_update",
    "credentials.json",
    "web_profiles",
    "data",
    "user_data",
    "logs",
    "updates",
    "build_release.py",
    "CHECK_RELEASE.sh",
}

REQUIRED = (
    "main.py",
    "app",
    "assets",
    "config.json",
    "requirements.txt",
    "install.sh",
    "UPDATE_OKO.sh",
    "run_oko.sh",
    "CREATE_DESKTOP_SHORTCUT.sh",
    "assets/themes/jabka/backgrounds/00_main_menu_wallpaper.png",
    "assets/themes/jabka/backgrounds/10_settings_menu_wallpaper.png",
    "assets/themes/jabka/sounds/frog_croak.wav",
    "app/assets/sounds/jabbix_graph_check_kvak.wav",
    "app/assets/sounds/jabbix_update_found_kvak.wav",
)


def should_exclude(relative: Path) -> bool:
    if not relative.parts:
        return False
    if relative.parts[0] in EXCLUDED_TOP_LEVEL:
        return True
    if "__pycache__" in relative.parts:
        return True
    name = relative.name
    if name.endswith((".pyc", ".log")):
        return True
    if name.startswith("RELEASE_NOTES_") and name.endswith(".md"):
        return True
    if name.startswith("JABBIX_ASSET_SHA256SUMS_") and name.endswith(".txt"):
        return True
    return False


def copy_runtime_tree() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    STAGE.mkdir(parents=True)

    for source in ROOT.rglob("*"):
        relative = source.relative_to(ROOT)
        if should_exclude(relative):
            continue
        destination = STAGE / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    for script in STAGE.glob("*.sh"):
        script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def verify_stage() -> None:
    if APP_VERSION != EXPECTED_VERSION:
        raise RuntimeError(f"Ожидалась версия {EXPECTED_VERSION}, получена {APP_VERSION}")
    for item in REQUIRED:
        if not (STAGE / item).exists():
            raise RuntimeError(f"В сборке отсутствует обязательный файл: {item}")
    forbidden = (
        STAGE / "credentials.json",
        STAGE / "tests",
        STAGE / ".github",
        STAGE / ".venv",
        STAGE / "logs",
        STAGE / "data",
    )
    for path in forbidden:
        if path.exists():
            raise RuntimeError(f"В релиз попал запрещённый путь: {path.relative_to(STAGE)}")


def add_tree(archive: zipfile.ZipFile, prefix: str) -> None:
    for path in sorted(STAGE.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(STAGE).as_posix()
        archive_name = f"{prefix}/{relative}" if prefix else relative
        info = zipfile.ZipInfo.from_file(path, archive_name)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
        archive.writestr(info, path.read_bytes())


def build_archives() -> tuple[Path, Path]:
    update_zip = DIST / "update.zip"
    install_zip = DIST / f"{PACKAGE_NAME}-linux.zip"
    with zipfile.ZipFile(update_zip, "w", allowZip64=True) as archive:
        add_tree(archive, "")
    with zipfile.ZipFile(install_zip, "w", allowZip64=True) as archive:
        add_tree(archive, PACKAGE_NAME)
    return update_zip, install_zip


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(paths: tuple[Path, ...]) -> Path:
    output = DIST / "SHA256SUMS.txt"
    output.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in paths),
        encoding="utf-8",
    )
    return output


def verify_update_zip(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        for required in ("main.py", "app/app_info.py", "install.sh", "UPDATE_OKO.sh"):
            if required not in names:
                raise RuntimeError(f"{required} отсутствует в update.zip")
        app_info = archive.read("app/app_info.py").decode("utf-8")
        if f'APP_VERSION = "{EXPECTED_VERSION}"' not in app_info:
            raise RuntimeError("В update.zip неверная версия приложения")
        if "credentials.json" in names:
            raise RuntimeError("В update.zip попал credentials.json")
        if any(name.startswith(("tests/", ".github/", ".venv/", "logs/", "data/")) for name in names):
            raise RuntimeError("В update.zip попали тесты, CI или пользовательские данные")


def main() -> None:
    copy_runtime_tree()
    verify_stage()
    update_zip, install_zip = build_archives()
    verify_update_zip(update_zip)
    checksums = write_checksums((update_zip, install_zip))
    for path in (update_zip, install_zip, checksums):
        print(f"{path.name}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
