from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "app" / "critical_redmine_images.py").read_text(encoding="utf-8")
MAIN_SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")


def test_critical_description_uses_attachment_filenames_not_technical_report():
    for marker in (
        "def build_critical_redmine_description",
        'f"!{filename}!"',
        "Ссылка на исходный график:",
        "Наблюдается критический триггер:",
        "Просьба проверить и устранить причину возникновения триггера.",
    ):
        assert marker in SOURCE

    forbidden = (
        "Проверка критического триггера выполнена автоматически Око",
        "Доля медленных запросов: не требуется",
        "Дополнительная проверка всех операций: не требуется",
        "Ссылки на графики:",
        "Картинка графика:",
    )
    for marker in forbidden:
        assert marker not in SOURCE


def test_chart_capture_extracts_authenticated_png_in_memory():
    for marker in (
        "document.images",
        "image.naturalWidth",
        "canvas.toDataURL('image/png')",
        "data_base64",
        "base64.b64decode",
    ):
        assert marker in SOURCE
    assert "TemporaryDirectory" not in SOURCE
    assert "tempfile" not in SOURCE


def test_redmine_attachment_script_uses_real_file_input_and_data_transfer():
    for marker in (
        "DataTransfer",
        "new File",
        "input.files = transfer.files",
        "dispatchEvent(new Event('change'",
        "attachments[dummy][file]",
        "[token]",
        "[filename]",
        "selected_count",
    ):
        assert marker in SOURCE


def test_submit_stays_locked_until_attachments_and_description_are_ready():
    assert "self._set_submit_enabled(False)" in SOURCE
    assert "self._attachment_upload_complete = True" in SOURCE
    assert "self._start_description_injection()" in SOURCE
    assert "self._set_submit_enabled(True)" in SOURCE
    assert "Создание задачи заблокировано" in SOURCE


def test_one_or_two_graphs_follow_analysis_result():
    assert "analysis.chart_image_urls" in SOURCE
    assert 'suffix = "main" if index == 0 else "all_operations"' in SOURCE
    assert 'title = "Основной график" if index == 0 else "График запросов по всем операциям"' in SOURCE
    assert "chart_graph_urls" in SOURCE


def test_runtime_patch_is_installed_before_main_window_creation():
    assert "def install_critical_redmine_images" in SOURCE
    assert "cls._critical_analysis_complete = analysis_complete_with_images" in SOURCE
    assert "cls._open_critical_redmine_dialog = open_redmine_dialog_with_images" in SOURCE
    assert "QApplication.instance() is None" in SOURCE
    assert "install_critical_redmine_images()" in MAIN_SOURCE
    assert MAIN_SOURCE.index("install_critical_redmine_images()") < MAIN_SOURCE.index("window = MainWindow")
