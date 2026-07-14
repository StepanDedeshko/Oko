from pathlib import Path

from app.canonical_link_store import (
    CANONICAL_LINKS_SCHEMA_KEY,
    CANONICAL_LINKS_SCHEMA_VERSION,
    ensure_canonical_links,
    get_canonical_link,
    migrate_canonical_links,
    set_canonical_link,
)


def test_first_migration_recovers_redmine_url_from_old_template_location():
    config = {
        "duty_links": {},
        "templates": {
            "redmine_task": {"create_url": "https://redmine.example/issues/new"},
            "redmine_special_task": {"create_url": ""},
        },
        "duty_mode": {},
        "live_zabbix_monitor": {},
    }

    links = ensure_canonical_links(config)

    assert links["redmine_create_url"] == "https://redmine.example/issues/new"
    assert config[CANONICAL_LINKS_SCHEMA_KEY] == CANONICAL_LINKS_SCHEMA_VERSION
    assert config["live_zabbix_monitor"]["redmine_create_url"] == links["redmine_create_url"]
    assert config["templates"]["redmine_special_task"]["create_url"] == links["redmine_create_url"]


def test_first_migration_recovers_all_historic_link_locations():
    config = {
        "duty_links": {},
        "duty_mode": {
            "otrs": {"create_url": "https://itsm.example/normal"},
            "mm_otrs_create_url": "https://itsm.example/mm",
        },
        "live_zabbix_monitor": {
            "problems_url": "https://zabbix.example/zabbix.php?action=problem.view",
        },
        "templates": {},
    }

    links = ensure_canonical_links(config)

    assert links["otrs_create_url"] == "https://itsm.example/normal"
    assert links["mm_otrs_create_url"] == "https://itsm.example/mm"
    assert links["live_zabbix_url"] == "https://zabbix.example/zabbix.php?action=problem.view"


def test_explicitly_cleared_canonical_value_does_not_resurrect_from_stale_copy():
    config = {
        CANONICAL_LINKS_SCHEMA_KEY: CANONICAL_LINKS_SCHEMA_VERSION,
        "duty_links": {
            "redmine_create_url": "",
            "otrs_create_url": "",
            "mm_otrs_create_url": "",
            "live_zabbix_url": "",
        },
        "duty_mode": {
            "redmine_create_url": "https://stale.example/redmine",
        },
        "live_zabbix_monitor": {},
        "templates": {
            "redmine_task": {"create_url": "https://stale.example/template"},
        },
    }

    links = ensure_canonical_links(config)

    assert links["redmine_create_url"] == ""
    assert config["duty_mode"]["redmine_create_url"] == ""
    assert config["templates"]["redmine_task"]["create_url"] == ""


def test_set_canonical_link_updates_legacy_mirrors_without_touching_other_settings():
    config = {
        "duty_links": {},
        "duty_mode": {
            "enabled": True,
            "otrs": {"note_url_base": "https://itsm.example/note?id="},
        },
        "live_zabbix_monitor": {"poll_interval_seconds": 120},
        "templates": {
            "redmine_task": {"subject_template": "Subject"},
            "redmine_special_task": {"subject_template": "Special"},
        },
    }

    set_canonical_link(config, "redmine_create_url", " https://redmine.example/issues/new ")
    set_canonical_link(config, "live_zabbix_url", "https://zabbix.example/problems")
    set_canonical_link(config, "otrs_create_url", "https://itsm.example/new")
    set_canonical_link(config, "mm_otrs_create_url", "https://itsm.example/mm")

    assert get_canonical_link(config, "redmine_create_url") == "https://redmine.example/issues/new"
    assert config["templates"]["redmine_task"]["create_url"] == "https://redmine.example/issues/new"
    assert config["templates"]["redmine_special_task"]["create_url"] == "https://redmine.example/issues/new"
    assert config["live_zabbix_monitor"]["problems_url"] == "https://zabbix.example/problems"
    assert config["live_zabbix_monitor"]["url"] == "https://zabbix.example/problems"
    assert config["duty_mode"]["otrs_create_url"] == "https://itsm.example/new"
    assert config["duty_mode"]["otrs"]["create_url"] == "https://itsm.example/new"
    assert config["live_zabbix_monitor"]["mm_otrs_create_url"] == "https://itsm.example/mm"
    assert config["duty_mode"]["enabled"] is True
    assert config["duty_mode"]["otrs"]["note_url_base"] == "https://itsm.example/note?id="
    assert config["live_zabbix_monitor"]["poll_interval_seconds"] == 120
    assert config["templates"]["redmine_task"]["subject_template"] == "Subject"


def test_migration_uses_first_problems_page_as_last_resort():
    config = {
        "duty_links": {},
        "duty_mode": {},
        "live_zabbix_monitor": {},
        "templates": {},
        "products": [
            {
                "name": "Zabbix",
                "dashboards": [
                    {
                        "type": "problems_page",
                        "url": "https://zabbix.example/zabbix.php?action=problem.view",
                    }
                ],
            }
        ],
    }

    changed = migrate_canonical_links(config)

    assert changed is True
    assert get_canonical_link(config, "live_zabbix_url") == "https://zabbix.example/zabbix.php?action=problem.view"


def test_main_installs_canonical_links_before_jabbix_sound_ui_patch():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    canonical_call = source.index("install_canonical_link_settings(config)")
    sound_call = source.index("install_jabbix_notification_sounds(config)")

    assert canonical_call < sound_call
