import unittest
from pathlib import Path

from app.detection_matcher import match_zabbix_host_to_node
from app.live_zabbix import build_live_zabbix_detection_status, extract_live_zabbix_itemid_from_url, match_live_zabbix_detection_host


class CombinedLiveZabbixFixesTests(unittest.TestCase):
    def test_dict_node_dash_alias_match(self):
        node = {"ip": "", "host": "kitai_1", "normalized_host": "kitai_1", "version": "v1"}
        result = match_zabbix_host_to_node("китай 1 - kitai_1", [node])
        self.assertTrue(result["matched"])
        self.assertEqual(result["version"], "v1")
        self.assertEqual(result["matched_by"], "dash_alias")
        self.assertEqual(result["matched_alias"], "kitai_1")


    def test_live_zabbix_public_match_wrapper_fills_dict_node_version_and_source(self):
        cfg = {
            "live_zabbix_monitor": {
                "live_zabbix_node_version_lists": {
                    "enabled": True,
                    "v1_nodes": [
                        {"ip": "", "host": "kitai_1", "normalized_host": "kitai_1", "version": "v1"}
                    ],
                    "v2_nodes": [],
                    "prefer_csv_version": True,
                }
            }
        }
        result = match_live_zabbix_detection_host(cfg, "китай 1 - kitai_1", "")
        self.assertTrue(result["matched"])
        self.assertEqual(result["version"], "v1")
        self.assertEqual(result["source"], "v1")
        self.assertEqual(result["matched_by"], "dash_alias")
        self.assertEqual(result["matched_alias"], "kitai_1")

    def test_live_zabbix_public_match_wrapper_fills_plain_string_version(self):
        cfg = {
            "live_zabbix_monitor": {
                "live_zabbix_node_version_lists": {
                    "enabled": True,
                    "v1_nodes": ["kitai_1"],
                    "v2_nodes": [],
                }
            }
        }
        result = match_live_zabbix_detection_host(cfg, "китай 1 - kitai_1", "")
        self.assertTrue(result["matched"])
        self.assertEqual(result["version"], "v1")
        self.assertEqual(result["source"], "v1")
        self.assertEqual(result["matched_by"], "dash_alias")

    def test_live_zabbix_public_match_wrapper_prefers_v2_by_default(self):
        cfg = {
            "live_zabbix_monitor": {
                "live_zabbix_node_version_lists": {
                    "enabled": True,
                    "v1_nodes": ["kitai_1"],
                    "v2_nodes": ["kitai_1"],
                }
            }
        }
        result = match_live_zabbix_detection_host(cfg, "китай 1 - kitai_1", "")
        self.assertEqual(result["version"], "v2")
        self.assertEqual(result["source"], "v2")

    def test_dash_alias_supports_common_dash_separators(self):
        for dash in ("-", "–", "—", "‑", "−"):
            result = match_zabbix_host_to_node(f"китай 1 {dash} kitai_1", ["kitai_1"])
            self.assertTrue(result["matched"], dash)
            self.assertEqual(result["matched_by"], "dash_alias")
            self.assertEqual(result["matched_alias"], "kitai_1")

    def test_plain_string_node_still_matches(self):
        result = match_zabbix_host_to_node("китай 1 - kitai_1", ["kitai_1"])
        self.assertTrue(result["matched"])
        self.assertEqual(result["matched_by"], "dash_alias")



    def test_extract_detection_itemid_from_live_zabbix_urls(self):
        cases = [
            "https://z/history.php?action=showgraph&itemids[]=12345",
            "https://z/history.php?action=showgraph&itemids=12345",
            "https://z/chart.php?itemids=12345",
        ]
        for url in cases:
            self.assertEqual(extract_live_zabbix_itemid_from_url(url)["itemid"], "12345")

    def test_build_detection_status_uses_row_graph_urls_for_itemid(self):
        cfg = {
            "live_zabbix_monitor": {
                "live_zabbix_node_version_lists": {
                    "v1_nodes": [{"host": "kitai_1", "normalized_host": "kitai_1", "version": "v1"}],
                    "v2_nodes": [],
                }
            }
        }
        status = build_live_zabbix_detection_status(
            cfg,
            "китай 1 - kitai_1",
            "",
            graph_urls=["https://z/history.php?action=showgraph&itemids[]=12345"],
        )
        self.assertEqual(status["itemid"], "12345")
        self.assertEqual(status["text"], "сработок нет")

    def test_build_detection_status_has_specific_itemid_failure_reasons(self):
        cfg = {
            "live_zabbix_monitor": {
                "live_zabbix_node_version_lists": {
                    "v1_nodes": [{"host": "kitai_1", "normalized_host": "kitai_1", "version": "v1"}],
                    "v2_nodes": [],
                }
            }
        }
        no_urls = build_live_zabbix_detection_status(cfg, "китай 1 - kitai_1", "")
        self.assertEqual(no_urls["text"], "itemid не найден: нет graph_urls/problem_url")
        graphid_only = build_live_zabbix_detection_status(
            cfg, "китай 1 - kitai_1", "", graph_urls=["https://z/chart.php?graphid=999"]
        )
        self.assertEqual(graphid_only["text"], "itemid не найден: найден graphid без itemid")

    def test_build_detection_status_returns_final_states(self):
        cfg = {
            "live_zabbix_monitor": {
                "live_zabbix_node_version_lists": {
                    "v1_nodes": [
                        {"host": "kitai_1", "normalized_host": "kitai_1", "version": "v1", "itemid": "100", "detections_count": 0},
                        {"host": "kitai_2", "normalized_host": "kitai_2", "version": "v1", "itemid": "200", "detections_count": 3},
                        {"host": "kitai_3", "normalized_host": "kitai_3", "version": "v1"},
                    ],
                    "v2_nodes": [],
                }
            }
        }
        self.assertEqual(build_live_zabbix_detection_status(cfg, "", "")["text"], "нет имени узла")
        self.assertEqual(build_live_zabbix_detection_status(cfg, "missing", "")["text"], "узел не найден в CSV")
        self.assertEqual(build_live_zabbix_detection_status(cfg, "китай 1 - kitai_1", "")["text"], "сработок нет")
        self.assertEqual(build_live_zabbix_detection_status(cfg, "китай 2 - kitai_2", "")["text"], "есть сработки")
        self.assertEqual(build_live_zabbix_detection_status(cfg, "китай 3 - kitai_3", "")["text"], "itemid не найден: нет graph_urls/problem_url")

    def test_live_zabbix_detection_column_and_empty_status_render_helpers(self):
        source = Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py"
        text = source.read_text(encoding="utf-8")
        columns_block = text[text.index("self.table_columns = [") : text.index("]", text.index("self.table_columns = ["))]
        self.assertIn('"Сработки"', columns_block)
        self.assertIn("self.detection_statuses = {}", text)
        self.assertNotIn("_detection_statuses", text)
        for marker in [
            "Проверить сработки сейчас",
            "Переискать itemid",
            "Открыть history",
            "Copy host/IP/itemid",
            "нет имени узла",
            "build_live_zabbix_detection_status",
            "return self._complete_detection_check",
            "_start_detection_graph_lookup",
            "проверяется",
        ]:
            self.assertIn(marker, text)

    def test_theme_styles_include_readable_tooltips_windows_and_menus(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "theme.py").read_text(encoding="utf-8")
        self.assertIn("QToolTip, QMenu", source)
        self.assertIn("QDialog, QWidget[windowType=\"tool\"]", source)
        self.assertIn("background-color: {p['bg_field']}", source)
        self.assertIn("color: {p['text_title']}", source)

    def test_app_version_unchanged(self):
        source = Path(__file__).resolve().parents[1] / "app" / "app_info.py"
        self.assertIn('APP_VERSION = "0.3.1"', source.read_text(encoding="utf-8"))


class LiveZabbixDetectionSourceRegressionTests(unittest.TestCase):
    def test_manual_detection_methods_are_not_log_only_placeholders(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        check_start = source.index("def check_detection_now")
        check_end = source.index("def rediscover_detection_itemid", check_start)
        rediscover_end = source.index("def open_detection_history", check_end)
        self.assertIn("return self._complete_detection_check", source[check_start:check_end])
        self.assertIn("return self._complete_detection_check", source[check_end:rediscover_end])
        self.assertNotIn("Manual detection check requested", source[check_start:rediscover_end])
        self.assertNotIn("Manual detection itemid rediscovery requested", source[check_start:rediscover_end])
        self.assertIn("force_rediscover=True", source[check_end:rediscover_end])
        self.assertIn("_start_detection_graph_lookup", source)


if __name__ == "__main__":
    unittest.main()
