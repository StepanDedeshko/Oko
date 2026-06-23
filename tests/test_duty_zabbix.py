import unittest

from app.duty_zabbix import find_problems_page_url, zabbix_status_color, zabbix_status_html


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


if __name__ == "__main__":
    unittest.main()
