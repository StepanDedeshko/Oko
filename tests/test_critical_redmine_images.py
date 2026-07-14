from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.critical_redmine_images import (
    CHART_IMAGE_EXTRACTION_SCRIPT,
    CriticalRedmineCreateDialog,
    build_critical_redmine_description,
    install_critical_redmine_images,
)
from app.critical_triggers import CriticalAnalysisResult, definition_by_id


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "app" / "critical_redmine_images.py").read_text(encoding="utf-8")
MAIN_SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")


def _context(trigger_id="last_request_gt_120m", two_images=False):
    definition = definition_by_id(trigger_id)
    assert definition is not None
    item = SimpleNamespace(
        event_id="123456",
        key="123456",
        trigger_name="ЕЦХД. Время с последнего запроса в ЕЦХД > 120 минут",
        host="host-01",
        host_ip="10.0.0.1",
    )
    analysis = CriticalAnalysisResult(
        trigger_id=trigger_id,
        analysis_text=(
            "Доля медленных запросов составляет 8.33%.\n"
            "Запросы по всем операциям за последние 30 минут отсутствуют."
            if two_images
            else ""
        ),
    )
    attachments = [
        {
            "filename": "oko_critical_123456_main.png",
            "data_base64": "AAAA",
            "graph_page_url": "http://zabbix.example/main",
        }
    ]
    if two_images:
        attachments.append(
            {
                "filename": "oko_critical_123456_all_operations.png",
                "data_base64": "BBBB",
                "graph_page_url": "http://zabbix.example/all",
            }
        )
    return {
        "item": item,
        "definition": definition,
        "analysis": analysis,
        "chart_attachments": attachments,
    }


def test_critical_description_uses_attached_image_names_not_technical_report():
    description = build_critical_redmine_description(_context())

    assert "!oko_critical_123456_main.png!" in description
    assert "Ссылка на исходный график: http://zabbix.example/main" in description
    assert "Наблюдается критический триггер" in description
    assert "Узел: host-01" in description
    assert "IP: 10.0.0.1" in description

    forbidden = (
        "Проверка критического триггера выполнена автоматически Око",
        "Сценарий:",
        "Доля медленных запросов: не требуется",
        "Дополнительная проверка всех операций: не требуется",
        "Ссылки на графики:",
        "Картинка графика:",
    )
    for marker in forbidden:
        assert marker not in description


def test_second_attachment_is_embedded_for_low_slow_share_branch():
    description = build_critical_redmine_description(
        _context("echd_delete_consumer_success_lt_10", two_images=True)
    )

    assert "!oko_critical_123456_main.png!" in description
    assert "!oko_critical_123456_all_operations.png!" in description
    assert "Результат проверки:" in description
    assert "8.33" in description
    assert "Запросы по всем операциям за последние 30 минут отсутствуют" in description


def test_chart_capture_extracts_authenticated_png_in_memory():
    for marker in (
        "document.images",
        "image.naturalWidth",
        "canvas.toDataURL('image/png')",
        "data_base64",
    ):
        assert marker in CHART_IMAGE_EXTRACTION_SCRIPT
    assert "TemporaryDirectory" not in SOURCE
    assert "tempfile" not in SOURCE


def test_redmine_attachment_script_uses_real_file_input_and_data_transfer():
    script = CriticalRedmineCreateDialog.attachment_injection_script(
        [{"filename": "graph.png", "data_base64": "AAAA"}]
    )

    for marker in (
        "DataTransfer",
        "new File",
        "input.files = transfer.files",
        "dispatchEvent(new Event('change'",
        "attachments[dummy][file]",
    ):
        assert marker in script

    status_script = CriticalRedmineCreateDialog.attachment_status_script(["graph.png"])
    assert "[token]" in status_script
    assert "[filename]" in status_script
    assert "selected_count" in status_script


def test_submit_stays_locked_until_attachments_and_description_are_ready():
    assert "self._set_submit_enabled(False)" in SOURCE
    assert "self._attachment_upload_complete = True" in SOURCE
    assert "self._start_description_injection()" in SOURCE
    assert "self._set_submit_enabled(True)" in SOURCE
    assert "Создание задачи заблокировано" in SOURCE


def test_runtime_patch_is_installed_before_main_window_creation():
    install_critical_redmine_images()
    import app.critical_live_zabbix_widget as critical_widget

    assert critical_widget.CriticalLiveZabbixMonitorWidget._critical_redmine_images_installed is True
    assert (
        critical_widget.CriticalLiveZabbixMonitorWidget._critical_analysis_complete.__module__
        == "app.critical_redmine_images"
    )
    assert "install_critical_redmine_images()" in MAIN_SOURCE
    assert MAIN_SOURCE.index("install_critical_redmine_images()") < MAIN_SOURCE.index("window = MainWindow")
