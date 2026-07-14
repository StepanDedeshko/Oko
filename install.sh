#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="Око"
DEFAULT_INSTALL_DIR="$HOME/Applications/Oko"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$DEFAULT_INSTALL_DIR"
ASSUME_YES=0
LAUNCH_AFTER=1
FORCE_UNSUPPORTED=0

usage() {
    cat <<'EOF'
Установка Око:
  bash install.sh [параметры]

Параметры:
  --install-dir PATH   каталог установки (по умолчанию ~/Applications/Oko)
  --yes                автоматически согласиться на установку apt-зависимостей
  --no-launch          не запускать Око после установки
  --force-unsupported  продолжить на неподдерживаемой системе
  -h, --help           показать справку
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --install-dir)
            INSTALL_DIR="${2:?После --install-dir нужен путь}"
            shift 2
            ;;
        --yes)
            ASSUME_YES=1
            shift
            ;;
        --no-launch)
            LAUNCH_AFTER=0
            shift
            ;;
        --force-unsupported)
            FORCE_UNSUPPORTED=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Неизвестный параметр: $1" >&2
            usage
            exit 2
            ;;
    esac
done

INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"
mkdir -p "$INSTALL_DIR"
INSTALL_DIR="$(cd "$INSTALL_DIR" && pwd)"

ok() { printf 'Проверка %-32s — ОК\n' "$1"; }
warn() { printf 'Проверка %-32s — ПРЕДУПРЕЖДЕНИЕ: %s\n' "$1" "$2"; }
fail() { printf 'Проверка %-32s — ОШИБКА: %s\n' "$1" "$2" >&2; exit 1; }

printf '%s\n' "УСТАНОВКА $APP_NAME"
printf 'Источник: %s\nКаталог: %s\n\n' "$SOURCE_DIR" "$INSTALL_DIR"

if [[ ! -f "$SOURCE_DIR/main.py" || ! -d "$SOURCE_DIR/app" || ! -f "$SOURCE_DIR/requirements.txt" ]]; then
    fail "комплекта установщика" "рядом с install.sh должны находиться main.py, app/ и requirements.txt"
fi
ok "комплекта установщика"

if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    if [[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" =~ ^(22\.04|24\.04)$ ]]; then
        ok "Ubuntu ${VERSION_ID} LTS"
    elif [[ "$FORCE_UNSUPPORTED" == "1" ]]; then
        warn "операционной системы" "${PRETTY_NAME:-неподдерживаемая версия}; продолжение разрешено параметром"
    elif [[ "${ID:-}" == "ubuntu" ]]; then
        fail "операционной системы" "проверены Ubuntu 22.04 и 24.04 LTS; для ручной попытки используйте --force-unsupported"
    else
        fail "операционной системы" "поддерживается Ubuntu 22.04/24.04 LTS; для ручной попытки используйте --force-unsupported"
    fi
else
    [[ "$FORCE_UNSUPPORTED" == "1" ]] || fail "операционной системы" "не найден /etc/os-release"
fi

if [[ ! -w "$INSTALL_DIR" ]]; then
    fail "прав на каталог" "нет прав записи в $INSTALL_DIR"
fi
probe="$INSTALL_DIR/.oko_write_test_$$"
: > "$probe" || fail "записи настроек" "не удалось создать файл в $INSTALL_DIR"
rm -f "$probe"
ok "прав и записи настроек"

APT_PACKAGES=(
    python3 python3-venv python3-pip
    rsync unzip git curl ca-certificates
    libxcb-cursor0 libxkbcommon-x11-0 libxcb-xinerama0
    libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0
    libxcb-render-util0 libxcb-shape0 libxcb-xfixes0
    libnss3 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libegl1 libgl1
)

if command -v dpkg-query >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
    if command -v apt-cache >/dev/null 2>&1 && apt-cache show libasound2t64 >/dev/null 2>&1; then
        APT_PACKAGES+=(libasound2t64)
    else
        APT_PACKAGES+=(libasound2)
    fi

    MISSING_PACKAGES=()
    for package in "${APT_PACKAGES[@]}"; do
        if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
            MISSING_PACKAGES+=("$package")
        fi
    done

    if (( ${#MISSING_PACKAGES[@]} > 0 )); then
        printf 'Не хватает системных пакетов:\n  %s\n' "${MISSING_PACKAGES[*]}"
        printf 'Команда исправления:\n  sudo apt-get update && sudo apt-get install -y %s\n\n' "${MISSING_PACKAGES[*]}"

        install_packages=0
        if [[ "$ASSUME_YES" == "1" ]]; then
            install_packages=1
        elif [[ -t 0 ]]; then
            read -r -p "Установить недостающие пакеты сейчас? [Y/n]: " answer
            answer="${answer:-Y}"
            [[ "$answer" =~ ^[YyДд]$ ]] && install_packages=1
        fi

        if [[ "$install_packages" == "1" ]]; then
            command -v sudo >/dev/null 2>&1 || fail "sudo" "sudo не найден; выполните показанную команду от администратора"
            sudo apt-get update
            sudo apt-get install -y "${MISSING_PACKAGES[@]}"
        else
            fail "системных библиотек" "установите недостающие пакеты и повторите запуск"
        fi
    fi
    ok "системных библиотек"
else
    warn "apt/dpkg" "автоматическая установка пакетов недоступна"
fi

if command -v python3 >/dev/null 2>&1; then
    ok "Python ($(python3 --version 2>&1))"
else
    fail "Python" "не найден python3; установите пакет python3"
fi

if [[ -x /usr/bin/curl ]]; then
    ok "нативного curl (/usr/bin/curl)"
elif command -v curl >/dev/null 2>&1 && [[ "$(command -v curl)" == /snap/* ]]; then
    fail "curl" "обнаружена только Snap-версия; установите нативную: sudo apt-get install -y curl"
else
    warn "curl" "curl не найден; для установки из локального архива он не требуется"
fi

MODE="new"
if [[ -f "$INSTALL_DIR/main.py" && -d "$INSTALL_DIR/app" ]]; then
    MODE="update"
    printf 'Обнаружена существующая установка: пользовательские данные будут сохранены.\n'
else
    printf 'Обнаружена новая установка: будет использован базовый config.json из сборки.\n'
fi

COMMON_RSYNC_EXCLUDES=(
    --exclude='.git/'
    --exclude='.venv/'
    --exclude='_backups/'
    --exclude='__pycache__/'
    --exclude='*.pyc'
)

RUNTIME_DATA_EXCLUDES=(
    --exclude='credentials.json'
    --exclude='web_profiles/'
    --exclude='data/'
    --exclude='user_data/'
    --exclude='logs/'
    --exclude='*.log'
)

RSYNC_EXCLUDES=("${COMMON_RSYNC_EXCLUDES[@]}" "${RUNTIME_DATA_EXCLUDES[@]}")
if [[ "$MODE" == "update" ]]; then
    # config.json уже принадлежит пользователю. В режиме обновления его нельзя
    # удалять или заменять базовым файлом из новой сборки.
    RSYNC_EXCLUDES+=(--exclude='config.json')
fi

if [[ "$SOURCE_DIR" != "$INSTALL_DIR" ]]; then
    if [[ "$MODE" == "update" ]]; then
        backup_dir="$INSTALL_DIR/_backups/before_install_$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$backup_dir"
        rsync -a --no-owner --no-group --no-perms \
            --exclude='.venv/' --exclude='_backups/' \
            "$INSTALL_DIR/" "$backup_dir/"
        printf 'Резервная копия: %s\n' "$backup_dir"
    fi

    rsync -a --delete --no-owner --no-group --no-perms \
        "${RSYNC_EXCLUDES[@]}" \
        "$SOURCE_DIR/" "$INSTALL_DIR/"
fi
ok "копирования файлов ($MODE)"

cd "$INSTALL_DIR"

if [[ ! -d .venv ]]; then
    python3 -m venv .venv || fail "виртуального окружения" "установите python3-venv"
fi
[[ -x .venv/bin/python ]] || fail "виртуального окружения" "нет .venv/bin/python"
ok "виртуального окружения"

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
ok "Python-зависимостей"

if pyside_output="$(.venv/bin/python - <<'PY' 2>&1
from PySide6 import __version__
print(f"PySide6 {__version__}")
PY
)"; then
    printf '%s\n' "$pyside_output"
    ok "PySide6"
else
    printf '%s\n' "$pyside_output" >&2
    printf 'Команда исправления: %s/.venv/bin/python -m pip install -r %s/requirements.txt\n' "$INSTALL_DIR" "$INSTALL_DIR" >&2
    fail "PySide6" "импорт завершился ошибкой"
fi

if qtwebengine_output="$(.venv/bin/python - <<'PY' 2>&1
from PySide6.QtWebEngineWidgets import QWebEngineView
print(QWebEngineView.__name__)
PY
)"; then
    printf '%s\n' "$qtwebengine_output"
    ok "QtWebEngine"
else
    printf '%s\n' "$qtwebengine_output" >&2
    missing_library="$(printf '%s\n' "$qtwebengine_output" | grep -oE 'lib[^ :]+\.so[^ :]*' | head -n1 || true)"
    if [[ -n "$missing_library" ]]; then
        printf 'Не хватает библиотеки: %s\n' "$missing_library" >&2
    fi
    printf 'Команда исправления системных зависимостей:\n  sudo apt-get update && sudo apt-get install -y %s\n' "${APT_PACKAGES[*]}" >&2
    fail "QtWebEngine" "импорт завершился ошибкой"
fi

.venv/bin/python -m py_compile main.py
find app -name '*.py' -print0 | xargs -0 -r -n1 .venv/bin/python -m py_compile
ok "Python-файлов и main.py"

if [[ -f CREATE_DESKTOP_SHORTCUT.sh ]]; then
    bash ./CREATE_DESKTOP_SHORTCUT.sh --no-pause || warn "ярлыка" "ярлык не создан; приложение можно запустить через run_oko.sh"
else
    warn "ярлыка" "не найден CREATE_DESKTOP_SHORTCUT.sh"
fi

printf '\nУстановка завершена. Режим: %s\nЗапуск: %s/run_oko.sh\n' "$MODE" "$INSTALL_DIR"

if [[ "$LAUNCH_AFTER" == "1" ]]; then
    bash ./run_oko.sh
fi
