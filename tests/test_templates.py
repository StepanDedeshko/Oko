import unittest

from app.templates import (
    DEFAULT_OTRS_GRAPH_CHECK_TEMPLATE_TEXT,
    ensure_templates_defaults,
    get_otrs_graph_check_template,
    render_template,
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


if __name__ == "__main__":
    unittest.main()
