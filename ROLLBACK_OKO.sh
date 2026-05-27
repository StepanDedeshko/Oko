#!/bin/bash
set -e

clear
echo "ОТКАТ ОКО"
echo ""

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_ROOT="$APP_DIR/_backups"

if [ ! -d "$BACKUP_ROOT" ]; then
    echo "Резервные копии не найдены."
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

LAST_BACKUP="$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"

if [ -z "$LAST_BACKUP" ]; then
    echo "Резервные копии не найдены."
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

echo "Будет восстановлена резервная копия:"
echo "$LAST_BACKUP"
echo ""

read -p "Продолжить откат? [y/N]: " CONFIRM
CONFIRM="${CONFIRM:-N}"

if [[ ! "$CONFIRM" =~ ^[YyДд]$ ]]; then
    echo "Откат отменён."
    read -p "Нажмите Enter для выхода..."
    exit 0
fi

TMP_CONFIG=""
if [ -f "$APP_DIR/config.json" ]; then
    TMP_CONFIG="$(mktemp)"
    cp "$APP_DIR/config.json" "$TMP_CONFIG"
fi

rsync -a --delete \
    --exclude ".venv" \
    --exclude "_backups" \
    "$LAST_BACKUP/" "$APP_DIR/"

if [ -n "$TMP_CONFIG" ]; then
    cp "$TMP_CONFIG" "$APP_DIR/config.json"
    rm -f "$TMP_CONFIG"
fi

bash "$APP_DIR/CREATE_DESKTOP_SHORTCUT.sh" --no-pause || true

echo ""
echo "Откат выполнен."
read -p "Нажмите Enter для выхода..."
