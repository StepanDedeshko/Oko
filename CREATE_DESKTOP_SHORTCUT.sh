#!/bin/bash
set -e

cd "$(dirname "$0")"
APP_DIR="$(pwd)"
DESKTOP_FILE="$HOME/.local/share/applications/oko.desktop"
DESKTOP_COPY="$HOME/Desktop/Око.desktop"

mkdir -p "$HOME/.local/share/applications"

ICON_PATH="$APP_DIR/assets/theme_logos/mass_effect.png"
if [ ! -f "$ICON_PATH" ]; then
    ICON_PATH="$APP_DIR/assets/icon.png"
fi

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Око
Comment=Панель дежурного мониторинга Zabbix/ОТРС
Exec=bash "$APP_DIR/run_oko.sh"
Icon=$ICON_PATH
Terminal=false
Categories=Utility;Network;Monitor;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"

if [ -d "$HOME/Desktop" ]; then
    cp "$DESKTOP_FILE" "$DESKTOP_COPY" 2>/dev/null || true
    chmod +x "$DESKTOP_COPY" 2>/dev/null || true
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi

if [ "$1" != "--no-pause" ]; then
    echo "Ярлык создан:"
    echo "$DESKTOP_FILE"
    echo ""
    echo "Если ярлык на рабочем столе не запускается, нажми по нему правой кнопкой и выбери 'Разрешить запуск'."
    read -p "Нажмите Enter для выхода..."
fi
