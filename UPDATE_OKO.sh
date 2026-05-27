#!/bin/bash
set -e

clear
echo "ОБНОВЛЕНИЕ ОКО"
echo ""

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_ROOT="$APP_DIR/_backups"
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/before_update_$TS"

echo "Текущая папка приложения:"
echo "$APP_DIR"
echo ""

read -p "Путь к архиву новой версии (.zip или .tar.gz): " ARCHIVE_PATH
ARCHIVE_PATH="${ARCHIVE_PATH/#\~/$HOME}"

if [ ! -f "$ARCHIVE_PATH" ]; then
    echo "Ошибка: архив не найден:"
    echo "$ARCHIVE_PATH"
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

mkdir -p "$BACKUP_DIR"

echo ""
echo "Делаю резервную копию текущей версии..."
rsync -a \
    --exclude ".venv" \
    --exclude "_backups" \
    "$APP_DIR/" "$BACKUP_DIR/"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Распаковываю новую версию..."
case "$ARCHIVE_PATH" in
    *.zip)
        unzip -q "$ARCHIVE_PATH" -d "$TMP_DIR"
        ;;
    *.tar.gz|*.tgz)
        tar -xzf "$ARCHIVE_PATH" -C "$TMP_DIR"
        ;;
    *)
        echo "Ошибка: поддерживаются только .zip, .tar.gz, .tgz"
        read -p "Нажмите Enter для выхода..."
        exit 1
        ;;
esac

NEW_ROOT="$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)"

if [ -z "$NEW_ROOT" ]; then
    echo "Ошибка: в архиве не найдена папка приложения."
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

if [ ! -f "$NEW_ROOT/main.py" ] || [ ! -d "$NEW_ROOT/app" ]; then
    echo "Ошибка: архив не похож на сборку Око."
    echo "Внутри должны быть main.py и папка app."
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

echo "Сохраняю пользовательские настройки..."
USER_CONFIG="$APP_DIR/config.json"
USER_VENV="$APP_DIR/.venv"

SAVED_CONFIG=""
if [ -f "$USER_CONFIG" ]; then
    SAVED_CONFIG="$TMP_DIR/config.json.saved"
    cp "$USER_CONFIG" "$SAVED_CONFIG"
fi

echo "Обновляю файлы приложения..."
rsync -a --delete \
    --exclude ".venv" \
    --exclude "_backups" \
    "$NEW_ROOT/" "$APP_DIR/"

if [ -n "$SAVED_CONFIG" ]; then
    echo "Возвращаю config.json пользователя..."
    cp "$SAVED_CONFIG" "$APP_DIR/config.json"
fi

cd "$APP_DIR"

if [ ! -d ".venv" ]; then
    echo "Создаю виртуальное окружение..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Обновляю зависимости..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "Проверяю Python-файлы..."
python -m py_compile main.py
find app -name "*.py" -print0 | xargs -0 -n1 python -m py_compile

bash ./CREATE_DESKTOP_SHORTCUT.sh --no-pause || true

echo ""
echo "Обновление завершено."
echo "Резервная копия предыдущей версии:"
echo "$BACKUP_DIR"
echo ""

read -p "Запустить Око сейчас? [Y/n]: " RUN_NOW
RUN_NOW="${RUN_NOW:-Y}"

if [[ "$RUN_NOW" =~ ^[YyДд]$ ]]; then
    bash ./run_oko.sh
else
    read -p "Нажмите Enter для выхода..."
fi
