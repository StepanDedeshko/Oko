from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl

from app.jabka_theme import is_jabka_config
from app.logger import get_logger

try:
    from PySide6.QtMultimedia import QSoundEffect
except Exception:  # pragma: no cover - optional Qt multimedia runtime
    QSoundEffect = None


PROJECT_ROOT = Path(__file__).resolve().parent.parent
GRAPH_CHECK_SOUND_PATH = PROJECT_ROOT / "app" / "assets" / "sounds" / "jabbix_graph_check_kvak.wav"
UPDATE_FOUND_SOUND_PATH = PROJECT_ROOT / "app" / "assets" / "sounds" / "jabbix_update_found_kvak.wav"
SOUND_ENABLED_KEY = "sound_enabled"


def _duty_settings(config: dict | None) -> dict:
    if not isinstance(config, dict):
        return {}
    value = config.get("duty_mode")
    return value if isinstance(value, dict) else {}


def notification_sounds_enabled(config: dict | None) -> bool:
    """Return the explicit notification-sound preference.

    Older Oko versions had no boolean switch and used a system beep when no
    custom file was selected. Keeping the default enabled therefore preserves
    the effective old behaviour, while the Jabbix settings hook makes
    "Убрать звук" an explicit opt-out from 0.3.7 onward.
    """
    settings = _duty_settings(config)
    return bool(settings.get(SOUND_ENABLED_KEY, True))


def _existing_custom_sound(config: dict | None) -> Path | None:
    value = str(_duty_settings(config).get("sound_path") or "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_file() else None


def graph_check_sound_path(config: dict | None) -> Path | None:
    if not is_jabka_config(config) or not notification_sounds_enabled(config):
        return None
    return _existing_custom_sound(config) or GRAPH_CHECK_SOUND_PATH


def update_found_sound_path(config: dict | None) -> Path | None:
    if not is_jabka_config(config) or not notification_sounds_enabled(config):
        return None
    return UPDATE_FOUND_SOUND_PATH


def play_notification_sound(owner: Any, path: Path | None, *, volume: float = 0.75) -> bool:
    """Play a short theme sound and keep the Qt object alive on its owner."""
    if path is None or not path.is_file() or QSoundEffect is None or owner is None:
        return False
    try:
        effect = getattr(owner, "_jabbix_notification_sound_effect", None)
        if effect is None:
            effect = QSoundEffect(owner)
            setattr(owner, "_jabbix_notification_sound_effect", effect)
        if effect.isPlaying():
            effect.stop()
        effect.setSource(QUrl.fromLocalFile(str(path.resolve())))
        effect.setVolume(max(0.0, min(1.0, float(volume))))
        effect.play()
        return True
    except Exception:
        get_logger().exception("Jabbix notification sound playback failed: %s", path)
        return False


def _install_duty_mode_patch() -> None:
    import app.duty_mode as duty_mode

    cls = duty_mode.DutyModeWidget
    if getattr(cls, "_jabbix_notification_sound_patched", False):
        return
    original_play_sound = cls.play_sound

    def play_sound(self):
        config = getattr(self, "config", None)
        if not is_jabka_config(config):
            return original_play_sound(self)
        path = graph_check_sound_path(config)
        if path is None:
            self.logger.debug("Jabbix graph notification sound skipped: disabled")
            return False
        played = play_notification_sound(self, path)
        if played:
            self.logger.info("Jabbix graph notification sound played: %s", path)
        else:
            self.logger.warning("Jabbix graph notification sound unavailable: %s", path)
        return played

    cls.play_sound = play_sound
    cls._jabbix_notification_sound_patched = True


def _install_update_widget_patch() -> None:
    import app.update_widget as update_widget

    cls = update_widget.UpdateWidget
    if getattr(cls, "_jabbix_notification_sound_patched", False):
        return
    original_finished = cls.on_release_check_finished

    def on_release_check_finished(self, payload):
        if isinstance(payload, dict) and payload.get("tag_name") and payload.get("is_newer"):
            path = update_found_sound_path(getattr(self, "config", None))
            if path is None:
                self.logger.debug("Jabbix update notification sound skipped: disabled")
            elif play_notification_sound(self, path):
                self.logger.info("Jabbix update notification sound played: %s", path)
            else:
                self.logger.warning("Jabbix update notification sound unavailable: %s", path)
        return original_finished(self, payload)

    cls.on_release_check_finished = on_release_check_finished
    cls._jabbix_notification_sound_patched = True


def _install_duty_settings_patch() -> None:
    import app.duty_settings as duty_settings

    cls = duty_settings.DutyModeSettingsWidget
    if getattr(cls, "_jabbix_notification_sound_patched", False):
        return

    original_build_general_section = cls.build_general_section
    original_choose_sound = cls.choose_sound
    original_clear_sound = cls.clear_sound
    original_save = cls.save

    def build_general_section(self, root):
        original_build_general_section(self, root)
        checkbox = duty_settings.QCheckBox("Воспроизводить звуки уведомлений")
        checkbox.setChecked(notification_sounds_enabled(getattr(self, "config", None)))
        checkbox.setToolTip(
            "Для темы «Жабка» используются встроенные квак-звуки. "
            "Выбранный пользовательский звук имеет приоритет для проверки графиков."
        )
        self.sound_enabled_checkbox = checkbox
        root.addWidget(checkbox)

    def choose_sound(self):
        original_choose_sound(self)
        text = str(getattr(self, "sound_label", None).text() or "").strip()
        checkbox = getattr(self, "sound_enabled_checkbox", None)
        if checkbox is not None and text and text != "Звук не выбран":
            checkbox.setChecked(True)

    def clear_sound(self):
        original_clear_sound(self)
        checkbox = getattr(self, "sound_enabled_checkbox", None)
        if checkbox is not None:
            checkbox.setChecked(False)

    def save(self):
        checkbox = getattr(self, "sound_enabled_checkbox", None)
        if checkbox is not None:
            self.settings()[SOUND_ENABLED_KEY] = bool(checkbox.isChecked())
        return original_save(self)

    cls.build_general_section = build_general_section
    cls.choose_sound = choose_sound
    cls.clear_sound = clear_sound
    cls.save = save
    cls._jabbix_notification_sound_patched = True


def install_jabbix_notification_sounds(config: dict | None) -> bool:
    """Install theme-only hooks before the first duty/update widgets are built."""
    if not is_jabka_config(config):
        return False
    _install_duty_mode_patch()
    _install_update_widget_patch()
    _install_duty_settings_patch()
    return True
