from app.module_status import (
    ROW_ERROR,
    ROW_LOGIN_REQUIRED,
    ROW_ONLINE,
    ModuleStatusTarget,
    aggregate_module_status,
    collect_module_status_targets,
)


def sample_config():
    return {
        "products": [
            {
                "name": "Сработки сферы",
                "enabled": True,
                "dashboards": [
                    {"name": "Проблемы", "type": "problems_page", "url": "https://zbx/problems", "zabbix_id": "z1"},
                    {"name": "Дашборд", "type": "dashboard_page", "url": "https://zbx/dashboard", "zabbix_id": "z1"},
                    {
                        "name": "Источник сработок Сфера",
                        "type": "mode_pages",
                        "url": "https://zbx/source",
                        "zabbix_id": "z1",
                        "modes": [
                            {"name": "Первый", "url": "https://zbx/mode1"},
                            {"name": "Второй", "url": "https://zbx/mode2"},
                        ],
                    },
                    {
                        "name": "Графики",
                        "type": "graphs_grid",
                        "zabbix_id": "z1",
                        "graphs": [
                            {"title": "CPU", "url": "https://zbx/graph", "open_url": "https://zbx/graph/open"},
                        ],
                    },
                ],
            }
        ],
        "duty_triggers": {
            "enabled": True,
            "items": [
                {
                    "id": "t1",
                    "enabled": True,
                    "display_name": "Проверка поступления сработок",
                    "source_product": "Сработки сферы",
                    "source_section": "Источник сработок Сфера",
                    "target_product": "Target",
                    "target_section": "Graphs",
                    "target_graph_title": "Target Graph 1",
                    "mode": "mode_1",
                },
                {
                    "id": "t2",
                    "enabled": True,
                    "display_name": "Проверка поступления сработок",
                    "source_product": "Сработки сферы",
                    "source_section": "Источник сработок Сфера",
                    "target_product": "Target",
                    "target_section": "Graphs",
                    "target_graph_title": "Target Graph 2",
                    "mode": "mode_2",
                },
            ],
        },
    }


def test_collect_module_status_targets_collects_dashboards_and_duty_sources():
    targets = collect_module_status_targets(sample_config())
    urls = [target.url for target in targets]

    assert "https://zbx/problems" in urls
    assert "https://zbx/dashboard" in urls
    assert "https://zbx/source" in urls
    assert "https://zbx/mode1" in urls
    assert "https://zbx/mode2" in urls
    assert "https://zbx/graph" in urls
    assert "https://zbx/graph/open" in urls

    duty_targets = [target for target in targets if target.source == "duty_trigger"]
    assert [target.url for target in duty_targets] == ["https://zbx/mode1", "https://zbx/mode2"]
    assert duty_targets[0].mode_name == "Сработки сферы / Источник сработок Сфера / mode_1 / Проверка поступления сработок"
    assert duty_targets[1].mode_name == "Сработки сферы / Источник сработок Сфера / mode_2 / Проверка поступления сработок"
    assert duty_targets[0].target_graph_title == "Target Graph 1"


def test_aggregate_module_status_states():
    assert aggregate_module_status([ModuleStatusTarget("p", "s", "u", status=ROW_ONLINE)])["state"] == "online"
    assert aggregate_module_status([
        ModuleStatusTarget("p", "s", "u1", status=ROW_ONLINE),
        ModuleStatusTarget("p", "s", "u2", status=ROW_LOGIN_REQUIRED),
    ])["state"] == "partial"
    assert aggregate_module_status([])["state"] == "disabled"
    assert aggregate_module_status([
        ModuleStatusTarget("p", "s", "u1", status=ROW_ERROR),
        ModuleStatusTarget("p", "s", "u2", status=ROW_LOGIN_REQUIRED),
    ])["state"] == "offline"


def test_aggregate_module_status_checking_not_offline():
    assert aggregate_module_status([
        ModuleStatusTarget("p", "s", "u1"),
        ModuleStatusTarget("p", "s", "u2"),
    ])["state"] == "checking"
    assert aggregate_module_status([
        ModuleStatusTarget("p", "s", "u1", status=ROW_ONLINE),
        ModuleStatusTarget("p", "s", "u2"),
    ])["state"] != "offline"


def test_main_window_starts_module_status_after_profiles_and_dashboards():
    from pathlib import Path

    implementation_path = Path("app/main_window_base.py")
    if not implementation_path.exists():
        implementation_path = Path("app/main_window.py")

    source = implementation_path.read_text(encoding="utf-8")
    hud_body = source[source.index("    def create_bottom_hud"):source.index("    def _module_badge_style")]
    assert "self.start_module_status_check()" not in hud_body

    init_body = source[source.index("    def __init__"):source.index("    def role_title")]
    assert init_body.index("self.create_profiles()") < init_body.index("self.create_dashboard_pages()")
    assert init_body.index("self.select_first_dashboard()") < init_body.index("self.start_module_status_check()")


def test_module_status_checker_preserves_empty_profiles_mapping_source():
    from pathlib import Path

    source = Path("app/module_status.py").read_text(encoding="utf-8")
    assert "profiles if profiles is not None else {}" in source
