from datetime import datetime, timedelta
import unittest

from app.live_zabbix import (
    DETECTION_NO_DATA,
    DETECTION_OK,
    DETECTION_ZERO,
    DETECTION_ZERO_STREAK,
    HistoryValue,
    import_detection_itemids,
    latest_detection_status,
    normalize_detection_items,
    parse_zabbix_history_values,
    resolve_detection_for_host,
    zabbix_history_auth_required,
)

HTML = '''<table class="list-table"><thead><tr><th>Отметка времени</th><th>{metric}</th></tr></thead><tbody>{rows}</tbody></table>'''

def row(ts, value):
    return f"<tr><td>{ts}</td><td><pre>{value}</pre></td></tr>"

class LiveZabbixDetectionParserTests(unittest.TestCase):
    def test_parse_count_metric_with_pre(self):
        values = parse_zabbix_history_values(HTML.format(metric="Количество_сработок", rows=row("29.06.2026 17:15:13", "3")))
        self.assertEqual(values[0].timestamp, datetime(2026, 6, 29, 17, 15, 13))
        self.assertEqual(values[0].value, 3)
        self.assertEqual(values[0].metric_name, "Количество_сработок")

    def test_parse_detected_human_and_ignore_garbage(self):
        html = HTML.format(metric="detected_human", rows='<tr><td>bad</td><td>text</td></tr>' + row("29.06.2026 17:13:27", "65"))
        values = parse_zabbix_history_values(html)
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].value, 65)

    def test_empty_table_is_no_data(self):
        self.assertEqual(parse_zabbix_history_values(HTML.format(metric="x", rows="")), [])
        self.assertEqual(latest_detection_status([]).status, DETECTION_NO_DATA)

    def test_auth_required_page(self):
        html = '<output class="msg-bad">Вы не выполнили вход. Для просмотра этой страницы вы должны войти в систему.</output><button id="login" name="login">Вход</button>'
        self.assertTrue(zabbix_history_auth_required(html))

class LiveZabbixDetectionStatusTests(unittest.TestCase):
    def test_positive_is_ok(self):
        st = latest_detection_status([HistoryValue(datetime(2026,6,29,17,15,13), 5)], now=datetime(2026,6,29,17,16))
        self.assertEqual(st.status, DETECTION_OK)
        self.assertEqual(st.text, "5 · 17:15")
        self.assertFalse(st.blink)

    def test_latest_zero_is_zero(self):
        st = latest_detection_status([HistoryValue(datetime(2026,6,29,17,15), 0), HistoryValue(datetime(2026,6,29,17,14), 3)], zero_alert_after_minutes=5, now=datetime(2026,6,29,17,16))
        self.assertEqual(st.status, DETECTION_ZERO)
        self.assertTrue(st.blink)

    def test_zero_streak_after_minutes(self):
        st = latest_detection_status([HistoryValue(datetime(2026,6,29,16,49), 0), HistoryValue(datetime(2026,6,29,16,48), 0)], zero_alert_after_minutes=5, now=datetime(2026,6,29,17,0))
        self.assertEqual(st.status, DETECTION_ZERO_STREAK)
        self.assertIn("нет сработок", st.text)

class LiveZabbixDetectionFallbackMappingTests(unittest.TestCase):
    def config(self):
        return {"live_zabbix_detection_items": {"enabled": True, "refresh_interval_sec": 60, "zero_alert_after_minutes": 5, "prefer_order": ["v2", "v1"], "items": [{"host_name": "node-001", "itemid_v2": "718873", "itemid_v1": "335007"}]}}

    def test_mapping_aliases(self):
        m = normalize_detection_items(self.config())
        self.assertEqual(m["node-001"]["v2_itemid"], "718873")
        self.assertEqual(m["node-001"]["v1_itemid"], "335007")

    def test_v2_no_data_falls_back_to_v1(self):
        calls=[]
        def fetch(itemid, version):
            calls.append(version)
            return HTML.format(metric="detected_human", rows="" if version == "v2" else row("29.06.2026 17:13:27", "65"))
        st = resolve_detection_for_host("node-001", self.config(), fetch, now=datetime(2026,6,29,17,14))
        self.assertEqual(st.status, DETECTION_OK)
        self.assertEqual(st.selected_version, "v1")
        self.assertEqual(calls, ["v2", "v1"])

    def test_v2_ok_does_not_check_v1(self):
        calls=[]
        st = resolve_detection_for_host("node-001", self.config(), lambda i,v: (calls.append(v) or HTML.format(metric="Количество_сработок", rows=row("29.06.2026 17:15:13", "3"))), now=datetime(2026,6,29,17,16))
        self.assertEqual(st.selected_version, "v2")
        self.assertEqual(calls, ["v2"])

    def test_both_no_data(self):
        st = resolve_detection_for_host("node-001", self.config(), lambda i,v: HTML.format(metric="x", rows=""))
        self.assertEqual(st.status, DETECTION_NO_DATA)

    def test_import_parser_urls(self):
        result = import_detection_itemids("node-001, history.php?action=showvalues&itemids%5B%5D=718873\nitemids[]=335007")
        self.assertEqual([x["itemid"] for x in result["items"]], ["718873", "335007"])
        self.assertTrue(result["items"][1]["needs_host"])

if __name__ == "__main__":
    unittest.main()
