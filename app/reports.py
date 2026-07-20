"""Core helpers for the Zabbix trigger downtime / passage-loss report.

This module intentionally contains no Qt code. The UI lives in
``app.reports_widget`` while CSV parsing, trigger matching and aggregation stay
unit-testable here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import csv
import io
import json
from typing import Iterable

REPORT_TRIGGER_TEMPLATES = (
    "{HOST.NAME} has been restarted (uptime < 10m)",
    "Zabbix agent on {HOST.IP} {HOST.NAME} is unreachable for {$AGENT.TIMEOUT}",
    "Точка монтирования {#FSNAME} находится в режиме read only",
    "Сервер недоступен через ping {HOST.IP} {HOST.NAME}",
    "docker service not running",
    "Не запущен docker контейнер {#NAME}",
    "Tevian: Ошибка получения API face detect http://{HOST.IP}:{$TVAPI_PORT}/face/detect",
    "Tevian: Ошибка получения API face match http://{HOST.IP}:{$TVAPI_PORT}/face/match",
)

REPORT_HEADERS = (
    "Начало",
    "Узел сети",
    "Сумма - Недоступность",
    "Ср. кол-во проходов (мин)",
    "Потерянное кол-во проходов",
)

# История проходов в рабочем Zabbix представлена значениями с пятиминутным
# шагом. По согласованной формуле потери считаются: время_в_минутах * значение / 5.
PASSAGE_SAMPLE_MINUTES = 5.0

_DATETIME_FORMATS = (
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d.%m.%y %H:%M:%S",
    "%d.%m.%y %H:%M",
)


@dataclass(frozen=True)
class OutageEvent:
    started_at: datetime
    recovered_at: datetime
    host: str
    problem: str

    @property
    def downtime_seconds(self) -> float:
        return max(0.0, (self.recovered_at - self.started_at).total_seconds())


@dataclass(frozen=True)
class OutageAggregate:
    report_date: date
    host: str
    downtime_seconds: float
    event_count: int


@dataclass(frozen=True)
class TriggerReportRow:
    report_date: date
    host: str
    downtime_seconds: float
    passage_average: float | None
    lost_passages: float | None


def normalize_host(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def _normalize_problem(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def problem_matches_report_trigger(problem: str) -> bool:
    """Match the eight outage trigger families after Zabbix macro expansion."""
    text = _normalize_problem(problem)
    if not text:
        return False
    return any(
        (
            "has been restarted (uptime < 10m)" in text,
            text.startswith("zabbix agent on ") and " is unreachable for " in text,
            text.startswith("точка монтирования ") and " находится в режиме read only" in text,
            text.startswith("сервер недоступен через ping "),
            "docker service not running" in text,
            text.startswith("не запущен docker контейнер "),
            text.startswith("tevian: ошибка получения api face detect http://") and "/face/detect" in text,
            text.startswith("tevian: ошибка получения api face match http://") and "/face/match" in text,
        )
    )


def parse_datetime_value(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())

    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass

    # Excel serial date fallback for CSV files exported after the operator's
    # old formulas ``=A2*1`` and ``=B2*1`` were added manually.
    try:
        serial = float(raw.replace(" ", "").replace(",", "."))
    except ValueError:
        return None
    if serial <= 0:
        return None
    return datetime(1899, 12, 30) + timedelta(days=serial)


def _decode_csv_bytes(data: bytes) -> str:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError("Не удалось определить кодировку CSV") from last_error


def _csv_reader(text: str):
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t,")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";"
    return csv.DictReader(io.StringIO(text), delimiter=delimiter)


def _header_key(value: str) -> str:
    return " ".join(str(value or "").replace("\ufeff", "").split()).casefold()


def _resolve_header(fieldnames: Iterable[str] | None, aliases: Iterable[str]) -> str | None:
    by_key = {_header_key(name): name for name in (fieldnames or []) if name is not None}
    for alias in aliases:
        found = by_key.get(_header_key(alias))
        if found is not None:
            return found
    return None


def load_outages_from_csv(
    path: str | Path,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[OutageEvent]:
    """Read outage events from the operator CSV export.

    ``Начало`` / ``Восстановление`` remain accepted as fallbacks, but they are
    not required anymore. Downtime is recalculated from the source timestamps,
    equivalent to the old spreadsheet formula ``=G2-F2``.
    """
    source = Path(path)
    text = _decode_csv_bytes(source.read_bytes())
    reader = _csv_reader(text)

    start_col = _resolve_header(reader.fieldnames, ("Время", "Начало"))
    recovery_col = _resolve_header(reader.fieldnames, ("Время восстановления", "Восстановление"))
    host_col = _resolve_header(reader.fieldnames, ("Узел сети", "Узел", "Host"))
    problem_col = _resolve_header(reader.fieldnames, ("Проблема", "Problem"))

    missing = []
    if start_col is None:
        missing.append("Время/Начало")
    if recovery_col is None:
        missing.append("Время восстановления/Восстановление")
    if host_col is None:
        missing.append("Узел сети")
    if problem_col is None:
        missing.append("Проблема")
    if missing:
        raise ValueError("В CSV не найдены обязательные столбцы: " + ", ".join(missing))

    events: list[OutageEvent] = []
    for row in reader:
        problem = str(row.get(problem_col, "") or "").strip()
        if not problem_matches_report_trigger(problem):
            continue

        started_at = parse_datetime_value(row.get(start_col))
        recovered_at = parse_datetime_value(row.get(recovery_col))
        host = " ".join(str(row.get(host_col, "") or "").split())
        if started_at is None or recovered_at is None or not host:
            continue
        if recovered_at < started_at:
            continue
        if date_from is not None and started_at.date() < date_from:
            continue
        if date_to is not None and started_at.date() > date_to:
            continue

        events.append(
            OutageEvent(
                started_at=started_at,
                recovered_at=recovered_at,
                host=host,
                problem=problem,
            )
        )
    return events


def aggregate_outages(events: Iterable[OutageEvent]) -> list[OutageAggregate]:
    """Sum downtime by start date and network host, as in the old pivot sheet."""
    buckets: dict[tuple[date, str], dict] = {}
    for event in events:
        key = (event.started_at.date(), normalize_host(event.host))
        bucket = buckets.setdefault(
            key,
            {
                "report_date": event.started_at.date(),
                "host": event.host,
                "downtime_seconds": 0.0,
                "event_count": 0,
            },
        )
        bucket["downtime_seconds"] += event.downtime_seconds
        bucket["event_count"] += 1

    result = [OutageAggregate(**payload) for payload in buckets.values()]
    return sorted(result, key=lambda item: (item.report_date, normalize_host(item.host)))


def passage_average_key(report_date: date, host: str) -> tuple[str, str]:
    return report_date.isoformat(), normalize_host(host)


def calculate_lost_passages(downtime_seconds: float, passage_average: float) -> float:
    """Apply the agreed report formula: time(min) * passage value / 5."""
    downtime_minutes = max(0.0, float(downtime_seconds or 0.0)) / 60.0
    return downtime_minutes * float(passage_average) / PASSAGE_SAMPLE_MINUTES


def build_report_rows(
    aggregates: Iterable[OutageAggregate],
    passage_averages: dict[tuple[str, str], float | None] | None = None,
) -> list[TriggerReportRow]:
    passage_averages = passage_averages or {}
    result: list[TriggerReportRow] = []
    for item in aggregates:
        average = passage_averages.get(passage_average_key(item.report_date, item.host))
        lost = calculate_lost_passages(item.downtime_seconds, average) if average is not None else None
        result.append(
            TriggerReportRow(
                report_date=item.report_date,
                host=item.host,
                downtime_seconds=item.downtime_seconds,
                passage_average=average,
                lost_passages=lost,
            )
        )
    return result


def format_duration(seconds: float) -> str:
    total = max(0, int(round(float(seconds or 0.0))))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _format_decimal(value: float | None, digits: int) -> str:
    if value is None:
        return ""
    return f"{float(value):.{digits}f}".replace(".", ",")


def write_report_csv(rows: Iterable[TriggerReportRow], path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(REPORT_HEADERS)
        for row in rows:
            writer.writerow(
                (
                    row.report_date.strftime("%d.%m.%Y"),
                    row.host,
                    format_duration(row.downtime_seconds),
                    _format_decimal(row.passage_average, 4),
                    _format_decimal(row.lost_passages, 2),
                )
            )
    return destination


def normalize_passage_items(items) -> list[dict]:
    result = []
    seen = set()
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        itemid = str(raw.get("itemid") or raw.get("item_id") or raw.get("id") or "").strip()
        if not itemid or not itemid.isdigit():
            continue
        row_text = str(raw.get("rowText") or raw.get("row_text") or "")
        host = str(raw.get("host") or "").strip()
        if not host:
            host = next((line.strip() for line in row_text.splitlines() if line.strip()), "")
        if not host:
            continue
        key = (normalize_host(host), itemid)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "host": host,
                "itemid": itemid,
                "type": str(raw.get("type") or "").strip(),
                "rowText": row_text or host,
            }
        )
    return result


def passage_item_map(items) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for item in normalize_passage_items(items):
        result.setdefault(normalize_host(item["host"]), item)
    return result


def load_passage_items_json(path: str | Path) -> list[dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("items") or payload.get("data") or []
    if not isinstance(payload, list):
        raise ValueError("JSON должен содержать список itemid")
    return normalize_passage_items(payload)


def save_passage_items_json(items, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_passage_items(items)
    destination.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination
