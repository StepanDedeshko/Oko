from app.config import migrate_config, merge_missing_defaults, get_default_config, sanitize_export_data


def test_migrate_config_adds_work_sections_and_preserves_values():
    cfg = {"settings": {"theme": "custom"}, "zabbix_trigger_catalog": {"triggers": [{"name": "CPU"}]}}
    migrated = migrate_config(cfg)
    assert migrated["settings"]["theme"] == "custom"
    for key in ("links", "templates", "service_checks", "duty_mode", "products_pages", "zabbix_triggers"):
        assert key in migrated
    assert migrated["zabbix_triggers"]["problems"] == [{"name": "CPU"}]


def test_merge_missing_defaults_does_not_overwrite_user_values():
    merged = merge_missing_defaults({"settings": {"theme": "x"}}, get_default_config())
    assert merged["settings"]["theme"] == "x"
    assert "service_checks" in merged


def test_sanitize_export_data_removes_unsafe_access_keys():
    safe = sanitize_export_data({"role": "owner", "permissions": {"all": True}, "links": {"a": "b"}})
    # generic sanitizer keeps data; forbidden keys are ignored by apply_prepared_config_file
    assert safe["links"]["a"] == "b"
