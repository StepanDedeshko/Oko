#!/bin/bash
set -e

cd "$(dirname "$0")"

INSTALL_DEPS=0
REPAIR=0
for arg in "$@"; do
    case "$arg" in
        --install-deps) INSTALL_DEPS=1 ;;
        --repair) INSTALL_DEPS=1; REPAIR=1 ;;
    esac
done

echo "Запуск Око"
echo "Папка: $(pwd)"
echo ""

if grep -q "PySide6-WebEngine" requirements.txt 2>/dev/null; then
    echo "ОШИБКА: В requirements.txt найден PySide6-WebEngine. Это старая/некорректная зависимость."
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

if [ -f "./CHECK_SYSTEM_DEPS.sh" ]; then
    if ! bash ./CHECK_SYSTEM_DEPS.sh; then
        read -p "Нажмите Enter для выхода..."
        exit 2
    fi
fi

if [ "$REPAIR" = "1" ] && [ -d ".venv" ]; then
    echo "--repair: пересоздаю виртуальное окружение..."
    rm -rf .venv
fi

if [ ! -d ".venv" ]; then
    echo "Создаю виртуальное окружение..."
    python3 -m venv .venv
    INSTALL_DEPS=1
fi

source .venv/bin/activate

REQ_HASH=""
if [ -f requirements.txt ]; then
    REQ_HASH="$(sha256sum requirements.txt | awk '{print $1}')"
fi
HASH_FILE=".venv/.oko_requirements_sha256"
OLD_HASH=""
if [ -f "$HASH_FILE" ]; then
    OLD_HASH="$(cat "$HASH_FILE")"
fi
if [ "$REQ_HASH" != "$OLD_HASH" ]; then
    INSTALL_DEPS=1
fi

if [ "$INSTALL_DEPS" = "1" ]; then
    echo "Устанавливаю Python-зависимости..."
    if ! python -m pip install -r requirements.txt; then
        echo "ОШИБКА: Не удалось установить зависимости. Проверьте сеть, SSL/сертификаты Python и requirements.txt."
        exit 3
    fi
    echo "$REQ_HASH" > "$HASH_FILE"
else
    echo "Зависимости уже установлены, пропускаю pip install."
fi

if [ -f "./CREATE_DESKTOP_SHORTCUT.sh" ]; then
    bash ./CREATE_DESKTOP_SHORTCUT.sh --no-pause || true
fi

echo ""
echo "Запускаю Око..."
python main.py
