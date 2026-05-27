#!/bin/bash
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Создаю venv..."
    python3 -m venv .venv
fi

source .venv/bin/activate

python - <<'PY'
from app.config_migrator import patch_config_file
patch_config_file()
print("config.json исправлен: новые настройки добавлены, ссылки сохранены.")
PY

echo ""
echo "Готово. Теперь перезапусти Дежурку."
read -p "Нажмите Enter для выхода..."
