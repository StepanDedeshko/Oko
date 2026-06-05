import unittest

from app.templates import (
    DEFAULT_OTRS_GRAPH_CHECK_TEMPLATE_TEXT,
    REDMINE_GRAPH_VARIABLE_DETAILS,
    ensure_templates_defaults,
    get_otrs_graph_check_template,
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


if __name__ == "__main__":
    unittest.main()
