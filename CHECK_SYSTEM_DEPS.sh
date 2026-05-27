#!/bin/bash

# Проверка системных компонентов для запуска Око.
# Скрипт ничего не устанавливает и не вызывает sudo.

MISSING=""

check_dpkg() {
    local pkg="$1"

    if command -v dpkg >/dev/null 2>&1; then
        if ! dpkg -s "$pkg" >/dev/null 2>&1; then
            MISSING="$MISSING $pkg"
        fi
    fi
}

if command -v dpkg >/dev/null 2>&1; then
    check_dpkg "python3-venv"
    check_dpkg "python3-pip"
    check_dpkg "libxcb-cursor0"
    check_dpkg "libnss3"
    check_dpkg "libxcomposite1"
    check_dpkg "libxdamage1"
    check_dpkg "libxrandr2"
    check_dpkg "libgbm1"

    # На новых Ubuntu пакет libasound2 заменён на libasound2t64.
    if ! dpkg -s "libasound2" >/dev/null 2>&1 && ! dpkg -s "libasound2t64" >/dev/null 2>&1; then
        MISSING="$MISSING libasound2t64"
    fi
fi

if [ -n "$MISSING" ]; then
    echo ""
    echo "Око не может запуститься: в системе отсутствуют компоненты:"
    echo "$MISSING"
    echo ""
    echo "Установщик не запускает sudo автоматически."
    echo "Попросите администратора выполнить:"
    echo ""
    echo "sudo apt update"
    echo "sudo apt install -y$MISSING"
    echo ""
    echo "После этого снова запустите Око."
    echo ""
    exit 2
fi

exit 0
