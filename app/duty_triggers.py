"""Pure HTML-table stagnation checks for duty trigger metrics.

The module intentionally has no GUI/WebEngine integration and uses only the
Python standard library so it can be tested independently from the application.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from html.parser import HTMLParser
from typing import Any

DATETIME_FORMAT = "%d.%m.%Y %H:%M:%S"
STATUS_OK = "OK"
STATUS_ALERT = "ALERT"
STATUS_NO_DATA = "NO_DATA"
STATUS_PARSE_ERROR = "PARSE_ERROR"


class DutyTriggerParseError(ValueError):
    """Raised when the target metric table exists but its data cannot be parsed."""


@dataclass(frozen=True)
class MetricRow:
    """One parsed metric row from the source table."""

    timestamp: datetime
    value: str


@dataclass(frozen=True)
class StableSeries:
    """Current topmost series of equal values in a newest-to-oldest table."""

    from_time: datetime
    to_time: datetime
    duration_minutes: int
    value: str
    metric_name: str


class _MetricTableParser(HTMLParser):
    """Small purpose-built parser for source pages with metric tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict[str, Any]] = []
        self._table_stack: list[dict[str, Any]] = []
        self._current_row: dict[str, Any] | None = None
        self._current_cell: dict[str, Any] | None = None
        self._in_pre = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name: value or "" for name, value in attrs}
        if tag == "table":
            self._table_stack.append({"headers": [], "rows": []})
            return

        if not self._table_stack:
            return

        if tag == "tr":
            self._current_row = {"cells": []}
        elif tag in {"td", "th"}:
            classes = set(attr_map.get("class", "").split())
            self._current_cell = {
                "tag": tag,
                "classes": classes,
                "text_parts": [],
                "pre_parts": [],
                "span_titles": [],
            }
        elif tag == "pre" and self._current_cell is not None:
            self._in_pre = True
        elif tag == "span" and self._current_cell is not None:
            classes = set(attr_map.get("class", "").split())
            title = attr_map.get("title", "").strip()
            if "text-vertical" in classes and title:
                self._current_cell["span_titles"].append(title)

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            if self._table_stack:
                table = self._table_stack.pop()
                if self._table_stack:
                    self._table_stack[-1]["rows"].extend(table["rows"])
                    self._table_stack[-1]["headers"].extend(table["headers"])
                else:
                    self.tables.append(table)
            return

        if not self._table_stack:
            return

        if tag == "pre":
            self._in_pre = False
        elif tag in {"td", "th"} and self._current_cell is not None:
            text = _normalize_text("".join(self._current_cell["text_parts"]))
            pre_text = _normalize_text("".join(self._current_cell["pre_parts"]))
            cell = {
                "tag": self._current_cell["tag"],
                "classes": self._current_cell["classes"],
                "text": text,
                "pre_text": pre_text,
                "span_titles": list(self._current_cell["span_titles"]),
            }
            if tag == "th":
                self._table_stack[-1]["headers"].append(cell)
            elif self._current_row is not None:
                self._current_row["cells"].append(cell)
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if self._current_row["cells"]:
                self._table_stack[-1]["rows"].append(self._current_row)
            self._current_row = None

    def handle_data(self, data: str) -> None:
        if self._current_cell is None:
            return
        self._current_cell["text_parts"].append(data)
        if self._in_pre:
            self._current_cell["pre_parts"].append(data)


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _parse_clock(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def _time_in_window(moment: time, start: time, end: time, *, include_end: bool = False) -> bool:
    if start <= end:
        return start <= moment <= end if include_end else start <= moment < end
    return moment >= start or (moment <= end if include_end else moment < end)


def _format_datetime(value: datetime | None) -> str | None:
    return value.strftime(DATETIME_FORMAT) if value is not None else None


def _empty_result(status: str, message: str, metric_name: str, check_time: datetime) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "from_time": None,
        "to_time": None,
        "check_time": _format_datetime(check_time),
        "duration_minutes": None,
        "value": None,
        "metric_name": metric_name,
    }


def parse_metric_rows(html_text: str, metric_title: str) -> list[MetricRow]:
    """Return rows for the table whose header matches ``metric_title``.

    Timestamps are read from ``td.nowrap`` and values from ``td pre``.
    If no matching table/rows are found, an empty list is returned. If a matching
    table is found but a row timestamp is invalid, ``DutyTriggerParseError`` is
    raised so callers can distinguish bad data from missing data.
    """

    target_title = _normalize_text(metric_title)
    parser = _MetricTableParser()
    parser.feed(html_text or "")

    for table in parser.tables:
        header_titles: list[str] = []
        for header in table["headers"]:
            header_titles.extend(_normalize_text(title) for title in header["span_titles"])
            if header["text"]:
                header_titles.append(header["text"])

        if target_title not in header_titles:
            continue

        rows: list[MetricRow] = []
        for row in table["rows"]:
            timestamp_text = None
            value_text = None
            for cell in row["cells"]:
                if timestamp_text is None and "nowrap" in cell["classes"] and cell["text"]:
                    timestamp_text = cell["text"]
                if value_text is None and cell["pre_text"]:
                    value_text = cell["pre_text"]
            if timestamp_text is None or value_text is None:
                continue
            try:
                timestamp = datetime.strptime(timestamp_text, DATETIME_FORMAT)
            except ValueError as exc:
                raise DutyTriggerParseError(f"Cannot parse timestamp: {timestamp_text!r}") from exc
            rows.append(MetricRow(timestamp=timestamp, value=value_text))
        return rows

    return []


def find_stable_series(
    rows: list[MetricRow],
    check_time: datetime | None = None,
    metric_name: str = "",
) -> StableSeries | None:
    """Find the newest uninterrupted series of equal values.

    The source table is expected to be ordered from newest row to oldest row.
    """

    if not rows:
        return None

    newest = rows[0]
    series_start = newest.timestamp
    for row in rows[1:]:
        if row.value != newest.value:
            break
        series_start = row.timestamp

    to_time = check_time or newest.timestamp
    duration = max(0, int((to_time - series_start).total_seconds() // 60))
    return StableSeries(
        from_time=series_start,
        to_time=to_time,
        duration_minutes=duration,
        value=newest.value,
        metric_name=metric_name,
    )


def format_trigger_message(template: str, series: StableSeries, check_time: datetime | None = None) -> str:
    """Format a trigger message with supported placeholders."""

    actual_check_time = check_time or series.to_time
    return template.format(
        from_time=_format_datetime(series.from_time),
        to_time=_format_datetime(series.to_time),
        check_time=_format_datetime(actual_check_time),
        duration=series.duration_minutes,
        value=series.value,
        metric_name=series.metric_name,
    )


def evaluate_stagnation(
    series: StableSeries,
    mode: str,
    check_time: datetime,
    day_start: str = "06:00",
    day_end: str = "00:00",
    day_threshold_minutes: int = 90,
    night_threshold_minutes: int = 180,
    mode1_night_silence_start: str = "01:00",
    mode1_night_silence_end: str = "05:30",
) -> bool:
    """Return ``True`` when the stable series should raise an alert."""

    moment = check_time.time()
    is_day = _time_in_window(moment, _parse_clock(day_start), _parse_clock(day_end))
    if is_day:
        return series.duration_minutes > day_threshold_minutes

    if mode == "mode_1":
        silence_start = _parse_clock(mode1_night_silence_start)
        silence_end = _parse_clock(mode1_night_silence_end)
        if _time_in_window(moment, silence_start, silence_end, include_end=True):
            return False

    return series.duration_minutes > night_threshold_minutes


def evaluate_stagnation_trigger(
    html_text: str,
    metric_title: str,
    mode: str,
    check_time: datetime | None = None,
    ok_text: str = "Сработки поступают все в пределах нормы",
    alert_template: str = "С {from_time} по {to_time} отсутствуют сработки.",
    day_start: str = "06:00",
    day_end: str = "00:00",
    day_threshold_minutes: int = 90,
    night_threshold_minutes: int = 180,
    mode1_night_silence_start: str = "01:00",
    mode1_night_silence_end: str = "05:30",
) -> dict[str, Any]:
    """Evaluate stagnation for one HTML metric table and return a plain dict."""

    actual_check_time = check_time or datetime.now()
    metric_name = _normalize_text(metric_title)

    try:
        rows = parse_metric_rows(html_text, metric_name)
    except DutyTriggerParseError as exc:
        return _empty_result(STATUS_PARSE_ERROR, str(exc), metric_name, actual_check_time)

    series = find_stable_series(rows, actual_check_time, metric_name)
    if series is None:
        return _empty_result(STATUS_NO_DATA, "Metric table or rows not found", metric_name, actual_check_time)

    is_alert = evaluate_stagnation(
        series,
        mode,
        actual_check_time,
        day_start=day_start,
        day_end=day_end,
        day_threshold_minutes=day_threshold_minutes,
        night_threshold_minutes=night_threshold_minutes,
        mode1_night_silence_start=mode1_night_silence_start,
        mode1_night_silence_end=mode1_night_silence_end,
    )
    status = STATUS_ALERT if is_alert else STATUS_OK
    message = format_trigger_message(alert_template, series, actual_check_time) if is_alert else ok_text

    return {
        "status": status,
        "message": message,
        "from_time": _format_datetime(series.from_time),
        "to_time": _format_datetime(series.to_time),
        "check_time": _format_datetime(actual_check_time),
        "duration_minutes": series.duration_minutes,
        "value": series.value,
        "metric_name": series.metric_name,
    }
