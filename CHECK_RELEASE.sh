#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

EXPECTED_VERSION="0.3.7"
ASSET_MANIFEST="JABBIX_ASSET_SHA256SUMS_0.3.7.txt"
REQUIRED_ASSETS=(
    "assets/themes/jabka/backgrounds/00_main_menu_wallpaper.png"
    "assets/themes/jabka/backgrounds/10_settings_menu_wallpaper.png"
    "assets/themes/jabka/sounds/frog_croak.wav"
    "app/assets/sounds/jabbix_graph_check_kvak.wav"
    "app/assets/sounds/jabbix_update_found_kvak.wav"
)

missing=0
for asset in "${REQUIRED_ASSETS[@]}"; do
    if [[ -f "$asset" ]]; then
        echo "Ассет Жабки — ОК: $asset"
    else
        echo "Ассет Жабки — ОШИБКА: отсутствует $asset" >&2
        missing=1
    fi
done
[[ "$missing" == "0" ]] || exit 2

if [[ ! -f "$ASSET_MANIFEST" ]]; then
    echo "Манифест ассетов — ОШИБКА: отсутствует $ASSET_MANIFEST" >&2
    exit 2
fi

echo "SHA256 финальных ассетов..."
sha256sum -c "$ASSET_MANIFEST"

if [[ ! -x .venv/bin/python ]]; then
    echo "Виртуальное окружение — ОШИБКА: сначала выполните bash install.sh --no-launch" >&2
    exit 2
fi

echo "Версия приложения..."
.venv/bin/python - <<PY
from app.app_info import APP_VERSION
expected = "$EXPECTED_VERSION"
assert APP_VERSION == expected, f"Ожидалась версия {expected}, получена {APP_VERSION}"
print(f"APP_VERSION {APP_VERSION} — ОК")
PY

echo "PySide6 и QtWebEngine..."
.venv/bin/python - <<'PY'
import PySide6
from PySide6.QtWebEngineWidgets import QWebEngineView
print(f"PySide6 {PySide6.__version__} — ОК")
print(f"QtWebEngine {QWebEngineView.__name__} — ОК")
PY

echo "Python compile..."
.venv/bin/python -m py_compile main.py
find app -name '*.py' -print0 | xargs -0 -r -n1 .venv/bin/python -m py_compile

echo "Полный pytest..."
PYTHONPATH=. .venv/bin/python -m pytest -q

if command -v git >/dev/null 2>&1 && [[ -d .git ]]; then
    echo "git diff --check..."
    git diff --check
    if git rev-parse --verify origin/main >/dev/null 2>&1; then
        git diff --check origin/main...HEAD
    fi
fi

echo ""
echo "Автоматические проверки релиза завершены."
echo "Остаётся ручной запуск: python3 main.py"
echo "И ручная проверка Live Zabbix / Redmine / OTRS / сервисов / тем / звуков Жабки."
