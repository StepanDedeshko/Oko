ЗАГРУЗОЧНАЯ ЗАСТАВКА С ВИДЕО И МУЗЫКОЙ

Добавлен загрузочный экран после авторизации.

Куда положить файлы:

    assets/loading/loading.mp4
    assets/loading/loading_music.mp3

Если файлов нет:
приложение покажет обычный sci-fi экран загрузки без видео и музыки.

Настройка в config.json:

"loading_screen": {
  "enabled": true,
  "show_after_login": true,
  "duration_ms": 5000,
  "video_path": "assets/loading/loading.mp4",
  "music_path": "assets/loading/loading_music.mp3",
  "music_volume": 35,
  "loop_video": true,
  "loop_music": true
}

Что можно поменять:
- duration_ms — сколько миллисекунд показывать заставку;
- music_volume — громкость музыки от 0 до 100;
- enabled — включить/выключить заставку;
- show_after_login — показывать после окна входа.

Важно:
QtMultimedia должен быть доступен в PySide6.
Если на конкретной Ubuntu видео не воспроизведётся,
заставка всё равно откроется как обычный экран.
