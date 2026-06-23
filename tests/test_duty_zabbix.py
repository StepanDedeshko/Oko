import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app.duty_zabbix import (
    adopt_latest_zabbix_problem_csv,
    apply_handled_zabbix_problems,
    cleanup_zabbix_problem_csv_files,
    compare_zabbix_problem_exports,
    ensure_zabbix_problem_export_dir,
    filter_problems_by_period,
    find_problems_page_url,
    format_zabbix_problems_note_block,
    load_handled_zabbix_problems,
    make_zabbix_problem_key,
    mark_zabbix_problems_handled,
    normalize_problem_row,
    parse_zabbix_problems_csv,
    problem_matches_keywords,
    rotate_zabbix_problem_csv_files,
    zabbix_problems_collect_js,
    zabbix_problem_row_status_color,
    zabbix_status_color,
    zabbix_status_html,
)


class DutyZabbixTests(unittest.TestCase):

    def _write_csv(self, path, rows, encoding="utf-8"):
        header = "Важность,Время,Время восстановления,Состояние,Узел сети,Проблема,Длительность,Подтверждено,Действия,Теги\n"
        Path(path).write_text(header + "\n".join(rows) + "\n", encoding=encoding)

    def test_parse_zabbix_problems_csv_russian_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "current.csv"
            self._write_csv(path, ["Высокая,23.06.2026 12:06:15,,ПРОБЛЕМА,server-01,CPU high,1ч 46м,Нет,,service=cpu"])
            problems = parse_zabbix_problems_csv(path)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0].severity, "Высокая")
        self.assertEqual(problems[0].time, "23.06.2026 12:06:15")
        self.assertEqual(problems[0].status, "ПРОБЛЕМА")
        self.assertTrue(problems[0].key)

    def test_parse_zabbix_problems_csv_utf8_sig_and_partial_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "current.csv"
            self._write_csv(path, ["Warning,23.06.2026 12:06:15,,,db-primary,Too many connections,,,,service=db", ",,,,,Only problem text,,, ,"], encoding="utf-8-sig")
            problems = parse_zabbix_problems_csv(path)
        self.assertEqual(len(problems), 2)
        self.assertEqual(problems[0].host, "db-primary")
        self.assertEqual(problems[1].problem, "Only problem text")

    def test_make_zabbix_problem_key_is_stable_after_whitespace_normalization(self):
        first = {"severity": "High", "time": "23.06.2026 12:06", "host": "server-01", "problem": "CPU   high", "tags": "service=cpu"}
        second = {"severity": " high ", "time": "23.06.2026 12:06", "host": "SERVER-01", "problem": "CPU high", "tags": "service=cpu"}
        self.assertEqual(make_zabbix_problem_key(first), make_zabbix_problem_key(second))

    def test_compare_zabbix_problem_exports_marks_missing_previous_as_resolved(self):
        previous = [parse_zabbix_problems_csv(self._csv_file(["High,23.06.2026 10:00,,ПРОБЛЕМА,old-host,Old problem,1ч,Нет,,service=old"]))[0]]
        current = [parse_zabbix_problems_csv(self._csv_file(["High,23.06.2026 11:00,,ПРОБЛЕМА,new-host,New problem,1ч,Нет,,service=new"]))[0]]
        compared = compare_zabbix_problem_exports(current, previous)
        statuses = {problem.problem: problem.status for problem in compared}
        self.assertEqual(statuses["Old problem"], "РЕШЕНО")
        self.assertEqual(statuses["New problem"], "ПРОБЛЕМА")

    def _csv_file(self, rows):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8")
        tmp.write("Важность,Время,Время восстановления,Состояние,Узел сети,Проблема,Длительность,Подтверждено,Действия,Теги\n")
        tmp.write("\n".join(rows))
        tmp.write("\n")
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return Path(tmp.name)

    def test_handled_problem_storage_and_marking(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_dir = ensure_zabbix_problem_export_dir(tmp)
            problem = parse_zabbix_problems_csv(self._csv_file(["High,23.06.2026 12:00,,ПРОБЛЕМА,server-01,CPU high,1ч,Нет,,service=cpu"]))[0]
            mark_zabbix_problems_handled(export_dir, [problem], handled_at="2026-06-23T12:30:00")
            handled = load_handled_zabbix_problems(export_dir)
            self.assertIn(problem.key, handled)
            apply_handled_zabbix_problems([problem], handled)
            self.assertTrue(problem.handled)

    def test_adopt_latest_export_handles_numbered_csv_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_dir = ensure_zabbix_problem_export_dir(tmp)
            numbered = export_dir / "zbx_problems_export(2).csv"
            numbered.write_text("csv", encoding="utf-8")
            current = adopt_latest_zabbix_problem_csv(export_dir)
            self.assertEqual(current.name, "current.csv")
            self.assertTrue(current.exists())
            self.assertFalse(numbered.exists())

    def test_csv_rotation_and_cleanup_keep_only_current_previous(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_dir = ensure_zabbix_problem_export_dir(tmp)
            (export_dir / "current.csv").write_text("old", encoding="utf-8")
            (export_dir / "zbx_problems_export(1).csv").write_text("extra", encoding="utf-8")
            current, previous = rotate_zabbix_problem_csv_files(export_dir)
            self.assertEqual(current.name, "current.csv")
            self.assertTrue(previous.exists())
            current.write_text("new", encoding="utf-8")
            cleanup_zabbix_problem_csv_files(export_dir)
            self.assertEqual(sorted(path.name for path in export_dir.glob("*.csv")), ["current.csv", "previous.csv"])

    def test_find_problems_page_prefers_named_page_profile_and_product(self):
        config = {
            "products": [
                {"name": "Other", "enabled": True, "dashboards": [{"type": "problems_page", "name": "Проблемы", "zabbix_id": "zbx_other", "url": "https://other/problems"}]},
                {"name": "FacePay", "enabled": True, "dashboards": [
                    {"type": "problems_page", "name": "Не то", "zabbix_id": "zbx_product_1", "url": "https://facepay/other"},
                    {"type": "problems_page", "name": "Проблемы", "zabbix_id": "zbx_product_1", "url": "https://facepay/problems"},
                ]},
            ]
        }
        url, page, product = find_problems_page_url(config, product_name="FacePay", zabbix_profile="zbx_product_1")
        self.assertEqual(url, "https://facepay/problems")
        self.assertEqual(page["name"], "Проблемы")
        self.assertEqual(product["name"], "FacePay")

    def test_find_problems_page_returns_empty_when_missing(self):
        url, page, product = find_problems_page_url({"products": [{"name": "FacePay", "dashboards": []}]}, product_name="FacePay")
        self.assertEqual(url, "")
        self.assertIsNone(page)
        self.assertIsNone(product)

    def test_zabbix_status_colors(self):
        self.assertEqual(zabbix_status_color("Проверено"), "#7CFC98")
        self.assertEqual(zabbix_status_color("Ошибка"), "#ff5c5c")
        self.assertEqual(zabbix_status_color("Требуется внимание"), "#f6d365")
        self.assertEqual(zabbix_status_color("Открыто для проверки"), "#58a6ff")
        self.assertEqual(zabbix_status_color("Ошибка: URL не найден"), "#ff5c5c")

    def test_problem_row_status_colors(self):
        self.assertEqual(zabbix_problem_row_status_color(" ПРОБЛЕМА "), "#ff5c5c")
        self.assertEqual(zabbix_problem_row_status_color("решено"), "#7CFC98")
        self.assertEqual(zabbix_problem_row_status_color("РЕШЕНА"), "#7CFC98")
        self.assertEqual(zabbix_problem_row_status_color("другое"), "")

    def test_zabbix_status_html_escapes_label(self):
        html = zabbix_status_html("Ошибка <script>")
        self.assertIn("#ff5c5c", html)
        self.assertIn("Ошибка &lt;script&gt;", html)
        self.assertNotIn("<script>", html)


    def test_collect_js_contains_problem_table_selectors_and_paging(self):
        js = zabbix_problems_collect_js(max_pages=10, max_problems=500)
        self.assertIn("#t6a3a4bcc6c78d563014208 > tbody", js)
        self.assertIn("#problem_form table tbody", js)
        self.assertIn("#problem_form tbody", js)
        self.assertIn("table tbody", js)
        self.assertIn("#problem_form > div.table-paging > nav", js)
        self.assertIn("MAX_PAGES = 10", js)
        self.assertIn("MAX_PROBLEMS = 500", js)

    def test_normalize_problem_row_keeps_raw_text_when_columns_unknown(self):
        problem = normalize_problem_row(["server-01 CPU load is high without columns"])
        self.assertEqual(problem["problem"], "server-01 CPU load is high without columns")
        self.assertEqual(problem["raw_text"], "server-01 CPU load is high without columns")

    def test_normalize_problem_row_extracts_columns(self):
        problem = normalize_problem_row(["23.06.2026 10:12", "High", "server-01", "CPU load is high", "service=cpu", "team=infra"])
        self.assertEqual(problem["time"], "23.06.2026 10:12")
        self.assertEqual(problem["severity"], "High")
        self.assertEqual(problem["host"], "server-01")
        self.assertEqual(problem["problem"], "CPU load is high")
        self.assertEqual(problem["tags"], "service=cpu; team=infra")

    def test_filter_problems_by_period_keeps_recent_and_undated(self):
        now = datetime(2026, 6, 23, 12, 0)
        problems = [
            {"time": "23.06.2026 10:12", "problem": "recent"},
            {"time": "20.06.2026 10:12", "problem": "old"},
            {"time": "без даты", "problem": "undated"},
        ]
        filtered = filter_problems_by_period(problems, 1, now=now)
        self.assertEqual([item["problem"] for item in filtered], ["recent", "undated"])

    def test_problem_keywords_include_and_exclude_case_insensitive(self):
        problem = {"severity": "High", "host": "DB-Primary", "problem": "Too many connections", "tags": "service=db"}
        self.assertTrue(problem_matches_keywords(problem, keywords=["db-primary"]))
        self.assertTrue(problem_matches_keywords(problem, keywords=["CONNECTIONS"]))
        self.assertFalse(problem_matches_keywords(problem, keywords=["cpu"]))
        self.assertFalse(problem_matches_keywords(problem, keywords=["db"], exclude_keywords=["many connections"]))

    def test_format_zabbix_problems_note_block(self):
        block = format_zabbix_problems_note_block([
            {"time": "23.06.2026 12:06:15", "severity": "Высокая", "host": "server-01", "problem": "CPU load is high", "tags": "service=cpu"}
        ])
        self.assertIn("Замеченные проблемы Zabbix:", block)
        self.assertIn('1. 23.06.2026 12:06:15, Высокая, server-01, CPU load is high. - "Ссылка на задачу в Redmine"', block)

    def test_format_zabbix_problems_note_block_uses_fallbacks_and_handled_note(self):
        block = format_zabbix_problems_note_block([
            {"time": "", "severity": "", "host": "", "problem": "", "raw_text": "", "handled": True}
        ])
        self.assertIn('1. Время не указано, Важность не указана, Узел не указан, Проблема не указана. - "Ссылка на задачу в Redmine"', block)
        self.assertIn("Примечание: проблема уже была добавлена в задачу ранее.", block)


if __name__ == "__main__":
    unittest.main()
