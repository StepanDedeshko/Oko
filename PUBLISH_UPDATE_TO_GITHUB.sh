#!/bin/bash
set -e

# Публикация архива обновления в GitHub Releases.
# Требуется GitHub CLI: gh auth login
# Пример:
#   ./PUBLISH_UPDATE_TO_GITHUB.sh v0.2.1 ./update.zip

if [ $# -lt 2 ]; then
  echo "Использование: $0 <tag> <archive_path> [title]"
  exit 1
fi

TAG="$1"
ARCHIVE_PATH="$2"
TITLE="${3:-$TAG}"

if [ ! -f "$ARCHIVE_PATH" ]; then
  echo "Ошибка: архив не найден: $ARCHIVE_PATH"
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "Ошибка: не найден GitHub CLI (gh)."
  echo "Установи gh и выполни: gh auth login"
  exit 1
fi

# Если релиз уже существует — просто загружаем/перезаписываем asset.
if gh release view "$TAG" >/dev/null 2>&1; then
  gh release upload "$TAG" "$ARCHIVE_PATH" --clobber
  echo "Asset обновлён в релизе $TAG"
  exit 0
fi

# Иначе создаём релиз и прикладываем архив.
gh release create "$TAG" "$ARCHIVE_PATH" \
  --title "$TITLE" \
  --notes "Обновление $TAG"

echo "Релиз $TAG создан и архив загружен."
