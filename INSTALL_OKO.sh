#!/bin/bash
set -e

clear
echo "УСТАНОВКА ОКО"
echo "Версия: 0.2 [pre-release]"
echo ""

DEFAULT_DIR="$HOME/Applications/Oko"

read -p "Куда установить Око? [$DEFAULT_DIR]: " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_DIR}"

CURRENT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$(realpath -m "$INSTALL_DIR")"

echo ""
echo "Папка установки:"
echo "$INSTALL_DIR"
echo ""

if [ "$CURRENT_DIR" = "$INSTALL_DIR" ]; then
    echo "Приложение уже находится в выбранной папке."
else
    mkdir -p "$INSTALL_DIR"

    echo "Копирую файлы..."
    if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete \
            --exclude ".venv" \
            --exclude "__pycache__" \
            --exclude "*.pyc" \
            "$CURRENT_DIR/" "$INSTALL_DIR/"
    else
        cp -a "$CURRENT_DIR/." "$INSTALL_DIR/"
    fi
fi

cd "$INSTALL_DIR"

if command -v apt >/dev/null 2>&1; then
    MISSING=""

    for pkg in python3-venv python3-pip libxcb-cursor0 libnss3 libxcomposite1 libxdamage1 libxrandr2 libgbm1; do
        if ! dpkg -s "$pkg" >/dev/null 2>&1; then
            MISSING="$MISSING $pkg"
        fi
    done

    if [ -n "$MISSING" ]; then
        echo ""
        echo "В системе могут отсутствовать компоненты, нужные для запуска."
        echo "Установщик НЕ будет спрашивать пароль и НЕ будет запускать sudo."
        echo ""
        echo "Если запуск не пойдёт, администратор должен выполнить:"
        echo "sudo apt update"
        echo "sudo apt install -y$MISSING"
        echo ""
    fi
fi

if [ ! -d ".venv" ]; then
    echo "Создаю виртуальное окружение..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Устанавливаю Python-зависимости..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "Создаю ярлык..."
bash ./CREATE_DESKTOP_SHORTCUT.sh --no-pause || true

echo ""
bash ./CHECK_SYSTEM_DEPS.sh || true

echo "Установка завершена."
echo ""
echo "Запуск:"
echo "$INSTALL_DIR/run_oko.sh"
echo ""

read -p "Запустить Око сейчас? [Y/n]: " RUN_NOW
RUN_NOW="${RUN_NOW:-Y}"

if [[ "$RUN_NOW" =~ ^[YyДд]$ ]]; then
    bash ./run_oko.sh
else
    read -p "Нажмите Enter для выхода..."
fi
