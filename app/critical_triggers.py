from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re
from typing import Iterable


CRITICAL_TRIGGER_KIND = "critical"
SLOW_SHARE_THRESHOLD = 50.0
RECENT_OPERATIONS_WINDOW_MINUTES = 30


@dataclass(frozen=True)
class CriticalTriggerDefinition:
    id: str
    pattern: re.Pattern
    main_graph_page_url: str
    main_chart_image_url: str
    slow_history_url: str = ""
    expected_slow_metric: str = ""
    all_operations_graph_page_url: str = ""
    all_operations_chart_image_url: str = ""
    all_operations_history_url: str = ""
    expected_all_operations_metric: str = ""


@dataclass(frozen=True)
class HistoryPoint:
    timestamp: datetime
    value: float


@dataclass
class CriticalAnalysisResult:
    trigger_id: str
    slow_value: float | None = None
    slow_timestamp: datetime | None = None
    all_operations_checked: bool = False
    all_operations_state: str = "not_required"
    analysis_text: str = ""
    graph_page_urls: list[str] = field(default_factory=list)
    chart_image_urls: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


LAST_REQUEST_GRAPH_PAGE_URL = "http://10.250.10.10/zabbix.php?action=charts.view&filter_hostids%5B0%5D=11168&filter_name=%D0%95%D0%A6%D0%A5%D0%94.%D0%92%D1%80%D0%B5%D0%BC%D1%8F%20%D1%81%20%D0%BF%D0%BE%D1%81%D0%BB%D0%B5%D0%B4%D0%BD%D0%B5%D0%B3%D0%BE%20%D0%B7%D0%B0%D0%BF%D1%80%D0%BE%D1%81%D0%B0%20%D0%BF%D0%BE%20%D0%B2%D1%81%D0%B5%D0%BC%20%D0%BE%D0%BF%D0%B5%D1%80%D0%B0%D1%86%D0%B8%D1%8F%D0%BC1&filter_show=1&filter_set=1&from=now-3h&to=now"
LAST_REQUEST_CHART_IMAGE_URL = "http://10.250.10.10/chart2.php?graphid=150727&from=now-3h&to=now&height=201&width=2660&profileIdx=web.charts.filter&"

ECHD_ALL_OPERATIONS_GRAPH_PAGE_URL = "http://10.250.10.10/zabbix.php?action=charts.view&filter_hostids%5B0%5D=11168&filter_name=%D0%95%D0%A6%D0%A5%D0%94.%D0%92%D1%80%D0%B5%D0%BC%D1%8F%20%D1%81%20%D0%BF%D0%BE%D1%81%D0%BB%D0%B5%D0%B4%D0%BD%D0%B5%D0%B3%D0%BE%20%D0%B7%D0%B0%D0%BF%D1%80%D0%BE%D1%81%D0%B0%20%D0%BF%D0%BE%20%D0%B2%D1%81%D0%B5%D0%BC%20%D0%BE%D0%BF%D0%B5%D1%80%D0%B0%D1%86%D0%B8%D1%8F%D0%BC1&filter_show=1&filter_set=1&from=now-3h&to=now"
ECHD_ALL_OPERATIONS_CHART_IMAGE_URL = "http://10.250.10.10/chart2.php?graphid=150756&from=now-3h&to=now&height=201&width=2660&profileIdx=web.charts.filter&"
ECHD_ALL_OPERATIONS_HISTORY_URL = "http://10.250.10.10/history.php?action=showvalues&itemids%5B%5D=1088434"
ECHD_ALL_OPERATIONS_METRIC = "echd_last_request_все_операции"

TIB_ALL_OPERATIONS_GRAPH_PAGE_URL = "http://10.250.10.10/zabbix.php?action=charts.view&filter_hostids%5B0%5D=11168&filter_name=%D0%A2%D0%98%D0%91.%D0%92%D1%80%D0%B5%D0%BC%D1%8F%20%D1%81%20%D0%BF%D0%BE%D1%81%D0%BB%D0%B5%D0%B4%D0%BD%D0%B5%D0%B3%D0%BE%20%D0%B7%D0%B0%D0%BF%D1%80%D0%BE%D1%81%D0%B0%20%D0%BF%D0%BE%20%D0%B2%D1%81%D0%B5%D0%BC%20%D0%BE%D0%BF%D0%B5%D1%80%D0%B0%D1%86%D0%B8%D1%8F%D0%BC1&filter_show=1&filter_set=1&from=now-3h&to=now&width=1374"
TIB_ALL_OPERATIONS_CHART_IMAGE_URL = "http://10.250.10.10/chart2.php?graphid=150755&from=now-3h&to=now&height=201&width=2660&profileIdx=web.charts.filter&"
TIB_ALL_OPERATIONS_HISTORY_URL = "http://10.250.10.10/history.php?action=showvalues&itemids%5B%5D=1088410"
TIB_ALL_OPERATIONS_METRIC = "tib_last_request_все_операции"


def _compile(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


CRITICAL_TRIGGER_DEFINITIONS: tuple[CriticalTriggerDefinition, ...] = (
    CriticalTriggerDefinition(
        id="last_request_gt_120m",
        pattern=_compile(r"время\s+с\s+последнего\s+запроса\s+в\s+.+>120\s+минут"),
        main_graph_page_url=LAST_REQUEST_GRAPH_PAGE_URL,
        main_chart_image_url=LAST_REQUEST_CHART_IMAGE_URL,
    ),
    CriticalTriggerDefinition(
        id="echd_delete_consumer_success_lt_10",
        pattern=_compile(r"доля\s+успешно\s+обработанных\s+запросов\s+в\s+.+\.\s*удаление\s+.+\s+в\s+потребителе<10"),
        main_graph_page_url="http://10.250.10.10/zabbix.php?action=charts.view&filter_hostids%5B0%5D=11168&filter_name=%D0%95%D0%A6%D0%A5%D0%94.%20%D0%A3%D0%B4%D0%B0%D0%BB%D0%B5%D0%BD%D0%B8%D0%B5%20%D0%91%D0%94%D0%BD%20%D0%B2%20%D0%BF%D0%BE%D1%82%D1%80%D0%B5%D0%B1%D0%B8%D1%82%D0%B5%D0%BB%D0%B5%20%D0%94%D0%BE%D0%BB%D1%8F%20%D1%83%D1%81%D0%BF%D0%B5%D1%88%D0%BD%D0%BE%20%D0%BE%D0%B1%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D0%B0%D0%BD%D0%BD%D1%8B%D1%85%20%D0%B7%D0%B0%D0%BF%D1%80%D0%BE%D1%81%D0%BE%D0%B2&filter_show=1&filter_set=1&from=now-3h&to=now",
        main_chart_image_url="http://10.250.10.10/chart2.php?graphid=150740&from=now-3h&to=now&height=201&width=1296&profileIdx=web.charts.filter&",
        slow_history_url="http://10.250.10.10/history.php?action=showvalues&itemids%5B%5D=1094986",
        expected_slow_metric="echd_opid_3_share_slow",
        all_operations_graph_page_url=ECHD_ALL_OPERATIONS_GRAPH_PAGE_URL,
        all_operations_chart_image_url=ECHD_ALL_OPERATIONS_CHART_IMAGE_URL,
        all_operations_history_url=ECHD_ALL_OPERATIONS_HISTORY_URL,
        expected_all_operations_metric=ECHD_ALL_OPERATIONS_METRIC,
    ),
    CriticalTriggerDefinition(
        id="echd_get_consumer_success_lt_10",
        pattern=_compile(r"доля\s+успешно\s+обработанных\s+запросов\s+в\s+.+\.\s*получение\s+.+\s+потребителем<10"),
        main_graph_page_url="http://10.250.10.10/zabbix.php?action=charts.view&filter_hostids%5B0%5D=11168&filter_name=%D0%95%D0%A6%D0%A5%D0%94.%20%D0%9F%D0%BE%D0%BB%D1%83%D1%87%D0%B5%D0%BD%D0%B8%D0%B5%20%D0%91%D0%9E%20%D0%BF%D0%BE%D1%82%D1%80%D0%B5%D0%B1%D0%B8%D1%82%D0%B5%D0%BB%D0%B5%D0%BC%20%D0%94%D0%BE%D0%BB%D1%8F%20%D1%83%D1%81%D0%BF%D0%B5%D1%88%D0%BD%D0%BE%20%D0%BE%D0%B1%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D0%B0%D0%BD%D0%BD%D1%8B%D1%85%20%D0%B7%D0%B0%D0%BF%D1%80%D0%BE%D1%81%D0%BE%D0%B2&filter_show=1&filter_set=1&from=now-3h&to=now&width=1374",
        main_chart_image_url="http://10.250.10.10/chart2.php?graphid=150744&from=now-3h&to=now&height=201&width=2660&profileIdx=web.charts.filter&",
        slow_history_url="http://10.250.10.10/history.php?action=showvalues&itemids%5B%5D=1094985",
        expected_slow_metric="echd_opid_2_share_slow",
        all_operations_graph_page_url=ECHD_ALL_OPERATIONS_GRAPH_PAGE_URL,
        all_operations_chart_image_url=ECHD_ALL_OPERATIONS_CHART_IMAGE_URL,
        all_operations_history_url=ECHD_ALL_OPERATIONS_HISTORY_URL,
        expected_all_operations_metric=ECHD_ALL_OPERATIONS_METRIC,
    ),
    CriticalTriggerDefinition(
        id="tib_registration_without_bo_success_lt_10",
        pattern=_compile(r"доля\s+успешно\s+обработанных\s+запросов\s+в\s+.+\.\s*регистрация\s+в\s+.+\s+без\s+.+<10"),
        main_graph_page_url="http://10.250.10.10/zabbix.php?action=charts.view&filter_hostids%5B0%5D=11168&filter_name=%D0%A2%D0%98%D0%91.%20%D0%A0%D0%B5%D0%B3%D0%B8%D1%81%D1%82%D1%80%D0%B0%D1%86%D0%B8%D1%8F%20%D0%B2%20%D0%95%D0%91%D0%A1%20%D0%B1%D0%B5%D0%B7%20%D0%91%D0%9E.%20%D0%94%D0%BE%D0%BB%D1%8F%20%D1%83%D1%81%D0%BF%D0%B5%D1%88%D0%BD%D0%BE%20%D0%BE%D0%B1%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D0%B0%D0%BD%D0%BD%D1%8Bx%20%D0%B8%20%D0%BC%D0%B5%D0%B4%D0%BB%D0%B5%D0%BD%D0%BD%D1%8B%D1%85%20%D0%B7%D0%B0%D0%BF%D1%80%D0%BE%D1%81%D0%BE%D0%B2&filter_show=1&filter_set=1&from=now-3h&to=now&width=1374",
        main_chart_image_url="http://10.250.10.10/chart2.php?graphid=150741&from=now-3h&to=now&height=201&width=2660&profileIdx=web.charts.filter&",
        slow_history_url="http://10.250.10.10/history.php?action=showvalues&itemids%5B%5D=1094915",
        expected_slow_metric="tib_opid_5_share_slow",
        all_operations_graph_page_url=TIB_ALL_OPERATIONS_GRAPH_PAGE_URL,
        all_operations_chart_image_url=TIB_ALL_OPERATIONS_CHART_IMAGE_URL,
        all_operations_history_url=TIB_ALL_OPERATIONS_HISTORY_URL,
        expected_all_operations_metric=TIB_ALL_OPERATIONS_METRIC,
    ),
    CriticalTriggerDefinition(
        id="tib_deactivation_success_lt_10",
        pattern=_compile(r"доля\s+успешно\s+обработанных\s+запросов\s+в\s+.+\.\s*деактивация\s+.+\s+в\s+.+<10"),
        main_graph_page_url="http://10.250.10.10/zabbix.php?action=charts.view&filter_hostids%5B0%5D=11168&filter_name=%D0%A2%D0%98%D0%91.%20%D0%94%D0%B5%D0%B0%D0%BA%D1%82%D0%B8%D0%B2%D0%B0%D1%86%D0%B8%D0%B8%20%D0%A3%D0%97%20%D0%B2%20%D0%95%D0%91%D0%A1%20%D0%94%D0%BE%D0%BB%D1%8F%20%D1%83%D1%81%D0%BF%D0%B5%D1%88%D0%BD%D0%BE%20%D0%BE%D0%B1%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D0%B0%D0%BD%D0%BD%D1%8B%D1%85%20%D0%B7%D0%B0%D0%BF%D1%80%D0%BE%D1%81%D0%BE%D0%B2&filter_show=1&filter_set=1&from=now-3h&to=now&width=1374",
        main_chart_image_url="http://10.250.10.10/chart2.php?graphid=150739&from=now-3h&to=now&height=201&width=2660&profileIdx=web.charts.filter&",
        slow_history_url="http://10.250.10.10/history.php?action=showvalues&itemids%5B%5D=1094917",
        expected_slow_metric="tib_opid_7_share_slow",
        all_operations_graph_page_url=TIB_ALL_OPERATIONS_GRAPH_PAGE_URL,
        all_operations_chart_image_url=TIB_ALL_OPERATIONS_CHART_IMAGE_URL,
        all_operations_history_url=TIB_ALL_OPERATIONS_HISTORY_URL,
        expected_all_operations_metric=TIB_ALL_OPERATIONS_METRIC,
    ),
)


def normalize_critical_trigger_text(value: str) -> str:
    text = " ".join(str(value or "").casefold().split())
    text = re.sub(r"\s*([<>])\s*", r"\1", text)
    text = re.sub(r"\s+([.])\s*", r"\1 ", text)
    return text.strip()


def match_critical_trigger(value: str) -> CriticalTriggerDefinition | None:
    normalized = normalize_critical_trigger_text(value)
    if not normalized:
        return None
    for definition in CRITICAL_TRIGGER_DEFINITIONS:
        if definition.pattern.search(normalized):
            return definition
    return None


def is_critical_trigger_name(value: str) -> bool:
    return match_critical_trigger(value) is not None


def definition_by_id(trigger_id: str) -> CriticalTriggerDefinition | None:
    key = str(trigger_id or "").strip()
    for definition in CRITICAL_TRIGGER_DEFINITIONS:
        if definition.id == key:
            return definition
    return None


def parse_history_value(value: str) -> float | None:
    text = str(value or "").strip().replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def parse_history_timestamp(value: str) -> datetime | None:
    text = str(value or "").strip()
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%y %H:%M:%S", "%d.%m.%y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def parse_history_rows(rows: Iterable[dict]) -> list[HistoryPoint]:
    points: list[HistoryPoint] = []
    for row in rows or []:
        timestamp = parse_history_timestamp((row or {}).get("timestamp"))
        value = parse_history_value((row or {}).get("value"))
        if timestamp is None or value is None:
            continue
        points.append(HistoryPoint(timestamp=timestamp, value=value))
    return sorted(points, key=lambda point: point.timestamp)


def validate_history_payload(payload: dict, expected_metric: str) -> tuple[list[HistoryPoint], list[str]]:
    warnings: list[str] = []
    if not isinstance(payload, dict) or not payload.get("ok"):
        return [], ["Не удалось автоматически получить или разобрать значения Zabbix."]
    actual_metric = str(payload.get("metric") or "").strip()
    if str(expected_metric or "").strip() and actual_metric != str(expected_metric or "").strip():
        return [], [f"Метрика Zabbix не совпала: ожидалась {expected_metric}, получена {actual_metric or 'пусто'}."]
    points = parse_history_rows(payload.get("rows") or [])
    if not points:
        warnings.append("Не удалось разобрать корректные значения Zabbix.")
    return points, warnings


def _format_value(value: float | None) -> str:
    if value is None:
        return "не определено"
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _format_dt(value: datetime | None) -> str:
    return value.strftime("%d.%m.%Y %H:%M:%S") if value else "не определено"


def last_history_point(points: Iterable[HistoryPoint]) -> HistoryPoint | None:
    values = sorted(list(points or []), key=lambda point: point.timestamp)
    return values[-1] if values else None


def slow_share_requires_all_operations_check(slow_value: float | None) -> bool:
    return slow_value is not None and slow_value < SLOW_SHARE_THRESHOLD


def analyze_slow_share_only(definition: CriticalTriggerDefinition, slow_points: Iterable[HistoryPoint]) -> CriticalAnalysisResult:
    latest = last_history_point(slow_points)
    result = CriticalAnalysisResult(
        trigger_id=definition.id,
        graph_page_urls=[definition.main_graph_page_url],
        chart_image_urls=[definition.main_chart_image_url],
    )
    if latest is None:
        result.all_operations_state = "analysis_failed"
        result.analysis_text = "Не удалось автоматически получить или разобрать значения Zabbix.\nТребуется ручная проверка графика."
        result.warnings.append("slow_history_empty")
        return result

    result.slow_value = latest.value
    result.slow_timestamp = latest.timestamp
    if latest.value >= SLOW_SHARE_THRESHOLD:
        result.all_operations_state = "not_required_high_slow_share"
        result.analysis_text = (
            f"Наблюдается высокая доля медленных запросов — {_format_value(latest.value)}%.\n"
            f"Время последнего значения: {_format_dt(latest.timestamp)}."
        )
        return result

    result.all_operations_checked = True
    result.all_operations_state = "required_not_loaded"
    result.graph_page_urls.append(definition.all_operations_graph_page_url)
    result.chart_image_urls.append(definition.all_operations_chart_image_url)
    result.analysis_text = (
        f"Доля медленных запросов составляет {_format_value(latest.value)}%.\n\n"
        "Не удалось автоматически получить или разобрать значения Zabbix.\n"
        "Требуется ручная проверка графика."
    )
    return result


def analyze_critical_history(
    definition: CriticalTriggerDefinition,
    slow_points: Iterable[HistoryPoint] | None = None,
    all_operations_points: Iterable[HistoryPoint] | None = None,
    now: datetime | None = None,
    warnings: Iterable[str] | None = None,
) -> CriticalAnalysisResult:
    result = analyze_slow_share_only(definition, slow_points or [])
    result.warnings.extend(str(item) for item in (warnings or []) if str(item or ""))
    if not result.all_operations_checked or result.slow_value is None:
        return result

    now = now or datetime.now()
    since = now - timedelta(minutes=RECENT_OPERATIONS_WINDOW_MINUTES)
    recent = sorted(
        [point for point in (all_operations_points or []) if point.timestamp >= since],
        key=lambda point: point.timestamp,
    )
    result.all_operations_checked = True

    if not recent:
        result.all_operations_state = "no_recent_points"
        result.analysis_text = (
            f"Доля медленных запросов составляет {_format_value(result.slow_value)}%.\n\n"
            "Не удалось определить наличие запросов: за последние 30 минут значения отсутствуют."
        )
        return result

    non_zero = [point for point in recent if point.value > 0]
    if not non_zero:
        result.all_operations_state = "all_zero"
        result.analysis_text = (
            f"Доля медленных запросов составляет {_format_value(result.slow_value)}%.\n\n"
            "Запросы по всем операциям за последние 30 минут отсутствуют."
        )
        return result

    latest_non_zero = non_zero[-1]
    result.all_operations_state = "has_non_zero"
    result.analysis_text = (
        f"Доля медленных запросов составляет {_format_value(result.slow_value)}%.\n\n"
        "За последние 30 минут наблюдаются запросы по всем операциям.\n"
        f"Последнее ненулевое значение: {_format_value(latest_non_zero.value)}.\n"
        f"Время: {_format_dt(latest_non_zero.timestamp)}."
    )
    return result


def build_redmine_description(definition: CriticalTriggerDefinition, trigger_name: str, host: str, ip: str, analysis: CriticalAnalysisResult | None = None) -> str:
    host_text = str(host or "узел не определён").strip() or "узел не определён"
    ip_text = str(ip or "не найден").strip() or "не найден"
    trigger_text = str(trigger_name or "Проблема Zabbix").strip() or "Проблема Zabbix"
    analysis = analysis or CriticalAnalysisResult(trigger_id=definition.id)

    if not definition.slow_history_url:
        lines = [
            "Наблюдается критический триггер:",
            trigger_text,
            "",
            f"Узел: {host_text}",
            f"IP: {ip_text}",
            "",
            "График:",
            f"!{definition.main_chart_image_url}!",
            "",
            "Картинка графика:",
            definition.main_chart_image_url,
            "",
            "Ссылка на график:",
            definition.main_graph_page_url,
            "",
            "Просьба проверить и устранить причину возникновения триггера.",
        ]
        return "\n".join(lines).strip()

    lines = [
        "Наблюдается критический триггер:",
        trigger_text,
        "",
        f"Узел: {host_text}",
        f"IP: {ip_text}",
        "",
        "Основной график:",
        f"!{definition.main_chart_image_url}!",
        "",
        "Картинка основного графика:",
        definition.main_chart_image_url,
        "",
        "Ссылка на основной график:",
        definition.main_graph_page_url,
        "",
        "Результат автоматического анализа:",
        analysis.analysis_text or "Не удалось автоматически получить или разобрать значения Zabbix.\nТребуется ручная проверка графика.",
    ]

    if analysis.all_operations_checked and definition.all_operations_chart_image_url:
        lines.extend([
            "",
            "Дополнительный график запросов по всем операциям:",
            f"!{definition.all_operations_chart_image_url}!",
            "",
            "Картинка дополнительного графика:",
            definition.all_operations_chart_image_url,
            "",
            "Ссылка на дополнительный график:",
            definition.all_operations_graph_page_url,
        ])

    lines.extend(["", "Просьба проверить и устранить причину возникновения триггера."])
    return "\n".join(lines).strip()


def build_zabbix_comment(issue_number: str, issue_url: str, analysis: CriticalAnalysisResult | None = None) -> str:
    base = f"Задача Redmine #{str(issue_number or '').strip()}: {str(issue_url or '').strip()}".strip()
    analysis_text = (analysis.analysis_text if analysis else "").strip()
    if not analysis_text or "Не удалось автоматически" in analysis_text:
        analysis_text = "Автоматический анализ значений не выполнен. Требуется ручная проверка графиков."
    return f"{base}\n\n{analysis_text}".strip()


HISTORY_EXTRACTION_SCRIPT = r"""
(function() {
  const root = document.querySelector('#flickerfreescreen_historyGraph');
  if (!root) return JSON.stringify({ok:false, reason:'history_root_not_found', metric:'', rows:[]});
  const metricNode = root.querySelector('z-vertical[title]');
  const metric = metricNode ? String(metricNode.getAttribute('title') || '').trim() : '';
  const rows = Array.from(root.querySelectorAll('table.list-table tbody tr')).map(function(row) {
    const timestampCell = row.querySelector('td:first-child');
    const valueNode = row.querySelector('td:nth-child(2) pre');
    return {
      timestamp: timestampCell ? String(timestampCell.innerText || timestampCell.textContent || '').trim() : '',
      value: valueNode ? String(valueNode.innerText || valueNode.textContent || '').trim() : ''
    };
  }).filter(function(row) { return row.timestamp || row.value; });
  return JSON.stringify({ok:true, metric:metric, rows:rows});
})();
"""
