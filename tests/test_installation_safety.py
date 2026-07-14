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
    assert "Обнаружена новая установка" in source
    assert "COMMON_RSYNC_EXCLUDES" in source
    assert "RUNTIME_DATA_EXCLUDES" in source
    assert "RSYNC_EXCLUDES" in source


def test_new_install_gets_base_config_but_update_preserves_user_config():
    source = _read("install.sh")
    runtime_block = source.split("RUNTIME_DATA_EXCLUDES=(", 1)[1].split("\n)", 1)[0]
    assert "config.json" not in runtime_block

    update_block = source.split('if [[ "$MODE" == "update" ]]', 1)[1].split("\nfi\n", 1)[0]
    assert "RSYNC_EXCLUDES+=(--exclude='config.json')" in update_block
    assert "базовый config.json" in source

    for protected_path in (
        "credentials.json",
        "web_profiles/",
        "data/",
        "user_data/",
        "logs/",
    ):
        assert f"--exclude='{protected_path}'" in runtime_block


def test_installer_checks_supported_ubuntu_and_system_packages():
    source = _read("install.sh")
    assert "22\\.04|24\\.04" in source
    assert "--force-unsupported" in source
    assert "python3-venv" in source
    assert "python3-pip" in source
    assert "apt-cache show libasound2t64" in source
    assert "sudo apt-get install -y" in source


def test_installer_checks_pyside_qtwebengine_and_native_curl():
    source = _read("install.sh")
    assert "from PySide6 import __version__" in source
    assert "from PySide6.QtWebEngineWidgets import QWebEngineView" in source
    assert "/usr/bin/curl" in source
    assert "обнаружена только Snap-версия" in source
    assert "Не хватает библиотеки:" in source
    assert "Команда исправления системных зависимостей" in source


def test_all_legacy_installers_delegate_to_install_sh():
    expected = 'exec bash "$SCRIPT_DIR/install.sh" "$@"'
    for script in ("INSTALL_OKO.sh", "INSTALL_OKO_GUI.sh", "install_gui.sh"):
        assert expected in _read(script)
