#!/usr/bin/env bash
set -Eeuo pipefail

if command -v clear >/dev/null 2>&1 && [[ -n "${TERM:-}" ]]; then
    clear || true
fi

echo "ОБНОВЛЕНИЕ ОКО"
echo ""

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_ROOT="$APP_DIR/_backups"
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/before_update_$TS"
ARCHIVE_PATH=""
NO_RUN_PROMPT=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --archive)
            ARCHIVE_PATH="${2:?После --archive нужен путь к архиву}"
            shift 2
            ;;
        --no-run-prompt)
            NO_RUN_PROMPT=1
            shift
            ;;
        *)
            echo "Неизвестный аргумент: $1" >&2
            exit 1
            ;;
    esac
done

pause_if_interactive() {
    if [[ "$NO_RUN_PROMPT" != "1" && -t 0 ]]; then
        read -r -p "Нажмите Enter для выхода..." _
    fi
}

fail() {
    echo "Ошибка: $*" >&2
    pause_if_interactive
    exit 1
}

if [[ -z "$ARCHIVE_PATH" ]]; then
    [[ -t 0 ]] || fail "не указан архив обновления (--archive PATH)"
    read -r -p "Путь к архиву новой версии (.zip или .tar.gz): " ARCHIVE_PATH
fi
ARCHIVE_PATH="${ARCHIVE_PATH/#\~/$HOME}"
[[ -f "$ARCHIVE_PATH" ]] || fail "архив не найден: $ARCHIVE_PATH"

echo "Текущая папка приложения: $APP_DIR"
mkdir -p "$BACKUP_DIR"

echo "Делаю резервную копию текущей версии..."
rsync -a --no-owner --no-group --no-perms \
    --exclude='.venv/' \
    --exclude='_backups/' \
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
        fail "поддерживаются только .zip, .tar.gz и .tgz"
        ;;
esac

if [[ -f "$TMP_DIR/main.py" && -d "$TMP_DIR/app" ]]; then
    NEW_ROOT="$TMP_DIR"
else
    NEW_ROOT="$(find "$TMP_DIR" -mindepth 1 -type f -name main.py -printf '%h\n' | while read -r directory; do
        if [[ -d "$directory/app" ]]; then
            echo "$directory"
            break
        fi
    done)"
fi

[[ -n "${NEW_ROOT:-}" ]] || fail "в архиве не найдена папка проекта с main.py и app/"
[[ -f "$NEW_ROOT/main.py" && -d "$NEW_ROOT/app" && -f "$NEW_ROOT/requirements.txt" ]] \
    || fail "архив не похож на полную сборку Око"

# Эти пути принадлежат пользователю и никогда не должны удаляться или
# перезаписываться обновлением. Исключения действуют и для rsync --delete.
PROTECTED_EXCLUDES=(
    --exclude='.git/'
    --exclude='.venv/'
    --exclude='_backups/'
    --exclude='__pycache__/'
    --exclude='*.pyc'
    --exclude='config.json'
    --exclude='credentials.json'
    --exclude='web_profiles/'
    --exclude='data/'
    --exclude='user_data/'
    --exclude='logs/'
    --exclude='*.log'
)

echo "Обновляю файлы приложения без изменения пользовательских данных..."
rsync -a --delete --no-owner --no-group --no-perms \
    "${PROTECTED_EXCLUDES[@]}" \
    "$NEW_ROOT/" "$APP_DIR/"

cd "$APP_DIR"

command -v python3 >/dev/null 2>&1 || fail "не найден python3"
if [[ ! -d .venv ]]; then
    echo "Создаю виртуальное окружение..."
    python3 -m venv .venv || fail "не удалось создать .venv; установите python3-venv"
fi
[[ -x .venv/bin/python ]] || fail "повреждено виртуальное окружение .venv"

echo "Обновляю Python-зависимости..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "Проверка PySide6..."
.venv/bin/python -c 'import PySide6; print("PySide6 — ОК")'

echo "Проверка QtWebEngine..."
.venv/bin/python -c 'from PySide6.QtWebEngineWidgets import QWebEngineView; print("QtWebEngine — ОК")'

echo "Проверяю Python-файлы..."
.venv/bin/python -m py_compile main.py
find app -name '*.py' -print0 | xargs -0 -r -n1 .venv/bin/python -m py_compile

grep -n 'APP_VERSION' app/app_info.py || true

if [[ -f CREATE_DESKTOP_SHORTCUT.sh ]]; then
    bash ./CREATE_DESKTOP_SHORTCUT.sh --no-pause || true
fi

echo ""
echo "Обновление завершено."
echo "Пользовательские config.json, credentials.json, web_profiles и data сохранены."
echo "Резервная копия предыдущей версии:"
echo "$BACKUP_DIR"
echo ""

if [[ "$NO_RUN_PROMPT" == "1" ]]; then
    exit 0
fi

read -r -p "Запустить Око сейчас? [Y/n]: " RUN_NOW
RUN_NOW="${RUN_NOW:-Y}"
if [[ "$RUN_NOW" =~ ^[YyДд]$ ]]; then
    bash ./run_oko.sh
fi
