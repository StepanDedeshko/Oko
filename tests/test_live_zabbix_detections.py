import unittest

from app.live_zabbix import (
    import_live_zabbix_node_list,
    live_zabbix_node_version_lists,
    parse_live_zabbix_node_list_text,
    resolve_live_zabbix_node_version,
    safe_detection_identifier,
)


class LiveZabbixDetectionCsvTests(unittest.TestCase):
    def test_csv_russian_header_ip_server_name_underscore_skips_header(self):
        self.assertEqual(parse_live_zabbix_node_list_text("ip сервера;Имя_сервера\n10.0.0.1;node-a\n"), ["10.0.0.1", "node-a"])

    def test_csv_russian_header_ip_node_name_space_skips_header(self):
        self.assertEqual(parse_live_zabbix_node_list_text("IP сервера;Имя узла\n10.0.0.2;node-b\n"), ["10.0.0.2", "node-b"])

    def test_header_normalization_handles_spaces_and_underscores(self):
        self.assertEqual(parse_live_zabbix_node_list_text("имя_узла\nnode-c\n"), ["node-c"])
        self.assertEqual(parse_live_zabbix_node_list_text("имя узла\nnode-d\n"), ["node-d"])

    def test_import_v1_and_v2_write_nested_config_and_filename_irrelevant(self):
        config = {}
        import_live_zabbix_node_list(config, "узел\nnode-v1\n", "v1")
        import_live_zabbix_node_list(config, "узел\nnode-v2\n", "v2")
        nested = config["live_zabbix_monitor"]["live_zabbix_node_version_lists"]
        self.assertEqual(nested["v1_nodes"], ["node-v1"])
        self.assertEqual(nested["v2_nodes"], ["node-v2"])
        self.assertEqual(live_zabbix_node_version_lists(config)["v1_nodes"], ["node-v1"])

    def test_detection_reads_nested_node_lists_and_short_host_matching_dashes(self):
        config = {"live_zabbix_monitor": {"live_zabbix_node_version_lists": {"v1_nodes": ["node-a", "node-b", "node-c"], "v2_nodes": []}}}
        self.assertEqual(resolve_live_zabbix_node_version(config, "description - node-a")["version"], "v1")
        self.assertEqual(resolve_live_zabbix_node_version(config, "description – node-b")["version"], "v1")
        self.assertEqual(resolve_live_zabbix_node_version(config, "description — node-c")["version"], "v1")

    def test_v2_wins_conflict_when_configured(self):
        config = {"live_zabbix_monitor": {"live_zabbix_node_version_lists": {"v1_nodes": ["node"], "v2_nodes": ["node"]}, "live_zabbix_detection_item_discovery": {"prefer_v2_on_conflict": True}}}
        self.assertEqual(resolve_live_zabbix_node_version(config, "node")["version"], "v2")

    def test_safe_detection_identifier_redacts_raw_values(self):
        value = safe_detection_identifier("secret-host-42 10.1.2.3")
        self.assertIn("sha256:", value)
        self.assertIn("len=", value)
        self.assertNotIn("secret-host", value)
        self.assertNotIn("10.1.2.3", value)


class LiveZabbixDetectionStateMachineSourceTests(unittest.TestCase):
    def test_final_status_markers_present(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        for marker in ["timeout", "ошибка загрузки", "itemid не найден", "узел не найден в CSV", "queue continued after error", "проверяю..."]:
            self.assertIn(marker, source)
        self.assertIn("detection_checking.discard", source)
        self.assertIn("detection_statuses[key]", source)


if __name__ == "__main__":
    unittest.main()
