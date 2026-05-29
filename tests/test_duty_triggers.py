import unittest
from datetime import datetime

from app.duty_triggers import (
    STATUS_ALERT,
    STATUS_NO_DATA,
    STATUS_OK,
    STATUS_PARSE_ERROR,
    MetricRow,
    StableSeries,
    evaluate_stagnation_trigger,
    find_stable_series,
    format_trigger_message,
    parse_metric_rows,
)


METRIC_TITLE = "Кол-во всех сработок (опер. сутки)"


def make_html(rows, metric_title=METRIC_TITLE):
    row_html = "\n".join(
        f'<tr><td class="nowrap">{timestamp}</td><td><pre>{value}</pre></td></tr>'
        for timestamp, value in rows
    )
    return f"""
<html><body>
<table class="list-table">
<thead>
<tr>
<th class="cell-width">Отметка времени</th>
<th><span class="text-vertical" title="{metric_title}">{metric_title}</span></th>
</tr>
</thead>
<tbody>
{row_html}
</tbody>
</table>
</body></html>
"""


class DutyTriggersTest(unittest.TestCase):
    def test_parse_metric_rows_by_metric_title(self):
        html = make_html(
            [
                ("29.05.2026 08:03:31", "17"),
                ("29.05.2026 08:02:31", "17"),
                ("29.05.2026 07:50:31", "16"),
            ]
        )

        rows = parse_metric_rows(html, METRIC_TITLE)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].timestamp, datetime(2026, 5, 29, 8, 3, 31))
        self.assertEqual(rows[0].value, "17")

    def test_parse_metric_rows_uses_header_text_when_title_missing(self):
        html = """
<table class="list-table">
<thead><tr><th>Отметка времени</th><th>Кол-во всех сработок (опер. сутки)</th></tr></thead>
<tbody><tr><td class="nowrap">29.05.2026 08:03:31</td><td><pre>17</pre></td></tr></tbody>
</table>
"""

        rows = parse_metric_rows(html, METRIC_TITLE)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].value, "17")

    def test_find_stable_series_for_latest_equal_value(self):
        rows = [
            MetricRow(datetime(2026, 5, 29, 8, 3, 31), "17"),
            MetricRow(datetime(2026, 5, 29, 8, 2, 31), "17"),
            MetricRow(datetime(2026, 5, 29, 8, 1, 31), "17"),
            MetricRow(datetime(2026, 5, 29, 7, 50, 31), "16"),
        ]

        series = find_stable_series(rows, datetime(2026, 5, 29, 9, 31, 31), METRIC_TITLE)

        self.assertIsNotNone(series)
        self.assertEqual(series.from_time, datetime(2026, 5, 29, 8, 1, 31))
        self.assertEqual(series.to_time, datetime(2026, 5, 29, 9, 31, 31))
        self.assertEqual(series.duration_minutes, 90)
        self.assertEqual(series.value, "17")

    def test_day_mode_1_more_than_90_minutes_alert(self):
        result = evaluate_stagnation_trigger(
            make_html([("29.05.2026 08:00:00", "17")]),
            METRIC_TITLE,
            "mode_1",
            check_time=datetime(2026, 5, 29, 9, 31, 0),
        )

        self.assertEqual(result["status"], STATUS_ALERT)
        self.assertEqual(result["duration_minutes"], 91)

    def test_day_mode_2_more_than_90_minutes_alert(self):
        result = evaluate_stagnation_trigger(
            make_html([("29.05.2026 08:00:00", "17")]),
            METRIC_TITLE,
            "mode_2",
            check_time=datetime(2026, 5, 29, 9, 31, 0),
        )

        self.assertEqual(result["status"], STATUS_ALERT)

    def test_day_less_than_90_minutes_ok(self):
        result = evaluate_stagnation_trigger(
            make_html([("29.05.2026 08:00:00", "17")]),
            METRIC_TITLE,
            "mode_1",
            check_time=datetime(2026, 5, 29, 9, 30, 0),
        )

        self.assertEqual(result["status"], STATUS_OK)
        self.assertEqual(result["message"], "Сработки поступают все в пределах нормы")

    def test_night_mode_2_more_than_180_minutes_alert(self):
        result = evaluate_stagnation_trigger(
            make_html([("29.05.2026 00:00:00", "17")]),
            METRIC_TITLE,
            "mode_2",
            check_time=datetime(2026, 5, 29, 3, 1, 0),
        )

        self.assertEqual(result["status"], STATUS_ALERT)
        self.assertEqual(result["duration_minutes"], 181)

    def test_night_mode_1_silence_interval_ok_without_alert(self):
        result = evaluate_stagnation_trigger(
            make_html([("29.05.2026 00:00:00", "17")]),
            METRIC_TITLE,
            "mode_1",
            check_time=datetime(2026, 5, 29, 3, 30, 0),
        )

        self.assertEqual(result["status"], STATUS_OK)
        self.assertNotIn("отсутствуют сработки", result["message"])

    def test_format_template_with_from_time_and_to_time(self):
        series = StableSeries(
            from_time=datetime(2026, 5, 29, 8, 0, 0),
            to_time=datetime(2026, 5, 29, 9, 31, 0),
            duration_minutes=91,
            value="17",
            metric_name=METRIC_TITLE,
        )

        message = format_trigger_message("С {from_time} по {to_time} отсутствуют сработки.", series)

        self.assertEqual(
            message,
            "С 29.05.2026 08:00:00 по 29.05.2026 09:31:00 отсутствуют сработки.",
        )

    def test_format_template_without_to_time(self):
        series = StableSeries(
            from_time=datetime(2026, 5, 29, 8, 0, 0),
            to_time=datetime(2026, 5, 29, 9, 31, 0),
            duration_minutes=91,
            value="17",
            metric_name=METRIC_TITLE,
        )

        message = format_trigger_message("С {from_time} нет сработок, значение {value}.", series)

        self.assertEqual(message, "С 29.05.2026 08:00:00 нет сработок, значение 17.")

    def test_table_not_found_returns_no_data(self):
        result = evaluate_stagnation_trigger(
            make_html([("29.05.2026 08:00:00", "17")], metric_title="Другая метрика"),
            METRIC_TITLE,
            "mode_1",
            check_time=datetime(2026, 5, 29, 9, 31, 0),
        )

        self.assertEqual(result["status"], STATUS_NO_DATA)

    def test_unparseable_date_returns_parse_error(self):
        result = evaluate_stagnation_trigger(
            make_html([("bad date", "17")]),
            METRIC_TITLE,
            "mode_1",
            check_time=datetime(2026, 5, 29, 9, 31, 0),
        )

        self.assertEqual(result["status"], STATUS_PARSE_ERROR)


if __name__ == "__main__":
    unittest.main()
