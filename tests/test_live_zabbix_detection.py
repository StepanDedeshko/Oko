import time
import unittest

from app.live_zabbix import (
    DetectionCheckQueue,
    detection_cache_get,
    detection_cache_put,
    detect_node_version,
    extract_zabbix_detection_item_from_html,
    host_match_aliases,
    hosts_match,
    live_zabbix_node_version_lists_from_config,
    normalize_host_name,
    parse_detection_node_csv_bytes,
    safe_detection_identifier,
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

    def test_import_csv_russian_server_headers_are_skipped(self):
        nodes = parse_detection_node_csv_bytes("ip сервера;Имя_сервера\n10.0.0.5;node5\n".encode(), "v2")
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["ip"], "10.0.0.5")
        self.assertEqual(nodes[0]["host"], "node5")

    def test_import_csv_russian_node_headers_with_spaces_are_skipped(self):
        nodes = parse_detection_node_csv_bytes("IP сервера;Имя узла\n10.0.0.6;node6\n".encode(), "v1")
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["normalized_host"], "node6")

    def test_header_normalization_handles_spaces_and_underscores(self):
        spaced = parse_detection_node_csv_bytes("ip сервера;имя сервера\n10.0.0.7;node7\n".encode(), "v1")
        underscored = parse_detection_node_csv_bytes("ip_сервера;имя_узла\n10.0.0.8;node8\n".encode(), "v2")
        self.assertEqual(spaced[0]["host"], "node7")
        self.assertEqual(underscored[0]["host"], "node8")

    def test_nested_live_zabbix_node_lists_are_read(self):
        nested = {"live_zabbix_monitor": {"live_zabbix_node_version_lists": {"v1_nodes": [], "v2_nodes": [{"ip": "", "host": "node-nested", "normalized_host": "node-nested", "version": "v2"}]}}}
        self.assertEqual(live_zabbix_node_version_lists_from_config(nested)["v2_nodes"][0]["host"], "node-nested")
        self.assertEqual(detect_node_version("Описание - node-nested", "", nested), "v2")


    def test_safe_detection_identifier_does_not_expose_host_or_ip(self):
        raw_host = "Описание - private-host-01"
        raw_ip = "192.0.2.44"
        host_id = safe_detection_identifier(raw_host)
        ip_id = safe_detection_identifier(raw_ip, prefix="ip")
        self.assertIn("sha256", host_id)
        self.assertIn("sha256", ip_id)
        self.assertNotIn("private-host-01", host_id)
        self.assertNotIn(raw_ip, ip_id)

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


class LiveZabbixDetectionStateTests(unittest.TestCase):
    def test_detection_timeout_does_not_leave_status_checking(self):
        queue = DetectionCheckQueue()
        queue.queue_check("a")
        result = queue.timeout("a")
        self.assertEqual(result["status"], "timeout")
        self.assertFalse(result["checking"])
        self.assertNotIn("a", queue.checking)

    def test_load_finished_false_does_not_leave_status_checking(self):
        queue = DetectionCheckQueue()
        queue.queue_check("a")
        result = queue.load_finished("a", False)
        self.assertEqual(result["status"], "ошибка загрузки")
        self.assertFalse(result["checking"])

    def test_item_not_found_does_not_leave_status_checking(self):
        queue = DetectionCheckQueue()
        queue.queue_check("a")
        result = queue.item_not_found("a", ["x"])
        self.assertEqual(result["status"], "itemid не найден")
        self.assertFalse(result["checking"])

    def test_empty_history_does_not_leave_status_checking(self):
        queue = DetectionCheckQueue()
        queue.queue_check("a")
        result = queue.empty_history("a")
        self.assertEqual(result["status"], "нет history")
        self.assertFalse(result["checking"])

    def test_queue_continues_after_one_failed_host(self):
        queue = DetectionCheckQueue()
        queue.queue_check("bad")
        queue.queue_check("good")
        queue.item_not_found("bad")
        self.assertNotIn("bad", queue.queue)
        self.assertIn("good", queue.queue)
        self.assertIn("good", queue.checking)


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
