#!/bin/bash
set -e

PR_NUMBER="$1"
if [ -z "$PR_NUMBER" ]; then
  echo "Использование: $0 <PR_NUMBER>"
  echo "Пример: $0 3"
  exit 1
fi

BRANCH="codex-pr-$PR_NUMBER"

git checkout main
git pull origin main
git fetch origin "pull/$PR_NUMBER/head:$BRANCH"
git checkout "$BRANCH"

set +e
git merge main
MERGE_EXIT=$?
set -e

if [ $MERGE_EXIT -ne 0 ]; then
  echo ""
  echo "Обнаружены конфликты merge."
  echo "Разрешите конфликты вручную, затем выполните:"
  echo "  git add <files>"
  echo "  git commit"
  exit 1
fi

python3 -m py_compile main.py
find app -name "*.py" -print0 | xargs -0 -n1 python3 -m py_compile

if ! git diff --quiet main -- config.json; then
  echo "Ошибка: config.json отличается от main. Исправьте перед merge."
  exit 1
fi

echo ""
echo "Проверка завершена успешно. Дальше:"
echo "  git push origin $BRANCH"
echo "  Откройте/обновите PR и выполните merge в main"
