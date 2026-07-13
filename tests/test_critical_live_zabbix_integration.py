from __future__ import annotations

from pathlib import Path

from app.app_info import APP_VERSION
from app.critical_live_zabbix_widget import CriticalLiveZabbixMonitorWidget
from app.critical_trigger_actions import (
    COPY_TASK_COMMENT_ACTION,
    MM_OTRS_ACTION,
    NO_ACTION_REQUIRED_ACTION,
    OBSERVED_ACTION,
    can_use_processing_action,
    redmine_auto_ack_enabled_for_items,
)
from app.critical_triggers import HISTORY_EXTRACTION_SCRIPT
from app.live_zabbix_widget import LiveZabbixMonitorWidget
from app.trigger_model import ZabbixProblemSnapshotItem


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_SOURCE = (ROOT / "app" / "critical_live_zabbix_widget.py").read_text(encoding="utf-8")
MAIN_WINDOW_SOURCE = (ROOT / "app" / "main_window.py").read_text(encoding="utf-8")
MAIN_SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")


def critical_item(name="ЕЦХД. Доля успешно обработанных запросов в ЕЦХД. Удаление БДн в потребителе < 10"):
    return ZabbixProblemSnapshotItem(
        key="critical-1",
        trigger_name=name,
        trigger_kind="critical",
        problem_url="http://10.250.10.10/zabbix.php?action=problem.view&eventid=1",
        ack_url="http://10.250.10.10/zabbix.php?action=popup.acknowledge.create&eventids[]=1",
    )


def normal_item():
    return ZabbixProblemSnapshotItem(key="normal-1", trigger_name="CPU high", trigger_kind="standard")


def test_integrated_widget_is_real_subclass_not_monkey_patch():
    assert issubclass(CriticalLiveZabbixMonitorWidget, LiveZabbixMonitorWidget)
    assert "class CriticalLiveZabbixMonitorWidget(LiveZabbixMonitorWidget)" in INTEGRATION_SOURCE
    assert "monkey" not in INTEGRATION_SOURCE.casefold()


def test_main_window_uses_integrated_widget_without_touching_main_py():
    assert "CriticalLiveZabbixMonitorWidget" in MAIN_WINDOW_SOURCE
    assert "CriticalLiveZabbixMonitorWidget(" in MAIN_WINDOW_SOURCE
    assert "critical_live_zabbix_widget" not in MAIN_SOURCE
    assert APP_VERSION == "0.3.6"


def test_history_webview_uses_shared_profile_and_safe_lifecycle_helpers():
    for marker in (
        "self.view.page().profile()",
        "register_web_view(QWebEngineView(self))",
        "run_javascript_if_alive(",
        "safe_delete_web_view(",
        "_critical_history_token",
        "CRITICAL_HISTORY_TIMEOUT_MS",
    ):
        assert marker in INTEGRATION_SOURCE


def test_history_script_uses_required_zabbix_selectors_and_json():
    for marker in (
        "#flickerfreescreen_historyGraph",
        "table.list-table tbody tr",
        "td:first-child",
        "td:nth-child(2) pre",
        "z-vertical[title]",
        "JSON.stringify",
    ):
        assert marker in HISTORY_EXTRACTION_SCRIPT


def test_critical_context_menu_contains_only_redmine_processing_action_branch():
    critical_branch = INTEGRATION_SOURCE.split("if has_critical:", 1)[1].split("else:", 1)[0]
    assert "Создать задачу Redmine" in critical_branch
    assert "Создать задачу на ММ" not in critical_branch
    assert "Наблюдаю" not in critical_branch
    assert "Не требует обработки" not in critical_branch
    assert "Скопировать комментарий" not in critical_branch


def test_forbidden_handlers_have_non_visual_guards():
    for action in (
        MM_OTRS_ACTION,
        OBSERVED_ACTION,
        NO_ACTION_REQUIRED_ACTION,
        COPY_TASK_COMMENT_ACTION,
    ):
        allowed, message = can_use_processing_action(action, [critical_item()])
        assert not allowed
        assert "только через создание задачи Redmine" in message
    for method in (
        "def open_mm_otrs_for_selected_row",
        "def mark_selected_as_observed",
        "def mark_selected_as_no_action_required",
        "def copy_task_comment_to_selected",
    ):
        assert method in INTEGRATION_SOURCE
        method_block = INTEGRATION_SOURCE.split(method, 1)[1].split("\n    def ", 1)[0]
        assert "_guard_processing_action" in method_block


def test_mixed_selection_is_blocked_by_integrated_redmine_selection_path():
    assert "critical_selection_error(items)" in INTEGRATION_SOURCE
    allowed, message = can_use_processing_action("redmine", [critical_item(), normal_item()])
    assert not allowed
    assert message == "Критический триггер необходимо обработать отдельно. Выберите одну критическую строку."


def test_critical_flow_skips_same_host_expansion_and_graph_lookup_prompt():
    critical_selection_block = INTEGRATION_SOURCE.split(
        "def _choose_redmine_items_for_selection", 1
    )[1].split("def open_mm_otrs_for_selected_row", 1)[0]
    assert "return items" in critical_selection_block
    assert "should_offer_same_host_expansion" in critical_selection_block
    critical_open_block = INTEGRATION_SOURCE.split(
        "def open_redmine_for_selected_row", 1
    )[1].split("def _critical_after_ip_lookup", 1)[0]
    assert "_enrich_redmine_graph_links" not in critical_open_block
    assert "Открыть связанные графики" not in critical_open_block


def test_critical_redmine_uses_existing_special_template_and_no_new_config_section():
    assert "get_redmine_task_template(self.config, special=True)" in INTEGRATION_SOURCE
    assert 'self.config.get("critical_redmine"' not in INTEGRATION_SOURCE
    assert 'self.config.setdefault("critical_redmine"' not in INTEGRATION_SOURCE
    assert "save_config" not in INTEGRATION_SOURCE
    assert "credentials.json" not in INTEGRATION_SOURCE


def test_critical_flow_does_not_upload_temporary_png_files():
    lowered = INTEGRATION_SOURCE.casefold()
    assert "qfiledialog" not in lowered
    assert "getopenfilename" not in lowered
    assert "screenshot" not in lowered
    assert "temporarydirectory" not in lowered
    assert "chart2.php" not in INTEGRATION_SOURCE


def test_critical_auto_ack_is_mandatory_but_normal_keeps_old_settings():
    assert redmine_auto_ack_enabled_for_items(
        [critical_item()],
        {"auto_ack_after_task_enabled": False, "auto_ack_after_redmine_enabled": False},
    )
    assert not redmine_auto_ack_enabled_for_items(
        [normal_item()],
        {"auto_ack_after_task_enabled": False, "auto_ack_after_redmine_enabled": False},
    )
    assert "super()._on_redmine_issue_created" in INTEGRATION_SOURCE
    assert "acknowledge_missing=True" in INTEGRATION_SOURCE
    assert "Critical Zabbix auto-confirm started" in INTEGRATION_SOURCE
    assert "Critical Zabbix auto-confirm finished" in INTEGRATION_SOURCE


def test_duplicate_redmine_callback_and_stale_history_callbacks_are_guarded():
    assert "_critical_issue_callbacks_seen" in INTEGRATION_SOURCE
    assert "duplicate callback skipped" in INTEGRATION_SOURCE
    assert "token != context.get(\"token\")" in INTEGRATION_SOURCE
    assert "stage != context.get(\"stage\")" in INTEGRATION_SOURCE


def test_status_and_diagnostic_markers_cover_full_flow():
    for marker in (
        "Критический триггер: загружаю долю медленных запросов...",
        "Критический триггер: проверяю запросы за последние 30 минут...",
        "Критический триггер: формирую описание Redmine...",
        "Открываю окно Redmine...",
        "Создана задача Redmine #",
        "Подтверждаю критический триггер в Zabbix...",
        "Critical trigger matched",
        "Critical history load started",
        "Critical history metric validated",
        "Critical slow share parsed",
        "Critical all-operations check required",
        "Critical analysis completed",
        "Critical Redmine dialog opened",
        "Critical Redmine issue detected",
        "Critical Zabbix auto-confirm started",
        "Critical Zabbix auto-confirm finished",
    ):
        assert marker in INTEGRATION_SOURCE


def test_close_event_cleans_hidden_history_view():
    close_block = INTEGRATION_SOURCE.split("def closeEvent", 1)[1]
    assert "_finish_critical_flow" in close_block
    assert "_cleanup_critical_history_view" in INTEGRATION_SOURCE
    assert "safe_delete_web_view" in INTEGRATION_SOURCE
