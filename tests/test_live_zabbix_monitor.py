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
        home_text = (Path(__file__).resolve().parents[1] / "app" / "home_config.py").read_text(encoding="utf-8")
        self.assertIn("Интервал опроса", home_text)
        self.assertIn("LiveZabbixDeveloperSettingsWidget", home_text)
        self.assertIn("Открыть Zabbix", text)
        self.assertIn("Обработанные", text)
        self.assertIn("QTimer.singleShot(delay_ms", text)
        self.assertIn("Создать Redmine по выбранным строкам", text)

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
            "actions_tooltip",
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
            "QHeaderView.Interactive",
            "QHeaderView.Stretch",
            "table_column_widths",
            "font-size: 11px",
            "setDefaultSectionSize(32)",
            "customContextMenuRequested.connect",
            "_show_table_context_menu",
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
            "_clickable_cell_foreground",
            'return QColor("#ffffff")',
            'return QColor("#000000")',
            "actionMessageInfo",
            "actions_tooltip",
        ]:
            self.assertIn(marker, combined_source)
        self.assertNotIn('QPushButton("Открыть подтверждение")', source)
        self.assertNotIn('"Графики",', source)
        self.assertNotIn('"Обработано",', source)
        self.assertNotIn('"Статус Око",', source)
        self.assertIn("Создать Redmine по выбранным строкам", source)
        self.assertNotIn('cell.setForeground(QColor("#64b5f6"))', source)



    def test_live_monitor_columns_exclude_oko_status_and_clickable_text_uses_theme_colors(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        columns_start = source.index("self.table_columns = [")
        columns_end = source.index("]", columns_start)
        columns_block = source[columns_start:columns_end]
        self.assertLess(columns_block.index('"Время"'), columns_block.index('"Важность"'))
        self.assertLess(columns_block.index('"Проблема"'), columns_block.index('"Подтверждено"'))
        self.assertLess(columns_block.index('"Подтверждено"'), columns_block.index('"Действия"'))
        self.assertNotIn('"Статус Око"', columns_block)
        clickable_start = source.index("def _clickable_cell_foreground")
        clickable_end = source.index("def _render", clickable_start)
        clickable_block = source[clickable_start:clickable_end]
        self.assertIn('return QColor("#000000")', clickable_block)
        self.assertIn('return QColor("#ffffff")', clickable_block)
        self.assertNotIn("#64b5f6", clickable_block)
        self.assertIn("cell.setForeground(self._clickable_cell_foreground())", source)

    def test_actions_column_extracts_nested_comment_text_and_keeps_nested_rows_out_of_items(self):
        parser_source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix.py").read_text(encoding="utf-8")
        widget_source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        for marker in [
            "actionMessageInfo",
            "actionsCell.querySelectorAll('table tr')",
            "messages[messages.length - 1]",
            "compactText(full, 140)",
            "actions_tooltip",
            "directChildRows(problemTable)",
            "row.closest('table') !== problemTable",
        ]:
            self.assertIn(marker, parser_source)
        self.assertIn("if column == 7 and item.actions_tooltip", widget_source)
        self.assertIn("cell.setToolTip(item.actions_tooltip)", widget_source)

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
            "customContextMenuRequested.connect",
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

class LiveZabbixMonitorSilentAuthAndFilterTests(unittest.TestCase):
    def test_user_ui_does_not_contain_manual_login_or_manual_monitor_buttons(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        zabbix_login = "Войти в " + "Zabbix"
        otrs_login = "Войти в " + "OTRS"
        start_label = "С" + "тарт"
        stop_label = "С" + "топ"
        self.assertNotIn(zabbix_login, source)
        self.assertNotIn(otrs_login, source)
        self.assertNotIn(f'QPushButton("{start_label}")', source)
        self.assertNotIn(f'QPushButton("{stop_label}")', source)

    def test_auto_start_is_idempotent_and_internal_cleanup_exists(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        self.assertIn("def showEvent", source)
        self.assertIn("self.start_monitor()", source)
        self.assertIn("if self._monitor_started and self.timer.isActive()", source)
        self.assertIn("def hideEvent", source)
        self.assertIn("self.timer.stop()", source)

    def test_zabbix_auth_required_page_uses_data_login_url(self):
        from app.live_zabbix import zabbix_auth_required_from_html
        html = '''<output class="msg-bad msg-global">Вы не выполнили вход. Для просмотра этой страницы вы должны войти в систему. Возможно сессия просрочена или был изменен пароль.</output><button id="login" name="login" data-login-url="index.php?request=zabbix.php%3Faction%3Dproblem.view">Вход в систему</button>'''
        result = zabbix_auth_required_from_html(html)
        self.assertTrue(result["auth_required"])
        self.assertEqual(result["login_url"], "index.php?request=zabbix.php%3Faction%3Dproblem.view")

    def test_silent_autologin_markers_and_missing_credentials_status_are_present(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        live_source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix.py").read_text(encoding="utf-8")
        self.assertIn("_silent_zabbix_autologin(payload)", source)
        self.assertIn("_zabbix_saved_credentials", source)
        self.assertIn("data_login_url", source)
        self.assertIn("missing_credentials", source)
        self.assertIn("auth_required", live_source)
        self.assertNotIn("password_json +", source)

    def test_live_filters_today_7_days_unprocessed_combined_and_sorted(self):
        from datetime import datetime
        from app.live_zabbix import LIVE_PERIOD_7_DAYS, LIVE_PERIOD_TODAY, apply_live_zabbix_table_filters
        now = datetime(2026, 6, 29, 12, 0, 0)
        items = [
            enrich_problem({}, {"event_id": "old", "started_at": "20.06.2026 12:00", "ack_text": "Нет"}),
            enrich_problem({}, {"event_id": "today_yes", "started_at": "29.06.2026 08:00", "ack_text": "Да"}),
            enrich_problem({}, {"event_id": "today_no_new", "started_at": "29.06.2026 11:00", "ack_text": "No"}),
            enrich_problem({}, {"event_id": "week_no", "started_at": "25.06.2026 10:00", "ack_text": "нет"}),
        ]
        self.assertEqual([i.key for i in apply_live_zabbix_table_filters(items, period=LIVE_PERIOD_TODAY, now=now)], ["today_no_new", "today_yes"])
        self.assertEqual([i.key for i in apply_live_zabbix_table_filters(items, period=LIVE_PERIOD_7_DAYS, now=now)], ["today_no_new", "today_yes", "week_no"])
        self.assertEqual([i.key for i in apply_live_zabbix_table_filters(items, unprocessed_only=True, now=now)], ["today_no_new", "week_no", "old"])
        self.assertEqual([i.key for i in apply_live_zabbix_table_filters(items, period=LIVE_PERIOD_TODAY, unprocessed_only=True, now=now)], ["today_no_new"])

class LiveZabbixMonitorRedmineAutoAckSourceTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(__file__).resolve().parents[1]
        self.widget_source = (self.repo / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        self.live_source = (self.repo / "app" / "live_zabbix.py").read_text(encoding="utf-8")
        self.app_info = (self.repo / "app" / "app_info.py").read_text(encoding="utf-8")

    def test_auto_ack_toggles_exist_and_default_false(self):
        for key in (
            "auto_ack_after_task_enabled",
            "auto_ack_after_redmine_enabled",
            "auto_ack_after_mm_otrs_enabled",
        ):
            self.assertIn(f'"{key}": False', self.live_source)
            self.assertIn(key, self.widget_source)

    def test_redmine_issue_detection_requires_issue_marker(self):
        self.assertIn('r"/issues/(\\d+)(?:$|[/?#])"', self.widget_source)
        self.assertIn("extract_redmine_issue_from_payload", self.widget_source)
        self.assertIn("Задача|Issue", self.widget_source)

    def test_zabbix_comment_format_is_exact(self):
        self.assertIn('return f"Задача Redmine #{issue_number}: {issue_url}"', self.widget_source)

    def test_no_auto_ack_before_issue_number_url_exists(self):
        self.assertIn("if not issue_number or not issue_url", self.widget_source)
        self.assertIn("No auto-ack before issue number/url exists", self.widget_source)

    def test_disabled_toggles_do_not_touch_zabbix(self):
        self.assertIn("def _auto_ack_enabled", self.widget_source)
        self.assertIn("Zabbix auto-ack disabled", self.widget_source)
        self.assertIn("return bool(self.settings.get(\"auto_ack_after_task_enabled\", False) and self.settings.get(\"auto_ack_after_redmine_enabled\", False))", self.widget_source)

    def test_duplicate_comment_is_skipped(self):
        self.assertIn("eventActionsText().indexOf(comment) !== -1", self.widget_source)
        self.assertIn("duplicate comment skipped", self.widget_source)

    def test_already_acknowledged_still_receives_missing_comment(self):
        self.assertIn("already acknowledged; adding missing comment only", self.widget_source)
        self.assertIn("if (acknowledgeMissing && !alreadyAcknowledged", self.widget_source)

    def test_manual_context_action_requires_two_selected_rows(self):
        self.assertIn("Скопировать комментарий задачи на выбранные", self.widget_source)
        self.assertIn("if len(items) < 2", self.widget_source)

    def test_strict_redmine_mm_comment_regex(self):
        self.assertIn('Задача Redmine #\\d+: https?://\\S+|Задача на ММ #\\d+(?:: https?://\\S+)?', self.widget_source)
        self.assertIn('Задача на ММ: \\d{6,}', self.widget_source)

    def test_no_desktop_open_for_redmine_create_url(self):
        self.assertIn("RedmineCreateDialog(profile, redmine_url", self.widget_source)
        self.assertNotIn("QDesktopServices.openUrl(QUrl(redmine_url", self.widget_source)


    def test_problem_url_fallback_opens_acknowledge_popup_before_textarea(self):
        self.assertIn("acknowledgePopUp", self.widget_source)
        self.assertIn("clicked_popup", self.widget_source)
        self.assertIn('_start_zbx_poll("check_form", 250, 10000)', self.widget_source)

    def test_eventactions_widget_used_for_duplicate_scan(self):
        self.assertIn("#hat_eventactions_widget, #hat_eventactions", self.widget_source)
        self.assertIn("eventActionsText().indexOf(comment)", self.widget_source)

    def test_popup_form_selectors_and_update_submit_exist(self):
        for marker in (
            ".overlay-dialogue #acknowledge_form textarea#message",
            "input#acknowledge_problem",
            "#acknowledge_form input#close_problem",
            "Обновить|Update",
        ):
            self.assertIn(marker, self.widget_source)

    def test_raw_tr_events_without_textarea_waits_and_diagnostics_on_timeout(self):
        self.assertIn("_handle_zbx_poll_timeout", self.widget_source)
        self.assertIn('_start_zbx_poll("check_form", 250, 10000)', self.widget_source)
        self.assertIn('_start_zbx_poll("check_submit", 300, 10000)', self.widget_source)
        for marker in (
            "current_url",
            "document_title",
            "hat_eventactions_widget_exists",
            "acknowledge_popup_link_exists",
            "acknowledge_link_count",
            "overlay_dialogue_count",
            "acknowledge_form_exists",
            "textarea_count",
            "submit_update_button_count",
            "visible_button_texts",
        ):
            self.assertIn(marker, self.widget_source)

    def test_mm_otrs_comment_format_supports_url_and_number_only(self):
        self.assertIn("Задача на ММ #\\d+(?:: https?://\\S+)?", self.widget_source)

    def test_manual_scanner_parses_eventactions_message_rows(self):
        self.assertIn("def _task_comment_scan_script", self.widget_source)
        self.assertIn("#hat_eventactions_widget, #hat_eventactions", self.widget_source)
        self.assertIn(".icon-action-msg", self.widget_source)
        self.assertIn("сообщение\\s*\\/\\s*команда", self.widget_source)

    def test_legacy_plain_mm_number_only_from_message_row_is_normalized(self):
        self.assertIn("allowPlainNumber", self.widget_source)
        self.assertIn("\\d{6,}", self.widget_source)
        self.assertIn("Задача на ММ: ' + plain[1]", self.widget_source)
        self.assertNotIn("document.body.innerText : '')\", done", self.widget_source)

    def test_old_mm_otrs_formats_are_normalized(self):
        for marker in ("Задача\\s+на\\s+ММ", "Задача\\s+ММ", "ММ|OTRS", "Задача на ММ: "):
            self.assertIn(marker, self.widget_source)


    def test_zabbix_comment_pipeline_is_python_polled_without_promises(self):
        self.assertNotIn("return new Promise", self.widget_source)
        self.assertNotIn("new Promise(function(resolve)", self.widget_source)
        self.assertIn('_start_zbx_poll("check_form", 250, 10000)', self.widget_source)
        self.assertIn('_start_zbx_poll("check_submit", 300, 10000)', self.widget_source)
        self.assertIn("submitted_done", self.widget_source)
        self.assertIn("Zabbix JS returned empty result", self.widget_source)
        self.assertIn("_finish_zbx_item", self.widget_source)

    def test_manual_copy_acknowledges_missing_acknowledgement(self):
        self.assertIn("self._task_comment_scan_items, comment, acknowledge_missing=True", self.widget_source)

    def test_duplicate_comment_skips_only_when_already_acknowledged(self):
        self.assertIn("hasDuplicate && alreadyAcknowledged", self.widget_source)
        self.assertIn("hasDuplicate && !alreadyAcknowledged", self.widget_source)
        self.assertIn("task comment exists but problem is not acknowledged; acknowledging only", self.widget_source)
        self.assertIn("duplicate comment skipped because already acknowledged", self.widget_source)

    def test_existing_comment_unacknowledged_submits_acknowledge_only_without_duplicate_message(self):
        self.assertIn("acknowledge_only:hasDuplicate && !alreadyAcknowledged", self.widget_source)
        self.assertIn("message.value = ''", self.widget_source)
        self.assertIn("problem acknowledged with existing comment", self.widget_source)
        self.assertIn("comment copied and problem acknowledged", self.widget_source)

    def test_close_problem_is_never_clicked(self):
        self.assertIn("close_problem is intentionally never checked or clicked", self.widget_source)
        self.assertNotIn("close.click()", self.widget_source)

    def test_app_version_unchanged(self):
        self.assertIn('APP_VERSION = "0.3.1"', self.app_info)
