#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Запуск графического установщика Око..."
echo ""

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python3 не найден."
    echo "Попросите администратора установить:"
    echo "sudo apt install python3"
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

if ! python3 - <<'PY' >/dev/null 2>&1
import tkinter
PY
then
    echo "Графический установщик не может открыться: отсутствует python3-tk."
    echo ""
    echo "Установщик НЕ будет спрашивать пароль и НЕ будет запускать sudo."
    echo ""
    echo "Чтобы включить графический установщик, администратор должен выполнить:"
    echo "sudo apt update"
    echo "sudo apt install -y python3-tk"
    echo ""
    echo "Сейчас будет запущен обычный установщик в терминале без sudo."
    echo ""
    read -p "Нажмите Enter для продолжения..."
    bash ./INSTALL_OKO.sh
    exit 0
fi

python3 ./installer_gui.py
