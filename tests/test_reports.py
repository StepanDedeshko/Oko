import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from app.reports import (
    OutageAggregate,
    OutageEvent,
    aggregate_outages,
    build_report_rows,
    calculate_lost_passages,
    load_outages_from_csv,
    passage_average_key,
    problem_matches_report_trigger,
)


class ReportsCoreTest(unittest.TestCase):
    def test_matches_all_required_trigger_families(self):
        samples = [
            "host-1 has been restarted (uptime < 10m)",
            "Zabbix agent on 10.0.0.1 host-1 is unreachable for 3m",
            "Точка монтирования /data находится в режиме read only",
            "Сервер недоступен через ping 10.0.0.1 host-1",
            "docker service not running",
            "Не запущен docker контейнер face-api",
            "Tevian: Ошибка получения API face detect http://10.0.0.1:8080/face/detect",
            "Tevian: Ошибка получения API face match http://10.0.0.1:8080/face/match",
        ]
        for problem in samples:
            with self.subTest(problem=problem):
                self.assertTrue(problem_matches_report_trigger(problem))
        self.assertFalse(problem_matches_report_trigger("CPU utilization is high"))

    def test_csv_uses_source_time_columns_and_filters_triggers(self):
        payload = (
            "Время;Время восстановления;Узел сети;Проблема;Длительность\n"
            "19.07.2026 10:00:00;19.07.2026 10:10:00;host-1;docker service not running;10m\n"
            "19.07.2026 11:00:00;19.07.2026 11:20:00;host-2;CPU utilization is high;20m\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "problems.csv"
            path.write_text(payload, encoding="utf-8-sig")
            events = load_outages_from_csv(
                path,
                date_from=date(2026, 7, 19),
                date_to=date(2026, 7, 19),
            )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].host, "host-1")
        self.assertEqual(events[0].downtime_seconds, 600)

    def test_aggregate_sums_downtime_by_date_and_host(self):
        events = [
            OutageEvent(
                datetime(2026, 7, 19, 10, 0),
                datetime(2026, 7, 19, 10, 10),
                "HOST-1",
                "docker service not running",
            ),
            OutageEvent(
                datetime(2026, 7, 19, 12, 0),
                datetime(2026, 7, 19, 12, 5),
                "host-1",
                "docker service not running",
            ),
        ]
        result = aggregate_outages(events)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].downtime_seconds, 900)
        self.assertEqual(result[0].event_count, 2)

    def test_lost_passages_formula_is_time_times_count_divided_by_five(self):
        # 10 minutes * 2 passages / 5 = 4 lost passages.
        self.assertEqual(calculate_lost_passages(10 * 60, 2.0), 4.0)

    def test_build_report_rows_uses_five_minute_formula(self):
        aggregate = OutageAggregate(
            report_date=date(2026, 7, 19),
            host="host-1",
            downtime_seconds=30 * 60,
            event_count=1,
        )
        averages = {passage_average_key(aggregate.report_date, aggregate.host): 1.5}
        row = build_report_rows([aggregate], averages)[0]
        self.assertEqual(row.passage_average, 1.5)
        self.assertEqual(row.lost_passages, 9.0)


if __name__ == "__main__":
    unittest.main()
