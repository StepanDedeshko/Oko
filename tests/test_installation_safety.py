from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_update_script_protects_user_data():
    source = _read("UPDATE_OKO.sh")
    for protected_path in (
        "config.json",
        "credentials.json",
        "web_profiles/",
        "data/",
        "user_data/",
        "logs/",
    ):
        assert f"--exclude='{protected_path}'" in source

    assert "rsync -a --delete" in source
    assert "PROTECTED_EXCLUDES" in source
    assert "PySide6.QtWebEngineWidgets" in source


def test_one_command_installer_distinguishes_new_install_and_update():
    source = _read("install.sh")
    assert 'MODE="new"' in source
    assert 'MODE="update"' in source
    assert "Обнаружена существующая установка" in source
    assert "PROTECTED_RSYNC_EXCLUDES" in source

    for protected_path in (
        "config.json",
        "credentials.json",
        "web_profiles/",
        "data/",
        "logs/",
    ):
        assert f"--exclude='{protected_path}'" in source


def test_installer_checks_pyside_and_qtwebengine():
    source = _read("install.sh")
    assert "from PySide6 import __version__" in source
    assert "from PySide6.QtWebEngineWidgets import QWebEngineView" in source
    assert "python3-venv" in source
    assert "/usr/bin/curl" in source


def test_legacy_installer_delegates_to_install_sh():
    source = _read("INSTALL_OKO.sh")
    assert 'exec bash "$SCRIPT_DIR/install.sh" "$@"' in source
