import unittest
from pathlib import Path

from app.detection_matcher import match_zabbix_host_to_node
from app.live_zabbix import SnapshotDiff
from app.trigger_model import ZabbixProblemSnapshotItem


class CombinedLiveZabbixFixesTests(unittest.TestCase):
    def test_dict_node_dash_alias_match(self):
        node = {"ip": "", "host": "kitai_1", "normalized_host": "kitai_1", "version": "v1"}
        result = match_zabbix_host_to_node("китай 1 - kitai_1", [node])
        self.assertTrue(result["matched"])
        self.assertEqual(result["version"], "v1")
        self.assertEqual(result["matched_by"], "dash_alias")
        self.assertEqual(result["matched_alias"], "kitai_1")

    def test_plain_string_node_still_matches(self):
        result = match_zabbix_host_to_node("китай 1 - kitai_1", ["kitai_1"])
        self.assertTrue(result["matched"])
        self.assertEqual(result["matched_by"], "dash_alias")

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


if __name__ == "__main__":
    unittest.main()
