from pathlib import Path
import time

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    MULTIMEDIA_AVAILABLE = True
except Exception:
    MULTIMEDIA_AVAILABLE = False
    QAudioOutput = None
    QMediaPlayer = None
    QVideoWidget = None


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class LoadingScreen(QWidget):
    """
    Загрузочный экран Дежурки.

    Поддерживает:
    - точные пути из config.json;
    - автопоиск видео/музыки в assets/loading;
    - fallback-экран, если медиа не найдено или QtMultimedia недоступен.
    """

    VIDEO_EXTENSIONS = [".mp4", ".webm", ".mov", ".mkv", ".avi"]
    AUDIO_EXTENSIONS = [".mp3", ".wav", ".ogg", ".flac", ".m4a"]

    def __init__(self, config, parent=None):
        super().__init__(parent)

        self.config = config.get("loading_screen", {})
        self.video_player = None
        self.music_player = None
        self.video_audio = None
        self.music_audio = None
        self.video_path = None
        self.music_path = None
        self.started_at = time.monotonic()

        self.setWindowTitle("Дежурка загружается")
        self.setWindowFlags(
            Qt.Dialog |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        self.setWindowModality(Qt.ApplicationModal)
        self.resize(900, 520)

        self.setStyleSheet("""
            QWidget {
                background-color: #020914;
                color: #d7e8ff;
            }

            QLabel#Title {
                color: #ffffff;
                font-size: 34px;
                font-weight: bold;
                padding: 10px;
            }

            QLabel#Subtitle {
                color: #8fc7ff;
                font-size: 16px;
                padding: 6px;
            }

            QLabel#Hint {
                color: #ff6570;
                font-size: 13px;
                padding: 6px;
            }
        """)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(18, 18, 18, 18)
        self.layout.setSpacing(8)

        self.title = QLabel("ДЕЖУРКА")
        self.title.setObjectName("Title")
        self.title.setAlignment(Qt.AlignCenter)

        self.subtitle = QLabel("Загрузка панели мониторинга")
        self.subtitle.setObjectName("Subtitle")
        self.subtitle.setAlignment(Qt.AlignCenter)

        self.hint = QLabel("Ожидаю загрузку страницы проблем и счётчика...")
        self.hint.setObjectName("Hint")
        self.hint.setAlignment(Qt.AlignCenter)

        self.layout.addWidget(self.title)
        self.layout.addWidget(self.subtitle)

        self.video_widget = None
        self.setup_media()

        self.layout.addWidget(self.hint)

    def resolve_path(self, value):
        if not value:
            return None

        path = Path(value).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path

        return path

    def find_first_media(self, extensions):
        loading_dir = PROJECT_ROOT / "assets" / "loading"
        if not loading_dir.exists():
            return None

        files = []
        for ext in extensions:
            files.extend(loading_dir.glob(f"*{ext}"))
            files.extend(loading_dir.glob(f"*{ext.upper()}"))

        files = [p for p in files if p.is_file() and not p.name.startswith(".")]
        files.sort(key=lambda p: p.name.lower())

        return files[0] if files else None

    def get_media_paths(self):
        video_path = self.resolve_path(self.config.get("video_path", "assets/loading/loading.mp4"))
        music_path = self.resolve_path(self.config.get("music_path", "assets/loading/loading_music.mp3"))

        auto_detect = bool(self.config.get("auto_detect_media", True))

        if (not video_path or not video_path.exists()) and auto_detect:
            video_path = self.find_first_media(self.VIDEO_EXTENSIONS)

        if (not music_path or not music_path.exists()) and auto_detect:
            music_path = self.find_first_media(self.AUDIO_EXTENSIONS)

        return video_path, music_path

    def setup_media(self):
        self.video_path, self.music_path = self.get_media_paths()

        has_video = self.video_path and self.video_path.exists()
        has_music = self.music_path and self.music_path.exists()

        if not MULTIMEDIA_AVAILABLE:
            media_status = "QtMultimedia недоступен. Видео/музыка не будут проигрываться."
        else:
            media_status = (
                f"Видео: {self.video_path.name if has_video else 'не найдено'} | "
                f"Музыка: {self.music_path.name if has_music else 'не найдена'}"
            )

        if MULTIMEDIA_AVAILABLE and has_video:
            self.video_widget = QVideoWidget()
            self.video_widget.setMinimumHeight(330)
            self.layout.addWidget(self.video_widget, stretch=1)

            self.video_player = QMediaPlayer(self)
            self.video_player.setVideoOutput(self.video_widget)

            # Звук видео выключаем, чтобы не смешивать с отдельной музыкой.
            self.video_audio = QAudioOutput(self)
            self.video_audio.setVolume(0.0)
            self.video_player.setAudioOutput(self.video_audio)

            self.video_player.setSource(QUrl.fromLocalFile(str(self.video_path)))

            if self.config.get("loop_video", True):
                self.video_player.mediaStatusChanged.connect(self.loop_video_if_needed)

            self.video_player.errorOccurred.connect(self.on_video_error)
        else:
            placeholder = QLabel(
                "◇ ДЕЖУРНЫЙ РЕЖИМ ◇\n\n"
                "Загрузка Zabbix и счётчика проблем...\n\n"
                f"{media_status}\n\n"
                "Папка: assets/loading"
            )
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setMinimumHeight(330)
            placeholder.setStyleSheet("""
                QLabel {
                    border: 1px solid #1f7bd6;
                    border-radius: 14px;
                    background-color: #06152d;
                    color: #9fd0ff;
                    font-size: 18px;
                    font-weight: bold;
                }
            """)
            self.layout.addWidget(placeholder, stretch=1)

        if MULTIMEDIA_AVAILABLE and has_music:
            self.music_player = QMediaPlayer(self)
            self.music_audio = QAudioOutput(self)

            volume = int(self.config.get("music_volume", 35))
            volume = max(0, min(volume, 100))
            self.music_audio.setVolume(volume / 100.0)

            self.music_player.setAudioOutput(self.music_audio)
            self.music_player.setSource(QUrl.fromLocalFile(str(self.music_path)))

            if self.config.get("loop_music", True):
                self.music_player.mediaStatusChanged.connect(self.loop_music_if_needed)

            self.music_player.errorOccurred.connect(self.on_music_error)

        self.set_status(media_status)

    def set_status(self, text):
        self.hint.setText(text)

    def on_video_error(self, error, error_string):
        self.set_status(f"Ошибка видео: {error_string}")

    def on_music_error(self, error, error_string):
        self.set_status(f"Ошибка музыки: {error_string}")

    def loop_video_if_needed(self, status):
        if self.video_player and status == QMediaPlayer.EndOfMedia:
            self.video_player.setPosition(0)
            self.video_player.play()

    def loop_music_if_needed(self, status):
        if self.music_player and status == QMediaPlayer.EndOfMedia:
            self.music_player.setPosition(0)
            self.music_player.play()

    def start_media(self):
        if self.video_player:
            self.video_player.play()

        if self.music_player:
            self.music_player.play()

    def stop_media(self):
        if self.video_player:
            self.video_player.stop()

        if self.music_player:
            self.music_player.stop()

    def elapsed_ms(self):
        return int((time.monotonic() - self.started_at) * 1000)

    def closeEvent(self, event):
        self.stop_media()
        super().closeEvent(event)
