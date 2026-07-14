from pathlib import Path

from app.jabka_notification_sounds import (
    GRAPH_CHECK_SOUND_PATH,
    UPDATE_FOUND_SOUND_PATH,
    graph_check_sound_path,
    notification_sounds_enabled,
    update_found_sound_path,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "app" / "jabka_notification_sounds.py").read_text(encoding="utf-8")
MAIN_SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")


def jabka_config(**duty_mode):
    return {"settings": {"theme": "jabka"}, "duty_mode": duty_mode}


def test_sound_preference_defaults_to_enabled_for_old_effective_beep_behaviour():
    assert notification_sounds_enabled(jabka_config())
    assert notification_sounds_enabled(jabka_config(sound_enabled=True))
    assert not notification_sounds_enabled(jabka_config(sound_enabled=False))


def test_graph_check_uses_packaged_jabbix_sound_by_default():
    assert graph_check_sound_path(jabka_config()) == GRAPH_CHECK_SOUND_PATH
    assert str(GRAPH_CHECK_SOUND_PATH).endswith(
        "app/assets/sounds/jabbix_graph_check_kvak.wav"
    )


def test_existing_custom_graph_sound_has_priority(tmp_path):
    custom = tmp_path / "custom.wav"
    custom.write_bytes(b"RIFF")
    assert graph_check_sound_path(jabka_config(sound_path=str(custom))) == custom


def test_missing_custom_graph_sound_falls_back_to_packaged_sound(tmp_path):
    missing = tmp_path / "missing.wav"
    assert graph_check_sound_path(jabka_config(sound_path=str(missing))) == GRAPH_CHECK_SOUND_PATH


def test_update_found_uses_separate_packaged_sound():
    assert update_found_sound_path(jabka_config()) == UPDATE_FOUND_SOUND_PATH
    assert str(UPDATE_FOUND_SOUND_PATH).endswith(
        "app/assets/sounds/jabbix_update_found_kvak.wav"
    )
    assert UPDATE_FOUND_SOUND_PATH != GRAPH_CHECK_SOUND_PATH


def test_disabled_or_non_jabbix_theme_never_routes_theme_sounds():
    assert graph_check_sound_path(jabka_config(sound_enabled=False)) is None
    assert update_found_sound_path(jabka_config(sound_enabled=False)) is None
    normal = {"settings": {"theme": "mass_effect"}, "duty_mode": {"sound_enabled": True}}
    assert graph_check_sound_path(normal) is None
    assert update_found_sound_path(normal) is None


def test_runtime_hooks_are_installed_before_widgets_are_created():
    assert "from app.jabka_notification_sounds import install_jabbix_notification_sounds" in MAIN_SOURCE
    assert "install_jabbix_notification_sounds(config)" in MAIN_SOURCE
    assert MAIN_SOURCE.index("install_jabbix_notification_sounds(config)") < MAIN_SOURCE.index(
        "window = MainWindow("
    )


def test_theme_hooks_cover_graph_update_and_user_opt_out_without_saving_on_startup():
    for marker in (
        "DutyModeWidget",
        "UpdateWidget",
        "DutyModeSettingsWidget",
        "on_release_check_finished",
        "Воспроизводить звуки уведомлений",
        "SOUND_ENABLED_KEY",
        "checkbox.setChecked(False)",
    ):
        assert marker in SOURCE
    assert "save_config" not in SOURCE
