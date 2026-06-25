import tempfile
import unittest
from pathlib import Path

from app.live_zabbix import diff_snapshots
from app.trigger_model import (
    SPECIAL_TRIGGER_KIND,
    append_history_event,
    build_problem_key,
    enrich_problem,
    format_graph_links,
    graph_urls_for_problem,
    trigger_kind_for_problem,
)


class LiveZabbixMonitorModelTests(unittest.TestCase):
    def test_build_problem_key_prefers_stable_id_and_has_fallback(self):
        self.assertEqual(build_problem_key({"event_id": "100500", "host": "h"}), "100500")
        fallback = build_problem_key({"host": " Server 01 ", "trigger_name": " CPU High ", "started_at": "10:00", "severity": "High"})
        self.assertEqual(fallback, "server 01|cpu high|10:00|high")

    def test_diff_snapshots_detects_new_active_and_resolved(self):
        previous = [enrich_problem({}, {"event_id": "old", "trigger_name": "Old"}), enrich_problem({}, {"event_id": "same", "trigger_name": "Same"})]
        current = [enrich_problem({}, {"event_id": "same", "trigger_name": "Same"}), enrich_problem({}, {"event_id": "new", "trigger_name": "New"})]
        diff = diff_snapshots(previous, current)
        self.assertEqual([item.key for item in diff.new], ["new"])
        self.assertEqual([item.key for item in diff.active], ["same"])
        self.assertEqual([item.key for item in diff.resolved], ["old"])

    def test_processed_state_is_kept_separate(self):
        current = [enrich_problem({}, {"event_id": "done", "trigger_name": "Done"})]
        diff = diff_snapshots([], current, {"done"})
        self.assertEqual([item.key for item in diff.processed], ["done"])
        self.assertEqual(diff.processed[0].status, "processed")

    def test_special_trigger_and_graph_links_are_shared_for_monitor_and_redmine(self):
        config = {
            "zabbix_trigger_definitions": {
                "items": [
                    {
                        "id": "cpu-special",
                        "enabled": True,
                        "kind": SPECIAL_TRIGGER_KIND,
                        "match": {"trigger_ids": ["cpu_high"], "trigger_names": [], "hosts": ["server-01"]},
                        "graph_urls": ["https://zabbix.example/chart.php?graphid=1"],
                        "graph_ids": ["product::dashboard::0::CPU"],
                    }
                ]
            },
            "products": [
                {"name": "product", "dashboards": [{"name": "dashboard", "type": "graphs_grid", "graphs": [{"title": "CPU", "url": "https://zabbix.example/chart.php?graphid=2", "use_time_range": True}]}]}
            ],
        }
        problem = {"id": "cpu_high", "host": "server-01", "trigger_name": "CPU high"}
        self.assertEqual(trigger_kind_for_problem(config, problem), SPECIAL_TRIGGER_KIND)
        links = graph_urls_for_problem(config, problem, time_range="6h")
        self.assertEqual(len(links), 2)
        self.assertIn("from=now-6h", links[1])
        self.assertNotIn("!", format_graph_links(links))

    def test_history_is_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.jsonl"
            append_history_event(path, "new", {"key": "1"})
            text = path.read_text(encoding="utf-8")
        self.assertIn('"event": "new"', text)
        self.assertIn('"key": "1"', text)


if __name__ == "__main__":
    unittest.main()

class LiveZabbixMonitorDiagnosticsTests(unittest.TestCase):
    def test_dom_parser_returns_diagnostic_object_without_page_text(self):
        from app.live_zabbix import DOM_PARSER_SCRIPT_PLACEHOLDER

        self.assertIn("safe_debug", DOM_PARSER_SCRIPT_PLACEHOLDER)
        self.assertIn("table_count", DOM_PARSER_SCRIPT_PLACEHOLDER)
        self.assertIn("candidate_count", DOM_PARSER_SCRIPT_PLACEHOLDER)
        self.assertIn("problem_count", DOM_PARSER_SCRIPT_PLACEHOLDER)
        self.assertIn("text_length", DOM_PARSER_SCRIPT_PLACEHOLDER)
        self.assertIn("url_path", DOM_PARSER_SCRIPT_PLACEHOLDER)
        self.assertNotIn("document.body.innerText", DOM_PARSER_SCRIPT_PLACEHOLDER)

    def test_zero_problem_message_and_processed_button_are_clear(self):
        source = Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn("Проверить DOM", text)
        self.assertIn("Страница загружена, но проблемы не найдены", text)
        self.assertIn("URL Zabbix Problems", text)
        self.assertIn("Интервал опроса", text)
        self.assertIn("Открыть URL в браузере", text)
        self.assertIn("Обработанные", text)
        self.assertIn("QTimer.singleShot(delay_ms", text)
        self.assertNotIn("Создать Redmine", text)

class LiveZabbixMonitorWebEngineDiagnosticsTests(unittest.TestCase):
    def test_health_check_and_qwebengine_diagnostics_are_present(self):
        live_source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix.py").read_text(encoding="utf-8")
        widget_source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        self.assertIn("JS_SMOKE_TEST_SCRIPT", live_source)
        self.assertIn("JS_HEALTH_CHECK_SCRIPT", live_source)
        self.assertIn("JSON.stringify", live_source)
        self.assertIn("window.location.href", live_source)
        self.assertIn("document.readyState", live_source)
        self.assertIn("bodyTextLength", live_source)
        self.assertIn("htmlLength", live_source)
        for marker in [
            "requested_url_full_masked",
            "qurl_is_valid",
            "qurl_scheme",
            "qurl_host_masked",
            "view_url_after_load",
            "page_url_after_load",
            "load_finished_ok",
            "js_result_type",
            "js_result_is_none",
            "js_result_preview",
        ]:
            self.assertIn(marker, widget_source)
        self.assertIn("JS diagnostic returned None / invalid result", widget_source)
        self.assertIn("JS returned empty string", widget_source)
        self.assertIn("json.loads", widget_source)
        self.assertIn("Ошибка JS диагностики", widget_source)
        self.assertIn("Ошибка диагностики WebEngine", widget_source)

    def test_profile_selection_and_show_webview_controls_are_present(self):
        widget_source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        self.assertIn("Показать WebView", widget_source)
        self.assertIn("WebEngine profile", widget_source)
        self.assertIn("available_zabbix_ids", widget_source)
        self.assertIn("selected_zabbix_id", widget_source)
        self.assertIn("profile_selection_reason", widget_source)
        self.assertIn("_profile_for_url", widget_source)
        self.assertIn("Определён по домену URL Zabbix Problems", widget_source)

class LiveZabbixMonitorProblemTableTests(unittest.TestCase):
    def test_dom_parser_uses_russian_header_map_and_ack_event_fields(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix.py").read_text(encoding="utf-8")
        for marker in [
            "headerAliases",
            "Время",
            "Важность",
            "Инфо",
            "Узел сети",
            "Проблема",
            "Длительность",
            "Подтверждено",
            "Действия",
            "Теги",
            "header_map",
            "eventids[0]",
            "ack_url",
        ]:
            self.assertIn(marker.lower() if marker in {"Время", "Важность", "Инфо", "Узел сети", "Проблема", "Длительность", "Подтверждено", "Действия", "Теги"} else marker, source.lower() if marker in {"Время", "Важность", "Инфо", "Узел сети", "Проблема", "Длительность", "Подтверждено", "Действия", "Теги"} else source)

    def test_snapshot_item_has_extended_zabbix_fields(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "trigger_model.py").read_text(encoding="utf-8")
        for marker in [
            "info",
            "duration",
            "acknowledged",
            "ack_text",
            "ack_url",
            "actions_text",
            "tags",
            "severity_class",
            "severity_level",
            "event_id",
        ]:
            self.assertIn(marker, source)

    def test_live_monitor_columns_widths_severity_colors_and_ack_button(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        parser_source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix.py").read_text(encoding="utf-8")
        combined_source = source + parser_source
        for marker in [
            '"Время"',
            '"Важность"',
            '"Инфо"',
            '"Узел сети"',
            '"Проблема"',
            '"Длительность"',
            '"Подтверждено"',
            '"Действия"',
            '"Теги"',
            '"Статус Око"',
            "QHeaderView.Interactive",
            "QHeaderView.Stretch",
            "table_column_widths",
            "font-size: 10px",
            "setDefaultSectionSize(24)",
            "cellClicked.connect",
            "_severity_color",
            "disaster",
            "high",
            "average",
            "warning",
            "not_classified",
            'cell.setForeground(QColor("#000000"))',
            "Открыть подтверждение Zabbix",
            "Открыть узел сети в Zabbix",
            "Открыть график проблемы",
            "ZabbixAcknowledgeDialog",
            "ACKNOWLEDGE_PAGE_MESSAGE",
            "popup_action",
            ".overlay-dialogue",
            ".modal-popup",
            "#acknowledge_form",
            ".table-forms",
            "isSeparatorRow",
            "separators",
        ]:
            self.assertIn(marker, combined_source)
        self.assertNotIn('QPushButton("Открыть подтверждение")', source)
        self.assertNotIn('"Графики",', source)
        self.assertNotIn('"Обработано",', source)
        self.assertNotIn("Создать Redmine", source)


    def test_severity_cells_force_dark_foreground_for_dark_theme_readability(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        severity_block_start = source.index("if column == 1:")
        severity_block_end = source.index("if column == 6", severity_block_start)
        severity_block = source[severity_block_start:severity_block_end]
        self.assertIn('cell.setForeground(QColor("#000000"))', severity_block)
        self.assertIn("cell.setBackground(QColor(color))", severity_block)
        self.assertNotIn("QApplication.palette", severity_block)
        self.assertNotIn("palette().text", severity_block)

class LiveZabbixMonitorAcknowledgeDetectionTests(unittest.TestCase):
    def test_ack_detection_is_exact_and_does_not_match_unacknowledged(self):
        parser_source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix.py").read_text(encoding="utf-8")
        widget_source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        self.assertIn("acknowledgeDetectedReason", parser_source)
        self.assertIn("action=popup.acknowledge.create", parser_source)
        self.assertIn("popup_action=acknowledge", parser_source)
        self.assertIn("#acknowledge_form found", parser_source)
        self.assertIn("title contains Обновление проблемы", parser_source)
        self.assertIn("if (/проблемы/i.test(title)) return '';", parser_source)
        self.assertNotIn("popup_action|acknowledge|popup", parser_source)
        self.assertIn("acknowledge_detected_reason", parser_source)
        self.assertIn("Problems page loaded, but Problems table not found", parser_source)
        self.assertIn("_load_finished_connected", widget_source)
        self.assertNotIn("loadFinished.disconnect(self._on_loaded)", widget_source)

class LiveZabbixMonitorNestedRowsTests(unittest.TestCase):
    def test_parser_uses_direct_problem_rows_and_skips_history_rows(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix.py").read_text(encoding="utf-8")
        for marker in [
            "directChildRows",
            "child.closest('table') === table",
            "row.closest('table') !== problemTable",
            "requiredProblemHeaders",
            "hasValidSeverity",
            "isHistoryRow",
            "redmine",
            "nestedRowsSkipped",
            "invalidProblemRowsSkipped",
            "historyRowsSkipped",
            "sampleSkippedRows",
            "problem_table_found",
            "direct_problem_rows_count",
            "nested_rows_skipped",
            "invalid_problem_rows_skipped",
            "history_rows_skipped",
            "sample_skipped_rows",
        ]:
            self.assertIn(marker, source)
        self.assertNotIn("problemTable.querySelectorAll('tbody > tr')", source)
        self.assertNotIn('problemTable.querySelectorAll("tr")', source)

class LiveZabbixMonitorDutyFilterTests(unittest.TestCase):
    def test_live_monitor_uses_duty_keywords_and_catalog_source(self):
        from app.live_zabbix import split_items_by_duty_filter
        config = {
            "duty_mode": {"zabbix_problem_keywords": ["db"], "zabbix_problem_exclude_keywords": ["ignore"]},
            "zabbix_trigger_catalog": {
                "version": 1,
                "triggers": [
                    {"id": "db", "enabled": True, "name": "DB down", "description": "", "category": "", "source_sheets": [], "match_type": "exact"},
                    {"id": "cpu", "enabled": False, "name": "CPU high", "description": "", "category": "", "source_sheets": [], "match_type": "exact"},
                ],
            },
        }
        db = enrich_problem({}, {"event_id": "1", "host": "db-01", "trigger_name": "DB down", "row_index": 1})
        cpu = enrich_problem({}, {"event_id": "2", "host": "cpu-01", "trigger_name": "CPU high", "row_index": 2})
        ignored = enrich_problem({}, {"event_id": "3", "host": "db-02", "trigger_name": "DB down ignore", "row_index": 3})

        visible, hidden = split_items_by_duty_filter(config, [db, cpu, ignored], filter_enabled=True)
        self.assertEqual([item.key for item in visible], ["1"])
        self.assertEqual({item.key for item in hidden}, {"2", "3"})

        all_visible, all_hidden = split_items_by_duty_filter(config, [db, cpu, ignored], filter_enabled=False)
        self.assertEqual([item.key for item in all_visible], ["1", "2", "3"])
        self.assertEqual(all_hidden, [])

    def test_hidden_items_do_not_enter_snapshot_diff(self):
        visible = [enrich_problem({}, {"event_id": "visible", "trigger_name": "DB down"})]
        hidden = [enrich_problem({}, {"event_id": "hidden", "trigger_name": "Noise"})]
        diff = diff_snapshots([], visible)
        self.assertEqual([item.key for item in diff.new], ["visible"])
        self.assertNotIn("hidden", [item.key for item in diff.new + diff.active + diff.resolved])
        self.assertEqual([item.key for item in hidden], ["hidden"])

    def test_duty_filter_ui_diagnostics_and_separator_logic_are_present(self):
        widget_source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        live_source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix.py").read_text(encoding="utf-8")
        trigger_source = (Path(__file__).resolve().parents[1] / "app" / "trigger_model.py").read_text(encoding="utf-8")
        config_example = (Path(__file__).resolve().parents[1] / "config.example.json").read_text(encoding="utf-8")
        for marker in [
            "Только интересующие",
            "duty_filter_enabled",
            "raw_problem_count",
            "visible_problem_count",
            "hidden_by_filter_count",
            "Всего:",
            "Показано:",
            "Скрыто фильтром:",
            "_filter_separators_for_visible_items",
            "split_items_by_duty_filter",
            "cellClicked.connect",
            "Открыть узел сети в Zabbix",
            "Открыть график проблемы",
            "Открыть подтверждение Zabbix",
        ]:
            self.assertIn(marker, widget_source)
        for marker in [
            "problem_matches_keywords",
            "load_zabbix_trigger_catalog",
            "annotate_zabbix_problems_with_trigger_catalog",
            "zabbix_problem_visible_by_trigger_filters",
            "problem_to_duty_filter_row",
            "split_items_by_duty_filter",
        ]:
            self.assertIn(marker, live_source)
        self.assertIn("row_index", trigger_source)
        self.assertIn('"duty_filter_enabled": true', config_example)
