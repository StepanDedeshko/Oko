import unittest

from app.templates import (
    DEFAULT_OTRS_GRAPH_CHECK_TEMPLATE_TEXT,
    REDMINE_GRAPH_VARIABLE_DETAILS,
    ensure_templates_defaults,
    get_otrs_graph_check_template,
    preview_otrs_template,
    preview_redmine_template,
    render_template,
    variable_details_text,
)


class TemplateRenderingTest(unittest.TestCase):
    def test_unknown_variables_render_empty_string(self):
        self.assertEqual(render_template("A {known} B {missing}", {"known": "ok"}), "A ok B ")

    def test_otrs_default_template_is_created_without_credentials(self):
        config = {}
        ensure_templates_defaults(config)
        template = get_otrs_graph_check_template(config)

        self.assertEqual(template["text"], DEFAULT_OTRS_GRAPH_CHECK_TEMPLATE_TEXT.strip())
        serialized = str(config["templates"]).lower()
        self.assertNotIn("password", serialized)
        self.assertNotIn("token", serialized)
        self.assertNotIn("cookie", serialized)

    def test_variable_help_contains_descriptions_and_examples(self):
        help_text = variable_details_text(REDMINE_GRAPH_VARIABLE_DETAILS)

        self.assertIn("Переменные можно вставлять в текст шаблона", help_text)
        self.assertIn("[Redmine-изображения]", help_text)
        self.assertIn("{graph_4_collapsed}", help_text)
        self.assertIn("Описание: готовый collapse-блок Redmine для 4-го графика", help_text)
        self.assertIn("Пример:", help_text)

    def test_otrs_preview_substitutes_sample_variables(self):
        preview = preview_otrs_template("{checked_at} {active_triggers} {missing}")

        self.assertIn("2026-06-05 12:00", preview)
        self.assertIn("Проверка поступления сработок — ALERT", preview)
        self.assertNotIn("{missing}", preview)

    def test_redmine_preview_substitutes_sample_variables(self):
        preview = preview_redmine_template("{trigger_name} {trigger_status}", "{graph_1_redmine_image} {screenshots_folder} {missing}")

        self.assertIn("Проверка поступления сработок ALERT", preview)
        self.assertIn("!graph_1.png!", preview)
        self.assertIn("/tmp/oko_screenshots/example", preview)
        self.assertNotIn("{missing}", preview)


class RedmineCustomFieldDefaultsTest(unittest.TestCase):
    def test_configured_custom_field_94_survives_template_lookup(self):
        from app.templates import REDMINE_TASK_TEMPLATE_KEY, REDMINE_SPECIAL_TASK_TEMPLATE_KEY, get_redmine_task_template

        config = {
            "templates": {
                REDMINE_TASK_TEMPLATE_KEY: {"custom_field_94": "Не применим"},
                REDMINE_SPECIAL_TASK_TEMPLATE_KEY: {"custom_field_94": "Не применим"},
            }
        }

        self.assertEqual(get_redmine_task_template(config)["custom_field_94"], "Не применим")
        self.assertEqual(get_redmine_task_template(config, special=True)["custom_field_94"], "Не применим")

    def test_normal_and_special_redmine_templates_include_custom_field_default(self):
        from app.templates import default_redmine_special_task_template, default_redmine_task_template

        self.assertEqual(default_redmine_task_template()["custom_field_94"], "Не применим")
        self.assertEqual(default_redmine_special_task_template()["custom_field_94"], "Не применим")

    def test_generated_redmine_url_uses_custom_field_94_value(self):
        from pathlib import Path
        from urllib.parse import parse_qs, urlencode, urlparse

        from app.templates import REDMINE_TASK_TEMPLATE_KEY, get_redmine_task_template

        config = {
            "templates": {
                REDMINE_TASK_TEMPLATE_KEY: {
                    "create_url": "https://redmine.example/issues/new",
                    "custom_field_94": "Не применим",
                }
            }
        }
        template = get_redmine_task_template(config)
        query = urlencode({"issue[custom_field_values][94]": str(template.get("custom_field_94") or "Не применим")})
        parsed = parse_qs(urlparse("https://redmine.example/issues/new?" + query).query)

        self.assertEqual(parsed["issue[custom_field_values][94]"], ["Не применим"])
        widget_source = (Path(__file__).resolve().parents[1] / "app" / "live_zabbix_widget.py").read_text(encoding="utf-8")
        self.assertIn('template.get("custom_field_94") or "Не применим"', widget_source)
        self.assertNotIn('template.get("custom_field_94") or "Применим"', widget_source)

    def test_app_version_unchanged_for_redmine_custom_field_fix(self):
        from app.app_info import APP_VERSION

        self.assertEqual(APP_VERSION, "0.3.1")


if __name__ == "__main__":
    unittest.main()
