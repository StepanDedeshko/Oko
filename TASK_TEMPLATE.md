# Шаблон задачи для Codex

## Задача

Кратко описать, что нужно сделать.

## Требования

1.
2.
3.

## Что нельзя ломать

- Запуск через `run_oko.sh`.
- Пользовательский `config.json`.
- Хранение credentials.
- Главная страница по клику на логотип/название.
- Установку без автоматического `sudo`.

## Проверка

```bash
python3 -m py_compile main.py
find app -name "*.py" -print0 | xargs -0 -n1 python3 -m py_compile
./run_oko.sh
```
