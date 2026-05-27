#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"

APP_MENU_FILE="$HOME/.local/share/applications/dezhurka.desktop"
LAUNCHER_FILE="$HOME/.local/bin/dezhurka-launcher.sh"
ICON_FILE="$HOME/.local/share/icons/hicolor/256x256/apps/dezhurka.png"

DESKTOP_DIR="$HOME/Рабочий стол"
if [ ! -d "$DESKTOP_DIR" ]; then
    DESKTOP_DIR="$HOME/Desktop"
fi
DESKTOP_FILE="$DESKTOP_DIR/Дежурка.desktop"

PROFILE_DIR="$HOME/.zabbix_duty_panel"
CREDENTIALS_DIR="$HOME/.config/zabbix_duty_panel"

echo "Удаление Дежурки"
echo ""

echo "Будет удалено:"
echo "- ярлык меню: $APP_MENU_FILE"
echo "- ярлык рабочего стола: $DESKTOP_FILE"
echo "- launcher: $LAUNCHER_FILE"
echo "- иконка: $ICON_FILE"
echo "- профили браузера/кэш: $PROFILE_DIR"
echo ""
echo "Папка приложения:"
echo "$APP_DIR"
echo ""

read -p "Удалить Дежурку? [y/N]: " CONFIRM

case "$CONFIRM" in
    y|Y|yes|YES|да|ДА)
        ;;
    *)
        echo "Удаление отменено."
        read -p "Нажмите Enter для выхода..."
        exit 0
        ;;
esac

rm -f "$APP_MENU_FILE"
rm -f "$DESKTOP_FILE"
rm -f "$LAUNCHER_FILE"
rm -f "$ICON_FILE"

if [ -d "$PROFILE_DIR" ]; then
    rm -rf "$PROFILE_DIR"
fi

echo ""
read -p "Удалить сохраненные логины/пароли? [y/N]: " REMOVE_CREDS

case "$REMOVE_CREDS" in
    y|Y|yes|YES|да|ДА)
        rm -rf "$CREDENTIALS_DIR"
        echo "Сохраненные логины/пароли удалены."
        ;;
    *)
        echo "Сохраненные логины/пароли оставлены."
        ;;
esac

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo ""
read -p "Удалить саму папку приложения? [y/N]: " REMOVE_APP_DIR

case "$REMOVE_APP_DIR" in
    y|Y|yes|YES|да|ДА)
        echo ""
        echo "Папка будет удалена после закрытия этого окна."
        (
            sleep 1
            rm -rf "$APP_DIR"
        ) >/dev/null 2>&1 &
        ;;
    *)
        echo "Папка приложения оставлена."
        ;;
esac

echo ""
echo "Дежурка удалена."
read -p "Нажмите Enter для выхода..."
