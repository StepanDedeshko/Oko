#!/bin/bash
set -e

cd "$(dirname "$0")"

if grep -q "PySide6-WebEngine" requirements.txt; then
    echo "ОШИБКА: В requirements.txt найден PySide6-WebEngine. Это старая версия проекта."
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

if command -v apt >/dev/null 2>&1; then
    if ! dpkg -s python3-venv >/dev/null 2>&1; then
        echo "Нужно установить системные компоненты Python/Qt. Ubuntu может попросить пароль."
        sudo apt update
        sudo apt install -y python3 python3-venv python3-pip \
            libxcb-cursor0 libnss3 libxcomposite1 libxdamage1 libxrandr2 libgbm1
    else
        sudo apt install -y \
            libxcb-cursor0 libnss3 libxcomposite1 libxdamage1 libxrandr2 libgbm1 >/dev/null 2>&1 || true
    fi
fi

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# На каждом запуске тихо обновляем ярлык, чтобы он не ломался после переноса папки.
if [ -f "./СОЗДАТЬ_ЯРЛЫК.sh" ]; then
    bash ./СОЗДАТЬ_ЯРЛЫК.sh --no-pause || true
fi

python main.py
