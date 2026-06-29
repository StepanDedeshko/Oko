import time
import unittest

from app.live_zabbix import (
    detection_cache_get,
    detection_cache_put,
    detect_node_version,
    extract_zabbix_detection_item_from_html,
    host_match_aliases,
    hosts_match,
    normalize_host_name,
    parse_detection_node_csv_bytes,
)


class LiveZabbixDetectionCsvTests(unittest.TestCase):
    def test_import_csv_semicolon_with_headers(self):
        nodes = parse_detection_node_csv_bytes("IP;Имя\n10.0.0.1; Server  01 \n".encode(), "v1")
        self.assertEqual(nodes[0]["ip"], "10.0.0.1")
        self.assertEqual(nodes[0]["normalized_host"], "server 01")
        self.assertEqual(nodes[0]["version"], "v1")

    def test_import_csv_comma_tsv_and_no_headers(self):
        self.assertEqual(parse_detection_node_csv_bytes(b"10.0.0.2,host2\n", "v2")[0]["host"], "host2")
        self.assertEqual(parse_detection_node_csv_bytes(b"10.0.0.3\thost3\n", "v2")[0]["host"], "host3")

    def test_cp1251_headers(self):
        nodes = parse_detection_node_csv_bytes("Адрес;Сервер\n10.0.0.4;Узел-4\n".encode("cp1251"), "v1")
        self.assertEqual(nodes[0]["host"], "Узел-4")

    def test_normalize_host(self):
        self.assertEqual(normalize_host_name("  SERVER   Name "), "server name")

    def test_detect_versions_conflict_prefers_v2_and_unknown(self):
        cfg = {"live_zabbix_node_version_lists": {
            "v1_nodes": parse_detection_node_csv_bytes(b"10.0.0.1;host1\n10.0.0.3;both\n", "v1"),
            "v2_nodes": parse_detection_node_csv_bytes(b"10.0.0.2;host2\n10.0.0.4;both\n", "v2"),
        }}
        self.assertEqual(detect_node_version("host1", "", cfg), "v1")
        self.assertEqual(detect_node_version("host2", "", cfg), "v2")
        self.assertEqual(detect_node_version("both", "", cfg), "v2")
        self.assertEqual(detect_node_version("missing", "", cfg), "unknown")

    def test_zabbix_extended_host_matches_csv_short_host_aliases(self):
        cases = [
            ("Описание - node01", "node01"),
            ("Описание – node01", "node01"),
            ("Описание — node01", "node01"),
            ("prefix - group - node01", "node01"),
            ("node01", "node01"),
            ("Описание - NODE01", "node01"),
            ("Описание -  node01  ", "node01"),
        ]
        for zabbix_host, csv_host in cases:
            with self.subTest(zabbix_host=zabbix_host):
                self.assertTrue(hosts_match(zabbix_host, csv_host))
                self.assertIn("node01", host_match_aliases(zabbix_host))

    def test_detect_versions_with_short_alias_conflict_ip_and_unknown(self):
        cfg = {"live_zabbix_node_version_lists": {
            "v1_nodes": parse_detection_node_csv_bytes(b"10.0.0.1;node01\n10.0.0.9;ip-only\n", "v1"),
            "v2_nodes": parse_detection_node_csv_bytes(b"10.0.0.2;node01\n", "v2"),
        }}
        self.assertEqual(detect_node_version("prefix - group - node01", "", cfg), "v2")
        self.assertEqual(detect_node_version("different-host", "10.0.0.9", cfg), "v1")
        self.assertEqual(detect_node_version("Описание - missing", "10.0.0.99", cfg), "unknown")


class LiveZabbixDetectionDiscoveryTests(unittest.TestCase):
    def test_extract_itemid_from_history_link_by_v2_alias(self):
        html = '<a href="history.php?action=showvalues&itemids[]=718873">Количество_сработок</a>'
        result = extract_zabbix_detection_item_from_html(html, ["Количество сработок"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["itemid"], "718873")

    def test_extract_itemid_from_item_link_by_v1_alias(self):
        html = '<a href="items.php?form=update&itemid=335007">detected_human</a>'
        result = extract_zabbix_detection_item_from_html(html, ["detected human"])
        self.assertEqual(result["itemid"], "335007")

    def test_item_not_found_and_cache(self):
        self.assertEqual(extract_zabbix_detection_item_from_html("<html></html>", ["x"])["status"], "itemid_not_found")
        cache = {}
        detection_cache_put(cache, "Host", status="ok", itemid="1", discovered_at=time.time())
        self.assertEqual(detection_cache_get(cache, "host", 60)["itemid"], "1")
        detection_cache_put(cache, "Bad", status="itemid_not_found", discovered_at=time.time() - 301)
        self.assertIsNone(detection_cache_get(cache, "bad", 60, 300))


if __name__ == "__main__":
    unittest.main()
