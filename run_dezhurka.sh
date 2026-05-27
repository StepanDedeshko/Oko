#!/bin/bash
set -e

cd "$(dirname "$0")"

APP_NAME="Дежурка"
APP_DIR="$(pwd)"
ICON_SRC="$APP_DIR/assets/dezhurka_icon.png"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
ICON_TARGET="$ICON_DIR/dezhurka.png"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/dezhurka.desktop"

show_msg() {
    if command -v zenity >/dev/null 2>&1; then
        zenity --info --title="$APP_NAME" --text="$1" || true
    else
        echo "$1"
    fi
}

show_error() {
    if command -v zenity >/dev/null 2>&1; then
        zenity --error --title="$APP_NAME" --text="$1" || true
    else
        echo "ОШИБКА: $1"
    fi
}

if grep -q "PySide6-WebEngine" requirements.txt; then
    show_error "В requirements.txt найден PySide6-WebEngine. Это старая версия проекта. Удали старую папку и распакуй новый архив."
    exit 1
fi

if command -v apt >/dev/null 2>&1; then
    if ! dpkg -s python3-venv >/dev/null 2>&1; then
        show_msg "Нужно установить системные компоненты Python/Qt. Сейчас Ubuntu может попросить пароль."
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

mkdir -p "$ICON_DIR"
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$ICON_TARGET"
fi

mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Дежурка
Comment=Локальная панель дежурного для нескольких Zabbix
Exec=$APP_DIR/ЗАПУСТИТЬ_ДЕЖУРКУ.sh
Path=$APP_DIR
Icon=$ICON_TARGET
Terminal=false
Categories=Network;Utility;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"

cat > "$APP_DIR/Дежурка.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Дежурка
Comment=Локальная панель дежурного для нескольких Zabbix
Exec=$APP_DIR/ЗАПУСТИТЬ_ДЕЖУРКУ.sh
Path=$APP_DIR
Icon=$ICON_TARGET
Terminal=false
Categories=Network;Utility;
StartupNotify=true
EOF

chmod +x "$APP_DIR/Дежурка.desktop"

python main.py
