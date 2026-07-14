from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from app.app_info import APP_VERSION
from app.critical_trigger_actions import is_critical_problem_item
from app.critical_triggers import CriticalAnalysisResult, build_zabbix_comment
from app.trigger_model import enrich_problem


ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW_SOURCE = (ROOT / "app" / "main_window.py").read_text(encoding="utf-8")
MAIN_WINDOW_BASE_SOURCE = (ROOT / "app" / "main_window_base.py").read_text(encoding="utf-8")
MAIN_SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")
APP_INFO_SOURCE = (ROOT / "app" / "app_info.py").read_text(encoding="utf-8")


def test_final_wiring_uses_critical_widget_without_changing_main_py():
    assert "CriticalLiveZabbixMonitorWidget(" in MAIN_WINDOW_SOURCE
    assert "critical_live_zabbix_widget" not in MAIN_SOURCE
    assert APP_VERSION == "0.3.7"
    assert 'APP_VERSION = "0.3.7"' in APP_INFO_SOURCE


def test_normal_redmine_flow_delegates_directly_to_original_once():
    block = MAIN_WINDOW_SOURCE.split(
        "def open_redmine_for_selected_row", 1
    )[1].split("def _critical_after_ip_lookup", 1)[0]
    assert "_StandardLiveZabbixMonitorWidget.open_redmine_for_selected_row(self)" in block
    assert "not any(is_critical_problem_item" in block


def test_last_request_trigger_uses_main_graph_and_truthful_internal_result():
    block = MAIN_WINDOW_SOURCE.split(
        "def _critical_after_ip_lookup", 1
    )[1].split("def _critical_history_result", 1)[0]
    assert "graph_page_urls=[definition.main_graph_page_url]" in block
    assert "chart_image_urls=[definition.main_chart_image_url]" in block
    assert "Дополнительный автоматический анализ значений не требуется" in block

    analysis = CriticalAnalysisResult(
        trigger_id="last_request_gt_120m",
        analysis_text=(
            "Критический триггер времени с последнего запроса. "
            "Дополнительный автоматический анализ значений не требуется."
        ),
        graph_page_urls=["https://zabbix.example/graph"],
        chart_image_urls=["https://zabbix.example/chart2.php"],
    )
    comment = build_zabbix_comment(
        "135500", "https://redmine.stdpr.ru/issues/135500", analysis
    )
    assert "Автоматический анализ значений не выполнен" not in comment
    assert "Дополнительный автоматический анализ" in comment


def test_incomplete_history_dom_is_retried_before_analysis():
    block = MAIN_WINDOW_SOURCE.split(
        "def _critical_history_result", 1
    )[1].split("class MainWindow", 1)[0]
    assert "not metric or not rows" in block
    assert "CRITICAL_HISTORY_RETRY_DELAYS_MS" in block
    assert "self._critical_try_extract" in block
    assert "super()._critical_history_result" in block


def test_hidden_history_view_is_cleaned_on_hide_and_shutdown():
    runtime_block = MAIN_WINDOW_SOURCE.split(
        "class CriticalLiveZabbixMonitorWidget", 1
    )[1].split("class MainWindow", 1)[0]
    assert "def hideEvent" in runtime_block
    assert "def cleanup" in runtime_block
    assert runtime_block.count("self._finish_critical_flow()") >= 2
    assert "super().cleanup()" in runtime_block


def test_runtime_app_name_is_forwarded_for_future_jabbix_merge():
    assert '_main_window_base.APP_NAME = globals().get("APP_NAME"' in MAIN_WINDOW_SOURCE
    assert "self.setWindowTitle(APP_NAME)" in MAIN_WINDOW_BASE_SOURCE


def test_critical_classification_does_not_modify_credentials_or_settings():
    config = {
        "settings": {"theme": "mass_effect", "keep": "value"},
        "credentials": {
            "zabbix": {"login": "user", "password": "secret"},
            "otrs": {"login": "otrs", "password": "secret2"},
            "service_check::1": {"login": "svc", "password": "secret3"},
        },
    }
    before_settings = deepcopy(config["settings"])
    before_credentials = deepcopy(config["credentials"])

    item = enrich_problem(
        config,
        {
            "event_id": "1",
            "trigger_name": (
                "ЕЦХД. Доля успешно обработанных запросов в ЕЦХД. "
                "Удаление БДн в потребителе < 10"
            ),
        },
    )

    assert is_critical_problem_item(item)
    assert config["settings"] == before_settings
    assert config["credentials"] == before_credentials
