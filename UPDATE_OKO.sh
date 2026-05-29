#!/bin/bash
set -euo pipefail

if command -v clear >/dev/null 2>&1 && [ -n "${TERM:-}" ]; then
    clear || true
fi
echo "ОБНОВЛЕНИЕ ОКО"
echo ""

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_ROOT="$APP_DIR/_backups"
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/before_update_$TS"

echo "Текущая папка приложения:"
echo "$APP_DIR"
echo ""

ARCHIVE_PATH=""
NO_RUN_PROMPT=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --archive)
            ARCHIVE_PATH="$2"
            shift 2
            ;;
        --no-run-prompt)
            NO_RUN_PROMPT=1
            shift
            ;;
        *)
            echo "Неизвестный аргумент: $1"
            exit 1
            ;;
    esac
done

if [ -z "$ARCHIVE_PATH" ]; then
    read -p "Путь к архиву новой версии (.zip или .tar.gz): " ARCHIVE_PATH
fi
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

if [ -f "$TMP_DIR/main.py" ] && [ -d "$TMP_DIR/app" ]; then
    NEW_ROOT="$TMP_DIR"
else
    NEW_ROOT="$(find "$TMP_DIR" -mindepth 1 -type f -name "main.py" -printf "%h\n" | while read -r d; do
        if [ -d "$d/app" ]; then
            echo "$d"
            break
        fi
    done)"
fi

if [ -z "${NEW_ROOT:-}" ]; then
    echo "Ошибка: в архиве не найдена папка проекта с main.py и app/."
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
SAVED_CONFIG=""
if [ -f "$USER_CONFIG" ]; then
    SAVED_CONFIG="$TMP_DIR/config.json.saved"
    cp "$USER_CONFIG" "$SAVED_CONFIG"
fi

LEGACY_DIRS=("DEZHURKA" "DEZHURKA_LOGIN_FIX")
for legacy_dir in "${LEGACY_DIRS[@]}"; do
    legacy_path="$APP_DIR/$legacy_dir"
    if [ -d "$legacy_path" ]; then
        echo "Удаляю устаревшую папку: $legacy_dir"
        rm -rf "$legacy_path"
    fi
done

echo "Обновляю файлы приложения..."
rsync -a --delete \
    --exclude ".git" \
    --exclude ".venv" \
    --exclude "_backups" \
    --exclude "__pycache__" \
    --exclude "config.json" \
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

echo "Диагностика после обновления..."
grep -n "APP_VERSION" app/app_info.py
test -f app/update_widget.py
grep -n "from app.update_widget import UpdateWidget" app/home_config.py
grep -n "def check_for_updates" app/home_config.py

if [ ! -f app/update_widget.py ]; then
    echo "Ошибка: app/update_widget.py отсутствует после обновления."
    exit 1
fi

if ! grep -q "from app.update_widget import UpdateWidget" app/home_config.py; then
    echo "Ошибка: app/home_config.py не импортирует UpdateWidget из app.update_widget."
    exit 1
fi

echo "Проверяю Python-файлы..."
python3 -m py_compile main.py
find app -name "*.py" -print0 | xargs -0 -n1 python3 -m py_compile

bash ./CREATE_DESKTOP_SHORTCUT.sh --no-pause || true

echo ""
echo "Обновление завершено."
echo "Резервная копия предыдущей версии:"
echo "$BACKUP_DIR"
echo ""

if [ "$NO_RUN_PROMPT" = "1" ]; then
    exit 0
fi

read -p "Запустить Око сейчас? [Y/n]: " RUN_NOW
RUN_NOW="${RUN_NOW:-Y}"

if [[ "$RUN_NOW" =~ ^[YyДд]$ ]]; then
    bash ./run_oko.sh
else
    read -p "Нажмите Enter для выхода..."
fi
