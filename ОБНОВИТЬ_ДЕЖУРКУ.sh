#!/bin/bash
set -e

cd "$(dirname "$0")"

ZIP_PATH="./updates/update.zip"

if [ ! -f "$ZIP_PATH" ]; then
    if command -v zenity >/dev/null 2>&1; then
        ZIP_PATH="$(zenity --file-selection --title="Выбери ZIP обновления Дежурки" --file-filter="ZIP files | *.zip")"
    else
        echo "Положи файл обновления сюда: ./updates/update.zip"
        read -p "Или введи путь к ZIP: " ZIP_PATH
    fi
fi

if [ ! -f "$ZIP_PATH" ]; then
    echo "Файл обновления не найден."
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

BACKUP_DIR="./_backup_before_update"
mkdir -p "$BACKUP_DIR"
TS="$(date +%Y%m%d_%H%M%S)"

if [ -f "config.json" ]; then
    cp "config.json" "$BACKUP_DIR/config_$TS.json"
fi

if [ -d "assets/loading" ]; then
    mkdir -p "$BACKUP_DIR/loading_media_$TS"
    cp -a assets/loading/. "$BACKUP_DIR/loading_media_$TS/" 2>/dev/null || true
fi

TMP_DIR="$(mktemp -d)"
unzip -q "$ZIP_PATH" -d "$TMP_DIR"

if [ -f "$TMP_DIR/main.py" ] && [ -d "$TMP_DIR/app" ]; then
    NEW_ROOT="$TMP_DIR"
else
    NEW_ROOT="$(find "$TMP_DIR" -maxdepth 2 -type f -name main.py -printf '%h\n' | head -n 1)"
fi

if [ -z "$NEW_ROOT" ]; then
    echo "В ZIP не найден проект: нет main.py"
    rm -rf "$TMP_DIR"
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

for item in "$NEW_ROOT"/*; do
    name="$(basename "$item")"

    if [ "$name" = "config.json" ] || [ "$name" = ".venv" ] || [ "$name" = "_backup_before_update" ]; then
        continue
    fi

    rm -rf "./$name"
    cp -a "$item" "./$name"
done

if [ -f "$BACKUP_DIR/config_$TS.json" ]; then
    cp "$BACKUP_DIR/config_$TS.json" "config.json"
fi

if [ -d "$BACKUP_DIR/loading_media_$TS" ]; then
    mkdir -p "assets/loading"
    cp -a "$BACKUP_DIR/loading_media_$TS/." "assets/loading/" 2>/dev/null || true
fi

if [ -f "app/config_migrator.py" ]; then
    source .venv/bin/activate 2>/dev/null || true
    python - <<'PY'
from app.config_migrator import patch_config_file
patch_config_file()
print("config.json дополнен новыми настройками.")
PY
fi

chmod +x ./*.sh 2>/dev/null || true

if [ -f "./СОЗДАТЬ_ЯРЛЫК.sh" ]; then
    bash "./СОЗДАТЬ_ЯРЛЫК.sh" --no-pause || true
fi

rm -rf "$TMP_DIR"

echo ""
echo "Готово. Дежурка обновлена."
echo "config.json сохранён."
echo "Перезапусти приложение."
echo ""
read -p "Нажмите Enter для выхода..."
