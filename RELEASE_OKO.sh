#!/bin/bash
set -e

TAG="$1"
if [ -z "$TAG" ]; then
  echo "Использование: $0 <tag>"
  echo "Пример: $0 v0.2.4"
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Рабочее дерево не чистое. Сначала закоммитьте или уберите изменения."
  exit 1
fi

VERSION="${TAG#v}"
CURRENT_VERSION="$(python3 - <<'PY'
from pathlib import Path
import re
text = Path('app/app_info.py').read_text(encoding='utf-8')
m = re.search(r'APP_VERSION\s*=\s*\"([^\"]+)\"', text)
print(m.group(1) if m else "")
PY
)"

if [ "$CURRENT_VERSION" != "$VERSION" ]; then
  python3 - <<PY
from pathlib import Path
import re
p = Path('app/app_info.py')
t = p.read_text(encoding='utf-8')
t = re.sub(r'APP_VERSION\s*=\s*\"[^\"]+\"', 'APP_VERSION = \"$VERSION\"', t, count=1)
p.write_text(t, encoding='utf-8')
PY
  git add app/app_info.py
  git commit -m "Bump version to $VERSION"
  git push origin main
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
  -x "config.json" \
  -x "update.zip"

bash ./PUBLISH_UPDATE_TO_GITHUB.sh "$TAG" "$OUT_ZIP"

echo ""
echo "Готово. URL обновления:"
echo "https://github.com/StepanDedeshko/Oko/releases/download/$TAG/update.zip"
