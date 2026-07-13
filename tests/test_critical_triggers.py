from __future__ import annotations

from datetime import datetime, timedelta

from app.app_info import APP_VERSION
from app.critical_trigger_actions import (
    COPY_TASK_COMMENT_ACTION,
    CRITICAL_SELECTION_MESSAGE,
    MM_OTRS_ACTION,
    NO_ACTION_REQUIRED_ACTION,
    OBSERVED_ACTION,
    REDMINE_ACTION,
    can_use_processing_action,
    critical_auto_ack_required,
    critical_selection_error,
    redmine_auto_ack_enabled_for_items,
    should_offer_same_host_expansion,
)
from app.critical_triggers import (
    CRITICAL_TRIGGER_KIND,
    CriticalAnalysisResult,
    HistoryPoint,
    analyze_critical_history,
    build_redmine_description,
    build_zabbix_comment,
    definition_by_id,
    is_critical_trigger_name,
    match_critical_trigger,
    parse_history_rows,
    slow_share_requires_all_operations_check,
    validate_history_payload,
)
from app.trigger_model import SPECIAL_TRIGGER_KIND, STANDARD_TRIGGER_KIND, enrich_problem, trigger_kind_for_problem


CRITICAL_EXAMPLES = {
    "last_request_gt_120m": "ЕЦХД.Время с последнего запроса в тестовой операции > 120 минут",
    "echd_delete_consumer_success_lt_10": "ЕЦХД. Доля успешно обработанных запросов в ЕЦХД. Удаление БДн в потребителе < 10",
    "echd_get_consumer_success_lt_10": "ЕЦХД. Доля успешно обработанных запросов в ЕЦХД. Получение БО потребителем < 10",
    "tib_registration_without_bo_success_lt_10": "ТИБ. Доля успешно обработанных запросов в ТИБ. Регистрация в ЕБС без БО < 10",
    "tib_deactivation_success_lt_10": "ТИБ. Доля успешно обработанных запросов в ТИБ. Деактивация УЗ в ЕБС < 10",
}


def point(minutes_ago: int, value: float, now: datetime | None = None) -> HistoryPoint:
    now = now or datetime(2026, 7, 13, 14, 0, 0)
    return HistoryPoint(now - timedelta(minutes=minutes_ago), value)


def definition(trigger_id: str):
    item = definition_by_id(trigger_id)
    assert item is not None
    return item


def critical_item(**extra):
    payload = {
        "event_id": "critical-1",
        "host": "host-01",
        "trigger_name": CRITICAL_EXAMPLES["echd_delete_consumer_success_lt_10"],
    }
    payload.update(extra)
    return enrich_problem({}, payload)


def normal_item(**extra):
    payload = {
        "event_id": "normal-1",
        "host": "host-01",
        "trigger_name": "CPU high on host",
    }
    payload.update(extra)
    return enrich_problem({}, payload)


def test_recognizes_all_five_patterns():
    for trigger_id, name in CRITICAL_EXAMPLES.items():
        matched = match_critical_trigger(name)
        assert matched is not None
        assert matched.id == trigger_id


def test_variable_parts_and_prefixes_do_not_break_matching():
    assert is_critical_trigger_name("ABC-01. Время с последнего запроса в ЛЮБАЯ ОПЕРАЦИЯ > 120 минут")
    assert is_critical_trigger_name("XYZ. Доля успешно обработанных запросов в Система. Удаление чего угодно в потребителе < 10")
    assert is_critical_trigger_name("HOST. Доля успешно обработанных запросов в система. Получение объекта потребителем < 10")
    assert is_critical_trigger_name("NODE. Доля успешно обработанных запросов в система. Регистрация в модуле без документа < 10")
    assert is_critical_trigger_name("NODE. Доля успешно обработанных запросов в система. Деактивация объекта в модуле < 10")


def test_extra_spaces_and_case_do_not_break_matching():
    assert is_critical_trigger_name("еЦхД.   ВРЕМЯ   с последнего запроса   в   X   >   120   минут")
    assert is_critical_trigger_name("ТИБ. ДОЛЯ успешно обработанных запросов в X. Деактивация Y в Z   <   10")


def test_similar_normal_trigger_is_not_critical():
    assert not is_critical_trigger_name("Доля успешно обработанных запросов в ЕЦХД. Получение БО потребителем < 30")
    assert not is_critical_trigger_name("Время с последнего запроса в тестовой операции > 60 минут")
    assert not is_critical_trigger_name("CPU high on host")


def test_expected_slow_metrics_and_itemids():
    delete_def = definition("echd_delete_consumer_success_lt_10")
    get_def = definition("echd_get_consumer_success_lt_10")
    reg_def = definition("tib_registration_without_bo_success_lt_10")
    deact_def = definition("tib_deactivation_success_lt_10")

    assert "1094986" in delete_def.slow_history_url
    assert delete_def.expected_slow_metric == "echd_opid_3_share_slow"
    assert "1094985" in get_def.slow_history_url
    assert get_def.expected_slow_metric == "echd_opid_2_share_slow"
    assert "1094915" in reg_def.slow_history_url
    assert reg_def.expected_slow_metric == "tib_opid_5_share_slow"
    assert "1094917" in deact_def.slow_history_url
    assert deact_def.expected_slow_metric == "tib_opid_7_share_slow"


def test_share_successful_is_not_used_in_threshold_logic():
    get_def = definition("echd_get_consumer_success_lt_10")
    assert "1094991" not in get_def.slow_history_url
    assert "share_successful" not in get_def.expected_slow_metric
    points, warnings = validate_history_payload(
        {"ok": True, "metric": "echd_opid_2_share_successful", "rows": [{"timestamp": "13.07.2026 14:00:00", "value": "99"}]},
        get_def.expected_slow_metric,
    )
    assert points == []
    assert warnings


def test_threshold_branches_for_slow_share():
    assert slow_share_requires_all_operations_check(49.99)
    assert not slow_share_requires_all_operations_check(50)
    assert not slow_share_requires_all_operations_check(67.4)

    result = analyze_critical_history(definition("echd_delete_consumer_success_lt_10"), [point(0, 67.4)])
    assert "высокая доля медленных запросов" in result.analysis_text
    assert not result.all_operations_checked


def test_all_zero_last_30_minutes_reports_no_requests():
    now = datetime(2026, 7, 13, 14, 0, 0)
    result = analyze_critical_history(
        definition("echd_delete_consumer_success_lt_10"),
        [point(1, 8.33, now)],
        [point(1, 0, now), point(20, 0, now)],
        now=now,
    )
    assert result.all_operations_state == "all_zero"
    assert "Запросы по всем операциям за последние 30 минут отсутствуют" in result.analysis_text


def test_non_zero_last_30_minutes_uses_latest_non_zero_point():
    now = datetime(2026, 7, 13, 14, 0, 0)
    result = analyze_critical_history(
        definition("echd_get_consumer_success_lt_10"),
        [point(1, 8.33, now)],
        [point(25, 5, now), point(10, 0, now), point(2, 7, now)],
        now=now,
    )
    assert result.all_operations_state == "has_non_zero"
    assert "Последнее ненулевое значение: 7" in result.analysis_text
    assert "13.07.2026 13:58:00" in result.analysis_text


def test_old_points_outside_30_minutes_are_ignored():
    now = datetime(2026, 7, 13, 14, 0, 0)
    result = analyze_critical_history(
        definition("tib_registration_without_bo_success_lt_10"),
        [point(1, 12, now)],
        [point(31, 9, now), point(60, 8, now)],
        now=now,
    )
    assert result.all_operations_state == "no_recent_points"
    assert "за последние 30 минут значения отсутствуют" in result.analysis_text
    assert "Запросы по всем операциям за последние 30 минут отсутствуют" not in result.analysis_text


def test_history_values_with_comma_and_invalid_values():
    rows = [
        {"timestamp": "13.07.2026 14:00:00", "value": "8,33"},
        {"timestamp": "13.07.2026 14:01:00", "value": " 0 "},
        {"timestamp": "bad", "value": "bad"},
    ]
    points = parse_history_rows(rows)
    assert [p.value for p in points] == [8.33, 0]


def test_wrong_metric_is_rejected():
    points, warnings = validate_history_payload({"ok": True, "metric": "wrong", "rows": [{"timestamp": "13.07.2026 14:00:00", "value": "8"}]}, "expected")
    assert points == []
    assert "не совпала" in warnings[0]


def test_parse_error_does_not_block_description():
    critical_def = definition("echd_delete_consumer_success_lt_10")
    result = analyze_critical_history(critical_def, [])
    description = build_redmine_description(critical_def, CRITICAL_EXAMPLES[critical_def.id], "host-01", "", result)
    assert "Не удалось автоматически получить или разобрать значения Zabbix" in description
    assert "Просьба проверить" in description


def test_description_contains_main_image_and_link():
    critical_def = definition("last_request_gt_120m")
    description = build_redmine_description(critical_def, CRITICAL_EXAMPLES[critical_def.id], "host-01", "10.0.0.1")
    assert f"!{critical_def.main_chart_image_url}!" in description
    assert critical_def.main_chart_image_url in description
    assert critical_def.main_graph_page_url in description


def test_description_contains_additional_graph_when_slow_below_threshold():
    critical_def = definition("echd_delete_consumer_success_lt_10")
    result = analyze_critical_history(critical_def, [point(1, 8.33)], [point(1, 0)])
    description = build_redmine_description(critical_def, CRITICAL_EXAMPLES[critical_def.id], "host-01", "10.0.0.1", result)
    assert critical_def.main_chart_image_url in description
    assert critical_def.all_operations_chart_image_url in description
    assert critical_def.all_operations_graph_page_url in description


def test_zabbix_comment_contains_issue_and_analysis_or_fallback():
    result = CriticalAnalysisResult(trigger_id="x", analysis_text="Доля медленных запросов составляет 8.33%.\nЗапросы по всем операциям за последние 30 минут отсутствуют.")
    comment = build_zabbix_comment("135501", "https://redmine.stdpr.ru/issues/135501", result)
    assert "Задача Redmine #135501" in comment
    assert "8.33" in comment

    failed = CriticalAnalysisResult(trigger_id="x", analysis_text="Не удалось автоматически получить или разобрать значения Zabbix.")
    comment = build_zabbix_comment("135502", "https://redmine.stdpr.ru/issues/135502", failed)
    assert "Автоматический анализ значений не выполнен" in comment


def test_trigger_model_marks_critical_without_config_and_keeps_special_standard():
    critical = enrich_problem({}, {"event_id": "1", "trigger_name": CRITICAL_EXAMPLES["echd_delete_consumer_success_lt_10"]})
    assert critical.trigger_kind == CRITICAL_TRIGGER_KIND
    assert trigger_kind_for_problem({}, {"trigger_name": "CPU high"}) == STANDARD_TRIGGER_KIND

    special_config = {
        "zabbix_trigger_definitions": {
            "items": [
                {"id": "s", "enabled": True, "kind": SPECIAL_TRIGGER_KIND, "match": {"trigger_ids": [], "trigger_names": ["Special"], "hosts": []}}
            ]
        }
    }
    assert trigger_kind_for_problem(special_config, {"trigger_name": "Special"}) == SPECIAL_TRIGGER_KIND


def test_critical_row_allows_only_redmine_processing_action():
    item = critical_item()
    ok, reason = can_use_processing_action(REDMINE_ACTION, [item])
    assert ok
    assert reason == ""

    for action in (MM_OTRS_ACTION, OBSERVED_ACTION, NO_ACTION_REQUIRED_ACTION, COPY_TASK_COMMENT_ACTION):
        ok, reason = can_use_processing_action(action, [item])
        assert not ok
        assert "только через создание задачи Redmine" in reason


def test_mixed_critical_selection_is_blocked():
    message = critical_selection_error([critical_item(), normal_item(event_id="normal-2")])
    assert message == CRITICAL_SELECTION_MESSAGE
    ok, reason = can_use_processing_action(REDMINE_ACTION, [critical_item(), normal_item(event_id="normal-3")])
    assert not ok
    assert reason == CRITICAL_SELECTION_MESSAGE


def test_multiple_critical_rows_are_blocked():
    items = [critical_item(event_id="critical-1"), critical_item(event_id="critical-2")]
    assert critical_selection_error(items) == CRITICAL_SELECTION_MESSAGE


def test_critical_trigger_does_not_offer_same_host_expansion():
    assert not should_offer_same_host_expansion([critical_item()])
    assert should_offer_same_host_expansion([normal_item()])


def test_critical_auto_ack_ignores_common_checkboxes():
    item = critical_item()
    assert critical_auto_ack_required([item])
    assert redmine_auto_ack_enabled_for_items([item], {"auto_ack_after_task_enabled": False, "auto_ack_after_redmine_enabled": False})


def test_regular_redmine_auto_ack_keeps_common_checkbox_logic():
    item = normal_item()
    assert not critical_auto_ack_required([item])
    assert not redmine_auto_ack_enabled_for_items([item], {"auto_ack_after_task_enabled": True, "auto_ack_after_redmine_enabled": False})
    assert not redmine_auto_ack_enabled_for_items([item], {"auto_ack_after_task_enabled": False, "auto_ack_after_redmine_enabled": True})
    assert redmine_auto_ack_enabled_for_items([item], {"auto_ack_after_task_enabled": True, "auto_ack_after_redmine_enabled": True})


def test_app_version_is_not_changed():
    assert APP_VERSION == "0.3.6"
