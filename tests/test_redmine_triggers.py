import unittest

from app.config import ensure_duty_mode_defaults
from app.redmine_triggers import (
    SPECIAL_REDMINE_TEMPLATE_KIND,
    STANDARD_REDMINE_TEMPLATE_KIND,
    find_special_redmine_trigger,
    format_graph_links,
    redmine_template_kind_for_trigger,
    special_redmine_graph_urls,
)
from app.templates import REDMINE_SPECIAL_TASK_TEMPLATE_KEY, ensure_templates_defaults, get_redmine_task_template, render_template


class RedmineTriggerTemplateTests(unittest.TestCase):
    def test_defaults_create_five_disabled_special_triggers(self):
        config = {}
        ensure_duty_mode_defaults(config)
        items = config["special_redmine_triggers"]["items"]
        self.assertEqual(len(items), 5)
        self.assertTrue(all(not item["enabled"] for item in items))

    def test_standard_trigger_uses_standard_template_kind(self):
        config = {"special_redmine_triggers": {"items": []}}
        trigger = {"id": "ordinary", "display_name": "Обычный"}
        self.assertIsNone(find_special_redmine_trigger(config, trigger))
        self.assertEqual(redmine_template_kind_for_trigger(config, trigger), STANDARD_REDMINE_TEMPLATE_KIND)

    def test_special_trigger_matches_by_id_and_collects_links_without_inline_images(self):
        config = {
            "special_redmine_triggers": {
                "items": [
                    {
                        "id": "cpu-special",
                        "enabled": True,
                        "match": {"trigger_ids": ["cpu_high"], "trigger_names": []},
                        "graph_urls": ["https://zabbix.example/chart.php?graphid=1"],
                        "graph_ids": ["product::dashboard::0::CPU"],
                    }
                ]
            },
            "products": [
                {
                    "name": "product",
                    "dashboards": [
                        {
                            "name": "dashboard",
                            "type": "graphs_grid",
                            "graphs": [
                                {"title": "CPU", "url": "https://zabbix.example/chart.php?graphid=2", "use_time_range": True}
                            ],
                        }
                    ],
                }
            ],
        }
        trigger = {"id": "cpu_high", "display_name": "CPU high"}
        self.assertEqual(redmine_template_kind_for_trigger(config, trigger), SPECIAL_REDMINE_TEMPLATE_KIND)
        links = special_redmine_graph_urls(config, trigger, time_range="3h")
        self.assertEqual(len(links), 2)
        self.assertIn("https://zabbix.example/chart.php?graphid=1", links)
        self.assertIn("from=now-3h", links[1])
        formatted = format_graph_links(links)
        self.assertNotIn("!", formatted)
        self.assertIn("1. https://zabbix.example/chart.php?graphid=1", formatted)

    def test_special_redmine_template_renders_plain_graph_links(self):
        config = {}
        templates = ensure_templates_defaults(config)
        self.assertIn(REDMINE_SPECIAL_TASK_TEMPLATE_KEY, templates)
        template = get_redmine_task_template(config, special=True)
        description = render_template(template["description_template"], {
            "trigger_name": "CPU high",
            "trigger_status": "ALERT",
            "special_graph_links": "1. https://zabbix.example/chart.php?graphid=1",
            "active_problems": "1. CPU high",
        })
        self.assertIn("Ссылки на графики", description)
        self.assertIn("1. https://zabbix.example/chart.php?graphid=1", description)
        self.assertNotIn("!https://", description)


if __name__ == "__main__":
    unittest.main()
