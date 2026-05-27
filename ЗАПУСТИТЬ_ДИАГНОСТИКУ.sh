#!/bin/bash
cd "$(dirname "$0")"

source .venv/bin/activate 2>/dev/null || true

echo "Запуск Дежурки в режиме диагностики..."
echo ""

python main.py

echo ""
echo "Если выше была ошибка, скопируй её и отправь в чат."
read -p "Нажмите Enter для выхода..."
