import tempfile
import unittest
from pathlib import Path

from app.live_zabbix import diff_snapshots
from app.trigger_model import (
    SPECIAL_TRIGGER_KIND,
    append_history_event,
    build_problem_key,
    enrich_problem,
    format_graph_links,
    graph_urls_for_problem,
    trigger_kind_for_problem,
)


class LiveZabbixMonitorModelTests(unittest.TestCase):
    def test_build_problem_key_prefers_stable_id_and_has_fallback(self):
        self.assertEqual(build_problem_key({"event_id": "100500", "host": "h"}), "100500")
        fallback = build_problem_key({"host": " Server 01 ", "trigger_name": " CPU High ", "started_at": "10:00", "severity": "High"})
        self.assertEqual(fallback, "server 01|cpu high|10:00|high")

    def test_diff_snapshots_detects_new_active_and_resolved(self):
        previous = [enrich_problem({}, {"event_id": "old", "trigger_name": "Old"}), enrich_problem({}, {"event_id": "same", "trigger_name": "Same"})]
        current = [enrich_problem({}, {"event_id": "same", "trigger_name": "Same"}), enrich_problem({}, {"event_id": "new", "trigger_name": "New"})]
        diff = diff_snapshots(previous, current)
        self.assertEqual([item.key for item in diff.new], ["new"])
        self.assertEqual([item.key for item in diff.active], ["same"])
        self.assertEqual([item.key for item in diff.resolved], ["old"])

    def test_processed_state_is_kept_separate(self):
        current = [enrich_problem({}, {"event_id": "done", "trigger_name": "Done"})]
        diff = diff_snapshots([], current, {"done"})
        self.assertEqual([item.key for item in diff.processed], ["done"])
        self.assertEqual(diff.processed[0].status, "processed")

    def test_special_trigger_and_graph_links_are_shared_for_monitor_and_redmine(self):
        config = {
            "zabbix_trigger_definitions": {
                "items": [
                    {
                        "id": "cpu-special",
                        "enabled": True,
                        "kind": SPECIAL_TRIGGER_KIND,
                        "match": {"trigger_ids": ["cpu_high"], "trigger_names": [], "hosts": ["server-01"]},
                        "graph_urls": ["https://zabbix.example/chart.php?graphid=1"],
                        "graph_ids": ["product::dashboard::0::CPU"],
                    }
                ]
            },
            "products": [
                {"name": "product", "dashboards": [{"name": "dashboard", "type": "graphs_grid", "graphs": [{"title": "CPU", "url": "https://zabbix.example/chart.php?graphid=2", "use_time_range": True}]}]}
            ],
        }
        problem = {"id": "cpu_high", "host": "server-01", "trigger_name": "CPU high"}
        self.assertEqual(trigger_kind_for_problem(config, problem), SPECIAL_TRIGGER_KIND)
        links = graph_urls_for_problem(config, problem, time_range="6h")
        self.assertEqual(len(links), 2)
        self.assertIn("from=now-6h", links[1])
        self.assertNotIn("!", format_graph_links(links))

    def test_history_is_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.jsonl"
            append_history_event(path, "new", {"key": "1"})
            text = path.read_text(encoding="utf-8")
        self.assertIn('"event": "new"', text)
        self.assertIn('"key": "1"', text)


if __name__ == "__main__":
    unittest.main()
