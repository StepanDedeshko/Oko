# Процесс проверки PR и выпуска обновления Око

## 1) Подготовка разработки

```bash
git checkout main
git pull origin main
```

## 2) Проверка PR от Codex

```bash
./MERGE_CODEX_PR.sh <номер_PR>
```

Скрипт:
- переключает на `main` и обновляет его;
- подтягивает ветку PR в `codex-pr-<номер_PR>`;
- делает merge `main` в ветку PR;
- при конфликтах останавливается;
- если конфликтов нет — запускает `py_compile`;
- проверяет, что `config.json` не отличается от `main`.

## 3) Сборка и публикация релиза

```bash
./RELEASE_OKO.sh v0.2.4
```

Скрипт:
- проверяет чистоту рабочего дерева;
- запускает `py_compile`;
- собирает `~/Загрузки/update.zip`;
- публикует архив через `PUBLISH_UPDATE_TO_GITHUB.sh`;
- печатает итоговый URL:

```text
https://github.com/StepanDedeshko/Oko/releases/download/<tag>/update.zip
```
