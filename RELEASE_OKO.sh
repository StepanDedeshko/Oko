#!/bin/bash
set -e

TAG="$1"
if [ -z "$TAG" ]; then
  echo "Использование: $0 <tag>"
  echo "Пример: $0 v0.2.4"
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Ошибка: рабочее дерево не чистое. Закоммитьте или уберите изменения."
  exit 1
fi

python3 -m py_compile main.py
find app -name "*.py" -print0 | xargs -0 -n1 python3 -m py_compile

OUT_ZIP="$HOME/Загрузки/update.zip"
mkdir -p "$(dirname "$OUT_ZIP")"
rm -f "$OUT_ZIP"

zip -r "$OUT_ZIP" . \
  -x "*.git*" \
  -x ".venv/*" \
  -x "*/__pycache__/*" \
  -x "*.pyc" \
  -x "_backups/*" \
  -x "update.zip"

bash ./PUBLISH_UPDATE_TO_GITHUB.sh "$TAG" "$OUT_ZIP"

echo ""
echo "Готово. URL обновления:"
echo "https://github.com/StepanDedeshko/Oko/releases/download/$TAG/update.zip"
