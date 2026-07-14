#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCHIVE="${1:-}"
EXPECTED_ROOT="jabbix_release_assets_0.3.7"
EXPECTED_MANIFEST="$ROOT/JABBIX_ASSET_SHA256SUMS_0.3.7.txt"

usage() {
    cat <<'EOF'
Импорт финальных ассетов Jabbix 0.3.7

Использование:
  bash IMPORT_JABBIX_RELEASE_ASSETS.sh /путь/к/jabbix_release_assets_0.3.7.zip

Скрипт:
  1. распакует архив во временный каталог;
  2. проверит SHA256SUMS.txt из архива;
  3. скопирует только утверждённые PNG/WAV и сопроводительные файлы;
  4. повторно проверит контрольные суммы уже в репозитории.

config.json, credentials.json, WebEngine-профили и пользовательские данные
скрипт не читает, не удаляет и не изменяет.
EOF
}

if [[ -z "$ARCHIVE" || "$ARCHIVE" == "-h" || "$ARCHIVE" == "--help" ]]; then
    usage
    [[ -n "$ARCHIVE" ]] && exit 0
    exit 2
fi

ARCHIVE="${ARCHIVE/#\~/$HOME}"
[[ -f "$ARCHIVE" ]] || { echo "Архив не найден: $ARCHIVE" >&2; exit 1; }
command -v unzip >/dev/null 2>&1 || { echo "Не найден unzip. Установите: sudo apt-get install -y unzip" >&2; exit 1; }
command -v sha256sum >/dev/null 2>&1 || { echo "Не найден sha256sum (пакет coreutils)." >&2; exit 1; }
[[ -f "$EXPECTED_MANIFEST" ]] || { echo "Не найден $EXPECTED_MANIFEST" >&2; exit 1; }

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

printf 'Распаковка: %s\n' "$ARCHIVE"
unzip -q "$ARCHIVE" -d "$TMP_DIR"

SOURCE_ROOT="$TMP_DIR/$EXPECTED_ROOT"
if [[ ! -d "$SOURCE_ROOT" ]]; then
    SOURCE_ROOT="$(find "$TMP_DIR" -type d -name "$EXPECTED_ROOT" -print -quit)"
fi
[[ -n "${SOURCE_ROOT:-}" && -d "$SOURCE_ROOT" ]] || {
    echo "В архиве не найдена папка $EXPECTED_ROOT" >&2
    exit 1
}

[[ -f "$SOURCE_ROOT/SHA256SUMS.txt" ]] || {
    echo "В архиве отсутствует SHA256SUMS.txt" >&2
    exit 1
}

echo "Проверка исходного архива..."
(
    cd "$SOURCE_ROOT"
    sha256sum -c SHA256SUMS.txt
)

FILES=(
    "assets/themes/jabka/backgrounds/00_main_menu_wallpaper.png"
    "assets/themes/jabka/backgrounds/10_settings_menu_wallpaper.png"
    "assets/themes/jabka/sounds/frog_croak.wav"
    "app/assets/sounds/jabbix_graph_check_kvak.wav"
    "app/assets/sounds/jabbix_update_found_kvak.wav"
)

for relative_path in "${FILES[@]}"; do
    source_path="$SOURCE_ROOT/$relative_path"
    target_path="$ROOT/$relative_path"
    [[ -f "$source_path" ]] || { echo "Не найден файл: $relative_path" >&2; exit 1; }
    mkdir -p "$(dirname "$target_path")"
    cp -- "$source_path" "$target_path"
    printf 'Добавлен: %s\n' "$relative_path"
done

cp -- "$SOURCE_ROOT/README_RELEASE.md" "$ROOT/README_JABBIX_RELEASE_0.3.7.md"
cp -- "$SOURCE_ROOT/SHA256SUMS.txt" "$ROOT/JABBIX_SOURCE_SHA256SUMS_0.3.7.txt"

echo "Повторная проверка файлов в репозитории..."
(
    cd "$ROOT"
    sha256sum -c JABBIX_ASSET_SHA256SUMS_0.3.7.txt
)

if command -v file >/dev/null 2>&1; then
    echo "Форматы:"
    file -- "${FILES[@]/#/$ROOT/}"
fi

echo
echo "Импорт завершён без изменения пользовательских данных."
echo "Далее выполните:"
echo "  bash CHECK_RELEASE.sh"
echo "  git status --short"
echo "  git add JABBIX_ASSET_SHA256SUMS_0.3.7.txt JABBIX_SOURCE_SHA256SUMS_0.3.7.txt README_JABBIX_RELEASE_0.3.7.md assets/themes/jabka app/assets/sounds"
echo "  git commit -m 'Add final Jabbix release assets'"
echo "  git push origin release/0.3.7"
