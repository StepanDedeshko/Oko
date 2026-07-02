from app.config import migrate_config


def test_settings_live_zabbix_url_migrates_to_canonical_live_monitor_url():
    config = {"settings": {"live_zabbix_url": "https://example/zabbix"}, "live_zabbix_monitor": {"problems_url": ""}}
    migrated = migrate_config(config)
    assert migrated["live_zabbix_monitor"]["problems_url"] == "https://example/zabbix"
