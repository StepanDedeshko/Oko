import pytest

pytest.importorskip("PySide6.QtGui", reason="PySide6 GUI libraries are not available")
from app.live_zabbix_widget import LiveZabbixMonitorWidget, REDMINE_DESCRIPTION_PLACEHOLDER, REDMINE_URL_LENGTH_LIMIT


def test_description_injection_script_json_serializes_text():
    script = LiveZabbixMonitorWidget.description_injection_script('quote " and newline\ntext')
    assert 'quote \\" and newline\\ntext' in script


def test_merge_redmine_url_hybrid_placeholder_excludes_full_description():
    base = "https://redmine.example/issues/new"
    long_description = "TRIGGER-LINE-" * 300
    url = LiveZabbixMonitorWidget._merge_redmine_url_params(
        base,
        {"issue[subject]": "s", "issue[description]": REDMINE_DESCRIPTION_PLACEHOLDER},
        {"issue[tracker_id]": "32"},
    )
    assert REDMINE_DESCRIPTION_PLACEHOLDER.replace(" ", "+") in url or "%D0%9E" in url
    assert long_description not in url
    assert len(url) < REDMINE_URL_LENGTH_LIMIT
