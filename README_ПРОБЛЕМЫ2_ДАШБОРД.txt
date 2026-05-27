ПРОБЛЕМЫ 2 ТЕПЕРЬ НЕ ТРОГАЕМ КАК ПРОБЛЕМЫ

Исправлено:

FacePay -> Проблемы
    type = problems_page
    Тут есть шаблоны проблем.

FacePay -> Проблемы 2
    type = dashboard_page
    Это обычная страница/дашборд Zabbix.
    Тут НЕТ шаблонов проблем.
    Тут НЕТ кнопок времени.
    Сюда просто вставляется ссылка на dashboard Zabbix.

Где вставить ссылку:
config.json -> product FacePay -> dashboard "Проблемы 2" -> url

Пример:
"url": "http://10.250.10.10/zabbix.php?action=dashboard.view&dashboardid=123"
