#!/bin/bash
set -e

cd "$(dirname "$0")"

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

if [ ! -d ".venv" ]; then
    echo "Создаю виртуальное окружение..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Проверяю Python-зависимости..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [ -f "./CREATE_DESKTOP_SHORTCUT.sh" ]; then
    bash ./CREATE_DESKTOP_SHORTCUT.sh --no-pause || true
fi

echo ""
echo "Запускаю Око..."
python main.py
