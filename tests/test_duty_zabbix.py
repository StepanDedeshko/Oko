import unittest
from datetime import datetime

from app.duty_zabbix import (
    filter_problems_by_period,
    find_problems_page_url,
    format_zabbix_problems_note_block,
    normalize_problem_row,
    problem_matches_keywords,
    zabbix_status_color,
    zabbix_status_html,
)


class DutyZabbixTests(unittest.TestCase):
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

    def test_zabbix_status_html_escapes_label(self):
        html = zabbix_status_html("Ошибка <script>")
        self.assertIn("#ff5c5c", html)
        self.assertIn("Ошибка &lt;script&gt;", html)
        self.assertNotIn("<script>", html)

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
            {"time": "23.06.2026 10:12", "severity": "High", "host": "server-01", "problem": "CPU load is high", "tags": "service=cpu"}
        ])
        self.assertIn("Замеченные проблемы Zabbix:", block)
        self.assertIn("1. [High] server-01 — CPU load is high", block)
        self.assertIn("Время: 23.06.2026 10:12", block)
        self.assertIn("Теги: service=cpu", block)


if __name__ == "__main__":
    unittest.main()
