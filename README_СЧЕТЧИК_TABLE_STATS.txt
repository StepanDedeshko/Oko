СЧЕТЧИК ПРОБЛЕМ ZABBIX — TABLE-STATS

Исправлено под твой HTML:

<div class="table-stats">Отображено с 1 до 100 из 294 найденных</div>

Теперь в config.json у страницы Проблемы стоит:

"problem_counter": {
  "enabled": true,
  "title": "Всего проблем",
  "selector": ".table-stats",
  "regex": "из\\s+(\\d+)\\s+найден",
  "refresh_after_load_ms": 1200
}

Это должно вывести:

Всего проблем: 294

Почему раньше не работало:
regex "(\\d+)" забирал первое число из строки, то есть 1.
А нужно брать число после "из".
